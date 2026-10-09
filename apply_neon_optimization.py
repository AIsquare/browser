from __future__ import annotations

"""Apply a targeted Neon-ingestion and crawler connection fix.

Run from either the repository root or apps/pipeline:
    python apply_neon_optimization.py

The script makes .bak copies, checks every anchor before changing either file,
and refuses to overwrite files if the expected source layout is missing.
"""

from pathlib import Path
import shutil

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = next(
    (
        parent
        for parent in (SCRIPT_DIR, *SCRIPT_DIR.parents)
        if (parent / "apps" / "pipeline" / "ingest.py").is_file()
    ),
    SCRIPT_DIR,
)
PIPELINE = ROOT / "apps" / "pipeline"
INGEST = PIPELINE / "ingest.py"
CRAWLER = PIPELINE / "dom_extract.py"


def replace_between(text: str, start: str, end: str, replacement: str, filename: str) -> str:
    first = text.find(start)
    if first < 0:
        raise RuntimeError(f"Could not find start anchor in {filename}: {start!r}")
    last = text.find(end, first + len(start))
    if last < 0:
        raise RuntimeError(f"Could not find end anchor in {filename}: {end!r}")
    return text[:first] + replacement + text[last:]


def insert_before_once(text: str, anchor: str, insert: str, filename: str) -> str:
    if text.count(anchor) != 1:
        raise RuntimeError(f"Expected exactly one insertion anchor in {filename}: {anchor!r}")
    return text.replace(anchor, insert + anchor, 1)


