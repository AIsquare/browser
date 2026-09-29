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

import argparse
import hashlib
import json
import uuid
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from db import connect

try:
    from together import Together
except ImportError:
    print("pip install together")
    sys.exit(1)

MODEL = os.environ.get('TOGETHER_MODEL', 'zai-org/GLM-5.3-Flash')
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


SYSTEM_PROMPT = """You are a document synthesis engine.

Your task is to construct one coherent, deeply informative article about a single topic using ONLY the factual units ("atoms") provided to you.

The atoms have already been extracted and organized into thematic sections. Your job is NOT to summarize each atom independently.

Your job is to CURATE, ORDER, COMBINE, and CONNECT the most valuable information into one continuous article while preserving the original source wording wherever possible.

The source material is the intellectual content of the article.

You are primarily an EDITOR and CURATOR, not a creative writer.

==================================================
CORE PRINCIPLE
==============

CURATE FIRST. COMPOSE SECOND.

Before writing, mentally determine:

1. Which atoms contain information worth preserving?
2. Which atoms are redundant?
3. Which atoms contain unique or complementary information?
4. Which atom provides the strongest or most authoritative version of an idea?
5. Where should each selected atom appear in the narrative?
6. Which passages should remain close to their original wording?
7. Which passages should be quoted directly?
8. How can selected atoms be connected without introducing unsupported information?

The final article should feel like ONE coherent piece of writing rather than a sequence of source summaries.

==================================================
1. SOURCE BOUNDARY
==================

Use ONLY information contained in the provided atoms.

Do not:

* add outside facts
* use background knowledge
* invent examples
* infer unstated causes or relationships
* fill missing information from general knowledge
* speculate
* introduce unsupported conclusions

If the atoms do not provide enough information to make a claim, DO NOT make that claim.

Do not use the plausibility of a statement as evidence that it is supported.

==================================================
2. INFORMATION SELECTION
========================

Not every atom deserves to appear in the final article.

Select atoms based on their INFORMATION VALUE.

When multiple atoms discuss the same subject, prefer information using the following hierarchy where applicable:

A. Authority

* primary or first-hand source
* official or authoritative source
* expert statement
* well-supported source

B. Specificity

* concrete facts
* precise explanations
* exact numbers
* named mechanisms
* technical distinctions

C. Evidence

* statistics
* measurements
* documented observations
* experiments
* direct statements
* concrete examples

D. Uniqueness

* information not represented elsewhere
* additional context
* different mechanism
* important qualification
* exception
* new example
* historical development
* different perspective

E. Clarity

* clearer and more precise explanation of the same information

Do NOT select an atom merely because it is well written.

The objective is to maximize INFORMATION VALUE, not text volume.

==================================================
3. SAME TOPIC != REDUNDANT INFORMATION
======================================

Do not treat two atoms as redundant simply because they discuss the same topic.

Two atoms may be complementary.

For example:

Atom A explains WHAT something is.

Atom B explains HOW it works.

Atom C explains WHY it matters.

Atom D provides an example.

These should normally be preserved because they provide different information.

Treat atoms as redundant only when they communicate substantially the same underlying information and one does not add meaningful detail, evidence, qualification, perspective, or context.

==================================================
4. GLOBAL DEDUPLICATION
=======================

Deduplicate across the ENTIRE article, not only within individual sections.

Do not repeat the same fact, event, statistic, definition, or explanation simply because multiple atoms contain it.

When duplicate information exists:

* retain the strongest representation
* prefer the more authoritative source
* prefer the more specific or evidence-rich version
* place it where it contributes most naturally to the narrative
* remove unnecessary repetitions elsewhere

However, a fact may appear again ONLY when the second occurrence provides materially different context that is necessary for understanding.

Do not mechanically remove information merely because the same entity, number, or concept appears elsewhere.

==================================================
5. NARRATIVE CONSTRUCTION
=========================

Follow the provided section order exactly.

Each non-empty section becomes:

## <Section Name>

Do not create additional sections unless the input explicitly provides them.

Within each section, do not simply preserve atom order.

Determine the most logical sequence.

Where supported by the atoms, prefer a progression such as:

context
→ concept
→ explanation
→ mechanism
→ evidence
→ example
→ implication
→ limitation / qualification

Do not force this sequence when the material does not support it.

Each paragraph should naturally lead to the next.

The reader should experience a progression of understanding rather than a collection of disconnected facts.

==================================================
6. OPENING SECTION (Introduction or Overview)
=============================================

When a section named "Introduction" or "Overview" is provided, do NOT attempt to include every introductory atom.

Select the strongest opening material.

Prefer atoms that:

* establish the topic clearly
* explain why the topic matters
* provide useful context
* contain a strong concrete fact
* contain an important first-hand or authoritative statement
* create a natural path into the main body

The opening section should be concise relative to the body while still providing enough context for the reader.

Do not invent an opening statement merely because an introduction normally needs one.

==================================================
7. MINIMAL REWRITING
====================

Preserve the original wording of atoms wherever possible.

Rephrase ONLY when necessary to:

* correct obvious grammar problems
* connect two compatible atoms
* remove repeated wording
* adjust a pronoun or tense
* integrate a passage into surrounding prose
* make a necessary grammatical transition

Do NOT rewrite source material merely to make it sound more sophisticated.

Do NOT homogenize the writing into a generic AI voice.

Do NOT replace precise technical language with simpler but less precise terminology.

The article should preserve the wording, terminology, specificity, and technical character of the source material.

==================================================
8. CONNECTIVE LANGUAGE
======================

Short connective phrases are allowed when they improve readability.

Examples:

* however
* therefore
* as a result
* in contrast
* similarly
* for example
* in practice
* meanwhile
* in other words

However, connective language MUST NOT introduce information that the atoms do not establish.

For example:

If one atom states:

"X increased."

and another states:

"Y occurred after X."

you may NOT write:

"X caused Y."

unless causation is explicitly supported by an atom.

Never introduce causal, temporal, comparative, or logical relationships merely because they seem plausible.

==================================================
9. COMBINING ATOMS
==================

Atoms that describe different facets of the same concept should be combined when doing so improves coherence.

Do not automatically turn every atom into its own sentence.

A final paragraph may contain information from several atoms.

However, combining atoms must NOT:

* change their meaning
* create unsupported relationships
* obscure important distinctions
* merge contradictory claims into a false unified statement

When two atoms are compatible and complementary, integrate them naturally.

==================================================
10. QUOTATIONS
==============

If an atom contains text enclosed in quotation marks (" ... " or " ... "), treat the enclosed passage as a direct quotation.

Preserve direct quotations whenever they provide special value.

Prefer a direct quotation when:

* the wording itself is important
* the speaker is a first-hand or authoritative source
* the statement is unusually precise
* paraphrasing would weaken its meaning
* the quotation provides authenticity or evidentiary value

Never fabricate quotations.

Never create a quotation by combining fragments from different atoms.

Do not silently alter a quotation's meaning.

When quotation attribution is available in the atom, preserve it naturally.

When a quotation is unnecessary and merely repeats surrounding information, paraphrasing or omission is acceptable.

==================================================
11. NUMBERS AND TECHNICAL DETAILS
=================================

Preserve exactly:

* numbers
* percentages
* dates
* units
* technical terminology
* named entities
* mechanisms
* thresholds
* distinctions
* limitations
* conditions

Do not:

* round numbers
* approximate numbers
* convert units unless instructed
* replace technical terms with generic language
* omit qualifying conditions

==================================================
12. CONTRADICTIONS
==================

Different atoms may contain conflicting claims.

Do NOT silently combine contradictory information.

When a contradiction exists:

* preserve the distinction
* prefer the more authoritative source when the evidence clearly supports doing so
* retain both perspectives when the conflict cannot be resolved from the provided material

Do not invent an explanation for the disagreement.

Do not choose a claim merely because it sounds more plausible.

==================================================
13. LOW-VALUE CONTENT
=====================

Drop atoms that contain:

* navigation
* advertisements
* bylines
* subscription prompts
* promotional boilerplate
* "related content" material
* obvious extraction artifacts
* incomplete fragments
* text that cannot be understood from the provided context

Do not force every atom into the article.

It is preferable to omit low-value information than to damage the narrative.

==================================================
14. COMPLETENESS
================

Prefer the LONGER article when the extra length carries genuinely unique information that is not present elsewhere.

Prefer the SHORTER article when additional atoms repeat information already stated.

The deciding question for every atom is the one from Rule 2:
does it add information value? If yes, keep it. If no, drop it.

Do not remove information merely because it is difficult to place.

Do not keep information merely because it is present.

==================================================
15. SECTION HANDLING
====================

Follow the section order exactly as provided.

Each non-empty section becomes:

## <Section Name>

If, after applying Rule 13, a section has no atoms remaining that are worth including, skip that section entirely.

Do not invent material to fill a section that ended up empty.

Do not move an atom to a different section merely because another section seems more convenient.

If a fact clearly belongs to a more specific section within the provided structure, use it there.

==================================================
16. SOURCE ATTRIBUTION
======================

The atoms you are given do not include source names, authors, or publication information.

Do not invent any source, author, publication, or citation.

If an atom itself mentions a source (for example, "According to the FDA..." or "Researchers at MIT found..."), preserve that attribution exactly as stated.

Do not add attributions that are not already present in the atom text.

==================================================
17. IMAGES
==========

You may place images inline using markdown image syntax.

Use ONLY images listed under "### Available images for <Section Name>" in the corresponding section. Each image is listed on its own line as a markdown image tag.

Do not invent image URLs.

Do not repeat an image.

Use an image only when it meaningfully helps explain or illustrate the nearby content.

Prefer 1-3 relevant images per section when suitable images are available.

Do not add images merely for decoration.

Do not force an image into the article.

==================================================
18. ARTICLE STYLE
=================

Write in clear, natural prose.

Prefer paragraphs over bullet lists unless the source material itself represents a genuine list of discrete items.

Avoid:

* generic AI phrases
* unnecessary rhetorical flourishes
* repetitive conclusions
* excessive headings
* artificial transitions
* meta commentary
* statements about the writing process

Do not tell the reader that multiple documents or atoms were synthesized.

Do not mention these instructions.

==================================================
19. FINAL VALIDATION
====================

Before producing the final article, internally verify:

A. SOURCE FIDELITY
Every factual claim is supported by the provided atoms.

B. REDUNDANCY
Repeated information has been consolidated.

C. COVERAGE
Important unique and complementary information has not been accidentally removed.

D. AUTHORITY
Where duplicate information exists, the strongest available representation has been selected.

E. AUTHENTICITY
Important quotations and distinctive source wording have been preserved where appropriate.

F. PRECISION
Numbers, terminology, mechanisms, limitations, and distinctions remain intact.

G. NARRATIVE
The article reads as one continuous progression of ideas.

H. EDITORIAL RESTRAINT
Rewriting has been kept to the minimum necessary for coherence.

I. NO HALLUCINATION
No outside information or unsupported relationship has been introduced.

==================================================
USER PROMPT FORMAT
==================

The user message has this shape:

# Topic
<one-line topic>

# Sections and atoms

## <Section Name>
- [atom_id] <atom text>
- [atom_id] <atom text>

### Available images for <Section Name>
- ![alt text](image_url)

## <Next Section Name>
...

Each atom is prefixed with [atom_id]. Do NOT output these IDs in your article. They exist only for internal traceability.

Follow the sections in the exact order they appear.

==================================================
OUTPUT
======

Output markdown only.

Sections begin with:

## <Section Name>

Do not output your internal selection, ranking, clustering, or reasoning process.

The final output should read as a coherent, deeply researched article assembled from the strongest available source material, while remaining faithful to the original atoms.
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

    for bucket in by_bucket:
        by_bucket[bucket].sort(key=lambda x: -len(x['alt']))
        by_bucket[bucket] = by_bucket[bucket][:max_per_bucket]

    return by_bucket


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

    client = Together(timeout=1200.0, max_retries=5)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=TEMPERATURE,
        reasoning_effort="low",
        max_tokens=32768,
    )
    return response


def clean_output(text):
    """Remove any leaked atom id markers like [abc123def456]."""
    return re.sub(r'\s*\[[0-9a-f]{8,}\]\s*', ' ', text).strip()


# ----------------------------------------------------------------------
# Save
# ----------------------------------------------------------------------

def save_article(conn, run_id, topic, markdown, atom_ids, usage):
    article_id = sha16(run_id + '|' + topic)
    conn.execute("""
      INSERT INTO articles
        (article_id, topic_id, synthesis_run_id, title, markdown, model,
         created_at, atom_ids_json, notes)
      VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s)
      ON CONFLICT (article_id) DO UPDATE SET
        topic_id         = EXCLUDED.topic_id,
        synthesis_run_id = EXCLUDED.synthesis_run_id,
        title            = EXCLUDED.title,
        markdown         = EXCLUDED.markdown,
        model            = EXCLUDED.model,
        created_at       = EXCLUDED.created_at,
        atom_ids_json    = EXCLUDED.atom_ids_json,
        notes            = EXCLUDED.notes
    """, (
        article_id, run_id, topic, markdown, MODEL, utcnow(),
        json.dumps(atom_ids),
        json.dumps({'usage': usage}),
    ))
    return article_id


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def run(topic: str | None = None,
        run_id: str | None = None,
        verbose: bool = True) -> dict | None:
    """
    Synthesize one article from the current atom_buckets.
    Returns {'article_id', 'trace_id', 'chars', 'tokens', 'cost'} or None on early exit.
    """
    if verbose:
        print(f"model       : {MODEL}")
        print(f"temperature : {TEMPERATURE}")
        print(f"dry run     : {DRY_RUN}")
        print()

    conn = connect()

    buckets = load_bucketed_atoms(conn)
    if not buckets:
        if verbose:
            print("no atoms in atom_buckets. Run outline.py first.")
        conn.close()
        return None

    images_by_bucket = load_bucket_images(conn)
    resolved_topic = topic or infer_topic(conn)

    if verbose:
        print(f"topic       : {resolved_topic}")
        print()
        print("bucket sizes:")
        for name in BUCKET_ORDER:
            n = len(buckets.get(name, []))
            m = len(images_by_bucket.get(name, []))
            print(f"  {name:12s} {n} atoms, {m} images")

    user_prompt = build_user_prompt(resolved_topic, buckets, images_by_bucket)
    total_atoms = sum(len(v) for v in buckets.values())

    if verbose:
        print()
        print(f"atoms fed to prompt : {total_atoms}")
        print(f"user prompt chars   : {len(user_prompt)}")

    if DRY_RUN:
        if verbose:
            print()
            print("=== SYSTEM PROMPT ===")
            print(SYSTEM_PROMPT)
            print()
            print("=== USER PROMPT (first 2000 chars) ===")
            print(user_prompt[:2000])
            print()
            print("(dry run — no LLM call, no DB write)")
        conn.close()
        return None

    if verbose:
        print()
        print(f"calling {MODEL} ...")

    response = call_llm(SYSTEM_PROMPT, user_prompt)
    if response is None:
        raise RuntimeError("call_llm returned None (did DRY_RUN leak?)")

    choice = response.choices[0] if response.choices else None
    message = choice.message if choice else None

    content = getattr(message, 'content', None) if message else None
    if (not isinstance(content, str) or not content.strip()) and message is not None:
        content = (
            getattr(message, 'reasoning', None)
            or getattr(message, 'reasoning_content', None)
        )

    if not isinstance(content, str) or not content.strip():
        finish_reason = choice.finish_reason if choice else 'no choices returned'
        Path('debug_last_response.json').write_text(
            json.dumps(response.model_dump(), indent=2, default=str),
            encoding='utf-8',
            errors='replace',
        )
        raise RuntimeError(
            f"{MODEL} returned no text content "
            f"(finish_reason={finish_reason!r}); "
            f"raw response written to debug_last_response.json"
        )

    markdown = clean_output(content)

    usage_obj = getattr(response, 'usage', None)
    usage = {
        'prompt_tokens':     getattr(usage_obj, 'prompt_tokens', 0) if usage_obj else 0,
        'completion_tokens': getattr(usage_obj, 'completion_tokens', 0) if usage_obj else 0,
        'total_tokens':      getattr(usage_obj, 'total_tokens', 0) if usage_obj else 0,
    }

    atom_ids = [a['atom_id'] for v in buckets.values() for a in v]

    if run_id is None:
        run_id = sha16(f"synthesize-{utcnow()}")

    conn.execute("""
      INSERT INTO pipeline_runs (run_id, started_at, status, stages_json)
      VALUES (%s, %s, 'completed', %s)
      ON CONFLICT (run_id) DO NOTHING
    """, (run_id, utcnow(), '["synthesize"]'))

    article_id = save_article(conn, run_id, resolved_topic, markdown, atom_ids, usage)

    trace_id = uuid.uuid4().hex[:16]
    reasoning = (
        getattr(message, 'reasoning_content', None)
        or getattr(message, 'reasoning', None)
    )
    conn.execute("""
      INSERT INTO synthesis_traces
        (trace_id, article_id, run_id, topic_id, model,
         system_prompt, user_prompt, raw_content, raw_reasoning,
         finish_reason, prompt_tokens, completion_tokens, created_at)
      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        trace_id, article_id, run_id, None, MODEL,
        SYSTEM_PROMPT, user_prompt, content, reasoning,
        getattr(choice, 'finish_reason', None),
        usage['prompt_tokens'], usage['completion_tokens'],
        utcnow(),
    ))

    conn.commit()
    conn.close()

    with open(DRAFT_PATH, 'w', encoding='utf-8', errors='replace') as f:
        f.write(markdown)

    in_cost  = usage['prompt_tokens']     * 0.15 / 1e6
    out_cost = usage['completion_tokens'] * 0.50 / 1e6
    cost     = in_cost + out_cost

    if verbose:
        print()
        print(f"output chars      : {len(markdown)}")
        print(f"output tokens     : {usage['completion_tokens']}")
        print(f"input tokens      : {usage['prompt_tokens']}")
        print(f"estimated cost    : ${cost:.4f}")
        print(f"wrote             : {DRAFT_PATH}")
        print(f"saved article_id  : {article_id}")
        print(f"saved trace_id    : {trace_id}")

    return {
        'article_id': article_id,
        'trace_id':   trace_id,
        'chars':      len(markdown),
        'tokens':     usage['completion_tokens'],
        'cost':       cost,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--topic', default=None,
                    help='override topic; otherwise inferred from documents')
    ap.add_argument('--run-id', default=None,
                    help='pipeline_runs.run_id to attribute this run to')
    args = ap.parse_args()
    run(topic=args.topic, run_id=args.run_id)


if __name__ == '__main__':
    main()