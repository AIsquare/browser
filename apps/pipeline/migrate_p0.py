"""
Phase 0 migration:
  - add first_ingested_at, last_ingested_at to documents
  - backfill from existing ingested_at
"""
import sqlite3

DB = 'corpus.db'
conn = sqlite3.connect(DB)

cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)")}

if 'first_ingested_at' not in cols:
    conn.execute("ALTER TABLE documents ADD COLUMN first_ingested_at TEXT")
    print("added first_ingested_at")
if 'last_ingested_at' not in cols:
    conn.execute("ALTER TABLE documents ADD COLUMN last_ingested_at TEXT")
    print("added last_ingested_at")

conn.execute("""
    UPDATE documents
    SET first_ingested_at = COALESCE(first_ingested_at, ingested_at),
        last_ingested_at  = COALESCE(last_ingested_at,  ingested_at)
""")
conn.commit()
conn.close()
print("migration done")