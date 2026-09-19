"""
Build clusters and cluster_members from atoms in corpus.db.

Cluster = group of atoms whose normalized text is identical.
Representative = longest atom text in the cluster.
doc_count = number of distinct doc_ids among members.
atom_count = number of atoms in the cluster.

Idempotent: wipes and rebuilds on every run.
"""
import hashlib
import re
import sqlite3

DB = 'corpus.db'

SCHEMA = """
CREATE TABLE IF NOT EXISTS clusters (
  cluster_id     TEXT PRIMARY KEY,
  norm_hash      TEXT UNIQUE,
  norm_text      TEXT,
  representative TEXT,
  atom_count     INTEGER,
  doc_count      INTEGER
);

CREATE TABLE IF NOT EXISTS cluster_members (
  cluster_id TEXT,
  atom_id    TEXT,
  doc_id     TEXT,
  PRIMARY KEY (cluster_id, atom_id)
);

CREATE INDEX IF NOT EXISTS idx_clusters_norm_hash ON clusters(norm_hash);
CREATE INDEX IF NOT EXISTS idx_clusters_atom_count ON clusters(atom_count DESC);
CREATE INDEX IF NOT EXISTS idx_clusters_doc_count  ON clusters(doc_count DESC);
CREATE INDEX IF NOT EXISTS idx_members_atom        ON cluster_members(atom_id);
CREATE INDEX IF NOT EXISTS idx_members_cluster     ON cluster_members(cluster_id);
"""


def norm_text(t):
    if not t:
        return ''
    s = t.lower()
    s = re.sub(r'\s+', ' ', s).strip()
    # strip wrapping quotes only
    if len(s) >= 2 and s[0] in '"\u201c\u2018\'' and s[-1] in '"\u201d\u2019\'':
        s = s[1:-1].strip()
    # strip trailing punctuation
    s = re.sub(r'[.,;:!?\s]+$', '', s)
    return s


def norm_hash(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]


def main():
    conn = sqlite3.connect(DB)
    conn.executescript(SCHEMA)

    # wipe prior state so re-runs are clean
    conn.execute("DELETE FROM cluster_members")
    conn.execute("DELETE FROM clusters")

    rows = conn.execute("""
        SELECT atom_id, doc_id, text
        FROM atoms
        WHERE text IS NOT NULL AND length(trim(text)) > 0
    """).fetchall()

    groups = {}
    for atom_id, doc_id, text in rows:
        n = norm_text(text)
        if not n:
            continue
        h = norm_hash(n)
        g = groups.get(h)
        if g is None:
            g = {'norm_text': n, 'members': []}
            groups[h] = g
        g['members'].append((atom_id, doc_id, text))

    inserted = 0
    for h, g in groups.items():
        members = g['members']
        # representative = longest atom text; tie-break by atom_id for determinism
        rep_atom_id = max(members, key=lambda m: (len(m[2]), m[0]))[0]
        doc_count  = len({m[1] for m in members})
        atom_count = len(members)

        conn.execute("""
            INSERT INTO clusters
              (cluster_id, norm_hash, norm_text, representative, atom_count, doc_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (h, h, g['norm_text'], rep_atom_id, atom_count, doc_count))

        conn.executemany("""
            INSERT OR IGNORE INTO cluster_members (cluster_id, atom_id, doc_id)
            VALUES (?, ?, ?)
        """, [(h, m[0], m[1]) for m in members])

        inserted += 1

    conn.commit()

    total_atoms    = conn.execute("SELECT count(*) FROM atoms").fetchone()[0]
    total_clusters = conn.execute("SELECT count(*) FROM clusters").fetchone()[0]
    multi_doc      = conn.execute(
        "SELECT count(*) FROM clusters WHERE doc_count > 1").fetchone()[0]
    repeats        = conn.execute(
        "SELECT count(*) FROM clusters WHERE atom_count > 1").fetchone()[0]

    print(f"atoms considered     : {len(rows)} / {total_atoms}")
    print(f"clusters built       : {total_clusters}")
    print(f"clusters with dupes  : {repeats}")
    print(f"multi-doc clusters   : {multi_doc}")

    conn.close()


if __name__ == '__main__':
    main()