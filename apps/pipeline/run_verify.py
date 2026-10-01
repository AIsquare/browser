#!/usr/bin/env python3
import sqlite3
import sys

def run_queries(db_path, sql_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    with open(sql_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # Split by query headers
    queries = [
        ("1. Document-Level Summary", """
            SELECT d.doc_id,
                   substr(d.title, 1, 60) AS title,
                   (SELECT count(*) FROM sections s WHERE s.doc_id = d.doc_id) AS sections,
                   (SELECT count(*) FROM blocks  b WHERE b.doc_id = d.doc_id) AS blocks,
                   (SELECT count(*) FROM atoms   a WHERE a.doc_id = d.doc_id) AS atoms
            FROM documents d;
        """),
        ("2. Atom Type Distribution", """
            SELECT doc_id, atom_type, count(*) AS n
            FROM atoms GROUP BY doc_id, atom_type ORDER BY doc_id, n DESC;
        """),
        ("3. Sections in Doc (Ordered, with first/last block)", """
            SELECT section_id, heading, heading_level, token_count, first_block_id, last_block_id
            FROM sections ORDER BY char_start;
        """),
        ("4. Atoms Under 'GPS signals'", """
            SELECT a.atom_id, a.atom_type, substr(a.text, 1, 80) AS preview
            FROM atoms a JOIN sections s ON a.section_id = s.section_id
            WHERE s.heading LIKE '%GPS signals%'
            ORDER BY a.block_id, a.order_index;
        """),
        ("5. Integrity Check (Non-heading, non-boilerplate blocks without atoms)", """
            SELECT b.block_id, b.block_type, substr(b.text, 1, 60) AS preview
            FROM blocks b
            LEFT JOIN atoms a ON a.block_id = b.block_id
            WHERE b.is_boilerplate = 0
              AND b.block_type <> 'heading'
              AND a.atom_id IS NULL
              AND length(trim(b.text)) > 0;
        """),
        ("6. Duplicate Atom Hashes", """
            SELECT content_hash, count(*) AS c
            FROM atoms GROUP BY content_hash HAVING c > 1 ORDER BY c DESC LIMIT 10;
        """)
    ]

    for title, q in queries:
        print(f"\n{'='*70}\n{title}\n{'='*70}")
        try:
            cursor.execute(q)
            rows = cursor.fetchall()
            if not rows:
                print("(No rows returned)")
                continue
            cols = rows[0].keys()
            print(" | ".join(f"{c:^20}" for c in cols))
            print("-" * (23 * len(cols)))
            for r in rows:
                print(" | ".join(f"{str(r[c])[:20]:<20}" for c in cols))
        except Exception as e:
            print(f"Error running query: {e}")

    conn.close()

if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "corpus.db"
    run_queries(db, "verify.sql")
