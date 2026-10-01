"""
inspect.py — observability CLI for the pipeline DB.

Usage:
  python inspect.py docs [PATTERN]                 list documents
  python inspect.py doc <PREFIX>                   doc summary
  python inspect.py doc <PREFIX> --blocks          all blocks
  python inspect.py doc <PREFIX> --atoms           all atoms
  python inspect.py doc <PREFIX> --sections        section tree
  python inspect.py doc <PREFIX> --images          images
  python inspect.py doc <PREFIX> --links           links
  python inspect.py doc <PREFIX> --stages          stage history
  python inspect.py runs                           recent pipeline runs
  python inspect.py run <PREFIX>                   stages for a run
  python inspect.py failures                       failed stages
  python inspect.py rejects                        fetch rejects
  python inspect.py queue                          url queue status

Options:
  --limit N                                        max rows (default 50)

Doc prefix matching: pass any unique prefix of the doc_id.
  python inspect.py doc cepi
  python inspect.py doc https_my_cleveland
"""
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).parent / 'corpus_v1.db'


def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def truncate(s, n=80):
    if s is None:
        return '-'
    s = str(s).replace('\n', ' ').replace('\r', ' ')
    return s if len(s) <= n else s[:n - 1] + '…'


def resolve_prefix(conn, table, column, prefix):
    rows = conn.execute(
        f"SELECT {column} FROM {table} WHERE {column} LIKE ? LIMIT 10",
        ('%' + prefix + '%',)
    ).fetchall()
    if not rows:
        print(f"no match for prefix: {prefix}")
        sys.exit(1)
    if len(rows) == 1:
        return rows[0][0]
    exact = [r[0] for r in rows if r[0] == prefix]
    if len(exact) == 1:
        return exact[0]
    print(f"prefix '{prefix}' matches {len(rows)} rows:")
    for r in rows[:10]:
        print(f"  {r[0]}")
    sys.exit(1)


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------

def cmd_docs(conn, pattern, limit):
    q = "SELECT doc_id, title, source_url, first_ingested_at FROM documents"
    args = ()
    if pattern:
        q += " WHERE doc_id LIKE ? OR title LIKE ?"
        args = (f'%{pattern}%', f'%{pattern}%')
    q += " ORDER BY first_ingested_at DESC"

    rows = conn.execute(q, args).fetchall()
    print(f"{len(rows)} documents\n")
    for r in rows:
        print(f"  {truncate(r['doc_id'], 70)}")
        print(f"    title: {r['title'] or '(none)'}")
        print(f"    url:   {r['source_url']}")
        print()