def patch_ingest(text: str) -> str:
    helper_anchor = "\ndef load_doc(conn, ast: dict, run_id: str | None = None) -> dict:\n"
    helper = '''\n\n# Psycopg 3's executemany pipelines parameterized statements. Bounded batches\n# avoid one network round-trip per row while keeping Python memory use modest.\nDB_WRITE_BATCH_SIZE = 500\n\ndef _executemany_batched(conn, sql: str, rows, batch_size: int = DB_WRITE_BATCH_SIZE) -> int:\n    """Execute parameter rows in bounded batches; return the number of rows."""\n    total = 0\n    batch = []\n    with conn.cursor() as cur:\n        for row in rows:\n            batch.append(row)\n            if len(batch) >= batch_size:\n                cur.executemany(sql, batch)\n                total += len(batch)\n                batch.clear()\n        if batch:\n            cur.executemany(sql, batch)\n            total += len(batch)\n    return total\n\n'''
    if "def _executemany_batched(" not in text:
        text = insert_before_once(text, helper_anchor, helper, "ingest.py")

    batched_rows = '''    # -- sections --\n    sections = derive_sections(blocks, doc_id)\n    _executemany_batched(conn, """\n      INSERT INTO sections\n        (section_id, doc_id, parent_section_id, heading, heading_level,\n         heading_path, first_block_id, last_block_id, token_count,\n         char_start, char_end, is_boilerplate)\n      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\n    """, (\n        (s['section_id'], s['doc_id'], s['parent_section_id'],\n         s['heading'], s['heading_level'], s['heading_path'],\n         s['first_block_id'], s['last_block_id'], s['token_count'],\n         s['char_start'], s['char_end'], s['is_boilerplate'])\n        for s in sections\n    ))\n\n    # -- blocks --\n    _executemany_batched(conn, """\n      INSERT INTO blocks\n        (block_id, doc_id, section_id, parent_block_id, prev_block_id, next_block_id,\n         list_id, block_type, heading_path, order_index, char_start, char_end,\n         char_count, token_count, text, raw_text, content_hash,\n         is_orphan, is_boilerplate, is_math, is_footnote, language, extra_json)\n      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\n    """, (\n        (b['block_id'], doc_id, b.get('section_id'),\n         b.get('parent_block_id'), b.get('prev_block_id'), b.get('next_block_id'),\n         b.get('list_id'), b['block_type'], json.dumps(b.get('heading_path', [])),\n         b['position_index'], b['char_start'], b['char_end'],\n         b.get('char_count'), b.get('token_count'), b.get('text', ''),\n         b.get('content', ''), b.get('content_hash'),\n         int(bool(b.get('is_orphan'))), int(bool(b.get('is_boilerplate'))),\n         int(bool(b.get('is_math'))), int(bool(b.get('is_footnote'))),\n         b.get('language'), json.dumps({'language': b.get('language')}) if b.get('language') else None)\n        for b in blocks\n    ))\n\n    # -- atoms --\n    def atom_rows():\n        for b in blocks:\n            if b.get('is_boilerplate'):\n                continue\n            for i, (atype, atom_text) in enumerate(atomize_block(b)):\n                if not atom_text:\n                    continue\n                atom_id = sha16(f"{b['block_id']}|{i}|{atom_text}")\n                yield (\n                    atom_id, b['block_id'], doc_id, b.get('section_id'),\n                    atype, i, b['char_start'], b['char_end'],\n                    count_tokens(atom_text), atom_text, sha16(atom_text),\n                )\n\n    atom_count = _executemany_batched(conn, """\n      INSERT INTO atoms\n        (atom_id, block_id, doc_id, section_id, atom_type,\n         order_index, char_start, char_end, token_count, text, content_hash)\n      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\n      ON CONFLICT (atom_id) DO UPDATE SET\n        block_id     = EXCLUDED.block_id,\n        doc_id       = EXCLUDED.doc_id,\n        section_id   = EXCLUDED.section_id,\n        atom_type    = EXCLUDED.atom_type,\n        order_index  = EXCLUDED.order_index,\n        char_start   = EXCLUDED.char_start,\n        char_end     = EXCLUDED.char_end,\n        token_count  = EXCLUDED.token_count,\n        text         = EXCLUDED.text,\n        content_hash = EXCLUDED.content_hash\n    """, atom_rows())\n\n    # -- images --\n    def image_rows():\n        for b in blocks:\n            for img in b.get('image_refs') or []:\n                url = img.get('url')\n                if not url:\n                    continue\n                yield (\n                    sha16(url), b['block_id'], doc_id, b.get('section_id'),\n                    url, img.get('alt', ''), now,\n                )\n\n    _executemany_batched(conn, """\n      INSERT INTO images\n        (image_id, block_id, doc_id, section_id, url, alt, created_at)\n      VALUES (%s, %s, %s, %s, %s, %s, %s)\n      ON CONFLICT (image_id) DO NOTHING\n    """, image_rows())\n\n    # -- links --\n    def link_rows():\n        for b in blocks:\n            for i, lnk in enumerate(b.get('links') or []):\n                url = lnk.get('url')\n                if not url:\n                    continue\n                yield (\n                    sha16(f"{b['block_id']}|{i}|{url}"), b['block_id'], doc_id,\n                    url, lnk.get('text', ''), int(url.startswith('/') or source_url in url),\n                    0, i,\n                )\n\n    _executemany_batched(conn, """\n      INSERT INTO links\n        (link_id, block_id, doc_id, url, text, is_internal, is_citation, order_index)\n      VALUES (%s, %s, %s, %s, %s, %s, %s, %s)\n      ON CONFLICT (link_id) DO UPDATE SET\n        block_id    = EXCLUDED.block_id,\n        doc_id      = EXCLUDED.doc_id,\n        url         = EXCLUDED.url,\n        text        = EXCLUDED.text,\n        is_internal = EXCLUDED.is_internal,\n        is_citation = EXCLUDED.is_citation,\n        order_index = EXCLUDED.order_index\n    """, link_rows())\n\n'''
    text = replace_between(
        text,
        "    # -- sections --\n",
        "    # -- doc_stages --\n",
        batched_rows,
        "ingest.py",
    )

    new_run = '''def run(blocks_dir: Path | None = None,\n        run_id: str | None = None) -> dict:\n    """\n    Load block JSONs into Neon using batched row writes. Each document is its\n    own transaction so a failed document rolls back cleanly without holding a\n    transaction open for the entire run.\n    """\n    src = Path(blocks_dir) if blocks_dir else BLOCKS_DIR\n    json_files = sorted(src.glob('*.json'))\n\n    if not json_files:\n        print(f"no JSON files in {src}")\n        return {'docs': 0, 'blocks': 0, 'atoms': 0, 'sections': 0, 'run_id': None}\n\n    if run_id is None:\n        run_id = sha16(f"ingest-{utcnow()}")\n\n    conn = connect()\n    total = {'docs': 0, 'blocks': 0, 'atoms': 0, 'sections': 0}\n    try:\n        conn.execute("""\n          INSERT INTO pipeline_runs (run_id, started_at, status, stages_json)\n          VALUES (%s, %s, 'running', %s)\n          ON CONFLICT (run_id) DO NOTHING\n        """, (run_id, utcnow(), json.dumps(['load'])))\n        conn.commit()\n\n        for jf in json_files:\n            try:\n                ast = json.loads(jf.read_text(encoding='utf-8'))\n            except Exception as e:\n                print(f"skip {jf.name}: {e}")\n                continue\n\n            try:\n                result = load_doc(conn, ast, run_id)\n                conn.commit()\n            except Exception:\n                conn.rollback()\n                try:\n                    conn.execute(\n                        "UPDATE pipeline_runs SET status='failed', finished_at=%s WHERE run_id=%s",\n                        (utcnow(), run_id),\n                    )\n                    conn.commit()\n                except Exception:\n                    conn.rollback()\n                raise\n\n            total['docs'] += 1\n            total['blocks'] += result['blocks']\n            total['atoms'] += result['atoms']\n            total['sections'] += result['sections']\n            print(f"{result['doc_id'][:55]:55s}  "\n                  f"{result['blocks']:4d} blocks  "\n                  f"{result['atoms']:4d} atoms  "\n                  f"{result['sections']:3d} sections")\n\n        conn.execute(\n            "UPDATE pipeline_runs SET status='completed', finished_at=%s WHERE run_id=%s",\n            (utcnow(), run_id),\n        )\n        conn.commit()\n    finally:\n        conn.close()\n\n    print()\n    print(f"loaded: {total['docs']} docs, "\n          f"{total['blocks']} blocks, "\n          f"{total['atoms']} atoms, "\n          f"{total['sections']} sections")\n    total['run_id'] = run_id\n    return total\n\n\n'''
    text = replace_between(text, "def run(blocks_dir:", "def main():\n", new_run, "ingest.py")
    return text


