"""
Batch test harness. Runs the pipeline on every topic sequentially.

  test_run/topics/<slug>/urls.txt

Produces:
  test_run/results/<slug>/draft.md
  test_run/results/<slug>/timing.json
  test_run/results/<slug>/errors.txt
  test_run/summary.json

Resume: topics with an existing draft.md are skipped unless --force.

Usage:
  python run_tests.py
  python run_tests.py --topics test_run/topics --results test_run/results
  python run_tests.py --force                 # re-run all
  python run_tests.py --only <slug>           # run one
  python run_tests.py --from <slug>           # run one and everything after
  python run_tests.py --report                # don't run, just summarize
"""
from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PIPELINE_DIR = Path(__file__).parent.resolve()
COORDINATOR_SCHEMA = PIPELINE_DIR / 'coordinator_schema.sql'  # optional
PIPELINE_SCHEMA = PIPELINE_DIR / 'schema.sql'

# Stages in order. Each is (name, script, extra_args, timeout_seconds).
STAGES = [
    ('crawl',      'dom_extract.py',    None,                 600),
    ('parse',      'ast_ingest_v2.py',  None,                 300),
    ('load',       'ingest.py',         None,                 300),
    ('cluster',    'cluster.py',        None,                 120),
    ('outline',    'outline.py',        None,                 600),
    ('synthesize', 'synthesize.py',     None,                1200),
]


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def discover_topics(topics_dir: Path) -> list[Path]:
    if not topics_dir.exists():
        return []
    topics = []
    for d in sorted(topics_dir.iterdir()):
        if d.is_dir() and (d / 'urls.txt').exists():
            topics.append(d)
    return topics


