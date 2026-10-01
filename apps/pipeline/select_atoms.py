"""
Per bucket: rank atoms, enforce source diversity, cap bucket size.

Pipeline:
  1. Load atoms + bucket + section heading.
  2. Filter junk (captions, short, chrome, blacklisted sections).
  3. Score each remaining atom:
       corroboration + specificity + substance
  4. Per bucket: greedy pick by score, max N per source doc.
  5. Write to selected_atoms and print.

BUCKET_CAP and PER_DOC_CAP are the two tuning knobs.
"""
import math
import re
import sqlite3

DB = 'corpus.db'

BUCKET_CAP  = 10   # max atoms per bucket
PER_DOC_CAP = 4    # max atoms from any single doc within one bucket
MIN_TOKENS  = 6    # drop fragments

# Sections whose atoms are never content.
BLACKLIST_SECTIONS = (
    'references', 'notes', 'see also', 'external links', 'further reading',
    'table of contents', 'related posts', 'contact us',
    'subscribe to get industry tips and insights',
    'get social', 'social', 'last updated', 'related video',
    'related question', 'questions? contact', 'more information',
    'search our facts',
)

# Regexes for chrome / non-content atoms.
CHROME_PATTERNS = [
    r'^permalink',
    r'^icon\b',
    r'^diagram',
    r'^\d+\s*minute\s*read',
    r'^thumbnail image',
    r'^profile badge',
    r'^\.?\d+px$',
    r'^image of',
    r'^animation of',
    r'^a drawing of',
    r'^illustration of',
    r'^graphic showing',
    r'^geotab team',
    r'^\|\s*\|',           # table fragment
    r'^[\|\-\s]+$',        # only pipes and dashes
]
CHROME_RE = re.compile('|'.join(CHROME_PATTERNS), re.IGNORECASE)

# Proper noun heuristic: any capitalized word that isn't sentence-initial and
# isn't a common sentence word.
PROPER_RE = re.compile(r'(?<!^)(?<!\. )(?<!\? )(?<!\! )\b[A-Z][a-z]{2,}\b')


def is_junk(atom_type, text, section_heading):
    if atom_type == 'caption':
        return True
    if not text:
        return True
    if len(text.split()) < MIN_TOKENS:
        return True
    if CHROME_RE.search(text.strip()):
        return True
    if section_heading:
        h = section_heading.lower()
        for b in BLACKLIST_SECTIONS:
            if b in h:
                return True
    return False


def has_number(text):
    return 1 if re.search(r'\d', text) else 0


def has_proper_noun(text):
    # strip common sentence-initial capital
    body = text[1:] if text else ''
    return 1 if PROPER_RE.search(body) else 0


def score_atom(doc_count, tokens, number, proper):
    # corroboration is small at this corpus scale; the other three carry
    # most of the signal. Numbers and named entities are weighted high
    # because they usually mark specific, load-bearing claims.
    return (
        2.0 * max(doc_count - 1, 0)
        + 1.5 * number
        + 1.2 * proper
        + 0.6 * min(tokens, 80) / 80.0
    )


def main():
    conn = sqlite3.connect(DB)

    conn.executescript("""
      CREATE TABLE IF NOT EXISTS selected_atoms (
        atom_id  TEXT PRIMARY KEY,
        bucket   TEXT,
        rank     INTEGER,
        score    REAL,
        doc_id   TEXT,
        reason   TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_selected_bucket ON selected_atoms(bucket);
      CREATE INDEX IF NOT EXISTS idx_selected_doc    ON selected_atoms(doc_id);
    """)
    conn.execute("DELETE FROM selected_atoms")

    # leaf heading per atom (last element of heading_path)
    rows = conn.execute("""
      SELECT a.atom_id, a.doc_id, a.text, a.atom_type, a.token_count,
             a.section_id, b.bucket,
             (SELECT s.heading FROM sections s WHERE s.section_id = a.section_id) AS leaf_heading
      FROM atoms a
      JOIN atom_buckets b ON b.atom_id = a.atom_id
    """).fetchall()

    # pull doc_count from clusters (0 if not in a cluster)
    doc_counts = {}
    for cid, dc in conn.execute(
            "SELECT c.norm_hash, c.doc_count FROM clusters c"):
        doc_counts[cid] = dc

    # build per-atom doc_count from cluster_members
    atom_dc = {}
    for (atom_id, cid) in conn.execute(
            "SELECT atom_id, cluster_id FROM cluster_members"):
        atom_dc[atom_id] = doc_counts.get(cid, 1)

    buckets = {}
    skipped = 0

    for atom_id, doc_id, text, atom_type, tokens, sid, bucket, leaf in rows:
        if is_junk(atom_type, text, leaf):
            skipped += 1
            continue
        tokens = tokens or len(text.split())
        dc = atom_dc.get(atom_id, 1)
        s = score_atom(dc, tokens, has_number(text), has_proper_noun(text))
        buckets.setdefault(bucket, []).append({
            'atom_id': atom_id, 'doc_id': doc_id, 'text': text,
            'score': s, 'dc': dc, 'tokens': tokens,
        })

    inserts = []

    for bucket, items in buckets.items():
        # rank
        items.sort(key=lambda x: -x['score'])

        # greedy pick with per-doc cap
        picked = []
        per_doc = {}
        for it in items:
            if len(picked) >= BUCKET_CAP:
                break
            d = it['doc_id']
            if per_doc.get(d, 0) >= PER_DOC_CAP:
                continue
            picked.append(it)
            per_doc[d] = per_doc.get(d, 0) + 1

        for rank, it in enumerate(picked, 1):
            inserts.append((
                it['atom_id'], bucket, rank, it['score'],
                it['doc_id'], 'top_score'
            ))

    conn.executemany("""
      INSERT OR REPLACE INTO selected_atoms
        (atom_id, bucket, rank, score, doc_id, reason)
      VALUES (?, ?, ?, ?, ?, ?)
    """, inserts)
    conn.commit()

    # ---------- report ----------
    print(f"atoms considered : {len(rows)}")
    print(f"atoms skipped    : {skipped}")
    print(f"atoms selected   : {len(inserts)}")
    print(f"buckets covered  : {len(buckets)}")
    print()
    print("=" * 78)
    print("SELECTED ATOMS BY BUCKET")
    print("=" * 78)

    for bucket in sorted(buckets):
        print(f"\n### {bucket}")
        sel = [i for i in inserts if i[1] == bucket]
        sel.sort(key=lambda x: x[2])
        for atom_id, _, rank, score, doc_id, _ in sel:
            row = next(i for i in buckets[bucket] if i['atom_id'] == atom_id)
            doc_short = doc_id.replace('www_', '').replace('_', ' ')[:24]
            text = row['text'].replace('\n', ' ')
            print(f"  [{rank:2d}] ({score:4.1f} | {doc_short:24s}) {text[:110]}")

    conn.close()


if __name__ == '__main__':
    main()