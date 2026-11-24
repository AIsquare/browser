"""
Pipeline orchestration. Called by worker.py via RQ.

Sequences the five stages and reports progress to RQ job meta.
Job-scoped: only the docs produced by this job contribute to the article.
"""
from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from db import connect
from dotenv import load_dotenv
load_dotenv()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def sha16(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]


def _set_progress(stage: str, pct: int) -> None:
    """Update RQ job meta so the API can report progress."""
    from rq import get_current_job
    job = get_current_job()
    if job:
        job.meta['stage'] = stage
        job.meta['progress'] = pct
        job.save_meta()


def run_topic_job(urls: list[str],
                  search_query: str | None = None,
                  user_id: str = 'anonymous',
                  session_id: str | None = None,
                  surface: str = 'api',
                  intent: str = 'deep_dive') -> dict:
    from rq import get_current_job
    rq_job = get_current_job()
    job_id = rq_job.id if rq_job else 'standalone'

    run_id = sha16(f"job-{job_id}-{utcnow()}")
    job_dir = Path(f'jobs/{job_id}')
    extracted_dir = job_dir / 'extracted'
    blocks_dir = job_dir / 'blocks'
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        _set_progress('crawl', 5)
        from dom_extract import run_sync as crawl
        crawl_result = crawl(
            urls=urls, out_dir=str(extracted_dir),
            run_id=run_id, verbose=False,
        )
        if not crawl_result or crawl_result.get('ok', 0) == 0:
            raise RuntimeError(
                f"Crawl produced 0 usable documents from {len(urls)} URLs"
            )

        _set_progress('parse', 35)
        from ast_ingest_v2 import run as parse
        parse(input_dir=extracted_dir, output_dir=blocks_dir)

        doc_ids = sorted(p.stem for p in blocks_dir.glob('*.json'))
        if not doc_ids:
            raise RuntimeError("parsing produced 0 block files")

        _set_progress('load', 45)
        from ingest import run as load
        load(blocks_dir=blocks_dir, run_id=run_id)

        _set_progress('manifest', 55)
        from doc_manifest import run as manifest
        manifest(run_dir=job_dir, topic=search_query or 'the topic',
                 subtopics=None, verbose=True)

        _set_progress('outline', 70)
        from outline import run as outline
        outline(run_id=run_id, doc_ids=doc_ids, verbose=False)

        _set_progress('select_sources', 75)
        from select_sources import run as select
        select(run_dir=job_dir,
               topic=search_query or 'the topic',
               intent=intent,
               verbose=False)

        _set_progress('select_atoms', 80)
        from select_atoms import run as pick
        pick(run_dir=job_dir, verbose=False)

        _set_progress('synthesize', 85)
        from synthesize import run as synth
        result = synth(
            topic=search_query,
            doc_ids=doc_ids,
            run_id=run_id,
            run_dir=job_dir,
            verbose=False,
        )

        _set_progress('synthesize', 85)

        # if not result or not result.get('markdown'):
        #     raise RuntimeError("Synthesis failed to produce an article.")
                # Change this:
        # if not result or not result.get('markdown'):
        
        # To this:
        if not result or result.get('chars', 0) == 0:
            raise RuntimeError("Synthesis failed to produce an article.")
        
        _set_progress('verify', 90)
        import json
        from collections import Counter
        from verify import evaluate_article
        from refine import fix_article
        
        with open(job_dir / 'manifests.json', 'r', encoding='utf-8') as f:
            manifests = json.load(f)
        with open(job_dir / 'selected_atoms.json', 'r', encoding='utf-8') as f:
            selected_plan = json.load(f)

        atoms_by_source = {}
        for sec in selected_plan.get('sections', []):
            for atom in sec.get('atoms', []):
                url = atom.get('source_url')
                if url:
                    atoms_by_source.setdefault(url, []).append(atom['text'])
                    
        def calculate_penalty(issue_list):
            counts = Counter(i.get("severity", "unknown") for i in issue_list)
            if counts["unknown"]: raise ValueError("Issues with unknown severity")
            return (counts["critical"], counts["major"], counts["minor"])

                # --- DRAFT 1 ---
        print("  [pipeline] Evaluating Draft 1...")
        eval_1 = evaluate_article(result.get('markdown', ''), manifests, atoms_by_source)
        
        if eval_1["evaluation_status"] != "complete":
            print("  [pipeline] 🚨 Draft 1 evaluation failed (JEV timeout). Flagging for review.")
            result['status'] = "needs_review"
        else:
            draft_1_issues = eval_1["issues"] 
            score_1 = calculate_penalty(draft_1_issues)
            
            if score_1 == (0, 0, 0):
                print("  [pipeline] ✅ Draft 1 passed all evaluations.")
                result['status'] = "completed"
            else:
                print(f"  [pipeline] ⚠️ Draft 1 penalty: {score_1}. Retrying...")
                for issue in draft_1_issues:
                    print(f"    - [{issue['severity'].upper()}] {issue['detail']}")
                    
                draft_2 = fix_article(result['markdown'], draft_1_issues, atoms_by_source)
                
                print("  [pipeline] Evaluating Draft 2...")
                eval_2 = evaluate_article(draft_2, manifests, atoms_by_source)
                
                # TOURNAMENT MATRIX
                if eval_2["evaluation_status"] != "complete":
                    print("  [pipeline] 🚨 Draft 2 evaluation failed. Preferring Draft 1.")
                    result['status'] = "needs_review"
                else:
                    score_2 = calculate_penalty(eval_2["issues"])
                    
                    if score_2 < score_1:
                        print(f"  [pipeline] ✅ Draft 2 wins! (Penalty: {score_2} vs {score_1})")
                        result['markdown'] = draft_2
                        result['status'] = "completed" if score_2 == (0,0,0) else "needs_review"
                    else:
                        print(f"  [pipeline] 🚨 Draft 2 failed to improve. Keeping Draft 1.")
                        result['status'] = "needs_review"

        # Save the final markdown to the DB
        conn = connect()
        try:
            conn.execute("UPDATE articles SET markdown = %s WHERE article_id = %s", (result['markdown'], result['article_id']))
            conn.commit()
        finally:
            conn.close()

        _set_progress('done', 100)
        return result or {}

    finally:
        try:
            pass # shutil.rmtree(job_dir)
        except Exception:
            pass

