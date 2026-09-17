#!/usr/bin/env python3
"""
Ingest AST JSONs into a SQLite store: documents, sections, blocks, atoms.

Configure DB_PATH, SCHEMA_PATH, and INPUTS below, then run:
    python ingest.py
"""
import glob, hashlib, json, os, re, sqlite3, sys
from datetime import datetime, timezone

# ---------- configuration ----------

DB_PATH = "corpus.db"
SCHEMA_PATH = "schema.sql"
INPUTS = [r"C:\Users\lenovo\Downloads\browser_based_agent\dom_extract_fixed_pkg\data\blocks"]

ABBREV = ['U.S.', 'U.K.', 'Mr.', 'Mrs.', 'Dr.', 'Ms.', 'e.g.', 'i.e.', 'etc.',
          'vs.', 'Inc.', 'Ltd.', 'Co.', 'St.', 'No.', 'Fig.', 'Vol.', 'Jr.', 'Sr.']

def split_sentences(text):
    if not text:
        return []
    p = text
    for a in ABBREV:
        p = p.replace(a, a.replace('.', '\x00'))
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"\'(])', p)
    return [s.replace('\x00', '.').strip() for s in parts if s.strip()]

def clean_text(t):
    if not t:
        return t
    t = re.sub(r'\[\s*\d+\s*\]', '', t)          # inline citation markers
    t = re.sub(r'\s*Open in new window\s*', ' ', t)  # scraper artifact
    t = re.sub(r'\s+([,.;:!?])', r'\1', t)       # space before punctuation
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def token_count(t):
    return len(t.split()) if t else 0

def sha16(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

# ---------- stage 1: documents + blocks ----------

def load_document(conn, ast):
    doc_id = ast['doc_id']
    blocks = ast['blocks']

    title, source_uri = None, None
    for b in blocks:
        if b.get('is_boilerplate'):
            continue
        if title is None and b.get('block_type') == 'heading' \
                and b.get('heading_level') == 1:
            title = clean_text(b['content']).lstrip('# ').strip()
        if source_uri is None and b.get('block_type') == 'paragraph' \
                and (b.get('content') or '').startswith('http'):
            source_uri = b['content'].strip()
        if title and source_uri:
            break

    content_hash = sha16(''.join(b.get('content', '') or '' for b in blocks))

    conn.execute("""
      INSERT OR REPLACE INTO documents
        (doc_id, source_path, source_uri, title, language, content_hash, ingested_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (doc_id, ast.get('source_path'), source_uri, title, None, content_hash, now_iso()))

    for b in blocks:
        conn.execute("""
          INSERT OR REPLACE INTO blocks
            (block_id, doc_id, section_id, parent_block_id, prev_block_id, next_block_id,
             list_id, block_type, heading_path, order_index, char_start, char_end,
             token_count, char_count, text, content_hash, is_orphan, is_boilerplate)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            b['block_id'], b['doc_id'], None,
            b.get('parent_block_id'), b.get('prev_block_id'), b.get('next_block_id'),
            b.get('list_id'), b['block_type'],
            json.dumps(b.get('heading_path', [])),
            b['position_index'], b['char_start'], b['char_end'],
            b.get('token_count') or b.get('word_count') or token_count(clean_text(b.get('content', ''))),
            b.get('char_count') or len(b.get('content', '') or ''),
            clean_text(b.get('content', '')),
            b.get('content_hash') or sha16(b.get('content', '') or ''),
            1 if b.get('is_orphan') else 0,
            1 if b.get('is_boilerplate') else 0,
        ))

# ---------- stage 2: section derivation ----------

