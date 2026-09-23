"""
Synthesize one article from bucketed atoms using an LLM.

Reads:  atom_buckets, atoms, sections, documents
Writes: draft.md + articles table row

Universal template order. Empty sections skipped. Topic inferred from
documents unless SYNTH_TOPIC is set. One LLM call per run.

Env:
  OPENAI_API_KEY     required
  OPENAI_MODEL       default gpt-4o-mini
  SYNTH_TOPIC        optional override; otherwise inferred from titles
  SYNTH_TEMPERATURE  default 0.2
  SYNTH_DRY_RUN      "1" prints the prompt and exits
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

from db import connect

try:
    from openai import OpenAI
except ImportError:
    print("pip install openai")
    sys.exit(1)


MODEL        = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')
TEMPERATURE  = float(os.environ.get('SYNTH_TEMPERATURE', '0.2'))
TOPIC_OVERRIDE = os.environ.get('SYNTH_TOPIC')
DRY_RUN      = os.environ.get('SYNTH_DRY_RUN', '0') == '1'
DRAFT_PATH   = 'draft.md'

# Universal narrative template. Order matters — this is the article order.
BUCKET_ORDER = [
    'Overview',
    'Context',
    'Mechanism',
    'Structure',
    'Examples',
    'Details',
    'Limits',
    'Related',
    'Sources',
]

# Sections that carry the argument of the article. If they're empty,
# we don't write them even if the LLM would try.
REQUIRED_SECTIONS = {'Overview', 'Mechanism'}


SYSTEM_PROMPT = """You are a document synthesis engine. Your job is to write one
coherent article on a single topic, drawing only from the short factual
units (atoms) that are provided to you, organized into thematic sections.

RULES:

1. Use ONLY the atoms provided. Do not add outside facts. Do not infer
   anything the atoms do not state.

2. Preserve the atoms' own wording wherever possible. Rephrase only to
   fix grammar, join two atoms into one sentence, or add short
   connective phrases ("because", "however", "as a result", "in fact").
   Never rephrase to change meaning, tone, or level of technical detail.

3. Follow the section order exactly as given. Each non-empty section
   becomes a `## <Section Name>` heading in the output.

4. Skip any section that has zero atoms. Do not write an empty section
   and do not invent content to fill it.

5. Deduplicate globally, not just within a section. If the same fact,
   event, number, or named thing appears in more than one section, keep
   it in the most specific section and drop it everywhere else. Never
   state the same specific fact twice.

6. Combine atoms that describe different facets of the same concept into
   one sentence or paragraph. Do not treat every atom as an independent
   sentence.

7. Drop atoms that are fragments, chrome (navigation, bylines, ads,
   subscription prompts, "related content" notes), or that only make
   sense with context that isn't present. Do not force-fit every atom.

8. Preserve all numbers, units, technical terms, mechanisms,
   distinctions, and limitations verbatim. Do not round numbers. Do not
   replace specific terms with generic ones.

9. Do not mention atoms, sources, documents, buckets, or these
   instructions. Do not add a bibliography or source list unless a
   Sources section is provided with real content.

10. Write in clear, plain prose. Prefer paragraphs over bullet lists
    unless the source atoms are themselves a list of discrete items.

11. Do not write an introduction or conclusion that is not grounded in
    the provided atoms.

12. IMAGES: You may place images inline using markdown image syntax.
    Only use images listed under "Available images" for a section.
    Do not invent image URLs. Do not repeat an image. Place each image
    where it helps the reader understand the nearby text — usually just
    after the paragraph it illustrates. Omit any image whose alt text
    does not clearly relate to the surrounding content. Prefer 1–3
    images per section; do not flood the article.

