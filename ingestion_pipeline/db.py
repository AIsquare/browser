"""
Shared DB connection helper.

Resolution order for the DB path:
  1. explicit path argument passed to connect()
  2. PIPELINE_DB_PATH environment variable
  3. corpus_v1.db in the current working directory

The pipeline orchestrator sets PIPELINE_DB_PATH per job so each job gets
its own isolated DB. Standalone scripts leave it unset and use corpus_v1.db.
"""
import os
import sqlite3

DEFAULT_DB = 'corpus_v1.db'


def connect(path: str | None = None) -> sqlite3.Connection:
    if path is None:
        path = os.environ.get('PIPELINE_DB_PATH') or DEFAULT_DB
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.row_factory = sqlite3.Row
    return conn