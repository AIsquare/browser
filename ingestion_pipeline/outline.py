"""
Assign every atom to a fixed, topic-agnostic narrative bucket.

Unlike the previous version (unsupervised agglomerative clustering of
headings), this classifies each heading against a small set of FIXED
rhetorical-role prototypes: "What it is", "How it works", "Components",
"Accuracy & limits", "Uses", "History", "Related & conclusion".

Why this instead of clustering:
  - Order is definitional (the template order), never derived from noisy
    statistics -> no more "Conclusion" landing near position 0.
  - No forced cluster count -> no more two buckets swallowing 55% of atoms.
  - The bucket list is topic-agnostic; only the prototype wording might need
    light tuning per domain. Same script works on a different corpus.
  - A similarity floor sends anything that doesn't clearly match a real
    bucket to "Unclassified" instead of forcing it somewhere wrong.

Env:
  EMBED_MODEL      default BAAI/bge-small-en-v1.5
  MIN_SIMILARITY   default 0.35  (below this -> Unclassified)
"""
import json
import os
import re
import sqlite3

import numpy as np
from sentence_transformers import SentenceTransformer

DB              = 'corpus.db'
MODEL_NAME      = os.environ.get('EMBED_MODEL', 'BAAI/bge-small-en-v1.5')
MIN_SIMILARITY  = float(os.environ.get('MIN_SIMILARITY', '0.55'))

# Fixed, topic-agnostic narrative template. Order here IS the article order.
# Edit the prototype sentence (not the bucket name) to tune classification
# for a different domain -- the bucket list itself should rarely need to change.
BUCKET_PROTOTYPES = [
    ("What it is",           "A definition or overview of what this thing fundamentally is."),
    ("How it works",         "An explanation of the mechanism, process, or method behind how it functions."),
    ("Components",           "The parts, pieces, elements, hardware, or architecture that make it up."),
    ("Accuracy & limits",    "Limitations, error sources, restrictions, tradeoffs, or challenges affecting it."),
    ("Uses",                 "Real-world applications, use cases, or benefits."),
    ("History",              "The origin, historical development, predecessors, or timeline of the technology."),
    ("Related & conclusion", "Related or similar systems, comparisons, or a summary and conclusion."),
]
UNCLASSIFIED = "Unclassified"

# Exact-match structural/chrome headings -- skipped before classification.
BLACKLIST_HEADINGS = {
    'source', 'table of contents', 'references', 'external links', 'see also',
    'further reading', 'notes', 'related posts', 'related video',
    'related question', 'subscribe to get industry tips and insights',
    'get social', 'social', 'last updated', 'more information',
    'contact us', 'search our facts', 'access denied',
    'frequently asked questions',
}

# Pattern-based chrome: catches things an exact-match list can't
# (date stamps, bare numbers, single-word nav labels).
_DATE_RE = re.compile(r'^\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}$')


def is_chrome_heading(h: str) -> bool:
    h_clean = h.strip().lower()
    if h_clean in BLACKLIST_HEADINGS:
        return True
    if _DATE_RE.match(h_clean):
        return True
    if len(h_clean) < 3:
        return True
    return False


SCHEMA = """
CREATE TABLE IF NOT EXISTS atom_buckets (
  atom_id    TEXT PRIMARY KEY,
  bucket     TEXT,
  method     TEXT,
  confidence REAL
);
CREATE INDEX IF NOT EXISTS idx_buckets_bucket ON atom_buckets(bucket);
CREATE INDEX IF NOT EXISTS idx_buckets_method ON atom_buckets(method);
"""


def load_headings(conn):
    """
    Return list of (section_id, doc_id, heading, contextual_text).

    contextual_text is what actually gets embedded -- the ancestor chain
    joined with the heading itself, e.g. "Navigation equations > Solution
    methods > Iterative", NOT the bare heading alone. Short, deeply-nested
    subsection titles ("Accuracy", "Entertainment", "Iterative") are
    frequently uninterpretable in isolation; heading_path is the context
    that makes them classifiable at all. "Source" is stripped from the
    path since every document's root heading is "Source" (chrome, not
    topical context).

    A section's heading IS a block (section_id == the heading block's
    block_id), so join back to blocks to respect any is_boilerplate flag
    already set upstream instead of re-deciding chrome from scratch here.
    """
    rows = conn.execute("""
        SELECT s.section_id, s.doc_id, s.heading, s.heading_path
        FROM sections s
        JOIN blocks b ON b.block_id = s.section_id
        WHERE s.heading IS NOT NULL AND length(trim(s.heading)) > 0
          AND b.is_boilerplate = 0
    """).fetchall()

    out = []
    skipped = 0
    for sid, did, h, hp_json in rows:
        h_clean = h.strip()
        if is_chrome_heading(h_clean):
            skipped += 1
            continue
        try:
            ancestors = [a for a in json.loads(hp_json or '[]') if a.strip().lower() != 'source']
        except (json.JSONDecodeError, TypeError):
            ancestors = []
        contextual_text = " > ".join(ancestors + [h_clean]) if ancestors else h_clean
        out.append((sid, did, h_clean, contextual_text))
    print(f"headings loaded     : {len(out)}  (skipped as chrome: {skipped})")
    return out