REJECT_HELPER = '''def _record_url_reject(url: str, reason: str, status=None, detail=None) -> None:\n    """Persist a rejected URL in its own short transaction."""\n    conn = connect()\n    try:\n        url_id = ensure_url(conn, url)\n        record_reject(conn, url_id, url, reason, status, detail)\n        conn.commit()\n    finally:\n        conn.close()\n\n\n'''


def patch_crawler(text: str) -> str:
    marker = "# =====================================================================\n# Per-doc processing\n# =====================================================================\n"
    if "def _record_url_reject(" not in text:
        text = insert_before_once(text, marker, REJECT_HELPER, "dom_extract.py")

    process_one = '''async def process_one(\n    url: str,\n    run_id: str,\n    out_dir: Path,\n    page,\n    timeout_ms: int,\n    max_retries: int,\n) -> dict:\n    """Fetch/extract one URL, then persist its results in an isolated transaction."""\n    slug = slugify(url)\n    raw_path = out_dir / f"{slug}.raw.html"\n    md_path = out_dir / f"{slug}.md"\n    json_path = out_dir / f"{slug}.json"\n\n    html = None\n    status = None\n    error = None\n    final_url = url\n    headers: dict = {}\n\n    # Do not open a database transaction while waiting for the network.\n    for attempt in range(max_retries + 1):\n        if page is not None and HAS_PLAYWRIGHT:\n            html, status, final_url, headers, error = await fetch_with_playwright(page, url, timeout_ms)\n        else:\n            html, status, final_url, headers, error = await fetch_plain(url, timeout_ms)\n\n        outcome, reason = classify_fetch(status, html, error)\n        if outcome == 'ok':\n            break\n        if attempt < max_retries:\n            await asyncio.sleep(1.5 ** attempt)\n        else:\n            _record_url_reject(url, reason or 'unknown', status, error)\n            return {'url': url, 'status': 'rejected', 'reason': reason}\n\n    raw_path.write_text(html, encoding='utf-8')\n    soup = BeautifulSoup(html, 'lxml')\n    meta = extract_metadata(soup, url)\n    region = find_content_region(soup)\n    blocks = extract_blocks(region, url)\n    markdown = blocks_to_markdown(blocks)\n\n    if markdown.strip():\n        fm_lines = [f"source_url: {url}"]\n        if meta.get('title'):\n            fm_lines.append(f"title: {json.dumps(meta['title'])}")\n        if meta.get('author'):\n            fm_lines.append(f"author: {json.dumps(meta['author'])}")\n        if meta.get('published_at'):\n            fm_lines.append(f"published_at: {json.dumps(meta['published_at'])}")\n        if meta.get('language'):\n            fm_lines.append(f"language: {meta['language']}")\n        if meta.get('description'):\n            fm_lines.append(f"description: {json.dumps(meta['description'])}")\n        if meta.get('updated_at'):\n            fm_lines.append(f"updated_at: {json.dumps(meta['updated_at'])}")\n        if meta.get('source_type') and meta['source_type'] != 'unknown':\n            fm_lines.append(f"source_type: {meta['source_type']}")\n\n        frontmatter = "---\\n" + "\\n".join(fm_lines) + "\\n---\\n\\n"\n        md_path.write_text(\n            f"{frontmatter}# Source\\n\\n{url}\\n\\n---\\n\\n{markdown}",\n            encoding='utf-8',\n        )\n        json_path.write_text(json.dumps({\n            'source': url,\n            'metadata': meta,\n            'blocks': blocks,\n        }, indent=2, ensure_ascii=False), encoding='utf-8')\n\n    # This connection belongs only to this URL; other crawl tasks never commit\n    # or roll back its transaction. Database activity starts after fetching.\n    conn = connect()\n    try:\n        url_id = ensure_url(conn, url)\n        record_fetch(conn, url_id, url, status, html, str(raw_path), final_url, headers)\n\n        if not markdown.strip():\n            record_reject(conn, url_id, url, 'no_content_extracted', status, None)\n            conn.commit()\n            return {'url': url, 'status': 'rejected', 'reason': 'no_content_extracted'}\n\n        conn.execute("""\n          UPDATE url_queue SET status='fetched', updated_at=%s WHERE url_id=%s\n        """, (utcnow(), url_id))\n        record_doc_stage(conn, run_id, slug, 'fetch', 'ok',\n                         counts={'bytes': len(html), 'status': status})\n        record_doc_stage(conn, run_id, slug, 'extract', 'ok',\n                         counts={'blocks': len(blocks), 'chars': len(markdown)})\n        conn.commit()\n    finally:\n        conn.close()\n\n    return {\n        'url': url,\n        'status': 'ok',\n        'blocks': len(blocks),\n        'chars': len(markdown),\n        'title': meta.get('title'),\n    }\n\n\n'''
    text = replace_between(
        text,
        "async def process_one(\n",
        "# =====================================================================\n# Main\n# =====================================================================\n",
        process_one,
        "dom_extract.py",
    )

    run_func = '''async def run(urls: str | Path | list[str],\n              out_dir: str | Path = 'extracted',\n              run_id: str | None = None,\n              rate_limit: float = 2.0,\n              timeout: int = 60000,\n              max_retries: int = 2,\n              concurrency: int = 4,\n              no_js: bool = False,\n              verbose: bool = True) -> dict:\n    """Crawl URLs concurrently while persisting each URL in its own transaction."""\n    if isinstance(urls, (str, Path)):\n        urls_path = Path(urls)\n        if not urls_path.exists():\n            raise FileNotFoundError(f"url file not found: {urls_path}")\n        url_list = [\n            u.strip() for u in urls_path.read_text(encoding='utf-8').splitlines()\n            if u.strip() and u.startswith(('http://', 'https://'))\n        ]\n    else:\n        url_list = [u for u in urls if u.startswith(('http://', 'https://'))]\n\n    if verbose:\n        print(f"loaded {len(url_list)} urls")\n\n    out_path = Path(out_dir)\n    out_path.mkdir(parents=True, exist_ok=True)\n    if run_id is None:\n        run_id = sha16(f"crawl-{utcnow()}-{len(url_list)}")\n\n    # Use a short, dedicated connection for run metadata, never the per-URL tasks.\n    conn = connect()\n    try:\n        ensure_run(conn, run_id, None, len(url_list))\n        conn.commit()\n    finally:\n        conn.close()\n\n    last_hit: dict[str, float] = defaultdict(float)\n    domain_locks: dict[str, asyncio.Lock] = {}\n    sem = asyncio.Semaphore(concurrency)\n\n    def _domain_lock(domain: str) -> asyncio.Lock:\n        if domain not in domain_locks:\n            domain_locks[domain] = asyncio.Lock()\n        return domain_locks[domain]\n\n    async def gate(url: str):\n        p = urlparse(url)\n        domain = domain_of(url)\n        parser = await get_robots(p.scheme or 'https', domain, timeout)\n        if not robots_can_fetch(parser, url, USER_AGENT):\n            return False, 'robots_disallow'\n\n        site_delay = robots_crawl_delay(parser, USER_AGENT)\n        effective_delay = max(rate_limit, site_delay or 0.0)\n        async with _domain_lock(domain):\n            now = time.monotonic()\n            wait = effective_delay - (now - last_hit[domain])\n            if wait > 0:\n                await asyncio.sleep(wait)\n            last_hit[domain] = time.monotonic()\n        return True, None\n\n    results = []\n\n    if no_js or not HAS_PLAYWRIGHT:\n        if not HAS_PLAYWRIGHT and not no_js and verbose:\n            print("playwright not installed — falling back to plain HTTP")\n\n        async def fetch_task(url: str):\n            try:\n                async with sem:\n                    allowed, reason = await gate(url)\n                    if not allowed:\n                        _record_url_reject(url, reason or 'robots_disallow', None, None)\n                        return url, {'url': url, 'status': 'rejected', 'reason': reason}\n                    result = await process_one(\n                        url, run_id, out_path, None, timeout, max_retries,\n                    )\n                    return url, result\n            except Exception as e:\n                return url, {'url': url, 'status': 'error', 'reason': str(e)}\n\n        tasks = [asyncio.create_task(fetch_task(u)) for u in url_list]\n        for coro in asyncio.as_completed(tasks):\n            url, result = await coro\n            results.append(result)\n            if verbose:\n                print(f"  {result['status']:9s}  {url[:80]}")\n    else:\n        async with async_playwright() as p:\n            browser = await p.chromium.launch(headless=True)\n            context = await browser.new_context(user_agent=USER_AGENT)\n            try:\n                async def fetch_task(url: str):\n                    try:\n                        async with sem:\n                            allowed, reason = await gate(url)\n                            if not allowed:\n                                _record_url_reject(url, reason or 'robots_disallow', None, None)\n                                return url, {'url': url, 'status': 'rejected', 'reason': reason}\n                            page = await context.new_page()\n                            try:\n                                result = await process_one(\n                                    url, run_id, out_path, page, timeout, max_retries,\n                                )\n                                return url, result\n                            finally:\n                                await page.close()\n                    except Exception as e:\n                        return url, {'url': url, 'status': 'error', 'reason': str(e)}\n\n                tasks = [asyncio.create_task(fetch_task(u)) for u in url_list]\n                for coro in asyncio.as_completed(tasks):\n                    url, result = await coro\n                    results.append(result)\n                    if verbose:\n                        print(f"  {result['status']:9s}  {url[:80]}")\n            finally:\n                await browser.close()\n\n    ok = sum(1 for result in results if result['status'] == 'ok')\n    rejected = sum(1 for result in results if result['status'] == 'rejected')\n    errored = sum(1 for result in results if result['status'] == 'error')\n    if verbose:\n        print(f"\\ndone: {ok} ok, {rejected} rejected, {errored} errored, {len(results)} total")\n\n    conn = connect()\n    try:\n        conn.execute(\n            "UPDATE pipeline_runs SET status='completed', finished_at=%s WHERE run_id=%s",\n            (utcnow(), run_id),\n        )\n        conn.commit()\n    finally:\n        conn.close()\n\n    return {\n        'ok': ok,\n        'rejected': rejected,\n        'errored': errored,\n        'total': len(results),\n        'run_id': run_id,\n    }\n\n\n'''
    text = replace_between(text, "async def run(urls: str | Path | list[str],", "def run_sync(", run_func, "dom_extract.py")

    # The new signature no longer accepts the formerly shared connection.
    return text


