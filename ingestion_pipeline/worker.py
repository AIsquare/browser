"""
RQ worker — consumes jobs from Redis, calls pipeline.run_topic_job.

Uses SimpleWorker for Windows compatibility (no os.fork, no os.wait4).
On Linux/macOS in production, switch to the default `Worker` class
for per-job process isolation.

Run:
  python worker.py

Env:
  REDIS_URL    redis connection string (rediss:// for Upstash)
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
load_dotenv()

import redis
from rq import Queue, SimpleWorker
from rq.timeouts import TimerDeathPenalty


class WindowsWorker(SimpleWorker):
    """SimpleWorker with Windows-compatible timeout handling."""
    death_penalty_class = TimerDeathPenalty


def main():
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')

    if redis_url.startswith('rediss://'):
        conn = redis.from_url(redis_url, ssl_cert_reqs=None)
    else:
        conn = redis.from_url(redis_url)

    queues = [Queue('default', connection=conn)]

    print(f"worker starting — redis={redis_url.split('@')[-1]} queues=['default']")

    worker = WindowsWorker(queues, connection=conn)
    worker.work(with_scheduler=True)


if __name__ == '__main__':
    main()