def cmd_doc_summary(conn, doc_id):
    row = conn.execute("SELECT * FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
    if not row:
        print("not found")
        return

    print(f"doc_id:   {row['doc_id']}")
    print(f"title:    {row['title']}")
    print(f"url:      {row['source_url']}")
    print(f"author:   {row['author']}")
    print(f"date:     {row['published_at']}")
    print(f"language: {row['language']}")
    print(f"ingested: {row['first_ingested_at']}")
    print()

    counts = {
        'sections': conn.execute("SELECT count(*) FROM sections WHERE doc_id=?", (doc_id,)).fetchone()[0],
        'blocks':   conn.execute("SELECT count(*) FROM blocks WHERE doc_id=?", (doc_id,)).fetchone()[0],
        'atoms':    conn.execute("SELECT count(*) FROM atoms WHERE doc_id=?", (doc_id,)).fetchone()[0],
        'images':   conn.execute("SELECT count(*) FROM images WHERE doc_id=?", (doc_id,)).fetchone()[0],
        'links':    conn.execute("SELECT count(*) FROM links WHERE doc_id=?", (doc_id,)).fetchone()[0],
    }
    for k, v in counts.items():
        print(f"  {k:10s} {v}")

    print("\nblock types:")
    for r in conn.execute(
        "SELECT block_type, count(*) FROM blocks WHERE doc_id=? GROUP BY block_type ORDER BY 2 DESC",
        (doc_id,)
    ):
        print(f"  {r[0]:15s} {r[1]}")

    print("\natom types:")
    for r in conn.execute(
        "SELECT atom_type, count(*) FROM atoms WHERE doc_id=? GROUP BY atom_type ORDER BY 2 DESC",
        (doc_id,)
    ):
        print(f"  {r[0]:15s} {r[1]}")

    print("\ntop-level sections:")
    for r in conn.execute(
        "SELECT heading, heading_level, token_count FROM sections "
        "WHERE doc_id=? AND heading_level=1 ORDER BY char_start",
        (doc_id,)
    ):
        print(f"  L{r[1]}  {r[0]}  ({r[2]} tok)")

    print(f"\nhint: run 'inspect.py doc {doc_id[:30]}... --blocks' for full block list")


def cmd_doc_blocks(conn, doc_id, limit):
    rows = conn.execute("""
        SELECT order_index, block_type, heading_path, token_count, text,
               is_math, is_boilerplate, is_orphan
        FROM blocks WHERE doc_id=? ORDER BY order_index LIMIT ?
    """, (doc_id, limit)).fetchall()
    print(f"{len(rows)} blocks\n")
    for r in rows:
        flags = ''
        if r['is_math']:        flags += 'M'
        if r['is_boilerplate']: flags += 'B'
        if r['is_orphan']:      flags += 'O'
        flags = f"[{flags:3s}]"
        print(f"  {r['order_index']:4d} {r['block_type']:12s} {r['token_count']:4d}t {flags} {truncate(r['text'], 100)}")


def cmd_doc_atoms(conn, doc_id, limit):
    rows = conn.execute("""
        SELECT a.atom_id, a.atom_type, a.token_count, a.text, s.heading AS section_heading
        FROM atoms a
        LEFT JOIN sections s ON s.section_id = a.section_id
        WHERE a.doc_id=? LIMIT ?
    """, (doc_id, limit)).fetchall()
    print(f"{len(rows)} atoms\n")
    for r in rows:
        sec = truncate(r['section_heading'], 30)
        print(f"  [{sec:32s}] {r['atom_type']:10s} {r['token_count']:4d}t  {truncate(r['text'], 100)}")


def cmd_doc_sections(conn, doc_id, limit):
    rows = conn.execute("""
        SELECT section_id, parent_section_id, heading, heading_level,
               token_count, is_boilerplate
        FROM sections WHERE doc_id=? ORDER BY char_start
    """, (doc_id,)).fetchall()

    by_parent = {}
    for r in rows:
        by_parent.setdefault(r['parent_section_id'], []).append(r)

    def render(node, depth=0):
        h = node['heading'] or '(root)'
        bp = ' [boilerplate]' if node['is_boilerplate'] else ''
        indent = '  ' * depth
        print(f"  {indent}L{node['heading_level'] or '-'} {truncate(h, 60)}  ({node['token_count']}t){bp}")
        for child in by_parent.get(node['section_id'], []):
            render(child, depth + 1)

    print(f"{len(rows)} sections (tree)\n")
    for root in by_parent.get(None, []):
        render(root)


def cmd_doc_images(conn, doc_id, limit):
    rows = conn.execute("""
        SELECT i.url, i.alt, s.heading AS section_heading
        FROM images i
        LEFT JOIN sections s ON s.section_id = i.section_id
        WHERE i.doc_id=? LIMIT ?
    """, (doc_id, limit)).fetchall()
    print(f"{len(rows)} images\n")
    for r in rows:
        print(f"  alt: {truncate(r['alt'], 90)}")
        print(f"  url: {truncate(r['url'], 110)}")
        print(f"  sec: {truncate(r['section_heading'], 60)}")
        print()


def cmd_doc_links(conn, doc_id, limit):
    rows = conn.execute("""
        SELECT url, text, is_internal, is_citation
        FROM links WHERE doc_id=? LIMIT ?
    """, (doc_id, limit)).fetchall()
    print(f"{len(rows)} links\n")
    for r in rows:
        mark = 'i' if r['is_internal'] else 'e'
        mark += 'C' if r['is_citation'] else ' '
        print(f"  [{mark}] {truncate(r['text'] or '(no text)', 60)}")
        print(f"        {truncate(r['url'], 100)}")


def cmd_doc_stages(conn, doc_id, limit):
    rows = conn.execute("""
        SELECT run_id, stage, status, started_at, finished_at, counts_json, error
        FROM doc_stages WHERE doc_id=? ORDER BY started_at LIMIT ?
    """, (doc_id, limit)).fetchall()
    print(f"{len(rows)} stage rows\n")
    for r in rows:
        print(f"  {r['stage']:12s}  {r['status']:10s}  {r['started_at']}")
        if r['counts_json']:
            print(f"      counts: {r['counts_json']}")
        if r['error']:
            print(f"      ERROR: {r['error']}")


def cmd_runs(conn, limit):
    rows = conn.execute("""
        SELECT run_id, started_at, finished_at, status, notes
        FROM pipeline_runs ORDER BY started_at DESC LIMIT ?
    """, (limit,)).fetchall()
    print(f"{len(rows)} runs\n")
    for r in rows:
        print(f"  {r['run_id'][:16]}  {r['status']:10s}  {r['started_at']}  {r['notes'] or ''}")


def cmd_run(conn, prefix, limit):
    run_id = resolve_prefix(conn, 'pipeline_runs', 'run_id', prefix)
    row = conn.execute("SELECT * FROM pipeline_runs WHERE run_id=?", (run_id,)).fetchone()

    print(f"run_id:    {row['run_id']}")
    print(f"status:    {row['status']}")
    print(f"started:   {row['started_at']}")
    print(f"finished:  {row['finished_at']}")
    print(f"notes:     {row['notes']}")
    print()

    stages = conn.execute("""
        SELECT doc_id, stage, status, error
        FROM doc_stages WHERE run_id=? ORDER BY started_at LIMIT ?
    """, (run_id, limit)).fetchall()
    print(f"{len(stages)} stage rows\n")
    for s in stages:
        print(f"  {truncate(s['doc_id'], 55):55s}  {s['stage']:10s}  {s['status']}")
        if s['error']:
            print(f"      ERROR: {s['error']}")


def cmd_failures(conn, limit):
    rows = conn.execute("""
        SELECT run_id, doc_id, stage, status, error, started_at
        FROM doc_stages WHERE status='failed'
        ORDER BY started_at DESC LIMIT ?
    """, (limit,)).fetchall()
    print(f"{len(rows)} failed stages\n")
    for r in rows:
        print(f"  [{r['stage']}] {truncate(r['doc_id'], 60)}")
        print(f"      {r['error'] or 'no error message'}")


def cmd_rejects(conn, limit):
    print("by reason:")
    for r in conn.execute("SELECT reason, count(*) FROM rejects GROUP BY reason ORDER BY 2 DESC"):
        print(f"  {r[0]:20s} {r[1]}")

    print()
    rows = conn.execute("""
        SELECT url, reason, status_code, detail, fetched_at
        FROM rejects ORDER BY fetched_at DESC LIMIT ?
    """, (limit,)).fetchall()
    print(f"{len(rows)} most recent rejects\n")
    for r in rows:
        print(f"  [{r['reason']}] {truncate(r['url'], 80)}")
        if r['detail']:
            print(f"      {truncate(r['detail'], 90)}")


def cmd_queue(conn, limit):
    print("url_queue status:")
    for r in conn.execute("SELECT status, count(*) FROM url_queue GROUP BY status ORDER BY 2 DESC"):
        print(f"  {r[0]:15s} {r[1]}")

    print()
    print(f"{limit} most recently touched URLs:")
    for r in conn.execute("""
        SELECT url, status, updated_at FROM url_queue
        ORDER BY updated_at DESC LIMIT ?
    """, (limit,)):
        print(f"  {truncate(r['url'], 70):70s}  {r['status']}")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

USAGE = __doc__


def main():
    args = sys.argv[1:]
    if not args:
        print(USAGE)
        sys.exit(1)

    limit = 50
    if '--limit' in args:
        i = args.index('--limit')
        limit = int(args[i + 1])
        args = args[:i] + args[i + 2:]

    cmd = args[0]
    rest = args[1:]
    conn = connect()

    try:
        if cmd == 'docs':
            cmd_docs(conn, rest[0] if rest else None, limit)

        elif cmd == 'doc':
            if not rest:
                print("usage: inspect.py doc <prefix> [flag]")
                sys.exit(1)
            doc_id = resolve_prefix(conn, 'documents', 'doc_id', rest[0])
            flags = rest[1:]
            if '--blocks' in flags:     cmd_doc_blocks(conn, doc_id, limit)
            elif '--atoms' in flags:    cmd_doc_atoms(conn, doc_id, limit)
            elif '--sections' in flags: cmd_doc_sections(conn, doc_id, limit)
            elif '--images' in flags:   cmd_doc_images(conn, doc_id, limit)
            elif '--links' in flags:    cmd_doc_links(conn, doc_id, limit)
            elif '--stages' in flags:   cmd_doc_stages(conn, doc_id, limit)
            else:                       cmd_doc_summary(conn, doc_id)

        elif cmd == 'runs':     cmd_runs(conn, limit)
        elif cmd == 'run':      cmd_run(conn, rest[0], limit) if rest else print("usage: inspect.py run <prefix>")
        elif cmd == 'failures': cmd_failures(conn, limit)
        elif cmd == 'rejects':  cmd_rejects(conn, limit)
        elif cmd == 'queue':    cmd_queue(conn, limit)
        else:
            print(f"unknown command: {cmd}\n")
            print(USAGE)
            sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    main()