def derive_sections(conn, ast):
    doc_id = ast['doc_id']
    blocks = ast['blocks']

    conn.execute("DELETE FROM atoms WHERE doc_id = ?", (doc_id,))
    conn.execute("UPDATE blocks SET section_id = NULL WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM sections WHERE doc_id = ?", (doc_id,))

    root_id = f"{doc_id}__root"
    conn.execute("""
      INSERT INTO sections
        (section_id, doc_id, parent_section_id, heading, heading_level,
         heading_path, first_block_id, last_block_id, token_count, char_start, char_end)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (root_id, doc_id, None, None, None, json.dumps([]), None, None, 0, None, None))

    stack = [(0, root_id)]
    stats = {}

    for b in blocks:
        if b['block_type'] == 'heading':
            level = b.get('heading_level') or 1
            if b.get('is_orphan'):
                # orphan heading: no section opened, folds into current section
                cur = stack[-1][1]
                conn.execute("UPDATE blocks SET section_id=? WHERE block_id=?",
                             (cur, b['block_id']))
                continue
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1] if stack else root_id
            sid = b['block_id']
            conn.execute("""
              INSERT OR REPLACE INTO sections
                (section_id, doc_id, parent_section_id, heading, heading_level,
                 heading_path, first_block_id, last_block_id, token_count, char_start, char_end)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sid, doc_id, parent,
                clean_text(b['content']).lstrip('# ').strip(),
                level,
                json.dumps(b.get('heading_path', [])),
                None, None, 0,
                b['char_start'], b['char_end'],
            ))
            stack.append((level, sid))
            conn.execute("UPDATE blocks SET section_id=? WHERE block_id=?",
                         (parent, b['block_id']))
            stats.setdefault(sid, {'first': None, 'last': None, 'tok': 0,
                                   'cs': b['char_start'], 'ce': b['char_end']})
        else:
            cur = stack[-1][1]
            conn.execute("UPDATE blocks SET section_id=? WHERE block_id=?",
                         (cur, b['block_id']))
            st = stats.setdefault(cur, {'first': None, 'last': None, 'tok': 0,
                                        'cs': b['char_start'], 'ce': b['char_end']})
            if st['first'] is None:
                st['first'] = b['block_id']; st['cs'] = b['char_start']
            st['last'] = b['block_id']; st['ce'] = b['char_end']
            st['tok'] += b.get('token_count') or b.get('word_count') or token_count(clean_text(b.get('content', '')))

    for sid, st in stats.items():
        conn.execute("""UPDATE sections
                        SET first_block_id=?, last_block_id=?, token_count=?,
                            char_start=?, char_end=?
                        WHERE section_id=?""",
                     (st['first'], st['last'], st['tok'], st['cs'], st['ce'], sid))

# ---------- stage 3: atomization ----------

def atomize(conn, ast):
    doc_id = ast['doc_id']
    conn.execute("DELETE FROM atoms WHERE doc_id = ?", (doc_id,))

    for b in ast['blocks']:
        if b.get('is_boilerplate'):
            continue
        bt = b['block_type']
        if bt == 'heading':
            continue
        row = conn.execute("SELECT section_id FROM blocks WHERE block_id=?",
                           (b['block_id'],)).fetchone()
        sid = row[0] if row else None
        raw = b.get('content', '') or ''

        atoms = []
        if bt == 'paragraph':
            atoms = [('sentence', s) for s in split_sentences(clean_text(raw))]
        elif bt == 'list_item':
            t = clean_text(re.sub(r'^\s*[-*]\s*', '', raw))
            if t: atoms = [('list_item', t)]
        elif bt == 'image':
            t = clean_text(raw)
            if t: atoms = [('caption', t)]
        elif bt == 'table':
            if raw.strip(): atoms = [('table', raw.strip())]
        else:
            atoms = [('sentence', s) for s in split_sentences(clean_text(raw))]

        for i, (atype, text) in enumerate(atoms):
            if not text:
                continue
            aid = sha16(f"{b['block_id']}|{i}|{text}")
            conn.execute("""
              INSERT OR REPLACE INTO atoms
                (atom_id, block_id, doc_id, section_id, atom_type,
                 order_index, char_start, char_end, token_count, text, content_hash)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (aid, b['block_id'], doc_id, sid, atype, i,
                  b['char_start'], b['char_end'], token_count(text), text, sha16(text)))




# ---------- main ----------

def main(db_path=DB_PATH, schema_path=SCHEMA_PATH, inputs=INPUTS):
    conn = sqlite3.connect(db_path)
    with open(schema_path, encoding="utf-8") as schema_file:
        conn.executescript(schema_file.read())

    paths = []
    for inp in inputs:
        if os.path.isdir(inp):
            paths.extend(glob.glob(os.path.join(inp, '*.json')))
        else:
            paths.extend(glob.glob(inp))

    for p in paths:
        print(f"ingesting {os.path.basename(p)}", file=sys.stderr)
        with open(p, encoding="utf-8") as f:
            ast = json.load(f)
        load_document(conn, ast)
        derive_sections(conn, ast)
        atomize(conn, ast)
        conn.commit()

    conn.close()
    print(f"done: {len(paths)} docs", file=sys.stderr)

if __name__ == '__main__':
    main()
