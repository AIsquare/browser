"""
Stage 2a: exact and normalized dedup of atoms.

Groups atoms by normalized text. Two atoms are duplicates if their
lowercase-whitespace-collapsed-stripped-punctuation forms match.

For each group:
  - representative = longest atom text (most complete statement)
  - atom_count = number of atoms in the group
  - doc_count = number of distinct documents in the group

Topic-agnostic: works on any corpus. No keywords, no domain assumptions.

Idempotent: wipes and rebuilds on every run.
"""
from __future__ import annotations

import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from db import connect


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def sha16(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]


def normalize_text(t: str) -> str:
    """Lowercase, collapse whitespace, strip wrapping quotes, strip trailing punctuation."""
    if not t:
        return ''
    s = t.lower().strip()
    s = re.sub(r'\s+', ' ', s)
    # strip wrapping quotes only (not internal ones)
    if len(s) >= 2 and s[0] in '"\u201c\u2018\'' and s[-1] in '"\u201d\u2019\'':
        s = s[1:-1].strip()
    # strip trailing punctuation
    s = re.sub(r'[.,;:!?\s]+$', '', s)
    return s


def main() -> None:
    conn = connect()

    run_id = sha16(f"cluster-{utcnow()}")
    conn.execute("""
      INSERT INTO pipeline_runs (run_id, started_at, status, stages_json)
      VALUES (?, ?, 'running', ?)
    """, (run_id, utcnow(), '["cluster"]'))

    # Wipe previous state (idempotent)
    conn.execute("DELETE FROM cluster_members")
    conn.execute("DELETE FROM clusters")

    # Load all atoms
    rows = conn.execute("""
      SELECT atom_id, doc_id, text
      FROM atoms
      WHERE text IS NOT NULL AND length(trim(text)) > 0
    """).fetchall()

    print(f"atoms loaded            : {len(rows)}")

    # Group by normalized form
    groups: dict[str, dict] = {}
    for atom_id, doc_id, text in rows:
        norm = normalize_text(text)
        if not norm:
            continue
        h = sha16(norm)
        g = groups.get(h)
        if g is None:
            g = {'norm_hash': h, 'norm_text': norm, 'members': []}
            groups[h] = g
        g['members'].append((atom_id, doc_id, text))

    print(f"unique normalized forms : {len(groups)}")

    # Build rows
    cluster_rows = []
    member_rows = []
    dup_clusters = 0
    multi_doc_clusters = 0

    for h, g in groups.items():
        members = g['members']
        rep_atom_id = max(members, key=lambda m: (len(m[2]), m[0]))[0]
        doc_count = len({m[1] for m in members})
        atom_count = len(members)

        cluster_rows.append((
            h, h, g['norm_text'], rep_atom_id, atom_count, doc_count
        ))
        for m in members:
            member_rows.append((h, m[0], m[1]))

        if atom_count > 1:
            dup_clusters += 1
        if doc_count > 1:
            multi_doc_clusters += 1

    conn.executemany("""
      INSERT INTO clusters
        (cluster_id, norm_hash, norm_text, representative, atom_count, doc_count)
      VALUES (?, ?, ?, ?, ?, ?)
    """, cluster_rows)

    conn.executemany("""
      INSERT OR IGNORE INTO cluster_members
        (cluster_id, atom_id, doc_id)
      VALUES (?, ?, ?)
    """, member_rows)

    conn.execute("""
      UPDATE pipeline_runs SET status='completed', finished_at=? WHERE run_id=?
    """, (utcnow(), run_id))
    conn.commit()

    # ---------- Report ----------
    print()
    print(f"clusters built          : {len(cluster_rows)}")
    print(f"cluster members         : {len(member_rows)}")
    print(f"clusters with dupes     : {dup_clusters}")
    print(f"clusters spanning docs  : {multi_doc_clusters}")
    print()

    print("top 10 largest clusters:")
    for row in conn.execute("""
      SELECT atom_count, doc_count, substr(norm_text, 1, 70) AS preview
      FROM clusters
      ORDER BY atom_count DESC, doc_count DESC
      LIMIT 10
    """):
        print(f"  [{row['atom_count']:3d} / {row['doc_count']:2d}]  {row['preview']}")

    print()
    print("top 10 multi-doc clusters:")
    for row in conn.execute("""
      SELECT atom_count, doc_count, substr(norm_text, 1, 70) AS preview
      FROM clusters
      WHERE doc_count > 1
      ORDER BY doc_count DESC, atom_count DESC
      LIMIT 10
    """):
        print(f"  [{row['atom_count']:3d} / {row['doc_count']:2d}]  {row['preview']}")

    conn.close()


if __name__ == '__main__':
    main()