"""
Step 1 (v4): Document manifest via JEV.

Richer profile. JEV-only. Two-level source ontology, audience, intent,
temporal focus, practical orientation, evidence type.

Reads:  <run_dir>/extracted/*.md
Writes:
  <run_dir>/doc_manifest.csv
  <run_dir>/manifests.json

Usage:
  python doc_manifest.py --run-dir <path> --topic "supply chains"
  python doc_manifest.py --run-dir <path> --topic "psychology" --subtopics "biases,heuristics,emotion"

Env:
  TYPESAFE_API_KEY   required
  TYPESAFE_MODEL     default jev-latest
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

try:
    from typesafe_sdk import Choice, Noul, Score, TypeSafeClient
except ImportError:
    print("pip install typesafe-sdk")
    sys.exit(1)


MODEL = os.environ.get('TYPESAFE_MODEL', 'jev-latest')
MAX_DOC_CHARS = 80_000

CAPABILITIES = [
    # Understanding
    "has_theoretical_framework",
    "explains_mechanisms",
    "has_mathematical_derivation",
    # Evidence
    "has_empirical_evidence",
    "has_experimental_results",
    "has_datasets",
    # Methods and practice
    "has_implementation_steps",
    "has_experimental_protocol",
    "has_computational_method",
    "has_executable_code",
    # Scientific investigation
    "has_comparative_analysis",
    "has_critical_analysis",
    "identifies_research_gaps"
]

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


def slugify(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')


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
        docs.append({'slug': p.stem, 'url': url, 'title': title, 'text': content})
    return docs


def build_questions(topic: str, subtopics: list[str]) -> dict:
    q = {}

    # --- Classification (Choice) ---
    q['source_type'] = Choice(
        instructions=f"What kind of source is `document` on the topic \"{topic}\"?",
        criteria={
            'academic_paper': 'Peer-reviewed research paper, journal article, or scholarly publication.',
            'academic_book': 'Book, textbook, or book chapter from an academic press.',
            'university': 'University department, faculty page, or course page.',
            'government': 'Government agency, regulator, or public body.',
            'professional_body': 'Professional association, standards body, or industry federation.',
            'reference': 'Encyclopedia, dictionary, or general reference work.',
            'educational': 'Course, tutorial, or open-learning resource intended to teach.',
            'practitioner': 'Industry blog, consulting page, or clinical practice writing.',
            'popular_media': 'News outlet, magazine, or consumer-facing publication.',
            'personal': 'Individual blog, Medium post, LinkedIn article, or personal essay.',
        },
    )
    q['contribution_role'] = Choice(
        instructions=f"What is the primary contribution `document` makes to understanding \"{topic}\"?",
        criteria={
            'definition':  'Explains what the topic fundamentally is.',
            'mechanism':   'Explains how it works — process, method, or underlying principle.',
            'example':     'Provides concrete cases, use cases, or applications.',
            'evidence':    'Provides numbers, data, statistics, or measurable outcomes.',
            'perspective': 'Offers a distinctive viewpoint, argument, or interpretation.',
            'taxonomy':    'Organizes the topic into categories, components, or named frameworks.',
            'history':     'Traces origin, development, or historical context.',
        },
    )
    q['angle'] = Choice(
        instructions="What is the writer's angle — who is this written for and from what stance?",
        criteria={
            'academic':      'Written for researchers or students in an academic register.',
            'practitioner':  'Written for operators, managers, or professionals doing the work.',
            'institutional': 'Written by an institution for a general audience.',
            'consumer':      'Written for end buyers or the general public.',
            'critical':      'Takes a critical, skeptical, or contrarian stance.',
            'neutral':       'No discernible angle; purely informational.',
        },
    )
    q['primary_concern'] = Choice(
        instructions="What is the document's primary concern or focus?",
        criteria={
            'definition': 'What it is.',
            'mechanics':  'How it works.',
            'strategy':   'How to make decisions about it.',
            'risk':       'What can go wrong.',
            'ethics':     'Social, environmental, or human concerns.',
            'economics':  'Financial or business impact.',
            'careers':    'Professional paths or workforce.',
        },
    )
    q['confidence_source'] = Choice(
        instructions="Where does the document's confidence or evidence come from?",
        criteria={
            'primary_research':  'Original studies, experiments, or first-hand data.',
            'expert_opinion':    'Named experts giving their judgment.',
            'industry_data':     'Statistics or findings from industry reports.',
            'general_knowledge': 'No attribution; common knowledge.',
            'mixed':             'Combination of the above.',
        },
    )
    q['audience_level'] = Choice(
        instructions="What level of reader is `document` written for?",
        criteria={
            'beginner':     'Written for a reader with no background in the topic.',
            'general':      'Written for an interested lay reader.',
            'informed':     'Written for someone with working familiarity.',
            'expert':       'Written for specialists or practitioners in the field.',
        },
    )
    q['reader_intent'] = Choice(
        instructions="What is `document` trying to do for its reader?",
        criteria={
            'inform':    'Convey facts or explanations.',
            'instruct':  'Teach a skill or procedure.',
            'persuade':  'Change the reader\'s opinion or behaviour.',
            'warn':      'Alert the reader to a risk or danger.',
            'entertain': 'Engage or inspire the reader.',
        },
    )
    q['temporal_focus'] = Choice(
        instructions="What time orientation does `document` primarily have?",
        criteria={
            'historical':    'About how things developed over time.',
            'current':       'About the present state or recent events.',
            'forward':       'About future trends, predictions, or emerging issues.',
            'timeless':      'About principles that are not tied to a particular moment.',
        },
    )
    q['evidence_type'] = Choice(
        instructions="What kind of evidence, if any, does `document` rely on?",
        criteria={
            'primary_research': 'Original experiments, surveys, or first-hand data.',
            'secondary_cited':  'Cites other studies, papers, or named sources.',
            'industry_data':    'Statistics from industry reports or market research.',
            'anecdotal':        'Examples, stories, or personal experience.',
            'mixed':            'A combination of the above.',
            'no_evidence':      'Assertions with no evidence or attribution.',
        },
    )

    # --- Scores ---
    form_anchors = ["essentially none", "very little", "some; present but secondary", "roughly half", "most; a dominant form", "essentially all"]
    q['form_definition'] = Score(instructions="What fraction explains what things are, names concepts?", criteria=form_anchors)
    q['form_mechanism'] = Score(instructions="What fraction explains how things work — processes, methods?", criteria=form_anchors)
    q['form_quantitative'] = Score(instructions="What fraction consists of numbers, percentages, dates?", criteria=form_anchors)
    q['form_example'] = Score(instructions="What fraction consists of concrete examples or cases?", criteria=form_anchors)
    q['form_framework'] = Score(instructions="What fraction presents named frameworks or structured lists?", criteria=form_anchors)
    q['form_argument'] = Score(instructions="What fraction consists of arguments or positions?", criteria=form_anchors)
    
    q['practical_orientation'] = Score(
        instructions="How practical or applicable is `document`?",
        criteria=["purely abstract", "mostly theoretical", "mixed", "practical orientation", "highly actionable", "purely operational"],
    )
    q['authority'] = Score(
        instructions=f"How much authority does `document` carry on \"{topic}\"?",
        criteria=["no authority", "low", "moderate", "solid", "high", "definitive"],
    )
    q['specificity'] = Score(
        instructions="How dense is `document` with concrete specifics — numbers, dates, names?",
        criteria=["entirely general", "mostly general", "some specifics", "roughly half", "most paragraphs", "dense with specifics"],
    )
    q['depth'] = Score(
        instructions="How deeply does `document` explain — does it go beyond *what* to *how* and *why*?",
        criteria=["purely descriptive", "states facts", "occasionally explains", "balances description", "consistently explains", "deep conceptual"],
    )
    q['narrative'] = Score(
        instructions="How strong is `document` as narrative or storytelling?",
        criteria=["no narrative", "mostly flat", "some narrative elements", "reads as an article", "strong narrative", "excellent storytelling"],
    )

    # --- STEM Capabilities (Noul) ---
    capability_prompts = {
        "has_theoretical_framework": "Does this document contain a theoretical framework, fundamental principles, or abstract concepts?",
        "explains_mechanisms": "Does this document explain underlying mechanisms, processes, or how something works?",
        "has_mathematical_derivation": "Does this document contain mathematical equations, proofs, or derivations?",
        "has_empirical_evidence": "Does this document contain empirical evidence, data, or observations?",
        "has_experimental_results": "Does this document report specific experimental results?",
        "has_datasets": "Does this document describe or provide datasets?",
        "has_implementation_steps": "Does this document provide step-by-step instructions or how-to guides?",
        "has_experimental_protocol": "Does this document contain a detailed experimental protocol or methodology?",
        "has_computational_method": "Does this document describe computational methods or simulations?",
        "has_executable_code": "Does this document contain executable code (e.g., Python, R, C++)?",
        "has_comparative_analysis": "Does this document compare different methods, approaches, or models?",
        "has_critical_analysis": "Does this document critically evaluate limitations, trade-offs, or failures?",
        "identifies_research_gaps": "Does this document identify gaps, open problems, or future research directions?"
    }
    for cap in CAPABILITIES:
        q[cap] = Noul(instructions=capability_prompts[cap])

    # --- Topic Coverage ---
    for sub in subtopics:
        key = f"topic_{slugify(sub)}"
        q[key] = Score(
            instructions=f"How much of `document` is specifically about \"{sub}\"?",
            criteria=[f"not at all about {sub}", "passing mention", "some discussion", "substantial portion", f"mostly about {sub}", f"entirely about {sub}"],
        )

    return q


def evaluate_doc(client, topic: str, doc: dict, subtopics: list[str]) -> dict:
    state = {
        'topic': topic,
        'document': {
            'url':   doc['url'],
            'title': doc['title'],
            'text':  doc['text'],
        },
    }
    
    all_questions = build_questions(topic, subtopics)
    out = {'url': doc['url'], 'title': doc['title']}

    # Split questions to avoid JEV's max question limit
    choice_score_keys = ['source_type', 'contribution_role', 'angle', 'primary_concern', 
                         'confidence_source', 'audience_level', 'reader_intent', 
                         'temporal_focus', 'evidence_type', 'practical_orientation',
                         'form_definition', 'form_mechanism', 'form_quantitative',
                         'form_example', 'form_framework', 'form_argument',
                         'authority', 'specificity', 'depth', 'narrative']
                         
    q1 = {k: v for k, v in all_questions.items() if k in choice_score_keys or k.startswith('topic_')}
    q2 = {k: v for k, v in all_questions.items() if k not in q1}

    # --- Call 1: Classification and Scores ---
    r1 = client.system_one(state=state, questions=q1, model=MODEL)
    
    # Dynamically extract whatever JEV actually returned (no hardcoded lists!)
    for key in q1.keys():
        if key in r1.choices:
            out[key] = r1.choices[key].choice
            out[f'{key}_conf'] = r1.choices[key].confidence
        elif key in r1.answers:
            out[key] = r1.answers[key].score
            out[f'{key}_conf'] = r1.answers[key].confidence

    # --- Call 2: STEM Capabilities ---
    r2 = client.system_one(state=state, questions=q2, model=MODEL)
    for key in q2.keys():
        if key in r2.nouls:
            out[key] = r2.nouls[key].noul
            out[f'{key}_conf'] = getattr(r2.nouls[key], 'confidence', None)

    return out


def to_structured_manifest(row: dict, subtopics: list[str]) -> dict:
    capabilities_dict = {cap: round(row[cap], 3) for cap in CAPABILITIES if cap in row}
    
    return {
        'url':   row.get('url'),
        'title': row.get('title'),
        'identity': {
            'source_type':       row.get('source_type', 'unknown'),
            'angle':             row.get('angle', 'neutral'),
            'audience_level':    row.get('audience_level', 'general'),
            'reader_intent':     row.get('reader_intent', 'inform'),
            'temporal_focus':    row.get('temporal_focus', 'timeless'),
            'confidence_source': row.get('confidence_source', 'general_knowledge'),
            'evidence_type':     row.get('evidence_type', 'no_evidence'),
        },
        'contribution': {
            'role':                row.get('contribution_role', 'definition'),
            'primary_concern':     row.get('primary_concern', 'definition'),
            'practical_orientation': row.get('practical_orientation', 0.0),
        },
        'capabilities': capabilities_dict,
        'content_forms': {
            'definition':   row.get('form_definition', 0),
            'mechanism':    row.get('form_mechanism', 0),
            'quantitative': row.get('form_quantitative', 0),
            'example':      row.get('form_example', 0),
            'framework':    row.get('form_framework', 0),
            'argument':     row.get('form_argument', 0),
        },
        'quality': {
            'authority':   row.get('authority', 0),
            'specificity': row.get('specificity', 0),
            'depth':       row.get('depth', 0),
            'narrative':   row.get('narrative', 0),
        },
        'topic_coverage': {
            sub: row.get(f'topic_{slugify(sub)}', 0) for sub in subtopics
        } if subtopics else {},
    }

def short_url(url: str, width: int = 40) -> str:
    s = url.replace('https://', '').replace('http://', '').replace('www.', '')
    return (s[:width-1] + '…') if len(s) > width else s

def run(run_dir: Path | str,
        topic: str,
        subtopics: list[str] | None = None,
        verbose: bool = True) -> list[dict]:
    """Programmatic entry point. Returns the list of manifest rows."""
    run_dir = Path(run_dir)
    subtopics = subtopics or []

    docs = load_documents(run_dir)
    if verbose:
        print(f"manifest: topic={topic!r} docs={len(docs)}")

    client = TypeSafeClient()
    rows = []

    for i, d in enumerate(docs, 1):
        if verbose:
            print(f"  [{i:2d}/{len(docs)}] {short_url(d['url'], 50):50s}", end='', flush=True)
        try:
            row = evaluate_doc(client, topic, d, subtopics)
        except Exception as e:
            if verbose:
                print(f" FAILED: {e}")
            continue
        rows.append(row)
        if verbose:
            print(
            f" {row.get('source_type', '?'):17s}"
            f" {row.get('contribution_role', '?'):11s}"
            f" spec={row.get('specificity', 0.0):.1f}"
            f" dep={row.get('depth', 0.0):.1f}"
        )

    if not rows:
        raise RuntimeError("doc_manifest produced no rows")

    out_csv = run_dir / 'doc_manifest.csv'
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)

    out_json = run_dir / 'manifests.json'
    manifests = [to_structured_manifest(r, subtopics) for r in rows]
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(manifests, f, indent=2, ensure_ascii=False)

    if verbose:
        print(f"  wrote: {out_csv}")
        print(f"  wrote: {out_json}")

    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-dir', required=True)
    ap.add_argument('--topic', default='supply chains')
    ap.add_argument('--subtopics', default='')
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.is_dir():
        print(f"not a directory: {run_dir}")
        sys.exit(1)

    subtopics = [s.strip() for s in args.subtopics.split(',') if s.strip()]

    print(f"run dir   : {run_dir}")
    print(f"topic     : {args.topic}")
    if subtopics:
        print(f"subtopics : {', '.join(subtopics)}")
    print(f"model     : {MODEL}")
    print()

    docs = load_documents(run_dir)
    if args.limit:
        docs = docs[:args.limit]

    print(f"documents : {len(docs)}")
    for d in docs:
        print(f"  {d['url'][:75]:75s}  {len(d['text']):>7,} chars")

    if args.dry_run:
        return

    client = TypeSafeClient()
    rows = []

    print()
    for i, d in enumerate(docs, 1):
        print(f"  [{i:2d}/{len(docs)}] {short_url(d['url'], 50):50s}", end='', flush=True)
        try:
            row = evaluate_doc(client, args.topic, d, subtopics)
        except Exception as e:
            print(f" FAILED: {e}")
            continue
        rows.append(row)
        print(
            f" {row['source_type']:17s}"
            f" {row['contribution_role']:11s}"
            f" aud={row['audience_level']:9s}"
            f" spec={row['specificity']:.1f}"
            f" dep={row['depth']:.1f}"
            f" evi={row['evidence_type']:16s}"
            f" ctr={row['has_contrarian_view']:.2f}"
        )

    if not rows:
        print("\nno results")
        return

    # CSV
    out_csv = run_dir / 'doc_manifest.csv'
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # Structured JSON
    out_json = run_dir / 'manifests.json'
    manifests = [to_structured_manifest(r, subtopics) for r in rows]
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(manifests, f, indent=2, ensure_ascii=False)

    # Summary table
    def quality(r):
        return r['authority'] + r['specificity'] + r['depth']

    print()
    print("=" * 140)
    print(f"{'document':40s} {'source_type':17s} {'role':11s} "
          f"{'aud':9s} {'auth':>5s} {'spec':>5s} {'dep':>5s} "
          f"{'prac':>5s} {'evi':17s}")
    print("-" * 140)
    for r in sorted(rows, key=quality, reverse=True):
        print(
            f"{short_url(r['url'], 40):40s} "
            f"{r['source_type']:17s} "
            f"{r['contribution_role']:11s} "
            f"{r['audience_level']:9s} "
            f"{r['authority']:5.1f} "
            f"{r['specificity']:5.1f} "
            f"{r['depth']:5.1f} "
            f"{r['practical_orientation']:5.1f} "
            f"{r['evidence_type']:17s}"
        )

    print()
    print(f"  csv       : {out_csv}")
    print(f"  manifests : {out_json}")


if __name__ == '__main__':
    main()