def init_db(db_path: Path):
    """Create a fresh pipeline DB from schema.sql."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    sql = PIPELINE_SCHEMA.read_text(encoding='utf-8').replace('\xa0', ' ')
    conn.executescript(sql)
    conn.commit()
    conn.close()


def run_stage(name: str, script: str, extra_args, job_dir: Path,
              db_path: Path, timeout: int) -> dict:
    """Run one stage. Returns {ok, elapsed, error, stdout_tail}."""
    env = os.environ.copy()
    env['PIPELINE_DB_PATH'] = str(db_path.resolve())
    env['PYTHONIOENCODING'] = 'utf-8'

    cmd = [sys.executable, str(PIPELINE_DIR / script)]
    if extra_args:
        cmd.extend(extra_args)

    t0 = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            cwd=str(job_dir),
            env=env,
            capture_output=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
        )
        elapsed = time.monotonic() - t0
        if result.returncode != 0:
            return {
                'ok': False,
                'elapsed': round(elapsed, 2),
                'error': f"exit {result.returncode}",
                'stderr_tail': (result.stderr or '')[-1500:],
                'stdout_tail': (result.stdout or '')[-500:],
            }
        return {
            'ok': True,
            'elapsed': round(elapsed, 2),
            'stdout_tail': (result.stdout or '')[-500:],
        }
    except subprocess.TimeoutExpired:
        return {
            'ok': False,
            'elapsed': round(time.monotonic() - t0, 2),
            'error': f"timeout after {timeout}s",
        }
    except Exception as e:
        return {
            'ok': False,
            'elapsed': round(time.monotonic() - t0, 2),
            'error': str(e),
        }


def run_topic(topic_dir: Path, results_root: Path, force: bool) -> dict:
    slug = topic_dir.name
    out_dir = results_root / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    draft = out_dir / 'draft.md'
    timing_path = out_dir / 'timing.json'
    errors_path = out_dir / 'errors.txt'

    # Resume: skip if done
    if draft.exists() and not force:
        print(f"  [skip] {slug} (already done, use --force to rerun)")
        existing = {}
        if timing_path.exists():
            existing = json.loads(timing_path.read_text())
        return {
            'slug': slug,
            'status': 'skipped',
            'duration': existing.get('total_seconds', 0),
            'stages': existing.get('stages', {}),
            'article_chars': draft.stat().st_size,
        }

    # Fresh start
    if force and out_dir.exists():
        shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)

    print(f"\n{'='*70}")
    print(f"TOPIC: {slug}")
    print(f"URLs:  {(topic_dir / 'urls.txt').read_text().count(chr(10))+1}")
    print(f"{'='*70}")

    # Copy urls into the job dir
    shutil.copy(topic_dir / 'urls.txt', out_dir / 'urls.txt')

    db_path = out_dir / 'corpus.db'
    if not db_path.exists():
        init_db(db_path)

    stages_result = {}
    errors = []
    overall_ok = True
    topic_start = time.monotonic()

    for name, script, extra, timeout in STAGES:
        # Special case for the crawler — pass the urls file
        args = ['--urls', 'urls.txt'] if script == 'dom_extract.py' else extra

        print(f"  [{name:11s}] running ...", end='', flush=True)
        r = run_stage(name, script, args, out_dir, db_path, timeout)

        stages_result[name] = {
            'ok': r['ok'],
            'elapsed': r['elapsed'],
        }

        if r['ok']:
            print(f" ok ({r['elapsed']:.1f}s)")
        else:
            print(f" FAILED ({r['elapsed']:.1f}s): {r.get('error')}")
            overall_ok = False
            errors.append({
                'stage': name,
                'error': r.get('error'),
                'stderr_tail': r.get('stderr_tail', ''),
            })
            break

    total_seconds = round(time.monotonic() - topic_start, 2)

    # Save timing
    timing = {
        'slug': slug,
        'started_at': utcnow(),
        'total_seconds': total_seconds,
        'overall_ok': overall_ok,
        'stages': stages_result,
    }
    timing_path.write_text(json.dumps(timing, indent=2))

    # Save errors
    if errors:
        errors_path.write_text(json.dumps(errors, indent=2))

    # Read article length
    article_chars = draft.stat().st_size if draft.exists() else 0

    return {
        'slug': slug,
        'status': 'done' if overall_ok else 'failed',
        'duration': total_seconds,
        'stages': stages_result,
        'article_chars': article_chars,
        'errors': errors,
    }


def write_summary(results: list[dict], summary_path: Path):
    """Aggregate and write test_run/summary.json."""
    done = [r for r in results if r['status'] == 'done']
    failed = [r for r in results if r['status'] == 'failed']
    skipped = [r for r in results if r['status'] == 'skipped']

    total_duration = sum(r.get('duration', 0) for r in results)

    per_stage = {}
    for r in results:
        for stage, info in (r.get('stages') or {}).items():
            per_stage.setdefault(stage, {'count': 0, 'failed': 0, 'total_s': 0.0})
            per_stage[stage]['count'] += 1
            per_stage[stage]['total_s'] += info.get('elapsed', 0)
            if not info.get('ok'):
                per_stage[stage]['failed'] += 1

    for stage, info in per_stage.items():
        info['avg_s'] = round(info['total_s'] / max(info['count'], 1), 2)
        info['total_s'] = round(info['total_s'], 2)

    summary = {
        'generated_at': utcnow(),
        'total_topics': len(results),
        'done': len(done),
        'failed': len(failed),
        'skipped': len(skipped),
        'total_duration_s': round(total_duration, 2),
        'per_stage': per_stage,
        'topics': [
            {
                'slug': r['slug'],
                'status': r['status'],
                'duration': r.get('duration', 0),
                'article_chars': r.get('article_chars', 0),
                'errors': [e['error'] for e in r.get('errors', [])],
            }
            for r in results
        ],
    }

    summary_path.write_text(json.dumps(summary, indent=2))
    return summary


def print_report(summary: dict):
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  topics      : {summary['total_topics']}")
    print(f"  done        : {summary['done']}")
    print(f"  failed      : {summary['failed']}")
    print(f"  skipped     : {summary['skipped']}")
    print(f"  total time  : {summary['total_duration_s']:.0f}s "
          f"({summary['total_duration_s']/60:.1f} min)")
    print()
    print("  per-stage averages:")
    for stage, info in summary['per_stage'].items():
        marker = '' if info['failed'] == 0 else f"  ({info['failed']} failed)"
        print(f"    {stage:11s} {info['avg_s']:7.1f}s  ({info['count']} runs){marker}")

    if summary['failed']:
        print()
        print("  FAILED TOPICS:")
        for t in summary['topics']:
            if t['status'] == 'failed':
                print(f"    {t['slug']}")
                for e in t['errors']:
                    print(f"      - {e}")

    print()
    print("  longest articles:")
    done = sorted(
        [t for t in summary['topics'] if t['status'] == 'done'],
        key=lambda t: -t['article_chars'],
    )
    for t in done[:5]:
        print(f"    {t['slug']:40s} {t['article_chars']:>7d} chars")

    print()
    print("  shortest articles:")
    for t in reversed(done[-5:]):
        print(f"    {t['slug']:40s} {t['article_chars']:>7d} chars")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--topics', default='test_run/topics')
    ap.add_argument('--results', default='test_run/results')
    ap.add_argument('--summary', default='test_run/summary.json')
    ap.add_argument('--force', action='store_true',
                    help='re-run topics that already have draft.md')
    ap.add_argument('--only', help='run a single topic by slug')
    ap.add_argument('--from', dest='from_slug',
                    help='start from this slug alphabetically')
    ap.add_argument('--report', action='store_true',
                    help='skip running, just print the report from summary.json')
    args = ap.parse_args()

    topics_dir = Path(args.topics)
    results_root = Path(args.results)
    summary_path = Path(args.summary)

    if args.report:
        if not summary_path.exists():
            print(f"no summary at {summary_path}")
            sys.exit(1)
        print_report(json.loads(summary_path.read_text()))
        return

    topics = discover_topics(topics_dir)
    if not topics:
        print(f"no topics found in {topics_dir}/")
        sys.exit(1)

    if args.only:
        topics = [t for t in topics if t.name == args.only]
        if not topics:
            print(f"topic not found: {args.only}")
            sys.exit(1)

    if args.from_slug:
        names = [t.name for t in topics]
        if args.from_slug not in names:
            print(f"slug not found: {args.from_slug}")
            sys.exit(1)
        idx = names.index(args.from_slug)
        topics = topics[idx:]

    print(f"Topics  : {len(topics)}")
    print(f"Results : {results_root}/")
    print(f"Force   : {args.force}")
    print()

    # Rough estimate: crawl+parse+load+outline+synthesize per topic
    estimate_min = len(topics) * 2
    print(f"estimated total time: {estimate_min}–{estimate_min*2} minutes")
    print()

    results_root.mkdir(parents=True, exist_ok=True)

    results = []
    for i, topic_dir in enumerate(topics, 1):
        print(f"[{i}/{len(topics)}]", end='')
        try:
            r = run_topic(topic_dir, results_root, args.force)
            results.append(r)
        except KeyboardInterrupt:
            print("\nstopped by user.")
            break

    summary = write_summary(results, summary_path)
    print_report(summary)
    print(f"\nsummary written: {summary_path}")


if __name__ == '__main__':
    main()