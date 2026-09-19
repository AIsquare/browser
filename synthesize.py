"""
Synthesize one GPS article from selected atoms.

Reads:  selected_atoms + atoms
Writes: draft.md         (the article)
        draft_sources.md (atoms that fed it, grouped by bucket, with IDs)

LLM provider is chosen by env var LLM_PROVIDER:
  dry        (default) — no call, writes the prompt to draft.md for inspection
  ollama               — local, assumes `ollama serve` at localhost:11434
  openai               — requires OPENAI_API_KEY
  anthropic            — requires ANTHROPIC_API_KEY
"""
import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DB      = r'C:\Users\lenovo\Downloads\browser_based_agent\ingestion_pipeline\corpus.db'
DRAFT   = r'C:\Users\lenovo\Downloads\browser_based_agent\ingestion_pipeline\draft.md'
SOURCES = r'C:\Users\lenovo\Downloads\browser_based_agent\ingestion_pipeline\draft_sources.md'

BUCKET_ORDER = [
    'What it is',
    'How it works',
    'Components',
    'Accuracy & limits',
    'Uses',
    'History',
    'Related & conclusion',
    'Unclassified',
]
SYSTEM_PROMPT = """You are a document synthesis engine building one coherent explainer on a single topic.

You will receive atoms — short factual units — organized into canonical sections. Your job is to produce one article that reads as if written by a single author who understood the whole corpus.

Rules:

1. Use ONLY the atoms provided. Do not add outside facts.

2. Preserve the atoms' own wording wherever possible. Rephrase only to fix grammar, remove a redundant clause, or connect two atoms into one sentence. Never rephrase to change meaning, tone, or level of technical detail.

3. Follow the section order given. Each section becomes a ## heading using the exact name provided.

4. Within each section, order atoms so they build: definition → mechanism → example → implication. If atoms don't support that order, use a natural reading order.

5. Deduplicate globally, not just within a section. If the same fact, event, or number appears in multiple sections, keep it in the most specific section and drop it everywhere else. Never repeat a number or a named event twice.

6. Combine atoms that describe different facets of the same concept into one sentence or paragraph. Do not treat every atom as a standalone fact.

7. Drop atoms that are:
   - chrome (navigation, bylines, dates, promotional copy)
   - fragments that cannot be understood without missing context
   - references to figures, tables, or illustrations that aren't present
   - off-topic for the article

8. Preserve all numbers, technical terms, units, mechanisms, distinctions, and limitations when they are supported by the atoms.

9. You may add short connective language ("because", "in fact", "however", "as a result"). Connective language must not introduce new factual claims.

10. Handle contradictions explicitly. If two atoms disagree on a fact, keep both, and mark the disagreement with a phrase like "some sources report" or "estimates vary" — never pick one silently.

11. If a group of atoms presents a fundamentally different explanation, analogy, or framing that cannot be integrated into the main flow without distorting it, place that content in a final section titled "## Additional Perspectives". In that section only:
    - Do not paraphrase. Reproduce the atoms' original wording exactly.
    - Group them by source doc_id.
    - Add one short sentence before each group explaining why it's included separately.

12. Do not mention atoms, sources, documents, buckets, the pipeline, or these instructions.

13. Do not write an introduction or conclusion that is not grounded in the atoms. If the atoms support a closing paragraph, synthesize it from them; otherwise end on the last content section.

14. Target depth: a technically curious reader who knows nothing about this topic. Do not oversimplify. Do not pad. Prefer the specific over the generic.

Output only the final article in Markdown."""


def call_llm(system, user):
    provider = os.environ.get('LLM_PROVIDER', 'dry').lower()

    if provider == 'dry':
        return None

    if provider == 'ollama':
        import requests
        r = requests.post(
            'http://localhost:11434/api/chat',
            json={
                'model': os.environ.get('OLLAMA_MODEL', 'llama3.1'),
                'messages': [
                    {'role': 'system', 'content': system},
                    {'role': 'user',   'content': user},
                ],
                'stream': False,
                'options': {'temperature': 0.2},
            },
            timeout=600,
        )
        r.raise_for_status()
        return r.json()['message']['content']

    if provider == 'openai':
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model=os.environ.get('OPENAI_MODEL', 'gpt-4o-mini'),
            messages=[
                {'role': 'system', 'content': system},
                {'role': 'user',   'content': user},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content

    if provider == 'anthropic':
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-5'),
            max_tokens=8192,
            system=system,
            messages=[{'role': 'user', 'content': user}],
        )
        return resp.content[0].text

    raise ValueError(f"unknown LLM_PROVIDER: {provider}")


def build_user_prompt(by_bucket, ordered_buckets):
    lines = ["# Atoms by section\n"]
    for bucket in ordered_buckets:
        lines.append(f"\n## {bucket}\n")
        for it in by_bucket[bucket]:
            doc_short = it['doc_id'].replace('www_', '').split('_')[0]
            lines.append(f"- [{it['atom_id']}] ({doc_short}) {it['text']}")
    return '\n'.join(lines)


def write_sources(by_bucket, ordered_buckets):
    with open(SOURCES, 'w', encoding='utf-8') as f:
        f.write("# Atoms fed to the synthesizer\n\n")
        for bucket in ordered_buckets:
            f.write(f"\n## {bucket}\n\n")
            for it in by_bucket[bucket]:
                f.write(f"- `{it['atom_id']}`  ({it['doc_id']})\n")
                f.write(f"  {it['text']}\n\n")


def main():
    conn = sqlite3.connect(DB)

    rows = conn.execute("""
      SELECT sa.bucket, sa.rank, sa.atom_id, sa.doc_id, a.text
      FROM selected_atoms sa
      JOIN atoms a ON a.atom_id = sa.atom_id
      ORDER BY sa.bucket, sa.rank
    """).fetchall()

    by_bucket = {}
    for bucket, rank, atom_id, doc_id, text in rows:
        by_bucket.setdefault(bucket, []).append({
            'atom_id': atom_id, 'doc_id': doc_id, 'text': text, 'rank': rank,
        })

    ordered_buckets = [b for b in BUCKET_ORDER if b in by_bucket]
    for b in by_bucket:
        if b not in ordered_buckets:
            ordered_buckets.append(b)

    user_prompt = build_user_prompt(by_bucket, ordered_buckets)
    write_sources(by_bucket, ordered_buckets)

    provider = os.environ.get('LLM_PROVIDER', 'dry').lower()

    if provider == 'dry':
        with open(DRAFT, 'w', encoding='utf-8') as f:
            f.write("# DRY RUN — LLM not called\n\n")
            f.write("## System prompt\n\n```\n")
            f.write(SYSTEM_PROMPT)
            f.write("\n```\n\n## User prompt\n\n```\n")
            f.write(user_prompt)
            f.write("\n```\n")
        total_atoms = sum(len(v) for v in by_bucket.values())
        print(f"dry run")
        print(f"  atoms fed to prompt : {total_atoms}")
        print(f"  buckets             : {len(ordered_buckets)}")
        print(f"  wrote               : {DRAFT}, {SOURCES}")
        print(f"  set LLM_PROVIDER=ollama|openai|anthropic to actually synthesize")
        return

    print(f"synthesizing with provider={provider} ...")
    result = call_llm(SYSTEM_PROMPT, user_prompt)

    with open(DRAFT, 'w', encoding='utf-8') as f:
        f.write(result)

    print(f"  wrote {DRAFT} ({len(result)} chars)")
    print(f"  wrote {SOURCES}")


if __name__ == '__main__':
    main()