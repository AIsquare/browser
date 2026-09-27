"""
Evaluate how well each source document is incorporated into a synthesized article.

V1 — document-level evaluation. One JEV call per source document.

For each source doc, four Score questions are evaluated against the same state
(source doc + final article):

  coverage            — how much of the source's substantive information survives
  faithfulness        — how accurately meaning, details, qualifications survive
  unique_contribution — how much of the source's specific/concrete content survives
  contradiction       — whether the article contradicts the source's claims

Reads:  synthesis_traces, articles, blocks, documents
Writes: eval_runs, eval_scores

Usage:
  python eval.py --article-id <id> --label "post-prompt-v3"
  python eval.py --latest --label "post-prompt-v3"
  python eval.py --article-id <id> --label "..." --dry-run

Env:
  TYPESAFE_API_KEY   required
  TYPESAFE_MODEL     default jev-latest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()
import os
from db import connect

try:
    from typesafe_sdk import Score, TypeSafeClient
except ImportError:
    print("pip install typesafe-sdk")
    sys.exit(1)


MODEL = os.environ.get('TYPESAFE_MODEL', 'jev-latest')

# JEV allows state + longest question <= 32k tokens. 4 chars/token for English
# means ~128k chars. We target 110k to leave headroom for the question text.
MAX_STATE_CHARS = 110_000


# =====================================================================
# Helpers
# =====================================================================

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def sha16(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]


def trim_article(article: str, budget: int) -> str:
    """
    If the article exceeds budget chars, keep 2/3 of the head and 1/3 of the
    tail. Preserves thesis (opening) and conclusions (closing), drops the middle.
    """
    if len(article) <= budget:
        return article
    head = budget * 2 // 3
    tail = budget - head - 60  # room for the marker
    return (
        article[:head]
        + "\n\n[... middle of article truncated for length ...]\n\n"
        + article[-tail:]
    )


def build_state(article_md: str, source_md: str) -> dict:
    """Fit article + source into the JEV state budget."""
    combined = len(article_md) + len(source_md)
    if combined <= MAX_STATE_CHARS:
        return {"article": article_md, "source_document": source_md}

    # Reserve half the budget for the source, half for the article.
    source_budget = MAX_STATE_CHARS // 2
    if len(source_md) > source_budget:
        source_md = trim_article(source_md, source_budget)

    article_budget = MAX_STATE_CHARS - len(source_md) - 200
    article_md = trim_article(article_md, article_budget)

    return {"article": article_md, "source_document": source_md}


def build_questions() -> dict:
    """The four Score questions. Each has an explicit 0-5 anchor scale."""
    return {
        "coverage": Score(
            instructions=(
                "How much of the substantive information contained in the source "
                "document is represented in the final article?\n\n"
                "Judge by information content, not lexical overlap. A claim is "
                "represented if a reader of the article would acquire the same "
                "factual understanding the source provides. Rewording, "
                "restructuring, compression, and synonym substitution all count.\n\n"
                "Do NOT credit the source merely because the article discusses the "
                "same topic. Ask: what specific facts, arguments, or examples does "
                "this source contain that the article does not? If most are absent, "
                "coverage is low."
            ),
            criteria=[
                "essentially none of the source's substantive information appears",
                "very little; article touches the topic but uses almost nothing from this source",
                "some minor information appears, but most substantive content is missing",
                "roughly half of the source's substantive information is represented",
                "most important information is represented; only minor points missing",
                "nearly all of the source's substantive information is represented",
            ],
        ),
        "faithfulness": Score(
            instructions=(
                "How faithfully does the final article preserve the source's "
                "meaning, qualifications, technical details, and attributions?\n\n"
                "Consider whether the article preserves:\n"
                "- numeric values, percentages, dates, units exactly\n"
                "- named entities (organizations, people, places, products)\n"
                "- qualifications (\"in some cases\", \"except when X\")\n"
                "- technical distinctions (A vs B is not the same as \"A and B\")\n"
                "- source attributions (\"according to the FDA\")\n\n"
                "Absence of the source's exact phrasing is not penalized. Judged "
                "on whether the underlying meaning survives intact."
            ),
            criteria=[
                "article contradicts or fundamentally distorts the source's meaning",
                "article preserves almost none of the source's specific details",
                "article captures general topic but loses most specifics",
                "article preserves about half of specific details faithfully",
                "article preserves most specifics; minor inaccuracies only",
                "article faithfully preserves meaning, details, and qualifications",
            ],
        ),
        "unique_contribution": Score(
            instructions=(
                "How much of this source's SPECIFIC content — its numbers, named "
                "examples, dated events, direct attributions, and particular "
                "qualifications — is represented in the final article?\n\n"
                "Ignore general or definitional content. Focus only on concrete, "
                "particular content: statistics with specific values, named "
                "examples, dates, direct quotations, attributions to specific "
                "people or organizations, and specific qualifications.\n\n"
                "This is NOT about topical coverage. It is about whether the "
                "source's concrete specifics — the things that make its "
                "contribution distinct — appear in the article."
            ),
            criteria=[
                "essentially none of the source's specific content appears",
                "very little specific content; only vague allusions",
                "some specific content appears, but most concrete details missing",
                "roughly half of the source's specific content is represented",
                "most specific content is represented; only minor details missing",
                "nearly all of the source's specific content is represented",
            ],
        ),
        "contradiction": Score(
            instructions=(
                "Does the final article contradict this source's factual claims, "
                "or misrepresent its position?\n\n"
                "Answer 5 if the article is silent or in agreement on the source's "
                "claims. Answer low only if the article asserts something that "
                "conflicts with the source, or presents the source's position in a "
                "way that misrepresents what the source actually said."
            ),
            criteria=[
                "article directly contradicts a key claim from this source",
                "article substantially misrepresents the source's position",
                "article contains a factual error that conflicts with this source",
                "minor tensions, but source's position is broadly respected",
                "no contradiction; source's position preserved accurately",
                "no contradiction; source's position preserved with high fidelity",
            ],
        ),
    }
# =====================================================================
# Data loading
# =====================================================================

def load_article_and_trace(conn, article_id: str | None) -> dict | None:
    if article_id is None:
        row = conn.execute("""
          SELECT t.trace_id, t.article_id, t.model, t.created_at,
                 a.markdown AS article_md, a.title
          FROM synthesis_traces t
          JOIN articles a ON a.article_id = t.article_id
          ORDER BY t.created_at DESC
          LIMIT 1
        """).fetchone()
    else:
        row = conn.execute("""
          SELECT t.trace_id, t.article_id, t.model, t.created_at,
                 a.markdown AS article_md, a.title
          FROM synthesis_traces t
          JOIN articles a ON a.article_id = t.article_id
          WHERE t.article_id = %s
          ORDER BY t.created_at DESC
          LIMIT 1
        """, (article_id,)).fetchone()
    return row


def load_source_docs(conn, article_id: str) -> list[dict]:
    """
    Load every source document whose atoms were fed into the synthesis prompt
    for this article. Reconstructs the doc text from the blocks table.
    """
    # Which doc_ids contributed atoms?
    art = conn.execute(
        "SELECT atom_ids_json FROM articles WHERE article_id = %s",
        (article_id,),
    ).fetchone()
    if not art or not art['atom_ids_json']:
        return []

    atom_ids = json.loads(art['atom_ids_json'])
    if not atom_ids:
        return []

    placeholders = ','.join(['%s'] * len(atom_ids))
    doc_rows = conn.execute(f"""
      SELECT DISTINCT doc_id FROM atoms
      WHERE atom_id IN ({placeholders})
    """, tuple(atom_ids)).fetchall()

    doc_ids = [r['doc_id'] for r in doc_rows]

    docs = []
    for doc_id in doc_ids:
        # Doc metadata
        d = conn.execute(
            "SELECT doc_id, source_url, canonical_url, title FROM documents WHERE doc_id = %s",
            (doc_id,),
        ).fetchone()
        if not d:
            continue

        # Reconstruct doc text from blocks in order
        block_rows = conn.execute("""
          SELECT raw_text, text FROM blocks
          WHERE doc_id = %s
          ORDER BY order_index
        """, (doc_id,)).fetchall()

        chunks = []
        for b in block_rows:
            t = (b['raw_text'] or b['text'] or '').strip()
            if t:
                chunks.append(t)
        doc_text = '\n\n'.join(chunks)

        if not doc_text.strip():
            continue

        docs.append({
            'doc_id': doc_id,
            'url': d['canonical_url'] or d['source_url'],
            'title': d['title'] or '(untitled)',
            'text': doc_text,
        })

    return docs


# =====================================================================
# Evaluation
# =====================================================================

def evaluate_doc(client, article_md: str, doc: dict) -> dict:
    """One JEV call. Returns {coverage, faithfulness, unique_contribution, contradiction}."""
    state = build_state(article_md, doc['text'])
    questions = build_questions()

    r = client.system_one(state=state, questions=questions, model=MODEL)

    return {
        'coverage':       r.answers['coverage'].score,
        'coverage_conf':  r.answers['coverage'].confidence,
        'faithfulness':   r.answers['faithfulness'].score,
        'faith_conf':     r.answers['faithfulness'].confidence,
        'unique_contrib': r.answers['unique_contribution'].score,
        'unique_conf':    r.answers['unique_contribution'].confidence,
        'contradiction':  r.answers['contradiction'].score,
        'contra_conf':    r.answers['contradiction'].confidence,
    }

# =====================================================================
# Report
# =====================================================================

def print_report(run_label: str, article_title: str, scores: list[dict]) -> None:
    if not scores:
        print("(no scores to report)")
        return

    def short_url(url: str, width: int = 50) -> str:
        s = url.replace('https://', '').replace('http://', '').replace('www.', '')
        return (s[:width-1] + '…') if len(s) > width else s

    print()
    print(f"eval_run: {run_label}")
    print(f"article : {article_title}")
    print(f"model   : {MODEL}")
    print(f"docs    : {len(scores)}")
    print()
    print(f"{'document':52s} {'cov':>5s} {'fai':>5s} {'uniq':>5s} {'ctr':>5s}")
    print('-' * 75)
    for s in sorted(scores, key=lambda x: -x['coverage']):
        print(f"{short_url(s['url']):52s} "
              f"{s['coverage']:5.1f} {s['faithfulness']:5.1f} "
              f"{s['unique_contrib']:5.1f} {s['contradiction']:5.1f}")

    # Aggregates
    def avg(key):
        return sum(s[key] for s in scores) / len(scores)

    def median(key):
        vals = sorted(s[key] for s in scores)
        n = len(vals)
        return vals[n//2] if n % 2 else (vals[n//2 - 1] + vals[n//2]) / 2

    print('-' * 75)
    print(f"{'mean':52s} "
          f"{avg('coverage'):5.1f} {avg('faithfulness'):5.1f} "
          f"{avg('unique_contrib'):5.1f} {avg('contradiction'):5.1f}")
    print(f"{'median':52s} "
          f"{median('coverage'):5.1f} {median('faithfulness'):5.1f} "
          f"{median('unique_contrib'):5.1f} {median('contradiction'):5.1f}")

    # Bottom 5 by coverage
    bottom = sorted(scores, key=lambda x: x['coverage'])[:5]
    print()
    print("worst 5 by coverage:")
    for s in bottom:
        print(f"  {short_url(s['url'], 60):60s}  "
              f"cov={s['coverage']:.1f}  "
              f"fai={s['faithfulness']:.1f}  "
              f"uniq={s['unique_contrib']:.1f}")


# =====================================================================
# Main
# =====================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--article-id', help='specific article_id to evaluate')
    ap.add_argument('--latest', action='store_true',
                    help='use the most recently created trace')
    ap.add_argument('--label', required=True,
                    help='human label for this eval run, e.g. "post-prompt-v3"')
    ap.add_argument('--dry-run', action='store_true',
                    help='print what would be evaluated, no JEV calls')
    ap.add_argument('--limit', type=int, default=None,
                    help='only evaluate first N docs (for testing)')
    args = ap.parse_args()

    if not args.article_id and not args.latest:
        ap.error('pass --article-id or --latest')

    conn = connect()

    trace = load_article_and_trace(conn, args.article_id)
    if not trace:
        print("no trace found")
        conn.close()
        return

    article_id = trace['article_id']
    article_md = trace['article_md']
    article_title = trace['title'] or article_id[:16]

    print(f"article_id : {article_id}")
    print(f"title      : {article_title}")
    print(f"chars      : {len(article_md):,}")
    print(f"label      : {args.label}")
    print()

    docs = load_source_docs(conn, article_id)
    print(f"source docs: {len(docs)}")

    if not docs:
        print("no source docs to evaluate")
        conn.close()
        return

    if args.limit:
        docs = docs[:args.limit]
        print(f"limited to : {len(docs)}")

    if args.dry_run:
        for d in docs:
            combined = len(article_md) + len(d['text'])
            marker = 'TRIM' if combined > MAX_STATE_CHARS else '    '
            print(f"  [{marker}] {d['url'][:70]:70s} "
                  f"doc={len(d['text']):>7,}  combined={combined:>7,}")
        conn.close()
        return

    # Init
    eval_run_id = uuid.uuid4().hex[:16]
    conn.execute("""
      INSERT INTO eval_runs
        (eval_run_id, label, model, started_at, article_id, doc_count)
      VALUES (%s, %s, %s, %s, %s, %s)
    """, (eval_run_id, args.label, MODEL, utcnow(), article_id, len(docs)))
    conn.commit()

    client = TypeSafeClient()
    all_scores = []

    print()
    print(f"evaluating {len(docs)} docs ...")
    for i, doc in enumerate(docs, 1):
        print(f"  [{i:2d}/{len(docs)}] {doc['url'][:60]:60s}", end='', flush=True)
        try:
            s = evaluate_doc(client, article_md, doc)
        except Exception as e:
            print(f" FAILED: {e}")
            continue

        all_scores.append({'url': doc['url'], **s})

        conn.execute("""
          INSERT INTO eval_scores
            (eval_run_id, article_id, doc_id,
             coverage, coverage_conf,
             faithfulness, faith_conf,
             unique_contrib, unique_conf,
             contradiction, contra_conf,
             created_at)
          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
          ON CONFLICT (eval_run_id, article_id, doc_id) DO UPDATE SET
            coverage       = EXCLUDED.coverage,
            coverage_conf  = EXCLUDED.coverage_conf,
            faithfulness   = EXCLUDED.faithfulness,
            faith_conf     = EXCLUDED.faith_conf,
            unique_contrib = EXCLUDED.unique_contrib,
            unique_conf    = EXCLUDED.unique_conf,
            contradiction  = EXCLUDED.contradiction,
            contra_conf    = EXCLUDED.contra_conf,
            created_at     = EXCLUDED.created_at
        """, (
            eval_run_id, article_id, doc['doc_id'],
            s['coverage'], s['coverage_conf'],
            s['faithfulness'], s['faith_conf'],
            s['unique_contrib'], s['unique_conf'],
            s['contradiction'], s['contra_conf'],
            utcnow(),
        ))
        conn.commit()

        print(f" cov={s['coverage']:.1f} fai={s['faithfulness']:.1f} "
              f"uniq={s['unique_contrib']:.1f} ctr={s['contradiction']:.1f}")

    conn.execute("""
      UPDATE eval_runs SET finished_at=%s WHERE eval_run_id=%s
    """, (utcnow(), eval_run_id))
    conn.commit()

    print_report(args.label, article_title, all_scores)
    print()
    print(f"eval_run_id: {eval_run_id}")
    conn.close()


if __name__ == '__main__':
    main()