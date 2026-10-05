"""
Source selector — one LLM call that decides how each source should be used.

v2: max_tokens raised, duplicate-URL validation, standalone rule clarified,
    run() wrapper for the pipeline.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

try:
    from together import Together
except ImportError:
    print("pip install together")
    sys.exit(1)


MODEL = os.environ.get('TOGETHER_MODEL', 'zai-org/GLM-5.3-Flash')
TEMPERATURE = 0.2
MAX_TOKENS = 16384


INTENTS = {
    'beginner_guide': {
        'label': 'Beginner guide',
        'description': (
            "For a reader with no prior background on the topic. "
            "Prioritize clarity, plain-language definitions, and concrete examples. "
            "Avoid jargon, technical depth, and academic nuance. "
            "Favor accessible sources over authoritative ones when they explain better."
        ),
    },
    'research_overview': {
        'label': 'Research overview',
        'description': (
            "For a reader who wants comprehensive, well-sourced understanding. "
            "Prioritize authoritative sources, depth, and evidence. "
            "Include contrarian or dissenting perspectives as standalone deep-dives. "
            "Do not omit sources merely because they are complex."
        ),
    },
    'deep_dive': {
        'label': 'Deep dive',
        'description': (
            "For a reader who wants thorough treatment of mechanism and detail. "
            "Prioritize sources with high depth, specificity, and quantitative content. "
            "Emphasize how and why, not just what. "
            "Keep the article focused; omit low-depth or definitional sources."
        ),
    },
    'briefing': {
        'label': 'Briefing',
        'description': (
            "Short, decision-oriented summary. Key facts only, minimal context. "
            "Prioritize evidence, specific numbers, and practical implications. "
            "Omit definitional, historical, and taxonomy sources. "
            "Prefer one strong source per topic over many redundant ones."
        ),
    },
    'comparison': {
        'label': 'Comparison',
        'description': (
            "Present multiple perspectives on the same topic side by side. "
            "Prioritize sources that take distinct or opposing positions. "
            "Include contrarian and minority-view sources prominently. "
            "Omit sources that merely restate the consensus."
        ),
    },
}


def load_manifests(run_dir: Path) -> list[dict]:
    path = run_dir / 'manifests.json'
    if not path.exists():
        raise FileNotFoundError(f"manifests.json not found in {run_dir}")
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def short_url(url: str, width: int = 60) -> str:
    s = url.replace('https://', '').replace('http://', '').replace('www.', '')
    return (s[:width-1] + '…') if len(s) > width else s


def build_system_prompt() -> str:
    return """You are a source selector for a research-synthesis pipeline.

You receive:
  - a list of source documents, each with a rich manifest
  - a target topic
  - a user intent

Your task is to produce a SECTION PLAN for the article.

For each source, decide one of five usage modes:

  primary_synthesis — backbone of a section. Its content gets merged in.
  supporting        — contributes specific atoms to a section.
  contextual        — background only. One or two atoms.
  standalone        — its own section. Used for distinctive/contrarian sources.
  omit              — not included.

Rules:
  1. Every source MUST be assigned exactly one usage mode.
  2. Organize primary/supporting sources into SECTIONS with clear titles.
     Do not exceed 6 sections.
  3. A section with a single source and a descriptive title should be
     `standalone`, not `primary`.
  4. Base decisions on the manifests, not source name or length.
  5. User intent overrides defaults.
  6. Be decisive. Do not include sources "just in case."

Output format — return ONLY valid JSON:

{
  "intent": "<intent>",
  "corpus_notes": "<one or two sentences>",
  "sections": [
    {
      "title": "Section title",
      "primary": ["url1", "url2"],
      "supporting": ["url3"],
      "rationale": "why"
    },
    {
      "title": "Standalone title",
      "standalone": "url",
      "rationale": "why"
    }
  ],
  "contextual": [{"url": "url", "reason": "why"}],
  "omit": [{"url": "url", "reason": "why"}]
}

