"""
Select atoms per section, per source, based on the selection plan.

Deterministic. No LLM, no JEV. Reads atoms from the DB, ranks them by
local specificity, allocates budgets per the plan, writes a structured
JSON that synthesize.py consumes.

Budgets:
  - section budget (primary + supporting): 250 atoms total
    - primary sources weighted 2x supporting
  - standalone source: 200 atoms
  - contextual source: 30 atoms

Atom ranking within a source:
  +2  contains a digit
  +1  contains a capitalized word (>3 chars, not sentence-start)
  +1  80 <= len <= 400 chars
  -2  len < 40 chars
  -1  starts with common stop words

Reads:
  <run_dir>/selection_plan.json
  documents, atoms from the DB

Writes:
  <run_dir>/selected_atoms.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from db import connect


SECTION_BUDGET = 250
STANDALONE_BUDGET = 200
CONTEXTUAL_BUDGET = 30

STOP_PREFIXES = (
    'see also', 'read more', 'related', 'share', 'follow',
    'subscribe', 'sign up', 'click here', 'advertisement',
)

_CAP_RE = re.compile(r'\b[A-Z][a-z]{2,}\b')


def load_plan(run_dir: Path) -> dict:
    path = run_dir / 'selection_plan.json'
    if not path.exists():
        raise FileNotFoundError(f"selection_plan.json not found in {run_dir}")
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_doc_id_map(conn) -> dict[str, str]:
    """url -> doc_id"""
    rows = conn.execute("SELECT doc_id, source_url FROM documents").fetchall()
    return {r['source_url']: r['doc_id'] for r in rows}


def load_atoms_for_doc(conn, doc_id: str) -> list[dict]:
    rows = conn.execute("""
        SELECT atom_id, text, char_start, char_end, atom_type
        FROM atoms
        WHERE doc_id = %s
        ORDER BY order_index
    """, (doc_id,)).fetchall()
    return [dict(r) for r in rows]


def atom_score(text: str) -> float:
    if not text:
        return -10.0
    t = text.strip()
    if not t:
        return -10.0

    score = 0.0
    if any(c.isdigit() for c in t):
        score += 2.0

    # proper noun indicator (ignore sentence-start capitalization)
    body = t[1:] if len(t) > 1 else ''
    if _CAP_RE.search(body):
        score += 1.0

    n = len(t)
    if 80 <= n <= 400:
        score += 1.0
    elif n < 40:
        score -= 2.0

    low = t.lower()
    if any(low.startswith(p) for p in STOP_PREFIXES):
        score -= 1.0

    return score


def rank_atoms(atoms: list[dict]) -> list[dict]:
    for a in atoms:
        a['_score'] = atom_score(a.get('text', ''))
    return sorted(atoms, key=lambda a: a['_score'], reverse=True)


def allocate_section_budget(primaries: int, supportings: int) -> dict:
    """Return per-source budgets within a section."""
    total_weight = 2 * primaries + 1 * supportings
    if total_weight == 0:
        return {'primary_each': 0, 'supporting_each': 0}
    per_weight = SECTION_BUDGET / total_weight
    return {
        'primary_each': int(round(per_weight * 2)),
        'supporting_each': int(round(per_weight * 1)),
    }


def select_for_section(section: dict,
                       doc_id_map: dict,
                       conn,
                       section_num: int) -> dict:
    """Return {'title', 'atoms': [...]} for one section."""
    title = section.get('title', f'Section {section_num}')
    selected = []

    if 'standalone' in section:
        url = section['standalone']
        doc_id = doc_id_map.get(url)
        if doc_id:
            atoms = rank_atoms(load_atoms_for_doc(conn, doc_id))
            chosen = atoms[:STANDALONE_BUDGET]
            for a in chosen:
                a['_role'] = 'standalone'
            selected.extend(chosen)
        return {'title': title, 'standalone': True, 'atoms': selected}

    primary_urls = section.get('primary', []) or []
    supporting_urls = section.get('supporting', []) or []
    budgets = allocate_section_budget(len(primary_urls), len(supporting_urls))

    for url in primary_urls:
        doc_id = doc_id_map.get(url)
        if not doc_id:
            continue
        atoms = rank_atoms(load_atoms_for_doc(conn, doc_id))
        for a in atoms[:budgets['primary_each']]:
            a['_role'] = 'primary'
            selected.append(a)

    for url in supporting_urls:
        doc_id = doc_id_map.get(url)
        if not doc_id:
            continue
        atoms = rank_atoms(load_atoms_for_doc(conn, doc_id))
        for a in atoms[:budgets['supporting_each']]:
            a['_role'] = 'supporting'
            selected.append(a)

    return {'title': title, 'standalone': False, 'atoms': selected}


def run(run_dir: Path | str, verbose: bool = True) -> dict:
    run_dir = Path(run_dir)
    plan = load_plan(run_dir)

    conn = connect()
    try:
        doc_id_map = load_doc_id_map(conn)

        sections_out = []
        for i, section in enumerate(plan.get('sections', []), 1):
            sections_out.append(select_for_section(section, doc_id_map, conn, i))

        # contextual sources: 30 atoms each
        contextual_out = []
        for entry in plan.get('contextual', []):
            url = entry.get('url')
            doc_id = doc_id_map.get(url)
            if not doc_id:
                continue
            atoms = rank_atoms(load_atoms_for_doc(conn, doc_id))
            chosen = atoms[:CONTEXTUAL_BUDGET]
            for a in chosen:
                a['_role'] = 'contextual'
            if chosen:
                contextual_out.append({
                    'url': url,
                    'title': entry.get('reason', 'contextual'),
                    'atoms': chosen,
                })
    finally:
        conn.close()

    result = {
        'intent': plan.get('intent'),
        'sections': sections_out,
        'contextual': contextual_out,
        'totals': {
            'sections': len(sections_out),
            'total_atoms': sum(len(s['atoms']) for s in sections_out)
                          + sum(len(c['atoms']) for c in contextual_out),
        },
    }

    out = run_dir / 'selected_atoms.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    if verbose:
        print(f"select_atoms: {result['totals']['sections']} sections, "
              f"{result['totals']['total_atoms']} atoms total")
        for s in sections_out:
            tag = 'STANDALONE' if s['standalone'] else 'section'
            print(f"  [{tag:10s}] {s['title'][:55]:55s}  {len(s['atoms']):>4d} atoms")
        for c in contextual_out:
            print(f"  [contextual] {c['url'][:55]:55s}  {len(c['atoms']):>4d} atoms")
        print(f"  wrote: {out}")

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-dir', required=True)
    args = ap.parse_args()
    run(Path(args.run_dir).expanduser().resolve(), verbose=True)


if __name__ == '__main__':
    main()