"""
Classify section headings into narrative roles using TypeSafe.

Two questions per heading:
  - is_chrome (Noul)  — is this site chrome rather than article content?
  - role      (Choice) — which of the 9 narrative roles?

Scoped to a list of doc_ids (typically the current job's docs).
When doc_ids is None, operates on the entire DB.

Writes: atom_buckets, sections.is_boilerplate

Env:
  TYPESAFE_API_KEY   required
  TYPESAFE_MODEL     default jev-latest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

from db import connect

try:
    from typesafe_sdk import Choice, Noul, TypeSafeClient
except ImportError:
    print("pip install typesafe-sdk")
    sys.exit(1)


MODEL = os.environ.get('TYPESAFE_MODEL', 'jev-latest')
BATCH = 20

ROLES = {
    "Overview":  "Definition, summary, or introduction of what this thing fundamentally is.",
    "Context":   "Background, motivation, history, why it exists, problem it solves.",
    "Mechanism": "How it works, the process, method, algorithm, or underlying principle.",
    "Structure": "Parts, components, architecture, subsystems, or makeup of the whole.",
    "Examples":  "Concrete examples, use cases, applications, or scenarios.",
    "Details":   "Numbers, specifications, parameters, code, formulas, or precise data.",
    "Limits":    "Risks, caveats, restrictions, side effects, or failure modes.",
    "Related":   "Alternatives, comparisons, similar things, or counterparts.",
    "Sources":   "References, citations, further reading, or acknowledgments.",
}


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def sha16(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]


def _placeholders(n: int) -> str:
    return ','.join(['%s'] * n)


def load_headings(conn, doc_ids=None):
    if doc_ids is not None and not doc_ids:
        return []

    if doc_ids is not None:
        rows = conn.execute(f"""
          SELECT section_id, heading, heading_path
          FROM sections
          WHERE doc_id IN ({_placeholders(len(doc_ids))})
            AND heading IS NOT NULL
            AND length(trim(heading)) > 0
            AND COALESCE(is_boilerplate, 0) = 0
        """, tuple(doc_ids)).fetchall()
    else:
        rows = conn.execute("""
          SELECT section_id, heading, heading_path
          FROM sections
          WHERE heading IS NOT NULL
            AND length(trim(heading)) > 0
            AND COALESCE(is_boilerplate, 0) = 0
        """).fetchall()

    out = []
    for r in rows:
        try:
            ancestors = [a for a in json.loads(r['heading_path'] or '[]')
                         if a and a.strip().lower() != 'source']
        except (json.JSONDecodeError, TypeError):
            ancestors = []
        if ancestors and ancestors[-1].strip().lower() == r['heading'].lower():
            ancestors = ancestors[:-1]
        out.append({
            'section_id': r['section_id'],
            'heading':    r['heading'].strip(),
            'path':       ' > '.join(ancestors) if ancestors else '',
        })
    return out


def classify(client, batch):
    state = {
        "headings": [
            {"text": h['heading'], "path": h['path'] or h['heading']}
            for h in batch
        ]
    }

    questions = {}
    for i, _ in enumerate(batch):
        questions[f"h{i}_chrome"] = Noul(
            instructions=(
                f"Is `headings[{i}]` site navigation, footer, author bio, "
                f"trust badge, subscription prompt, related-content teaser, "
                f"or boilerplate that appears across pages rather than "
                f"content specific to this article?"
            ),
        )
        questions[f"h{i}_role"] = Choice(
            instructions=f"What narrative role does `headings[{i}]` play in the article?",
            criteria=ROLES,
        )

    r = client.system_one(state=state, questions=questions, model=MODEL)

    out = {}
    for i, h in enumerate(batch):
        out[h['section_id']] = {
            'is_chrome': r.nouls[f"h{i}_chrome"].noul,
            'role':      r.choices[f"h{i}_role"].choice,
            'role_conf': r.choices[f"h{i}_role"].confidence,
        }
    return out


def store(conn, results, doc_ids=None):
    if doc_ids is not None and not doc_ids:
        return {}

    # Mark chrome sections
    for sid, ans in results.items():
        if ans['is_chrome'] > 0.7:
            conn.execute(
                "UPDATE sections SET is_boilerplate = 1 WHERE section_id = %s",
                (sid,)
            )

    # Scope DELETE and atom selection to the job's docs
    if doc_ids is not None:
        conn.execute(f"""
          DELETE FROM atom_buckets
          WHERE atom_id IN (
            SELECT atom_id FROM atoms WHERE doc_id IN ({_placeholders(len(doc_ids))})
          )
        """, tuple(doc_ids))
        rows = conn.execute(f"""
          SELECT a.atom_id, a.section_id,
                 COALESCE(s.is_boilerplate, 0) AS is_boilerplate
          FROM atoms a
          LEFT JOIN sections s ON s.section_id = a.section_id
          WHERE a.doc_id IN ({_placeholders(len(doc_ids))})
            AND a.section_id IS NOT NULL
        """, tuple(doc_ids)).fetchall()
    else:
        conn.execute("DELETE FROM atom_buckets")
        rows = conn.execute("""
          SELECT a.atom_id, a.section_id,
                 COALESCE(s.is_boilerplate, 0) AS is_boilerplate
          FROM atoms a
          LEFT JOIN sections s ON s.section_id = a.section_id
          WHERE a.section_id IS NOT NULL
        """).fetchall()

    chrome_sections = {
        sid for sid, ans in results.items()
        if ans['is_chrome'] > 0.7
    }
    sec_to_role = {
        sid: (ans['role'], ans['role_conf'])
        for sid, ans in results.items()
        if ans['is_chrome'] <= 0.7
    }

    batch, counts = [], {}
    for r in rows:
        atom_id = r['atom_id']
        section_id = r['section_id']
        if r['is_boilerplate'] or section_id in chrome_sections:
            continue
        if section_id in sec_to_role:
            role, conf = sec_to_role[section_id]
            method = 'typesafe'
        else:
            role, conf = 'Overview', 0.5
            method = 'default'
        batch.append((atom_id, None, role, method, conf))
        counts[role] = counts.get(role, 0) + 1

        if len(batch) >= 1000:
            with conn.cursor() as cur:
                cur.executemany("""
                  INSERT INTO atom_buckets
                    (atom_id, topic_id, bucket, method, confidence)
                  VALUES (%s, %s, %s, %s, %s)
                  ON CONFLICT (atom_id) DO UPDATE SET
                    topic_id   = EXCLUDED.topic_id,
                    bucket     = EXCLUDED.bucket,
                    method     = EXCLUDED.method,
                    confidence = EXCLUDED.confidence
                """, batch)
            batch = []

    if batch:
        with conn.cursor() as cur:
            cur.executemany("""
              INSERT INTO atom_buckets
                (atom_id, topic_id, bucket, method, confidence)
              VALUES (%s, %s, %s, %s, %s)
              ON CONFLICT (atom_id) DO UPDATE SET
                topic_id   = EXCLUDED.topic_id,
                bucket     = EXCLUDED.bucket,
                method     = EXCLUDED.method,
                confidence = EXCLUDED.confidence
            """, batch)

    return counts


def run(run_id=None, doc_ids=None, batch_size=None, verbose=True):
    bs = batch_size if batch_size else BATCH
    conn = connect()

    if run_id is None:
        run_id = sha16(f"outline-{utcnow()}")

    if verbose:
        print(f"model : {MODEL}")
        print(f"batch : {bs}")
        if doc_ids:
            print(f"scope : {len(doc_ids)} docs")
        print()

    conn.execute("""
      INSERT INTO pipeline_runs (run_id, started_at, status, stages_json)
      VALUES (%s, %s, 'running', %s)
      ON CONFLICT (run_id) DO NOTHING
    """, (run_id, utcnow(), '["outline"]'))

    headings = load_headings(conn, doc_ids=doc_ids)
    if verbose:
        print(f"headings loaded : {len(headings)}")

    if not headings:
        if verbose:
            print("nothing to classify")
        conn.close()
        return {
            'run_id': run_id,
            'headings': 0,
            'atoms_bucketed': 0,
            'chrome_sections': 0,
            'counts': {},
        }

    client = TypeSafeClient()
    results = {}
    for i in range(0, len(headings), bs):
        chunk = headings[i:i + bs]
        if verbose:
            print(f"  batch {i//bs + 1} ({len(chunk)} headings)")
        results.update(classify(client, chunk))

    counts = store(conn, results, doc_ids=doc_ids)

    conn.execute("""
      UPDATE pipeline_runs SET status='completed', finished_at=%s WHERE run_id=%s
    """, (utcnow(), run_id))
    conn.commit()

    chrome_count = sum(1 for a in results.values() if a['is_chrome'] > 0.7)
    total_bucketed = sum(counts.values())

    if verbose:
        print()
        print(f"atoms with bucket : {total_bucketed}")
        print()
        print("bucket distribution:")
        for name in ROLES.keys():
            n = counts.get(name, 0)
            bar = '█' * min(int(n / 3), 40)
            print(f"  {name:12s} {n:4d}  {bar}")
        print(f"\nchrome sections dropped : {chrome_count}")

    conn.close()
    return {
        'run_id': run_id,
        'headings': len(headings),
        'atoms_bucketed': total_bucketed,
        'chrome_sections': chrome_count,
        'counts': counts,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-id', default=None)
    ap.add_argument('--batch-size', type=int, default=None)
    args = ap.parse_args()
    run(run_id=args.run_id, batch_size=args.batch_size)


if __name__ == '__main__':
    main()