def main() -> None:
    for path in (INGEST, CRAWLER):
        if not path.is_file():
            raise SystemExit(f"Could not locate pipeline source file: {path}")

    originals = {INGEST: INGEST.read_text(encoding="utf-8"), CRAWLER: CRAWLER.read_text(encoding="utf-8")}
    updated_ingest = patch_ingest(originals[INGEST])
    updated_crawler = patch_crawler(originals[CRAWLER])

    # Simple source sanity checks before writing anything.
    checks = [
        (updated_ingest, "def _executemany_batched(", "batched helper missing"),
        (updated_ingest, "cur.executemany(sql, batch)", "executemany calls missing"),
        (updated_crawler, "def _record_url_reject(", "URL reject helper missing"),
        (updated_crawler, "async def process_one(\n    url: str,\n    run_id: str,\n    out_dir: Path,\n    page,", "new process_one signature missing"),
    ]
    for body, needle, message in checks:
        if needle not in body:
            raise RuntimeError(message)

    updates = ((INGEST, updated_ingest), (CRAWLER, updated_crawler))
    backups = {path: path.with_suffix(path.suffix + ".before-neon-optimization.bak")
               for path, _ in updates}
    existing = [str(backup) for backup in backups.values() if backup.exists()]
    if existing:
        raise SystemExit("Backup already exists; refusing to overwrite: " + ", ".join(existing))

    for path, content in updates:
        shutil.copy2(path, backups[path])
        path.write_text(content, encoding="utf-8")

    print("Applied Neon ingestion/crawler changes.")
    print("Backups created:")
    print(f"  {INGEST.with_suffix(INGEST.suffix + '.before-neon-optimization.bak')}")
    print(f"  {CRAWLER.with_suffix(CRAWLER.suffix + '.before-neon-optimization.bak')}")
    print("Next: run `python -m py_compile apps/pipeline/ingest.py apps/pipeline/dom_extract.py`.")


if __name__ == "__main__":
    main()
