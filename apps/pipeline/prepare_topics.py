"""
Convert flat topic files into the folder structure run_tests.py expects.

Input:  <topics_dir>/*.txt          (each file = one topic, URLs inside)
Output: test_run/topics/<slug>/urls.txt

Handles:
  - files with one URL per line
  - files with blank lines, comments (#), or other text
  - duplicate URLs within the same file (deduped)
  - URL lines prefixed with bullets, numbers, or markdown

Usage:
  python prepare_topics.py --from "C:\\path\\to\\topic_files"
  python prepare_topics.py --from "C:\\path\\to\\topic_files" --out test_run/topics
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


URL_RE = re.compile(r'https?://[^\s\)\]\>",\']+')


def slugify(name: str) -> str:
    """The Psychology of Decision-Making -> the_psychology_of_decision_making"""
    s = name.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '_', s)
    return s.strip('_')


def extract_urls(text: str) -> list[str]:
    """Find every URL in the file, in order, deduped."""
    seen = set()
    out = []
    for match in URL_RE.findall(text):
        # strip trailing punctuation that regex may have caught
        url = match.rstrip('.,;:!?)')
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='src', required=True,
                    help='folder containing The Psychology of Decision-Making.txt etc.')
    ap.add_argument('--out', default='test_run/topics',
                    help='output folder (default test_run/topics)')
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        raise SystemExit(f"source folder not found: {src}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    txt_files = sorted(src.glob('*.txt'))
    if not txt_files:
        raise SystemExit(f"no .txt files found in {src}")

    print(f"source : {src}")
    print(f"target : {out}")
    print(f"files  : {len(txt_files)}")
    print()

    total_urls = 0
    skipped = []

    for f in txt_files:
        text = f.read_text(encoding='utf-8', errors='replace')
        urls = extract_urls(text)

        if not urls:
            skipped.append(f.name)
            print(f"  [skip] {f.name} (no URLs found)")
            continue

        slug = slugify(f.stem)
        target_dir = out / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / 'urls.txt').write_text('\n'.join(urls) + '\n', encoding='utf-8')

        print(f"  {slug:50s} {len(urls):3d} urls")
        total_urls += len(urls)

    print()
    print(f"topics written : {len(txt_files) - len(skipped)}")
    print(f"urls total     : {total_urls}")
    if skipped:
        print(f"skipped        : {len(skipped)}")
        for s in skipped:
            print(f"  - {s}")
    print()
    print(f"next: python run_tests.py --topics {out}")


if __name__ == '__main__':
    main()