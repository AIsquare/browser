"""
Load block ASTs into Neon Postgres.

Reads every data/blocks/*.json, derives sections, splits atoms, and
writes to documents, sections, blocks, atoms, images, links.

Math blocks are emitted as a single atom — never sentence-split.
List items become single atoms. Paragraphs become sentences.

Idempotent: re-running on the same doc deletes and rebuilds its rows.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from db import connect

BLOCKS_DIR = Path('data/blocks')


# ----------------------------------------------------------------------
# Sentence splitting
# ----------------------------------------------------------------------

ABBREV = {
    'U.S.', 'U.K.', 'Mr.', 'Mrs.', 'Ms.', 'Dr.', 'e.g.', 'i.e.', 'etc.',
    'vs.', 'Inc.', 'Ltd.', 'Co.', 'St.', 'No.', 'Fig.', 'Vol.', 'Jr.', 'Sr.',
    'Ph.D.', 'M.D.', 'B.A.', 'M.A.', 'D.C.', 'U.N.',
}


def split_sentences(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    protected = text
    for a in ABBREV:
        protected = protected.replace(a, a.replace('.', '\x00'))
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"\'\(])', protected)
    parts = [p.replace('\x00', '.').strip() for p in parts]
    return [p for p in parts if p]


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def sha16(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# ----------------------------------------------------------------------
# Section derivation (stack walk) — unchanged logic
# ----------------------------------------------------------------------

def derive_sections(blocks: list[dict], doc_id: str) -> list[dict]:
    sections = []
    stack: list[tuple[int, str, str]] = []

    root_id = f"{doc_id}__root"
    sections.append({
        'section_id': root_id,
        'doc_id': doc_id,
        'parent_section_id': None,
        'heading': None,
        'heading_level': None,
        'heading_path': '[]',
        'first_block_id': None,
        'last_block_id': None,
        'token_count': 0,
        'char_start': None,
        'char_end': None,
        'is_boilerplate': 0,
    })

    stats: dict[str, dict] = {root_id: {
        'first': None, 'last': None, 'tok': 0, 'cs': None, 'ce': None
    }}

    for b in blocks:
        if b['block_type'] == 'heading':
            if b.get('is_orphan'):
                cur_id = stack[-1][1] if stack else root_id
                b['section_id'] = cur_id
                s = stats.setdefault(cur_id, {'first': None, 'last': None, 'tok': 0, 'cs': None, 'ce': None})
                if s['first'] is None:
                    s['first'] = b['block_id']; s['cs'] = b['char_start']
                s['last'] = b['block_id']; s['ce'] = b['char_end']
                s['tok'] += b.get('token_count') or 0
                continue

            level = b.get('heading_level') or 1
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent_id = stack[-1][1] if stack else None

            sid = b['block_id']
            sections.append({
                'section_id': sid,
                'doc_id': doc_id,
                'parent_section_id': parent_id,
                'heading': b.get('text') or b.get('content', '').lstrip('# ').strip(),
                'heading_level': level,
                'heading_path': json.dumps(b.get('heading_path', [])),
                'first_block_id': None,
                'last_block_id': None,
                'token_count': 0,
                'char_start': b['char_start'],
                'char_end': b['char_end'],
                'is_boilerplate': int(bool(b.get('is_boilerplate'))),
            })
            stack.append((level, sid, sections[-1]['heading']))
            b['section_id'] = parent_id
            stats[sid] = {'first': None, 'last': None, 'tok': 0,
                          'cs': b['char_start'], 'ce': b['char_end']}

        else:
            cur_id = stack[-1][1] if stack else root_id
            b['section_id'] = cur_id
            s = stats.setdefault(cur_id, {'first': None, 'last': None, 'tok': 0, 'cs': None, 'ce': None})
            if s['first'] is None:
                s['first'] = b['block_id']; s['cs'] = b['char_start']
            s['last'] = b['block_id']; s['ce'] = b['char_end']
            s['tok'] += b.get('token_count') or 0

    for sec in sections:
        sid = sec['section_id']
        s = stats.get(sid, {})
        sec['first_block_id'] = s.get('first')
        sec['last_block_id']  = s.get('last')
        sec['token_count']    = s.get('tok', 0)
        if sec['char_start'] is None:
            sec['char_start'] = s.get('cs')
        if sec['char_end'] is None:
            sec['char_end'] = s.get('ce')

    return sections


# ----------------------------------------------------------------------
# Atomization — unchanged
# ----------------------------------------------------------------------

def atomize_block(b: dict) -> list[dict]:
    bt = b['block_type']
    text = b.get('text') or ''

    if bt == 'heading':
        return []

    atoms = []

    if bt == 'paragraph' or bt == 'blockquote':
        if b.get('is_math'):
            if text.strip():
                atoms.append(('math', text.strip()))
        else:
            for s in split_sentences(text):
                atoms.append(('sentence', s))

    elif bt == 'list_item':
        t = re.sub(r'^\s*[-*+]\s+', '', text).strip()
        t = re.sub(r'^\s*\d+\.\s+', '', t).strip()
        if t:
            atoms.append(('list_item', t))

    elif bt == 'image':
        if text.strip():
            atoms.append(('caption', text.strip()))

    elif bt == 'code':
        if text.strip():
            atoms.append(('code', text.strip()))

    elif bt == 'table':
        if text.strip():
            atoms.append(('table', text.strip()))

    else:
        for s in split_sentences(text):
            atoms.append(('sentence', s))

    return atoms


# ----------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------

def _extract_source_url(blocks: list[dict], frontmatter: dict | None = None) -> str | None:
    for i, b in enumerate(blocks):
        if b['block_type'] == 'heading' and b.get('text', '').strip().lower() == 'source':
            for j in range(i + 1, min(i + 3, len(blocks))):
                t = blocks[j].get('text', '').strip()
                if t.startswith('http'):
                    return t
    if frontmatter and frontmatter.get('source_url'):
        return frontmatter['source_url']
    return None


def load_doc(conn, ast: dict, run_id: str | None = None) -> dict:
    doc_id = ast['doc_id']
    blocks = ast['blocks']
    frontmatter = ast.get('frontmatter') or {}

    source_url = _extract_source_url(blocks, frontmatter) or f"unknown://{doc_id}"
    content_hash = sha16(json.dumps(blocks, sort_keys=True))

    title = None
    for b in blocks:
        if b['block_type'] == 'heading' and b.get('heading_level') == 1:
            if not b.get('is_boilerplate'):
                t = b.get('text', '').lstrip('# ').strip()
                if t and t != '-':
                    title = t
                    break
    if not title and frontmatter.get('title'):
        title = frontmatter['title']

    now = utcnow()

    # -- documents --
    conn.execute("""
        INSERT INTO documents
        (doc_id, source_url, canonical_url, title, author, published_at,
         updated_at, language, description, source_type, content_hash,
         frontmatter_json, first_ingested_at, last_ingested_at)
      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
      ON CONFLICT(doc_id) DO UPDATE SET
        source_url       = EXCLUDED.source_url,
        title            = EXCLUDED.title,
        author           = EXCLUDED.author,
        published_at     = EXCLUDED.published_at,
        updated_at       = EXCLUDED.updated_at,
        language         = EXCLUDED.language,
        description      = EXCLUDED.description,
        source_type      = EXCLUDED.source_type,
        content_hash     = EXCLUDED.content_hash,
        frontmatter_json = EXCLUDED.frontmatter_json,
        last_ingested_at = EXCLUDED.last_ingested_at
    """, (
        doc_id, source_url, source_url, title,
        frontmatter.get('author'),
        frontmatter.get('published_at'),
        frontmatter.get('updated_at'),
        frontmatter.get('language'),
        frontmatter.get('description'),
        frontmatter.get('source_type') or 'unknown',
        content_hash,
        json.dumps(frontmatter) if frontmatter else None,
        now, now,
    ))

    # -- clear previous rows (idempotent re-ingest) --
    conn.execute("""
      DELETE FROM section_images
      WHERE section_id IN (SELECT section_id FROM sections WHERE doc_id=%s)
    """, (doc_id,))
    conn.execute("""
      DELETE FROM footnote_refs
      WHERE block_id IN (SELECT block_id FROM blocks WHERE doc_id=%s)
    """, (doc_id,))
    conn.execute("DELETE FROM footnotes WHERE doc_id=%s", (doc_id,))

    conn.execute("DELETE FROM selected_atoms WHERE doc_id=%s", (doc_id,))
    conn.execute("""
      DELETE FROM atom_buckets
      WHERE atom_id IN (SELECT atom_id FROM atoms WHERE doc_id=%s)
    """, (doc_id,))

    conn.execute("DELETE FROM atoms WHERE doc_id=%s", (doc_id,))
    conn.execute("DELETE FROM links WHERE doc_id=%s", (doc_id,))
    conn.execute("DELETE FROM images WHERE doc_id=%s", (doc_id,))
    conn.execute("DELETE FROM blocks WHERE doc_id=%s", (doc_id,))
    conn.execute("DELETE FROM sections WHERE doc_id=%s", (doc_id,))

    # -- sections --
    sections = derive_sections(blocks, doc_id)
    for s in sections:
        conn.execute("""
          INSERT INTO sections
            (section_id, doc_id, parent_section_id, heading, heading_level,
             heading_path, first_block_id, last_block_id, token_count,
             char_start, char_end, is_boilerplate)
          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            s['section_id'], s['doc_id'], s['parent_section_id'],
            s['heading'], s['heading_level'], s['heading_path'],
            s['first_block_id'], s['last_block_id'], s['token_count'],
            s['char_start'], s['char_end'], s['is_boilerplate'],
        ))

    # -- blocks --
    for b in blocks:
        conn.execute("""
          INSERT INTO blocks
            (block_id, doc_id, section_id, parent_block_id, prev_block_id, next_block_id,
             list_id, block_type, heading_path, order_index, char_start, char_end,
             char_count, token_count, text, raw_text, content_hash,
             is_orphan, is_boilerplate, is_math, is_footnote, language, extra_json)
          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            b['block_id'], doc_id, b.get('section_id'),
            b.get('parent_block_id'), b.get('prev_block_id'), b.get('next_block_id'),
            b.get('list_id'), b['block_type'],
            json.dumps(b.get('heading_path', [])),
            b['position_index'], b['char_start'], b['char_end'],
            b.get('char_count'), b.get('token_count'),
            b.get('text', ''), b.get('content', ''),
            b.get('content_hash'),
            int(bool(b.get('is_orphan'))),
            int(bool(b.get('is_boilerplate'))),
            int(bool(b.get('is_math'))),
            int(bool(b.get('is_footnote'))),
            b.get('language'),
            json.dumps({'language': b.get('language')}) if b.get('language') else None,
        ))

    # -- atoms --
    atom_count = 0
    for b in blocks:
        if b.get('is_boilerplate'):
            continue
        atom_list = atomize_block(b)
        for i, (atype, text) in enumerate(atom_list):
            if not text:
                continue
            atom_id = sha16(f"{b['block_id']}|{i}|{text}")
            conn.execute("""
              INSERT INTO atoms
                (atom_id, block_id, doc_id, section_id, atom_type,
                 order_index, char_start, char_end, token_count, text, content_hash)
              VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
              ON CONFLICT (atom_id) DO UPDATE SET
                block_id     = EXCLUDED.block_id,
                doc_id       = EXCLUDED.doc_id,
                section_id   = EXCLUDED.section_id,
                atom_type    = EXCLUDED.atom_type,
                order_index  = EXCLUDED.order_index,
                char_start   = EXCLUDED.char_start,
                char_end     = EXCLUDED.char_end,
                token_count  = EXCLUDED.token_count,
                text         = EXCLUDED.text,
                content_hash = EXCLUDED.content_hash
            """, (
                atom_id, b['block_id'], doc_id, b.get('section_id'),
                atype, i,
                b['char_start'], b['char_end'],
                count_tokens(text), text, sha16(text),
            ))
            atom_count += 1

    # -- images --
    for b in blocks:
        for img in b.get('image_refs') or []:
            url = img.get('url')
            if not url:
                continue
            image_id = sha16(url)
            conn.execute("""
              INSERT INTO images
                (image_id, block_id, doc_id, section_id, url, alt, created_at)
              VALUES (%s, %s, %s, %s, %s, %s, %s)
              ON CONFLICT (image_id) DO NOTHING
            """, (
                image_id, b['block_id'], doc_id, b.get('section_id'),
                url, img.get('alt', ''), now,
            ))

    # -- links --
    for b in blocks:
        for i, lnk in enumerate(b.get('links') or []):
            url = lnk.get('url')
            if not url:
                continue
            link_id = sha16(f"{b['block_id']}|{i}|{url}")
            conn.execute("""
              INSERT INTO links
                (link_id, block_id, doc_id, url, text, is_internal, is_citation, order_index)
              VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
              ON CONFLICT (link_id) DO UPDATE SET
                block_id    = EXCLUDED.block_id,
                doc_id      = EXCLUDED.doc_id,
                url         = EXCLUDED.url,
                text        = EXCLUDED.text,
                is_internal = EXCLUDED.is_internal,
                is_citation = EXCLUDED.is_citation,
                order_index = EXCLUDED.order_index
            """, (
                link_id, b['block_id'], doc_id, url,
                lnk.get('text', ''),
                int(url.startswith('/') or source_url in url),
                0, i,
            ))

    # -- doc_stages --
    if run_id:
        conn.execute("""
          INSERT INTO doc_stages
            (run_id, doc_id, stage, status, started_at, finished_at, counts_json, error)
          VALUES (%s, %s, 'load', 'ok', %s, %s, %s, NULL)
          ON CONFLICT (run_id, doc_id, stage) DO UPDATE SET
            status       = EXCLUDED.status,
            started_at   = EXCLUDED.started_at,
            finished_at  = EXCLUDED.finished_at,
            counts_json  = EXCLUDED.counts_json,
            error        = EXCLUDED.error
        """, (run_id, doc_id, now, now,
              json.dumps({'blocks': len(blocks), 'atoms': atom_count,
                          'sections': len(sections)})))

    return {
        'doc_id': doc_id,
        'blocks': len(blocks),
        'atoms': atom_count,
        'sections': len(sections),
    }


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------


def run(blocks_dir: Path | None = None,
        run_id: str | None = None) -> dict:
    """
    Load every block JSON in blocks_dir into the DB.
    Returns {'docs': N, 'blocks': M, 'atoms': K, 'sections': S, 'run_id': str}.
    """
    src = Path(blocks_dir) if blocks_dir else BLOCKS_DIR
    json_files = sorted(src.glob('*.json'))

    if not json_files:
        print(f"no JSON files in {src}")
        return {'docs': 0, 'blocks': 0, 'atoms': 0, 'sections': 0, 'run_id': None}

    conn = connect()
    if run_id is None:
        run_id = sha16(f"ingest-{utcnow()}")

    conn.execute("""
      INSERT INTO pipeline_runs (run_id, started_at, status, stages_json)
      VALUES (%s, %s, 'running', %s)
      ON CONFLICT (run_id) DO NOTHING
    """, (run_id, utcnow(), json.dumps(['load'])))

    total = {'docs': 0, 'blocks': 0, 'atoms': 0, 'sections': 0}

    for jf in json_files:
        try:
            ast = json.loads(jf.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"skip {jf.name}: {e}")
            continue
        r = load_doc(conn, ast, run_id)
        total['docs'] += 1
        total['blocks'] += r['blocks']
        total['atoms'] += r['atoms']
        total['sections'] += r['sections']
        print(f"{r['doc_id'][:55]:55s}  "
              f"{r['blocks']:4d} blocks  "
              f"{r['atoms']:4d} atoms  "
              f"{r['sections']:3d} sections")

    conn.execute("""
      UPDATE pipeline_runs SET status='completed', finished_at=%s WHERE run_id=%s
    """, (utcnow(), run_id))
    conn.commit()
    conn.close()

    print()
    print(f"loaded: {total['docs']} docs, "
          f"{total['blocks']} blocks, "
          f"{total['atoms']} atoms, "
          f"{total['sections']} sections")

    total['run_id'] = run_id
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--blocks-dir', default=str(BLOCKS_DIR),
                    help='directory containing block JSONs')
    ap.add_argument('--run-id', default=None,
                    help='pipeline_runs.run_id to attribute this run to')
    args = ap.parse_args()
    run(blocks_dir=args.blocks_dir, run_id=args.run_id)


if __name__ == '__main__':
    main()