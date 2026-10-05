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
                 subtopics=None, verbose=False)

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

        _set_progress('done', 100)
        return result or {}

    finally:
        try:
            shutil.rmtree(job_dir)
        except Exception:
            pass