Output: markdown only. Sections begin with `## ` headings matching the
section names provided.
"""


# ----------------------------------------------------------------------
# Load
# ----------------------------------------------------------------------
def load_bucket_images(conn, max_per_bucket=8):
    """
    Returns {bucket: [{url, alt, section_heading}, ...]}.

    Images attach to sections; sections map to buckets via the atoms
    in that section. Filters out obvious chrome. Caps per bucket.
    """
    rows = conn.execute("""
      SELECT i.url, i.alt, i.section_id, s.heading AS section_heading
      FROM images i
      JOIN sections s ON s.section_id = i.section_id
      WHERE i.section_id IS NOT NULL
        AND i.alt IS NOT NULL
        AND length(trim(i.alt)) >= 5
        AND i.url NOT LIKE '%avatar%'
        AND i.url NOT LIKE '%icon%'
        AND i.url NOT LIKE '%badge%'
        AND i.url NOT LIKE '%logo%'
        AND i.url NOT LIKE '%favicon%'
    """).fetchall()

    # section_id -> bucket (from any atom in that section)
    sec_role = {}
    for r in conn.execute("""
      SELECT DISTINCT a.section_id, b.bucket
      FROM atoms a
      JOIN atom_buckets b ON b.atom_id = a.atom_id
      WHERE a.section_id IS NOT NULL
    """):
        sec_role[r['section_id']] = r['bucket']

    by_bucket = {}
    for r in rows:
        bucket = sec_role.get(r['section_id'])
        if not bucket:
            continue
        by_bucket.setdefault(bucket, []).append({
            'url':             r['url'],
            'alt':             r['alt'].strip(),
            'section_heading': r['section_heading'] or '',
        })

    # Sort by alt length desc, cap
    for bucket in by_bucket:
        by_bucket[bucket].sort(key=lambda x: -len(x['alt']))
        by_bucket[bucket] = by_bucket[bucket][:max_per_bucket]

    return by_bucket

def build_user_prompt(topic, buckets, images_by_bucket):
    lines = [f"# Topic\n\n{topic}\n"]
    lines.append("# Sections and atoms\n")

    for name in BUCKET_ORDER:
        atoms = buckets.get(name, [])
        images = images_by_bucket.get(name, [])
        if not atoms and not images:
            continue

        lines.append(f"\n## {name}\n")

        for a in atoms:
            lines.append(f"- [{a['atom_id']}] {a['text']}")

        if images:
            lines.append(f"\n### Available images for {name}\n")
            for img in images:
                lines.append(f"- ![{img['alt']}]({img['url']})")
            lines.append("")

    return '\n'.join(lines)


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def sha16(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]


def load_bucketed_atoms(conn):
    """Returns {bucket: [{atom_id, text, section_heading}, ...]}."""
    rows = conn.execute("""
      SELECT b.bucket, a.atom_id, a.text, s.heading AS section_heading
      FROM atom_buckets b
      JOIN atoms a ON a.atom_id = b.atom_id
      LEFT JOIN sections s ON s.section_id = a.section_id
      ORDER BY b.bucket, s.heading, a.order_index
    """).fetchall()

    buckets = {}
    for r in rows:
        buckets.setdefault(r['bucket'], []).append({
            'atom_id':         r['atom_id'],
            'text':            r['text'],
            'section_heading': r['section_heading'] or '',
        })
    return buckets


def infer_topic(conn):
    """Return the most common non-boilerplate H1 title, or a fallback."""
    if TOPIC_OVERRIDE:
        return TOPIC_OVERRIDE

    rows = conn.execute("""
      SELECT title FROM documents
      WHERE title IS NOT NULL AND length(trim(title)) > 2
    """).fetchall()

    titles = [r['title'].strip() for r in rows if r['title']]
    if not titles:
        return 'the subject described by the atoms below'

    # Shortest reasonable title is usually the most generic and accurate.
    titles.sort(key=lambda t: len(t))
    for t in titles:
        if len(t) < 120:
            return t
    return titles[0]


# ----------------------------------------------------------------------
# Prompt
# ----------------------------------------------------------------------

def build_user_prompt(topic, buckets, images_by_bucket):
    lines = [f"# Topic\n\n{topic}\n"]
    lines.append("# Sections and atoms\n")

    for name in BUCKET_ORDER:
        atoms = buckets.get(name, [])
        images = images_by_bucket.get(name, [])
        if not atoms and not images:
            continue

        lines.append(f"\n## {name}\n")

        for a in atoms:
            lines.append(f"- [{a['atom_id']}] {a['text']}")

        if images:
            lines.append(f"\n### Available images for {name}\n")
            for img in images:
                lines.append(f"- ![{img['alt']}]({img['url']})")
            lines.append("")

    return '\n'.join(lines)


# ----------------------------------------------------------------------
# LLM
# ----------------------------------------------------------------------

def call_llm(system, user):
    if DRY_RUN:
        return None

    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {'role': 'system', 'content': system},
            {'role': 'user',   'content': user},
        ],
        temperature=TEMPERATURE,
    )
    return response


def clean_output(text):
    """Remove any leaked atom id markers like [abc123def456]."""
    return re.sub(r'\s*\[[0-9a-f]{8,}\]\s*', ' ', text).strip()


# ----------------------------------------------------------------------
# Save
# ----------------------------------------------------------------------

def ensure_articles_table(conn):
    conn.execute("""
      CREATE TABLE IF NOT EXISTS articles (
        article_id         TEXT PRIMARY KEY,
        topic_id           TEXT,
        synthesis_run_id   TEXT,
        title              TEXT,
        markdown           TEXT NOT NULL,
        model              TEXT,
        created_at         TEXT NOT NULL,
        atom_ids_json      TEXT,
        notes              TEXT
      )
    """)


def save_article(conn, run_id, topic, markdown, atom_ids, usage):
    article_id = sha16(run_id + '|' + topic)
    conn.execute("""
      INSERT OR REPLACE INTO articles
        (article_id, topic_id, synthesis_run_id, title, markdown, model,
         created_at, atom_ids_json, notes)
      VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?)
    """, (
        article_id, run_id, topic, markdown, MODEL, utcnow(),
        json.dumps(atom_ids),
        json.dumps({'usage': usage}),
    ))


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    print(f"model       : {MODEL}")
    print(f"temperature : {TEMPERATURE}")
    print(f"dry run     : {DRY_RUN}")
    print()

    conn = connect()
    ensure_articles_table(conn)

    buckets = load_bucketed_atoms(conn)
    if not buckets:
        print("no atoms in atom_buckets. Run outline.py first.")
        conn.close()
        return
    images_by_bucket = load_bucket_images(conn)
    topic = infer_topic(conn)
    print(f"topic       : {topic}")
    print()
    print("bucket sizes:")
    for name in BUCKET_ORDER:
        n = len(buckets.get(name, []))
        m = len(images_by_bucket.get(name, []))
        print(f"  {name:12s} {n} atoms, {m} images")

    user_prompt = build_user_prompt(topic, buckets, images_by_bucket)

    total_atoms = sum(len(v) for v in buckets.values())
    print()
    print(f"atoms fed to prompt : {total_atoms}")
    print(f"user prompt chars   : {len(user_prompt)}")

    if DRY_RUN:
        print()
        print("=== SYSTEM PROMPT ===")
        print(SYSTEM_PROMPT)
        print()
        print("=== USER PROMPT (first 2000 chars) ===")
        print(user_prompt[:2000])
        print()
        print("(dry run — no LLM call, no DB write)")
        conn.close()
        return

    print()
    print(f"calling {MODEL} ...")
    response = call_llm(SYSTEM_PROMPT, user_prompt)

    markdown = clean_output(response.choices[0].message.content)
    usage = {
        'prompt_tokens':     response.usage.prompt_tokens,
        'completion_tokens': response.usage.completion_tokens,
        'total_tokens':      response.usage.total_tokens,
    }

    atom_ids = [a['atom_id'] for v in buckets.values() for a in v]

    run_id = sha16(f"synthesize-{utcnow()}")
    conn.execute("""
      INSERT INTO pipeline_runs (run_id, started_at, status, stages_json)
      VALUES (?, ?, 'completed', ?)
    """, (run_id, utcnow(), '["synthesize"]'))

    save_article(conn, run_id, topic, markdown, atom_ids, usage)
    conn.commit()

    with open(DRAFT_PATH, 'w', encoding='utf-8') as f:
        f.write(markdown)

    print()
    print(f"output chars      : {len(markdown)}")
    print(f"output tokens     : {usage['completion_tokens']}")
    print(f"input tokens      : {usage['prompt_tokens']}")
    print(f"estimated cost    : ${usage['prompt_tokens'] * 0.15/1e6 + usage['completion_tokens'] * 0.60/1e6:.4f}")
    print(f"wrote             : {DRAFT_PATH}")
    print(f"saved article_id  : {run_id[:16]}")

    conn.close()


if __name__ == '__main__':
    main()