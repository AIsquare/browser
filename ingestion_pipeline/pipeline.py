"""
Pipeline orchestration. Called by worker.py via RQ.
Sequences the five stages and reports progress to RQ job meta.
"""
from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from rq import get_current_job


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def sha16(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]


def _set_progress(stage: str, pct: int) -> None:
    """Update RQ job meta so the API can report progress."""
    job = get_current_job()
    if job:
        job.meta['stage'] = stage
        job.meta['progress'] = pct
        job.save_meta()


def run_topic_job(urls: list[str],
                  search_query: str | None = None,
                  user_id: str = 'anonymous',
                  session_id: str | None = None,
                  surface: str = 'api') -> dict:
    """
    Orchestrate the full pipeline for one job.
    Returns {'article_id', 'trace_id', 'chars', 'tokens', 'cost'}.
    """
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
        crawl(urls=urls, out_dir=str(extracted_dir), run_id=run_id, verbose=False)

        _set_progress('parse', 40)
        from ast_ingest_v2 import run as parse
        parse(input_dir=extracted_dir, output_dir=blocks_dir)

        _set_progress('load', 55)
        from ingest import run as load
        load(blocks_dir=blocks_dir, run_id=run_id)

        _set_progress('outline', 70)
        from outline import run as outline
        outline(run_id=run_id, verbose=False)

        _set_progress('synthesize', 85)
        from synthesize import run as synth
        result = synth(topic=None, run_id=run_id, verbose=False)

        _set_progress('done', 100)
        return result or {}

    finally:
        try:
            shutil.rmtree(job_dir)
        except Exception:
            pass