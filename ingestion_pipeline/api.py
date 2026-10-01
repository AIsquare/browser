"""
Pipeline API — internal service called by the Node.js frontend.

Endpoints:
  POST /jobs             enqueue a pipeline job for a set of URLs
  GET  /jobs/{job_id}    status of a job
  GET  /articles/{id}    fetch a finished article
  GET  /health           liveness check

Not public-facing. Node is the gate. No auth here.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv()

import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job

from db import connect, connect_signal


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


app = FastAPI(title="Pipeline API")

redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
redis_conn = redis.from_url(
    redis_url,
    socket_timeout=30,
    socket_connect_timeout=30,
    ssl_cert_reqs=None if redis_url.startswith('rediss://') else 'required',
)
job_queue = Queue('default', connection=redis_conn)


# ----------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------

class JobRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1)
    search_query: str | None = None
    user_id: str = 'anonymous'
    session_id: str | None = None
    surface: str = 'web'


class JobResponse(BaseModel):
    job_id: str
    status: str


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _canonical(url: str) -> tuple[str, str]:
    from dom_extract import canonicalize, sha16
    c = canonicalize(url)
    return c, sha16(c)


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().lstrip('www.')


def _record_selection_events(job_id: str, req: JobRequest) -> None:
    """Write one selection_events row per URL to the signal store."""
    conn = connect_signal()
    try:
        for url in req.urls:
            canonical_url, url_id = _canonical(url)
            conn.execute("""
              INSERT INTO selection_events
                (event_id, url_id, url, canonical_url, domain,
                 search_query, topic_id, user_id, session_id,
                 selected_at, surface, metadata_json)
              VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                uuid.uuid4().hex, url_id, url, canonical_url,
                _domain(canonical_url),
                req.search_query, job_id, req.user_id, req.session_id,
                utcnow(), req.surface,
                json.dumps({'job_id': job_id}),
            ))
        conn.commit()
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------

@app.post("/jobs", response_model=JobResponse)
def create_job(req: JobRequest):
    job_id = uuid.uuid4().hex[:16]

    try:
        _record_selection_events(job_id, req)
    except Exception as e:
        raise HTTPException(500, f"failed to record selection: {e}")

    try:
        from pipeline import run_topic_job
        rq_job = job_queue.enqueue(
            run_topic_job,
            job_id=job_id,
            urls=req.urls,
            search_query=req.search_query,
            user_id=req.user_id,
            session_id=req.session_id,
            surface=req.surface,
            job_timeout='30m',
            result_ttl=7 * 24 * 3600,
            failure_ttl=7 * 24 * 3600,
        )
    except Exception as e:
        raise HTTPException(500, f"failed to enqueue: {e}")

    return JobResponse(job_id=rq_job.id, status='queued')


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        status = job.get_status()
        out = {
            'job_id': job_id,
            'status': status,
            'progress': job.meta.get('progress', 0),
            'stage': job.meta.get('stage'),
            'error': None,
            'article_id': None,
        }

        if status == 'finished':
            result = job.result or {}
            out['article_id'] = result.get('article_id')
            out['trace_id'] = result.get('trace_id')
            out['progress'] = 100
        elif status == 'failed':
            out['error'] = str(job.exc_info or 'unknown error')

        return out
    except NoSuchJobError:
        raise HTTPException(404, "job not found")
    except redis.exceptions.RedisError as e:
        return {
            'job_id': job_id,
            'status': 'unknown',
            'progress': 0,
            'stage': None,
            'error': None,
            'article_id': None,
            'transient_error': str(e),
        }


@app.get("/articles/{article_id}")
def get_article(article_id: str):
    conn = connect()
    try:
        row = conn.execute("""
          SELECT article_id, title, markdown, model, created_at
          FROM articles WHERE article_id = %s
        """, (article_id,)).fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(404, "article not found")

    return dict(row)


@app.get("/health")
def health():
    try:
        redis_conn.ping()
        redis_ok = True
    except Exception:
        redis_ok = False

    try:
        c = connect()
        c.execute("SELECT 1")
        c.close()
        db_ok = True
    except Exception:
        db_ok = False

    return {'ok': redis_ok and db_ok, 'redis': redis_ok, 'db': db_ok, 'time': utcnow()}