"""
Shared DB connection helper.

Resolution order for the DB URL:
  1. explicit url argument passed to connect()
  2. DATABASE_URL environment variable

Neon pooled connection strings work with psycopg3 out of the box.
If you see "prepared statement does not exist" errors, uncomment
prepare_threshold=None below.
"""
from __future__ import annotations

import os
import psycopg
from psycopg.rows import dict_row



def connect(url: str | None = None) -> psycopg.Connection:
    url = url or os.environ.get('DATABASE_URL')
    if not url:
        raise RuntimeError(
            "DATABASE_URL not set. Copy the pooled connection string "
            "from the Neon console into .env."
        )

    conn = psycopg.connect(
        url,
        row_factory=dict_row,
        autocommit=False,
        # prepare_threshold=None,  # uncomment if Neon pooler rejects prepares
    )
    return conn

def connect_signal(url: str | None = None) -> psycopg.Connection:
    url = url or os.environ.get('DATABASE_URL_SIGNAL')
    if not url:
        raise RuntimeError(
            "DATABASE_URL_SIGNAL not set. Copy the signal-database "
            "connection string from the Neon console into .env."
        )
    return psycopg.connect(
        url,
        row_factory=dict_row,
        autocommit=False,
    )