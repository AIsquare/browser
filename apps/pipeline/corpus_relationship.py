"""
Corpus relationship layer via JEV — no embeddings.

Stage A: for each doc, ask which other doc is most similar.
Stage B: for each doc, ask how much of its content is already in
         its most-similar sibling.

Produces per-doc redundancy and corpus-relative novelty, then combines
with the composite from doc_understanding.csv.

Reads:
  <run_dir>/extracted/*.md
  <run_dir>/doc_understanding.csv   (optional, for weighting)

Writes:
  <run_dir>/corpus_relationship.csv

Usage:
  python corpus_relationship.py --run-dir C:\\path\\to\\run --topic "supply chains"

Env:
  TYPESAFE_API_KEY   required
  TYPESAFE_MODEL     default jev-latest
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

try:
    from typesafe_sdk import Choice, Score, TypeSafeClient
except ImportError:
    print("pip install typesafe-sdk")
    sys.exit(1)


MODEL = os.environ.get('TYPESAFE_MODEL', 'jev-latest')

# JEV: state + longest question <= 32k tokens (~128k chars). Cap at 110k.
MAX_STATE_CHARS    = 110_000
STAGE_A_DOC_CHARS  = 25_000     # doc text cap in stage A (character profile only)
STAGE_A_PREVIEW    = 200        # chars of each other doc in stage A corpus list
STAGE_B_EACH_CHARS = 50_000     # per-doc cap in stage B (pairwise overlap)


# ----------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------

def parse_frontmatter(text: str) -> tuple[dict, str]:
    fm = {}
    if text.startswith('---'):
        m = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
        if m:
            for line in m.group(1).splitlines():
                if ':' in line:
                    k, v = line.split(':', 1)
                    fm[k.strip()] = v.strip().strip('"')
            text = text[m.end():]
    m = re.match(r'^#\s+Source\s*\n+.*?\n+---\s*\n+', text, re.DOTALL)
    if m:
        text = text[m.end():]
    return fm, text.strip()


def trim(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    head = budget * 2 // 3
    tail = budget - head - 80
    return text[:head] + "\n\n[... middle truncated ...]\n\n" + text[-tail:]


def load_documents(run_dir: Path) -> list[dict]:
    ext = run_dir / 'extracted'
    if not ext.exists():
        raise FileNotFoundError(f"extracted/ not found in {run_dir}")

    docs = []
    for p in sorted(ext.glob('*.md')):
        raw = p.read_text(encoding='utf-8')
        fm, content = parse_frontmatter(raw)
        url = fm.get('source_url') or fm.get('source') or p.stem
        title = fm.get('title') or '(untitled)'
        if not content.strip():
            continue
        docs.append({
            'slug':  p.stem,
            'url':   url,
            'title': title,
            'text':  content,
        })
    return docs


def load_composite(run_dir: Path) -> dict:
    """Optional: read doc_understanding.csv for composite_weighted per URL."""
    path = run_dir / 'doc_understanding.csv'
    if not path.exists():
        return {}
    out = {}
    with open(path, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                out[row['url']] = float(row.get('composite_weighted') or 0)
            except (ValueError, TypeError):
                continue
    return out


# ----------------------------------------------------------------------
# Stage A — most similar
# ----------------------------------------------------------------------

def stage_a_state(topic: str, doc: dict, others: list[dict]) -> dict:
    return {
        'topic': topic,
        'document': {
            'url':   doc['url'],
            'title': doc['title'],
            'text':  trim(doc['text'], STAGE_A_DOC_CHARS),
        },
        'other_documents': [
            {
                'n':       i + 1,
                'title':   o['title'],
                'url':     o['url'],
                'preview': o['text'][:STAGE_A_PREVIEW].replace('\n', ' ').strip(),
            }
            for i, o in enumerate(others)
        ],
    }


def stage_a_question(n_others: int) -> Choice:
    criteria = {
        str(i + 1): f"the document identified by n={i + 1}"
        for i in range(n_others)
    }
    return Choice(
        instructions=(
            "Which document in `other_documents` is MOST SIMILAR to `document` "
            "in subject matter, content, and approach? Judge by overlap of "
            "actual content, not by topic alone. Return the `n` value of the "
            "single most similar document."
        ),
        criteria=criteria,
    )


# ----------------------------------------------------------------------
# Stage B — redundancy
# ----------------------------------------------------------------------

def stage_b_state(topic: str, doc: dict, reference: dict) -> dict:
    combined = len(doc['text']) + len(reference['text'])
    if combined <= MAX_STATE_CHARS:
        doc_text = doc['text']
        ref_text = reference['text']
    else:
        # Proportional trim
        budget = MAX_STATE_CHARS - 200
        ratio = len(doc['text']) / combined if combined else 0.5
        doc_budget = max(2000, int(budget * ratio))
        ref_budget = max(2000, budget - doc_budget)
        doc_text = trim(doc['text'], doc_budget)
        ref_text = trim(reference['text'], ref_budget)

    return {
        'topic': topic,
        'document': {
            'url':   doc['url'],
            'title': doc['title'],
            'text':  doc_text,
        },
        'reference': {
            'url':   reference['url'],
            'title': reference['title'],
            'text':  ref_text,
        },
    }


def stage_b_question() -> Score:
    return Score(
        instructions=(
            "How much of `document`'s substantive content is ALREADY covered "
            "by `reference`? Judge by actual information content, not phrasing. "
            "If a reader of `reference` would already know most of what "
            "`document` says, score high. If `document` contributes content "
            "that `reference` does not have, score low."
        ),
        criteria=[
            "essentially none; reference covers none of document's content",
            "very little overlap; document is almost entirely new",
            "some overlap, but most of document's content is new",
            "about half; document and reference share roughly half their content",
            "most of document's content is also in reference; a little is new",
            "document is fully covered by reference; essentially no new content",
        ],
    )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def short_url(url: str, width: int = 50) -> str:
    s = url.replace('https://', '').replace('http://', '').replace('www.', '')
    return (s[:width-1] + '…') if len(s) > width else s


def find_doc_by_url(docs: list[dict], url: str) -> dict | None:
    for d in docs:
        if d['url'] == url:
            return d
    return None


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-dir', required=True)
    ap.add_argument('--topic', default='supply chains')
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.is_dir():
        print(f"not a directory: {run_dir}")
        sys.exit(1)

    print(f"run dir : {run_dir}")
    print(f"topic   : {args.topic}")
    print(f"model   : {MODEL}")
    print()

    docs = load_documents(run_dir)
    if args.limit:
        docs = docs[:args.limit]
    composites = load_composite(run_dir)

    print(f"documents: {len(docs)}")
    if composites:
        print(f"composites loaded: {len(composites)}")
    print()

    client = TypeSafeClient()

    # ------------------------------------------------------------------
    # Stage A — most similar
    # ------------------------------------------------------------------
    print("Stage A — most similar sibling")
    most_similar: dict[str, str] = {}   # doc_url -> sibling_url

    for i, doc in enumerate(docs, 1):
        others = [d for d in docs if d['url'] != doc['url']]
        if not others:
            continue

        state = stage_a_state(args.topic, doc, others)
        q = stage_a_question(len(others))

        try:
            r = client.system_one(state=state, questions={'most_similar': q}, model=MODEL)
            answer = r.choices['most_similar'].choice
            idx = int(answer) - 1
            if 0 <= idx < len(others):
                most_similar[doc['url']] = others[idx]['url']
                print(f"  [{i:2d}/{len(docs)}] {short_url(doc['url'], 40):40s} → {short_url(others[idx]['url'], 40)}")
            else:
                print(f"  [{i:2d}/{len(docs)}] {short_url(doc['url'], 40):40s} → (invalid: {answer})")
        except Exception as e:
            print(f"  [{i:2d}/{len(docs)}] {short_url(doc['url'], 40):40s} FAILED: {e}")

    # ------------------------------------------------------------------
    # Stage B — redundancy
    # ------------------------------------------------------------------
    print()
    print("Stage B — redundancy against most-similar")
    results = []

    for i, doc in enumerate(docs, 1):
        ref_url = most_similar.get(doc['url'])
        if not ref_url:
            results.append({
                'url': doc['url'], 'title': doc['title'],
                'most_similar_url': None, 'redundancy': 0.0,
                'corpus_novelty': 1.0,
            })
            continue

        reference = find_doc_by_url(docs, ref_url)
        if not reference:
            continue

        state = stage_b_state(args.topic, doc, reference)
        try:
            r = client.system_one(
                state=state,
                questions={'redundancy': stage_b_question()},
                model=MODEL,
            )
            score = r.answers['redundancy'].score
        except Exception as e:
            print(f"  [{i:2d}/{len(docs)}] {short_url(doc['url'], 40):40s} FAILED: {e}")
            continue

        redundancy = score / 5.0
        novelty = 1.0 - redundancy
        results.append({
            'url':              doc['url'],
            'title':            doc['title'],
            'most_similar_url': ref_url,
            'redundancy':       round(redundancy, 3),
            'corpus_novelty':   round(novelty, 3),
        })
        print(f"  [{i:2d}/{len(docs)}] {short_url(doc['url'], 40):40s} "
              f"red={redundancy:.2f} novel={novelty:.2f}")

    # ------------------------------------------------------------------
    # Combine with composite_weighted
    # ------------------------------------------------------------------
    print()
    print("=" * 120)
    print(f"{'document':45s} {'composite':>9s} {'redundancy':>10s} {'novelty':>8s} {'final':>8s}")
    print("-" * 120)

    for r in results:
        comp = composites.get(r['url'], 0.0)
        r['composite_weighted'] = comp
        r['final_score'] = round(comp * r['corpus_novelty'], 3)

    for r in sorted(results, key=lambda x: x['final_score'], reverse=True):
        print(f"{short_url(r['url'], 45):45s} "
              f"{r['composite_weighted']:9.2f} "
              f"{r['redundancy']:10.2f} "
              f"{r['corpus_novelty']:8.2f} "
              f"{r['final_score']:8.2f}")

    # Write CSV
    out = run_dir / 'corpus_relationship.csv'
    fields = ['url', 'title', 'most_similar_url', 'redundancy',
              'corpus_novelty', 'composite_weighted', 'final_score']
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k) for k in fields})

    print()
    print(f"  wrote: {out}")


if __name__ == '__main__':
    main()