URLs must be exactly as given in the input.
"""


def format_manifest_for_prompt(i: int, m: dict) -> str:
    identity = m.get('identity', {})
    contribution = m.get('contribution', {})
    forms = m.get('content_forms', {})
    quality = m.get('quality', {})

    return "\n".join([
        f"### S{i+1}: {m['url']}",
        f"title: {m.get('title', '(untitled)')}",
        f"source_type: {identity.get('source_type', '?')}",
        f"role: {contribution.get('role', '?')}",
        f"angle: {identity.get('angle', '?')}",
        f"audience_level: {identity.get('audience_level', '?')}",
        f"reader_intent: {identity.get('reader_intent', '?')}",
        f"temporal_focus: {identity.get('temporal_focus', '?')}",
        f"evidence_type: {identity.get('evidence_type', '?')}",
        f"confidence_source: {identity.get('confidence_source', '?')}",
        f"primary_concern: {contribution.get('primary_concern', '?')}",
        (
            f"quality: authority={quality.get('authority', '?')} "
            f"specificity={quality.get('specificity', '?')} "
            f"depth={quality.get('depth', '?')} "
            f"narrative={quality.get('narrative', '?')}"
        ),
        (
            f"content_forms: definition={forms.get('definition', '?')} "
            f"mechanism={forms.get('mechanism', '?')} "
            f"quantitative={forms.get('quantitative', '?')} "
            f"example={forms.get('example', '?')} "
            f"framework={forms.get('framework', '?')} "
            f"argument={forms.get('argument', '?')}"
        ),
        (
            f"practical_orientation: {contribution.get('practical_orientation', '?')} | "
            f"has_named_framework: {contribution.get('has_named_framework', '?')} | "
            f"has_contrarian_view: {contribution.get('has_contrarian_view', '?')}"
        ),
        "",
    ])


def build_user_prompt(topic: str, intent: str, manifests: list[dict]) -> str:
    intent_meta = INTENTS[intent]
    lines = [
        f"# Topic\n\n{topic}\n",
        f"# Intent\n\n{intent_meta['label']}: {intent_meta['description']}\n",
        f"# Sources ({len(manifests)})\n",
    ]
    for i, m in enumerate(manifests):
        lines.append(format_manifest_for_prompt(i, m))

    lines.append(
        f"# Task\n\n"
        f"Produce a section plan for a {intent_meta['label'].lower()} article "
        f"about \"{topic}\" using these {len(manifests)} sources. "
        f"Assign every source a usage mode. Return only JSON."
    )
    return "\n".join(lines)


def call_llm(system: str, user: str) -> str:
    client = Together(timeout=600.0, max_retries=3)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {'role': 'system', 'content': system},
            {'role': 'user',   'content': user},
        ],
        temperature=TEMPERATURE,
        reasoning_effort='low',
        max_tokens=MAX_TOKENS,
    )
    choice = response.choices[0] if response.choices else None
    message = choice.message if choice else None
    content = getattr(message, 'content', None) if message else None
    if (not isinstance(content, str) or not content.strip()) and message is not None:
        content = (
            getattr(message, 'reasoning_content', None)
            or getattr(message, 'reasoning', None)
        )
    if not isinstance(content, str) or not content.strip():
        finish = choice.finish_reason if choice else 'no choices'
        raise RuntimeError(f"{MODEL} returned no content (finish_reason={finish!r})")
    return content


def extract_json(text: str) -> dict:
    fence = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1 or end <= start:
            raise ValueError("no JSON object found in response")
        text = text[start:end+1]
    return json.loads(text)


def validate_plan(plan: dict, manifests: list[dict]) -> list[str]:
    warnings = []
    all_urls = {m['url'] for m in manifests}

    seen = {}   # url -> list of modes
    for section in plan.get('sections', []):
        for url in section.get('primary', []):
            seen.setdefault(url, []).append('primary')
        for url in section.get('supporting', []):
            seen.setdefault(url, []).append('supporting')
        if 'standalone' in section:
            seen.setdefault(section['standalone'], []).append('standalone')
    for entry in plan.get('contextual', []):
        seen.setdefault(entry.get('url'), []).append('contextual')
    for entry in plan.get('omit', []):
        seen.setdefault(entry.get('url'), []).append('omit')

    duplicates = {u: modes for u, modes in seen.items() if len(modes) > 1}
    if duplicates:
        for url, modes in duplicates.items():
            warnings.append(f"URL assigned multiple modes: {url} → {modes}")

    unknown = set(seen.keys()) - all_urls
    missing = all_urls - set(seen.keys())
    if unknown:
        warnings.append(f"plan references unknown URLs: {sorted(unknown)}")
    if missing:
        warnings.append(f"plan does not account for: {sorted(missing)}")

    return warnings


def print_plan(plan: dict, manifests: list[dict]) -> None:
    url_to_title = {m['url']: m.get('title', '') for m in manifests}

    print(f"intent: {plan.get('intent', '?')}")
    if plan.get('corpus_notes'):
        print(f"notes:  {plan['corpus_notes']}")
    print()

    for i, section in enumerate(plan.get('sections', []), 1):
        title = section.get('title', f'Section {i}')
        print(f"[{i}] {title}")
        if 'standalone' in section:
            print(f"    STANDALONE: {short_url(section['standalone'], 55)}")
        else:
            for url in section.get('primary', []):
                print(f"    primary   : {short_url(url, 55)}")
            for url in section.get('supporting', []):
                print(f"    supporting: {short_url(url, 55)}")
        if section.get('rationale'):
            print(f"    → {section['rationale']}")
        print()

    if plan.get('contextual'):
        print("Contextual:")
        for entry in plan['contextual']:
            print(f"  {short_url(entry.get('url', ''), 55)}")
            print(f"    → {entry.get('reason', '')}")
        print()

    if plan.get('omit'):
        print("Omitted:")
        for entry in plan['omit']:
            print(f"  {short_url(entry.get('url', ''), 55)}")
            print(f"    → {entry.get('reason', '')}")
        print()


def run(run_dir: Path | str,
        topic: str,
        intent: str,
        verbose: bool = True) -> dict:
    """Programmatic entry point. Returns the parsed plan."""
    run_dir = Path(run_dir)
    manifests = load_manifests(run_dir)

    if intent not in INTENTS:
        raise ValueError(f"unknown intent: {intent}")

    if verbose:
        print(f"selector: topic={topic!r} intent={intent} sources={len(manifests)}")

    system = build_system_prompt()
    user = build_user_prompt(topic, intent, manifests)

    raw = call_llm(system, user)
    plan = extract_json(raw)
    plan['intent'] = intent

    warnings = validate_plan(plan, manifests)
    if warnings and verbose:
        for w in warnings:
            print(f"  [warn] {w}")

    out = run_dir / 'selection_plan.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)

    if verbose:
        print_plan(plan, manifests)
        print(f"  wrote: {out}")

    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-dir', required=True)
    ap.add_argument('--topic', default='the topic')
    ap.add_argument('--intent', required=True, choices=list(INTENTS.keys()))
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.is_dir():
        print(f"not a directory: {run_dir}")
        sys.exit(1)

    if args.dry_run:
        manifests = load_manifests(run_dir)
        print(build_system_prompt())
        print("\n=== USER PROMPT (first 3000 chars) ===")
        print(build_user_prompt(args.topic, args.intent, manifests)[:3000])
        return

    run(run_dir, args.topic, args.intent, verbose=True)


if __name__ == '__main__':
    main()