def classify_headings(model, headings):
    """
    For each heading, assign the nearest bucket prototype by cosine
    similarity, or UNCLASSIFIED if nothing clears MIN_SIMILARITY.
    Classification runs on each heading's CONTEXTUAL text (ancestor path +
    heading), not the bare heading -- see load_headings().
    Returns dict: section_id -> (bucket_name, confidence)
    """
    bucket_names = [b[0] for b in BUCKET_PROTOTYPES]
    bucket_texts = [b[1] for b in BUCKET_PROTOTYPES]

    proto_embs = model.encode(bucket_texts, normalize_embeddings=True, show_progress_bar=False)
    proto_embs = np.asarray(proto_embs, dtype=np.float32)

    contextual_texts = [h[3] for h in headings]
    head_embs = model.encode(contextual_texts, normalize_embeddings=True, show_progress_bar=False)
    head_embs = np.asarray(head_embs, dtype=np.float32)

    # cosine similarity matrix: (n_headings, n_buckets)
    sims = head_embs @ proto_embs.T

    sec_to_bucket = {}
    per_bucket_headings = {name: [] for name in bucket_names}
    per_bucket_headings[UNCLASSIFIED] = []

    for i, (sid, did, h, ctx) in enumerate(headings):
        best_j = int(np.argmax(sims[i]))
        best_sim = float(sims[i, best_j])
        if best_sim >= MIN_SIMILARITY:
            bucket = bucket_names[best_j]
        else:
            bucket = UNCLASSIFIED
        sec_to_bucket[sid] = (bucket, best_sim)
        per_bucket_headings[bucket].append((h, ctx, did, round(best_sim, 3)))

    return sec_to_bucket, per_bucket_headings


def assign_atoms(conn, sec_to_bucket):
    insert_batch = []
    counts = {}
    for atom_id, sid in conn.execute("SELECT atom_id, section_id FROM atoms"):
        if sid is None or sid not in sec_to_bucket:
            continue
        bucket, conf = sec_to_bucket[sid]
        insert_batch.append((atom_id, bucket, 'prototype_classify', conf))
        counts[bucket] = counts.get(bucket, 0) + 1
        if len(insert_batch) >= 1000:
            conn.executemany(
                "INSERT OR REPLACE INTO atom_buckets VALUES (?, ?, ?, ?)", insert_batch)
            insert_batch = []
    if insert_batch:
        conn.executemany(
            "INSERT OR REPLACE INTO atom_buckets VALUES (?, ?, ?, ?)", insert_batch)
    conn.commit()
    return counts


def main():
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM atom_buckets")

    headings = load_headings(conn)
    if not headings:
        print("no headings to classify")
        return

    print(f"embedding model     : {MODEL_NAME}")
    print(f"min similarity      : {MIN_SIMILARITY}")
    model = SentenceTransformer(MODEL_NAME)

    sec_to_bucket, per_bucket_headings = classify_headings(model, headings)
    counts = assign_atoms(conn, sec_to_bucket)

    print()
    print(f"atoms assigned      : {sum(counts.values())}")
    print()
    print("buckets in template order:")
    ordered_names = [b[0] for b in BUCKET_PROTOTYPES] + [UNCLASSIFIED]
    for name in ordered_names:
        n_atoms = counts.get(name, 0)
        n_headings = len(per_bucket_headings.get(name, []))
        print(f"  {name:22s}  {n_atoms:4d} atoms  ({n_headings} sections)")

    print()
    print("sample headings per bucket (up to 5, for a sanity check):")
    for name in ordered_names:
        members = per_bucket_headings.get(name, [])
        if not members:
            continue
        print(f"\n  [{name}]")
        for h, ctx, did, sim in sorted(members, key=lambda m: -m[3])[:5]:
            print(f"    ({sim:.2f}) {h}  <- {did[:40]}")
            if ctx != h:
                print(f"           context used: {ctx}")

    print()
    print(f"Unclassified atoms  : {counts.get(UNCLASSIFIED, 0)}")
    print("Confidence spread per bucket (min/max similarity of assigned headings):")
    for name in ordered_names:
        members = per_bucket_headings.get(name, [])
        if members:
            sims = [m[3] for m in members]  # index 3: (h, ctx, did, sim)
            print(f"  {name:22s}  min={min(sims):.2f}  max={max(sims):.2f}  n={len(sims)}")

    conn.close()


if __name__ == '__main__':
    main()