import sqlite3

def verify(db='corpus_v1.db'):
    with sqlite3.connect(db) as conn:
        # 1. All expected tables present
        expected = {
            'corpus_config', 'pipeline_runs', 'doc_stages',
            'url_queue', 'fetches', 'rejects',
            'documents', 'sections', 'blocks', 'atoms',
            'images', 'links', 'footnotes', 'footnote_refs',
            'clusters', 'cluster_members', 'boilerplate_patterns', 'embeddings',
            'topics', 'doc_topics', 'atom_buckets', 'selected_atoms',
            'section_images', 'articles',
        }
        actual = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        missing = expected - actual
        extra = actual - expected
        print(f"tables expected : {len(expected)}")
        print(f"tables present  : {len(actual)}")
        if missing:
            print(f"MISSING: {missing}")
        if extra:
            print(f"extra (ok): {extra}")

        # 2. Indexes exist
        idx_count = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()[0]
        print(f"indexes         : {idx_count}")

        # 3. Foreign keys enforced in this connection
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        print(f"foreign_keys    : {'ON' if fk else 'OFF (must set on every connect)'}")

        # 4. Sanity: can we insert + read + rollback?
        conn.execute("BEGIN")
        conn.execute("INSERT INTO pipeline_runs (run_id, started_at, status) VALUES ('_test', '2026-01-01T00:00:00Z', 'running')")
        n = conn.execute("SELECT count(*) FROM pipeline_runs WHERE run_id='_test'").fetchone()[0]
        conn.execute("ROLLBACK")
        print(f"smoke test      : {'ok' if n == 1 else 'FAILED'}")

if __name__ == '__main__':
    verify()