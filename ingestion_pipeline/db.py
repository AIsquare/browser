"""
Shared DB connection helper. Every script uses this.

  from db import connect

  with connect() as conn:
      conn.execute(...)

Why: SQLite's PRAGMA foreign_keys and journal_mode are per-connection,
not stored in the schema file. Setting them here means every script
gets the same behavior without repeating the PRAGMAs.
"""
import sqlite3

DB_PATH = 'corpus_v1.db'


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.row_factory = sqlite3.Row
    return conn