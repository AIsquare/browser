"""
Classify section headings into narrative roles using TypeSafe.

Two questions per heading:
  - is_chrome (Noul)  — is this site chrome rather than article content?
  - role      (Choice) — which of the 9 narrative roles?

No thresholds on role. Take the top choice. Store confidence alongside.
Chrome detected by is_chrome > 0.7 (one threshold, one question).

Writes: atom_buckets, sections.is_boilerplate

Env:
  TYPESAFE_API_KEY   required
  TYPESAFE_MODEL     default jev-latest
"""
from __future__ import annotations

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
BATCH = 20  # headings per request

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


def load_headings(conn):
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


def store(conn, results):
    # Mark chrome sections
    for sid, ans in results.items():
        if ans['is_chrome'] > 0.7:
            conn.execute(
                "UPDATE sections SET is_boilerplate = 1 WHERE section_id = ?",
                (sid,)
            )

    # Assign atoms in non-chrome sections
    conn.execute("DELETE FROM atom_buckets")

    sec_to_role = {
        sid: (ans['role'], ans['role_conf'])
        for sid, ans in results.items()
        if ans['is_chrome'] <= 0.7
    }

    rows = conn.execute("""
      SELECT atom_id, section_id
      FROM atoms
      WHERE section_id IS NOT NULL
    """).fetchall()

    batch, counts = [], {}
    for atom_id, section_id in rows:
        if section_id not in sec_to_role:
            continue
        role, conf = sec_to_role[section_id]
        batch.append((atom_id, None, role, 'typesafe', conf))
        counts[role] = counts.get(role, 0) + 1

        if len(batch) >= 1000:
            conn.executemany("""
              INSERT OR REPLACE INTO atom_buckets
                (atom_id, topic_id, bucket, method, confidence)
              VALUES (?, ?, ?, ?, ?)
            """, batch)
            batch = []

    if batch:
        conn.executemany("""
          INSERT OR REPLACE INTO atom_buckets
            (atom_id, topic_id, bucket, method, confidence)
          VALUES (?, ?, ?, ?, ?)
        """, batch)

    return counts


def main():
    print(f"model : {MODEL}")
    print(f"batch : {BATCH}")
    print()

    conn = connect()
    run_id = sha16(f"outline-{utcnow()}")
    conn.execute("""
      INSERT INTO pipeline_runs (run_id, started_at, status, stages_json)
      VALUES (?, ?, 'running', ?)
    """, (run_id, utcnow(), '["outline"]'))

    headings = load_headings(conn)
    print(f"headings loaded : {len(headings)}")

    if not headings:
        print("nothing to classify")
        conn.close()
        return

    client = TypeSafeClient()
    results = {}
    for i in range(0, len(headings), BATCH):
        chunk = headings[i:i + BATCH]
        print(f"  batch {i//BATCH + 1} ({len(chunk)} headings)")
        results.update(classify(client, chunk))

    counts = store(conn, results)

    conn.execute("""
      UPDATE pipeline_runs SET status='completed', finished_at=? WHERE run_id=?
    """, (utcnow(), run_id))
    conn.commit()

    # Report
    print()
    print(f"atoms with bucket : {sum(counts.values())}")
    print()
    print("bucket distribution:")
    for name in ROLES.keys():
        n = counts.get(name, 0)
        bar = '█' * min(int(n / 3), 40)
        print(f"  {name:12s} {n:4d}  {bar}")

    chrome_count = sum(1 for a in results.values() if a['is_chrome'] > 0.7)
    print(f"\nchrome sections dropped : {chrome_count}")

    conn.close()


if __name__ == '__main__':
    main()