"""
Step 1 (v2): Document understanding via JEV, with corpus-relative novelty.

For each document in a run directory, one JEV call asking seven questions:
  source_type        (Choice)
  contribution_role  (Choice)
  authority          (Score 0-5)
  specificity        (Score 0-5)
  depth              (Score 0-5)
  narrative          (Score 0-5)
  novelty            (Score 0-5)  <- corpus-relative

The novelty question is passed the other documents' titles + previews
so JEV can judge what this document adds that the corpus doesn't have.

Reads:  <run_dir>/extracted/*.md
Writes: <run_dir>/doc_understanding.csv

Usage:
  python doc_understanding.py --run-dir C:\\path\\to\\run --topic "supply chains"
  python doc_understanding.py --run-dir ... --dry-run

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
MAX_DOC_CHARS = 100_000       # JEV state + longest question <= 32k tokens
CORPUS_PREVIEW_CHARS = 150    # per-other-doc preview


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
        content = trim(content, MAX_DOC_CHARS)

        if not content:
            continue

        docs.append({
            'slug':  p.stem,
            'url':   url,
            'title': title,
            'text':  content,
        })
    return docs


def build_questions(topic: str) -> dict:
    return {
        'source_type': Choice(
            instructions=(
                f"What kind of source is `document` on the topic \"{topic}\"? "
                "Base this on the URL pattern, the publication venue, and the "
                "register of the writing. Choose the single best match."
            ),
            criteria={
                'expert_interview': 'Interview or Q&A with a named expert, practitioner, or academic in the field.',
                'academic':         'Peer-reviewed paper, academic article, or scholarly publication.',
                'encyclopedia':     'Reference article (Wikipedia-style), broad encyclopedic coverage.',
                'corporate':        'Company blog, marketing page, vendor glossary, or branded explainer.',
                'blog':             'Individual or small-team blog, personal essay, or opinion piece.',
                'news':             'News article, journalism, or current-events reporting.',
                'standards_body':   'Industry association, standards organization, or regulatory body.',
                'other':            'None of the above.',
            },
        ),
        'contribution_role': Choice(
            instructions=(
                f"Given the topic \"{topic}\", what is the primary contribution "
                f"`document` makes to understanding it? Choose the single most "
                f"prominent role."
            ),
            criteria={
                'definition':  'Explains what the topic fundamentally is.',
                'mechanism':   'Explains how it works — the process, method, or underlying principle.',
                'example':     'Provides concrete cases, use cases, or applications.',
                'evidence':    'Provides numbers, data, statistics, or measurable outcomes.',
                'perspective': 'Offers a distinctive viewpoint, argument, or interpretation.',
                'taxonomy':    'Organizes the topic into categories, components, or named frameworks.',
                'history':     'Traces origin, development, or historical context.',
            },
        ),
        'authority': Score(
            instructions=(
                f"How much authority does `document` carry on the topic \"{topic}\"? "
                "Consider the author's credentials, the publication venue, whether "
                "claims are attributed, and whether it is a primary or secondary source."
            ),
            criteria=[
                "no authority; anonymous or clearly unqualified",
                "low; personal opinion without credentials",
                "moderate; informed commentary but not expert",
                "solid; named expert or established institution",
                "high; primary source or recognized authority",
                "definitive; the canonical reference on this topic",
            ],
        ),
        'specificity': Score(
            instructions=(
                "How dense is `document` with concrete specifics — numbers, dates, "
                "named entities, quoted speech, precise values? Score high if most "
                "claims are anchored. Score low if the writing is general and "
                "definitional."
            ),
            criteria=[
                "entirely general prose; no specifics at all",
                "mostly general with one or two concrete details",
                "some specifics, but they are incidental",
                "roughly half the content is concrete and specific",
                "most paragraphs contain a number, date, or named entity",
                "dense with specifics; nearly every claim is anchored",
            ],
        ),
        'depth': Score(
            instructions=(
                "How deeply does `document` explain its subject? Does it go beyond "
                "*what* to explain *how* and *why*? Score high if it explains "
                "mechanism, causation, or tradeoffs. Score low if it only describes "
                "or lists."
            ),
            criteria=[
                "purely descriptive; no explanation of how or why",
                "states facts without explaining underlying causes",
                "occasionally explains mechanism but mostly describes",
                "balances description with explanation of how things work",
                "consistently explains mechanisms and causal relationships",
                "deep technical or conceptual explanation throughout",
            ],
        ),
        'narrative': Score(
            instructions=(
                "How strong is `document` as narrative? Does it tell a story, use "
                "concrete examples, draw the reader through a sequence of ideas? "
                "Score high for compelling writing with cases or arcs. Score low "
                "for dry reference material."
            ),
            criteria=[
                "no narrative; purely factual or reference material",
                "mostly flat; occasional examples but no story",
                "some narrative elements, but not a driving feature",
                "reads as an article with a shape and progression",
                "strong narrative; concrete cases or examples drive the piece",
                "excellent storytelling; vivid, specific, memorable throughout",
            ],
        ),
        'novelty': Score(
            instructions=(
                f"How much does `document` contribute to understanding \"{topic}\" "
                "that is NOT already covered by the other documents listed in "
                "`corpus`?\n\n"
                "Compare `document` against the corpus previews. Score high if "
                "`document` says something the corpus does not — a distinct fact, "
                "argument, example, framework, or perspective. Score low if it "
                "mostly restates what other documents already say.\n\n"
                "Judge by actual content, not by source type or writing quality. "
                "A well-written document that repeats the corpus has low novelty. "
                "A plain document that adds a unique fact has high novelty."
            ),
            criteria=[
                "fully redundant; adds nothing the corpus does not already cover",
                "mostly redundant; one small unique detail at most",
                "some unique content, but mostly overlapping",
                "roughly half of the content is distinct from the corpus",
                "mostly unique; the corpus does not cover most of this",
                "highly novel; introduces substantial content new to the corpus",
            ],
        ),
    }


def make_corpus_previews(docs: list[dict], exclude_slug: str) -> list[dict]:
    """Build a compact list of the other docs for the novelty state."""
    out = []
    for d in docs:
        if d['slug'] == exclude_slug:
            continue
        preview = d['text'][:CORPUS_PREVIEW_CHARS].replace('\n', ' ').strip()
        out.append({
            'url':     d['url'],
            'title':   d['title'],
            'preview': preview,
        })
    return out


def evaluate_doc(client, topic: str, doc: dict, docs: list[dict]) -> dict:
    state = {
        'topic': topic,
        'corpus': make_corpus_previews(docs, exclude_slug=doc['slug']),
        'document': {
            'url':   doc['url'],
            'title': doc['title'],
            'text':  doc['text'],
        },
    }

    r = client.system_one(
        state=state,
        questions=build_questions(topic),
        model=MODEL,
    )

    return {
        'source_type':  r.choices['source_type'].choice,
        'type_conf':    r.choices['source_type'].confidence,
        'role':         r.choices['contribution_role'].choice,
        'role_conf':    r.choices['contribution_role'].confidence,
        'authority':    r.answers['authority'].score,
        'auth_conf':    r.answers['authority'].confidence,
        'specificity':  r.answers['specificity'].score,
        'spec_conf':    r.answers['specificity'].confidence,
        'depth':        r.answers['depth'].score,
        'depth_conf':   r.answers['depth'].confidence,
        'narrative':    r.answers['narrative'].score,
        'narr_conf':    r.answers['narrative'].confidence,
        'novelty':      r.answers['novelty'].score,
        'nov_conf':     r.answers['novelty'].confidence,
    }


def short_url(url: str, width: int = 55) -> str:
    s = url.replace('https://', '').replace('http://', '').replace('www.', '')
    return (s[:width-1] + '…') if len(s) > width else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-dir', required=True)
    ap.add_argument('--topic', default='supply chains')
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--dry-run', action='store_true')
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

    print(f"documents: {len(docs)}")
    for d in docs:
        print(f"  {d['url'][:75]:75s}  {len(d['text']):>7,} chars")

    if args.dry_run:
        return

    client = TypeSafeClient()
    results = []

    print()
    for i, d in enumerate(docs, 1):
        print(f"  [{i:2d}/{len(docs)}] {d['url'][:60]:60s}", end='', flush=True)
        try:
            r = evaluate_doc(client, args.topic, d, docs)
        except Exception as e:
            print(f" FAILED: {e}")
            continue

        r['url']   = d['url']
        r['title'] = d['title']
        results.append(r)
        print(
            f" {r['source_type']:16s}"
            f" {r['role']:12s}"
            f" auth={r['authority']:.1f}"
            f" spec={r['specificity']:.1f}"
            f" dep={r['depth']:.1f}"
            f" nar={r['narrative']:.1f}"
            f" nov={r['novelty']:.1f}"
        )

    if not results:
        print("\nno results")
        return

    # Two composites for comparison
    def composite_sum(r):
        return (r['authority'] + r['specificity']
                + r['depth'] + r['narrative'] + r['novelty'])

    def composite_weighted(r):
        # Intent-agnostic starting weights. Adjust per intent later.
        return (0.25 * r['authority']
                + 0.20 * r['specificity']
                + 0.15 * r['depth']
                + 0.10 * r['narrative']
                + 0.30 * r['novelty'])

    print()
    print("=" * 130)
    print(f"{'document':50s} {'source_type':16s} {'role':12s} "
          f"{'auth':>5s} {'spec':>5s} {'dep':>5s} {'nar':>5s} {'nov':>5s} "
          f"{'sum':>5s} {'wt':>5s}")
    print("-" * 130)

    for r in sorted(results, key=composite_weighted, reverse=True):
        print(
            f"{short_url(r['url'], 50):50s} "
            f"{r['source_type']:16s} "
            f"{r['role']:12s} "
            f"{r['authority']:5.1f} "
            f"{r['specificity']:5.1f} "
            f"{r['depth']:5.1f} "
            f"{r['narrative']:5.1f} "
            f"{r['novelty']:5.1f} "
            f"{composite_sum(r):5.1f} "
            f"{composite_weighted(r):5.2f}"
        )

    # Write CSV
    out = run_dir / 'doc_understanding.csv'
    fields = ['url', 'title',
              'source_type', 'type_conf', 'role', 'role_conf',
              'authority', 'auth_conf',
              'specificity', 'spec_conf',
              'depth', 'depth_conf',
              'narrative', 'narr_conf',
              'novelty', 'nov_conf',
              'composite_sum', 'composite_weighted']
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            row = {k: r.get(k) for k in fields if k in r}
            row['composite_sum'] = round(composite_sum(r), 3)
            row['composite_weighted'] = round(composite_weighted(r), 3)
            w.writerow(row)

    print()
    print(f"  wrote: {out}")


if __name__ == '__main__':
    main()