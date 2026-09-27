"""
General web crawler + extractor.

Reads a list of URLs from a file, fetches each with retries and
per-domain rate limiting, extracts clean markdown + structured blocks
from the content region, and records every step in the DB.

Failed fetches (404, 403, 5xx, "Access Denied", empty body, paywall
walls) go to the `rejects` table — never to `documents`.

Output per doc:
  extracted/<slug>.md        — markdown, ready for ast_ingest_v2.py
  extracted/<slug>.json      — structured blocks + metadata
  extracted/<slug>.raw.html  — raw HTML (source of truth)

Usage:
  python dom_extract.py --urls urls.txt
  python dom_extract.py --urls urls.txt --out extracted/ --db corpus_v1.db

Env / flags:
  --concurrency N      parallel fetches (default 3)
  --rate-limit SEC     min seconds between fetches to same domain (default 2)
  --timeout MS         page timeout in ms (default 60000)
  --max-retries N      fetch retries (default 2)
  --no-js              disable Playwright, use plain HTTP
"""
from __future__ import annotations
from db import connect
import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlparse, urldefrag, urlunparse, parse_qsl, urlencode

from bs4 import BeautifulSoup, Tag

# Robots.txt parsers — prefer protego (modern, handles wildcards + crawl-delay)
try:
    from protego import Protego
    HAS_PROTEGO = True
except ImportError:
    from urllib.robotparser import RobotFileParser
    HAS_PROTEGO = False

# Optional Playwright import — allows --no-js mode without playwright installed
try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False



# =====================================================================
# Configuration
# =====================================================================

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Tracking params stripped from URLs during canonicalization
TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'utm_id', 'fbclid', 'gclid', 'mc_cid', 'mc_eid', 'ref', 'ref_src',
    'source', 'igshid', 'yclid',
}

# Tags always treated as chrome
BOILERPLATE_TAGS = {
    'script', 'style', 'noscript', 'svg', 'canvas', 'iframe',
    'nav', 'aside', 'header', 'footer', 'form',
}

# ARIA roles always treated as chrome
BOILERPLATE_ROLES = {'navigation', 'banner', 'contentinfo', 'search'}

# CSS class hints that reliably signal chrome across the web
BOILERPLATE_CLASS_HINTS = {
    'cookie', 'consent', 'gdpr', 'newsletter', 'subscribe',
    'advert', 'advertisement', 'sponsored', 'promo',
    'social-share', 'share-buttons', 'share-bar', 'share-this',
    'sharebox', 'share-box', 'share-widget', 'sharing',
    'breadcrumb', 'pagination', 'pager',
    'sidebar', 'widget', 'related-posts', 'related-articles',
    'related-content', 'recommended', 'recommended-posts',
    'read-next', 'read-more-', 'you-might-also',
    'author-bio', 'about-author', 'author-box',
    'post-navigation', 'post-nav', 'next-post', 'prev-post',
    'comments-section', 'comment-list', 'disqus_thread',
    'comment-form', 'login-form', 'signup-form',
}

# Headings whose text is exactly one of these — skip the heading and
# everything under it until the next non-chrome heading appears.
BOILERPLATE_HEADING_TEXT = {
    'share', 'share this', 'share this article', 'share article',
    'tweet', 'follow', 'follow us', 'subscribe', 'subscribe now',
    'related articles', 'related posts', 'you might also like',
    'read more', 'read next', 'more from', 'more stories',
    'advertisement', 'sponsored content', 'sign up',
    'table of contents', 'in this article', 'in this section',
}

# Text patterns that indicate a soft failure (bot wall, paywall, error page)
SOFT_FAILURE_PATTERNS = [
    r'access denied',
    r'403 forbidden',
    r'checking your browser',
    r'enable javascript',
    r'just a moment\.\.\.',
    r'please verify you are human',
    r'subscribe to (read|continue)',
    r'this content is (not available|for subscribers)',
]
SOFT_FAILURE_RE = re.compile('|'.join(SOFT_FAILURE_PATTERNS), re.IGNORECASE)

# =====================================================================
# Robots.txt
# =====================================================================

# Per-domain cache: {domain: parser-or-None}
# None means "no robots.txt found / fetch failed" — treat as allow-all.
_robots_cache: dict[str, object] = {}
_robots_lock = asyncio.Lock()


async def _fetch_robots_text(scheme: str, domain: str, timeout_ms: int) -> str | None:
    """Fetch /robots.txt using plain HTTP. Returns text or None."""
    import urllib.request
    import urllib.error
    url = f"{scheme}://{domain}/robots.txt"
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout_ms / 1000) as resp:
            if resp.status == 200:
                return resp.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return None  # no robots.txt -> allow all
        return None
    except Exception:
        return None
    return None


async def get_robots(scheme: str, domain: str, timeout_ms: int):
    """Return a parser (or None) for this domain. Cached."""
    async with _robots_lock:
        if domain in _robots_cache:
            return _robots_cache[domain]
        text = await _fetch_robots_text(scheme, domain, timeout_ms)
        parser = None
        if text is not None:
            if HAS_PROTEGO:
                parser = Protego.parse(text)
            else:
                parser = RobotFileParser()
                parser.parse(text.splitlines())
        _robots_cache[domain] = parser
        return parser


def robots_can_fetch(parser, url: str, user_agent: str) -> bool:
    """True if allowed (or no parser)."""
    if parser is None:
        return True
    if HAS_PROTEGO:
        return parser.can_fetch(url, user_agent)
    return parser.can_fetch(user_agent, url)


def robots_crawl_delay(parser, user_agent: str) -> float | None:
    """Return Crawl-delay in seconds, or None."""
    if parser is None:
        return None
    if HAS_PROTEGO:
        try:
            d = parser.crawl_delay(user_agent)
            return float(d) if d is not None else None
        except Exception:
            return None
    try:
        d = parser.crawl_delay(user_agent)
        return float(d) if d is not None else None
    except Exception:
        return None
# =====================================================================
# Utility
# =====================================================================

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def sha16(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]


def canonicalize(url: str) -> str:
    """Strip fragments and tracking params, normalize scheme/host."""
    url, _ = urldefrag(url)
    p = urlparse(url)
    scheme = p.scheme.lower() or 'https'
    host = p.netloc.lower()
    if host.startswith('www.'):
        host = host[4:]
    path = p.path or '/'
    # drop trailing slash except for root
    if len(path) > 1 and path.endswith('/'):
        path = path.rstrip('/')
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False)
         if k.lower() not in TRACKING_PARAMS]
    q.sort()
    return urlunparse((scheme, host, path, '', urlencode(q), ''))


def slugify(url: str) -> str:
    """Filesystem-safe, collision-resistant slug for a URL."""
    c = canonicalize(url)
    h = sha16(c)
    s = re.sub(r'[^a-zA-Z0-9]+', '_', c)
    return f"{s[:100]}_{h}"


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().lstrip('www.')


def clean_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


# =====================================================================
# Fetch — Playwright or plain HTTP, with retries
# =====================================================================

async def fetch_with_playwright(page, url: str, timeout_ms: int):
    """Returns (html, status_code, final_url, headers, error)."""
    try:
        response = await page.goto(url, wait_until='domcontentloaded', timeout=timeout_ms)
        status = response.status if response else None
        final_url = response.url if response else url
        headers = dict(response.headers) if response else {}

        # Give lazy content a moment
        try:
            await page.wait_for_load_state('networkidle', timeout=5000)
        except Exception:
            pass

        await page.wait_for_timeout(800)

        # Trigger lazy-loaded content
        try:
            await page.evaluate("""
                async () => {
                    await new Promise(resolve => {
                        let total = 0;
                        const step = 600;
                        const timer = setInterval(() => {
                            window.scrollBy(0, step);
                            total += step;
                            if (total >= document.body.scrollHeight) {
                                clearInterval(timer);
                                resolve();
                            }
                        }, 80);
                    });
                    window.scrollTo(0, 0);
                }
            """)
            await page.wait_for_timeout(300)
        except Exception:
            pass

        html = await page.content()
        return html, status, final_url, headers, None
    except Exception as e:
        return None, None, url, {}, str(e)

async def fetch_plain(url: str, timeout: int):
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout / 1000) as resp:
            html = resp.read().decode('utf-8', errors='replace')
            final_url = resp.url
            headers = dict(resp.headers)
            return html, resp.status, final_url, headers, None
    except urllib.error.HTTPError as e:
        return None, e.code, url, {}, f"http_{e.code}"
    except Exception as e:
        return None, None, url, {}, str(e)


# =====================================================================
# Fetch outcome classification
# =====================================================================

def classify_fetch(status: int | None, html: str | None, error: str | None) -> tuple[str, str | None]:
    """
    Returns (outcome, reject_reason).
      outcome: 'ok' | 'reject'
    """
    if error and not html:
        if 'timeout' in error.lower():
            return 'reject', 'timeout'
        return 'reject', 'fetch_error'

    if status is None:
        return 'reject', 'no_status'

    if status == 404:
        return 'reject', 'http_404'
    if status == 403:
        return 'reject', 'http_403'
    if status == 429:
        return 'reject', 'rate_limited'
    if 500 <= status < 600:
        return 'reject', f'http_{status}'
    if status >= 400:
        return 'reject', f'http_{status}'

    if not html or len(html) < 500:
        return 'reject', 'empty_body'

    # Soft failures — bot walls, paywalls, "Access Denied", etc.
    body_start = html[:5000]
    if SOFT_FAILURE_RE.search(body_start):
        return 'reject', 'soft_failure'

    return 'ok', None


# =====================================================================
# Metadata extraction
# =====================================================================

def extract_metadata(soup: BeautifulSoup, url: str) -> dict:
    """Pull title, author, published, canonical, language, description."""
    meta = {
        'title': None,
        'author': None,
        'published_at': None,
        'updated_at': None,
        'canonical_url': None,
        'language': None,
        'description': None,
        'source_type': 'unknown',
    }

    # Language
    html_tag = soup.find('html')
    if html_tag and html_tag.get('lang'):
        meta['language'] = html_tag['lang'].split('-')[0].lower()

    # Canonical
    canonical = soup.find('link', rel='canonical')
    if canonical and canonical.get('href'):
        meta['canonical_url'] = urljoin(url, canonical['href'])

    # Description / og:description
    for name in ('description', 'og:description'):
        tag = soup.find('meta', attrs={'name': name}) or soup.find('meta', property=name)
        if tag and tag.get('content'):
            meta['description'] = clean_text(tag['content'])[:500]
            break

    # Title — prefer og:title, fall back to <title>
    og_title = soup.find('meta', property='og:title')
    if og_title and og_title.get('content'):
        meta['title'] = clean_text(og_title['content'])
    elif soup.title and soup.title.string:
        meta['title'] = clean_text(soup.title.string)

    # Author
    for attrs in [
        {'name': 'author'},
        {'property': 'article:author'},
        {'name': 'twitter:creator'},
    ]:
        tag = soup.find('meta', attrs=attrs)
        if tag and tag.get('content'):
            meta['author'] = clean_text(tag['content'])[:200]
            break

    # Published
    for attrs in [
        {'property': 'article:published_time'},
        {'name': 'publication_date'},
        {'name': 'date'},
        {'itemprop': 'datePublished'},
    ]:
        tag = soup.find('meta', attrs=attrs)
        if tag and tag.get('content'):
            meta['published_at'] = clean_text(tag['content'])[:40]
            break
    if not meta['published_at']:
        t = soup.find('time')
        if t and (t.get('datetime') or t.string):
            meta['published_at'] = clean_text(t.get('datetime') or t.string)[:40]

    # JSON-LD (schema.org) — merge if present
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string or '{}')
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            meta['title'] = meta['title'] or item.get('headline') or item.get('name')
            if 'author' in item:
                a = item['author']
                if isinstance(a, dict):
                    meta['author'] = meta['author'] or a.get('name')
                elif isinstance(a, list) and a and isinstance(a[0], dict):
                    meta['author'] = meta['author'] or a[0].get('name')
                elif isinstance(a, str):
                    meta['author'] = meta['author'] or a
            meta['published_at'] = meta['published_at'] or item.get('datePublished')
            meta['description'] = meta['description'] or item.get('description')

            # source_type from @type
            if meta['source_type'] == 'unknown':
                t = item.get('@type')
                if isinstance(t, list) and t:
                    t = t[0]
                if t == 'NewsArticle':       meta['source_type'] = 'article'
                elif t == 'BlogPosting':     meta['source_type'] = 'article'
                elif t == 'TechArticle':     meta['source_type'] = 'article'
                elif t == 'ScholarlyArticle': meta['source_type'] = 'paper'
                elif t == 'Product':          meta['source_type'] = 'product'
                elif t == 'QAPage':           meta['source_type'] = 'forum'
                elif t == 'FAQPage':          meta['source_type'] = 'article'
                elif t == 'WebPage':          meta['source_type'] = 'article'

            # updated_at
            if not meta['updated_at']:
                meta['updated_at'] = item.get('dateModified')
            # Fallback source_type from og:type
            if meta['source_type'] == 'unknown':
                og_type = soup.find('meta', property='og:type')
                if og_type and og_type.get('content'):
                    t = og_type['content'].strip().lower()
                    if t in ('article', 'news'):
                        meta['source_type'] = 'article'
                    elif t == 'product':
                        meta['source_type'] = 'product'
                    elif t == 'website':
                        meta['source_type'] = 'website'

    return meta


# =====================================================================
# Content region detection (unchanged logic, slightly cleaner)
# =====================================================================

def class_string(tag: Tag) -> str:
    classes = tag.get('class', [])
    if isinstance(classes, list):
        return ' '.join(classes).lower()
    return str(classes).lower()


def looks_like_boilerplate(tag: Tag) -> bool:
    if tag.name in BOILERPLATE_TAGS:
        return True
    role = tag.get('role')
    if role and role.lower() in BOILERPLATE_ROLES:
        return True
    classes = class_string(tag)
    for hint in BOILERPLATE_CLASS_HINTS:
        if hint in classes:
            return True
    return False


def score_content_candidate(tag: Tag) -> float:
    text = clean_text(tag.get_text(' ', strip=True))
    if len(text) < 200:
        return -1000

    paragraphs = tag.find_all('p')
    headings = tag.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    tables = tag.find_all('table')
    images = tag.find_all('img')
    links = tag.find_all('a')

    score = 0.0
    score += min(len(text) / 100, 50)
    score += len(paragraphs) * 3
    score += len(headings) * 8
    score += len(tables) * 15
    score += len(images) * 5

    if len(links) > 100:
        score -= 30

    link_text = clean_text(' '.join(a.get_text(' ', strip=True) for a in links))
    if len(text) > 0:
        ratio = len(link_text) / len(text)
        if ratio > 0.7:
            score -= 40

    return score


def find_content_region(soup: BeautifulSoup) -> Tag:
    for candidate_sel in ('article', 'main', '[role="main"]'):
        candidates = soup.select(candidate_sel)
        if candidates:
            scored = [(score_content_candidate(t), t) for t in candidates]
            scored.sort(key=lambda x: x[0], reverse=True)
            if scored[0][0] > 0:
                return scored[0][1]

    divs = soup.find_all('div')
    scored = []
    for tag in divs:
        if len(tag.find_all(recursive=False)) < 2:
            continue
        s = score_content_candidate(tag)
        if s > 0:
            scored.append((s, tag))
    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    return soup.body or soup


# =====================================================================
# Table / image / code extraction
# =====================================================================

def table_to_markdown(table: Tag) -> str:
    rows = []
    for tr in table.find_all('tr'):
        cells = tr.find_all(['th', 'td'], recursive=False)
        if not cells:
            cells = tr.find_all(['th', 'td'])
        row = [clean_text(c.get_text(' ', strip=True)) for c in cells]
        if any(row):
            rows.append(row)
    if not rows:
        return ''
    col_count = max(len(r) for r in rows)
    rows = [r + [''] * (col_count - len(r)) for r in rows]
    lines = ['| ' + ' | '.join(rows[0]) + ' |',
             '| ' + ' | '.join(['---'] * col_count) + ' |']
    for r in rows[1:]:
        lines.append('| ' + ' | '.join(r) + ' |')
    return '\n'.join(lines)


def get_image_url(img: Tag, base_url: str) -> str | None:
    for attr in ('src', 'data-src', 'data-lazy-src', 'data-original'):
        v = img.get(attr)
        if v and not v.startswith('data:'):
            return urljoin(base_url, v)
    srcset = img.get('srcset')
    if srcset:
        candidates = [c.strip().split()[0] for c in srcset.split(',') if c.strip()]
        if candidates:
            return urljoin(base_url, candidates[-1])
    return None


def extract_code_block(pre: Tag) -> str:
    code = pre.find('code')
    target = code or pre
    # Drop line-number gutters
    for node in target.find_all(True):
        classes = class_string(node)
        if any(h in classes for h in ('line-number', 'linenumber', 'gutter')):
            node.decompose()
    for br in target.find_all('br'):
        br.replace_with('\n')
    text = target.get_text(separator='', strip=False)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip('\n')


# =====================================================================
# Block extraction from content region
# =====================================================================

def extract_blocks(root: Tag, base_url: str) -> list[dict]:
    blocks = []
    skipping = False

    for el in root.find_all([
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'ul', 'ol', 'blockquote', 'pre', 'table', 'img', 'figure',
    ]):
        if looks_like_boilerplate(el):
            continue

        parent = el.parent
        if parent and parent.name in ('li', 'td', 'th', 'blockquote', 'pre', 'table', 'figure'):
            continue

        if re.fullmatch(r'h[1-6]', el.name):
            t = clean_text(el.get_text(' ', strip=True))
            if not t:
                continue
            # Chrome heading: start skipping until next real heading
            if t.lower().strip() in BOILERPLATE_HEADING_TEXT:
                skipping = True
                continue
            skipping = False
            blocks.append({'type': 'heading', 'level': int(el.name[1]), 'text': t})
            continue

        if skipping:
            continue

        elif el.name == 'p':
            t = clean_text(el.get_text(' ', strip=True))
            imgs = [extract_image(i, base_url) for i in el.find_all('img')]
            imgs = [i for i in imgs if i]
            if t or imgs:
                blocks.append({'type': 'paragraph', 'text': t, 'images': imgs})

        elif el.name in ('ul', 'ol'):
            items = [clean_text(li.get_text(' ', strip=True))
                     for li in el.find_all('li', recursive=False)]
            items = [i for i in items if i]
            if items:
                blocks.append({'type': 'list', 'ordered': el.name == 'ol', 'items': items})

        elif el.name == 'blockquote':
            t = clean_text(el.get_text(' ', strip=True))
            if t:
                blocks.append({'type': 'blockquote', 'text': t})

        elif el.name == 'pre':
            t = extract_code_block(el)
            if t:
                lang = ''
                code = el.find('code')
                for node in (code, el):
                    if node is None:
                        continue
                    for cls in (node.get('class') or []):
                        if cls.startswith('language-'):
                            lang = cls[9:]
                            break
                    if lang:
                        break
                blocks.append({'type': 'code', 'language': lang, 'text': t})

        elif el.name == 'table':
            md = table_to_markdown(el)
            if md:
                blocks.append({'type': 'table', 'markdown': md})

        elif el.name == 'img':
            img = extract_image(el, base_url)
            if img:
                blocks.append({'type': 'image', **img})

    return blocks


def extract_image(img: Tag, base_url: str) -> dict | None:
    src = get_image_url(img, base_url)
    if not src:
        return None
    return {
        'src': src,
        'alt': clean_text(img.get('alt', '')),
    }


# =====================================================================
# Markdown rendering
# =====================================================================

def blocks_to_markdown(blocks: list[dict]) -> str:
    out = []
    for b in blocks:
        t = b['type']
        if t == 'heading':
            out.append(f"{'#' * b['level']} {b['text']}")
        elif t == 'paragraph':
            if b.get('text'):
                out.append(b['text'])
            for img in b.get('images', []):
                out.append(f"![{img['alt']}]({img['src']})")
        elif t == 'list':
            for i, item in enumerate(b['items'], 1):
                out.append(f"{i}. {item}" if b['ordered'] else f"- {item}")
        elif t == 'blockquote':
            out.append(f"> {b['text']}")
        elif t == 'code':
            fence = '~~~' if '```' in b['text'] else '```'
            out.append(f"{fence}{b.get('language','')}\n{b['text']}\n{fence}")
        elif t == 'table':
            out.append(b['markdown'])
        elif t == 'image':
            out.append(f"![{b['alt']}]({b['src']})")
    return '\n\n'.join(out)


# =====================================================================
# DB recording
# =====================================================================

def ensure_run(conn, run_id: str, config_id: str | None, urls_count: int) -> None:
    conn.execute("""
      INSERT OR IGNORE INTO pipeline_runs
        (run_id, config_id, started_at, status, stages_json, notes)
      VALUES (?, ?, ?, 'running', ?, ?)
    """, (run_id, config_id, utcnow(),
          json.dumps(['fetch', 'extract']),
          f'crawl of {urls_count} urls'))


def ensure_url(conn, url: str) -> str:
    """Return url_id, inserting into url_queue if new."""
    c = canonicalize(url)
    url_id = sha16(c)
    conn.execute("""
      INSERT OR IGNORE INTO url_queue
        (url_id, url, canonical_url, domain, status, created_at, updated_at)
      VALUES (?, ?, ?, ?, 'pending', ?, ?)
    """, (url_id, url, c, domain_of(c), utcnow(), utcnow()))
    return url_id


def record_fetch(conn, url_id: str, url: str, status: int | None,
                 html: str, html_path: str, final_url: str,
                 headers: dict | None) -> str:
    fetch_id = sha16(url_id + utcnow() + str(status))
    conn.execute("""
      INSERT INTO fetches
        (fetch_id, url_id, url, final_url, fetched_at, status_code,
         content_type, content_length, raw_html_path, raw_html_hash,
         response_headers_json)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (fetch_id, url_id, url, final_url, utcnow(), status,
          headers.get('content-type') if headers else None,
          len(html), html_path, sha16(html),
          json.dumps(headers or {})))
    return fetch_id


def record_reject(conn, url_id: str, url: str, reason: str,
                  status: int | None, detail: str | None) -> None:
    rid = sha16(url_id + reason + utcnow())
    conn.execute("""
      INSERT INTO rejects
        (reject_id, url_id, url, reason, status_code, detail, fetched_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (rid, url_id, url, reason, status, detail, utcnow()))
    conn.execute("""
      UPDATE url_queue SET status='rejected', updated_at=? WHERE url_id=?
    """, (utcnow(), url_id))


def record_doc_stage(conn, run_id: str, doc_id: str, stage: str,
                     status: str, counts: dict | None = None,
                     error: str | None = None) -> None:
    conn.execute("""
      INSERT OR REPLACE INTO doc_stages
        (run_id, doc_id, stage, status, started_at, finished_at,
         counts_json, error)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (run_id, doc_id, stage, status, utcnow(), utcnow(),
          json.dumps(counts or {}), error))


# =====================================================================
# Per-doc processing
# =====================================================================

async def process_one(
    url: str,
    run_id: str,
    out_dir: Path,
    conn,
    page,                # playwright page or None
    timeout_ms: int,
    max_retries: int,
) -> dict:
    """Fetch, extract, write, record. Returns a status dict."""
    url_id = ensure_url(conn, url)
    slug = slugify(url)
    raw_path = out_dir / f"{slug}.raw.html"
    md_path = out_dir / f"{slug}.md"
    json_path = out_dir / f"{slug}.json"

    # ---- fetch with retries ----
    html = None
    status = None
    error = None


    for attempt in range(max_retries + 1):
        if page is not None and HAS_PLAYWRIGHT:
            html, status, final_url, headers, error = await fetch_with_playwright(page, url, timeout_ms)
        else:
            html, status, final_url, headers, error = await fetch_plain(url, timeout_ms)

        outcome, reason = classify_fetch(status, html, error)
        if outcome == 'ok':
            break
        if attempt < max_retries:
            await asyncio.sleep(1.5 ** attempt)
        else:
            record_reject(conn, url_id, url, reason or 'unknown', status, error)
            conn.commit()
            return {'url': url, 'status': 'rejected', 'reason': reason}

    # ---- persist raw HTML ----
    raw_path.write_text(html, encoding='utf-8')
    record_fetch(conn, url_id, url, status, html, str(raw_path), final_url, headers)

    # ---- parse & extract ----
    soup = BeautifulSoup(html, 'lxml')
    meta = extract_metadata(soup, url)
    region = find_content_region(soup)
    blocks = extract_blocks(region, url)
    markdown = blocks_to_markdown(blocks)

    if not markdown.strip():
        record_reject(conn, url_id, url, 'no_content_extracted', status, None)
        conn.commit()
        return {'url': url, 'status': 'rejected', 'reason': 'no_content_extracted'}

    # ---- write outputs ----
    fm_lines = [f"source_url: {url}"]
    if meta.get('title'):
        fm_lines.append(f"title: {json.dumps(meta['title'])}")
    if meta.get('author'):
        fm_lines.append(f"author: {json.dumps(meta['author'])}")
    if meta.get('published_at'):
        fm_lines.append(f"published_at: {json.dumps(meta['published_at'])}")
    if meta.get('language'):
        fm_lines.append(f"language: {meta['language']}")
    if meta.get('description'):
        fm_lines.append(f"description: {json.dumps(meta['description'])}")
    if meta.get('updated_at'):
        fm_lines.append(f"updated_at: {json.dumps(meta['updated_at'])}")
    if meta.get('source_type') and meta['source_type'] != 'unknown':
        fm_lines.append(f"source_type: {meta['source_type']}")

    frontmatter = "---\n" + "\n".join(fm_lines) + "\n---\n\n"
    md_path.write_text(
        f"{frontmatter}# Source\n\n{url}\n\n---\n\n{markdown}",
        encoding='utf-8'
    )
    json_path.write_text(json.dumps({
        'source': url,
        'metadata': meta,
        'blocks': blocks,
    }, indent=2, ensure_ascii=False), encoding='utf-8')

    # ---- update url_queue ----
    conn.execute("""
      UPDATE url_queue SET status='fetched', updated_at=? WHERE url_id=?
    """, (utcnow(), url_id))

    record_doc_stage(conn, run_id, slug, 'fetch', 'ok',
                     counts={'bytes': len(html), 'status': status})
    record_doc_stage(conn, run_id, slug, 'extract', 'ok',
                     counts={'blocks': len(blocks), 'chars': len(markdown)})
    conn.commit()

    return {
        'url': url,
        'status': 'ok',
        'blocks': len(blocks),
        'chars': len(markdown),
        'title': meta.get('title'),
    }


# =====================================================================
# Main
# =====================================================================

async def run(args):
    urls_path = Path(args.urls)
    if not urls_path.exists():
        print(f"error: url file not found: {urls_path}", file=sys.stderr)
        sys.exit(1)

    urls = [u.strip() for u in urls_path.read_text(encoding='utf-8').splitlines() if u.strip()]
    urls = [u for u in urls if u.startswith(('http://', 'https://'))]
    print(f"loaded {len(urls)} urls")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = connect(args.db)
    run_id = sha16(f"crawl-{utcnow()}-{len(urls)}")
    ensure_run(conn, run_id, None, len(urls))
    conn.commit()

    # Per-domain rate limiting
        # Per-domain rate limiting
    last_hit: dict[str, float] = defaultdict(float)

    async def gate(url: str) -> tuple[bool, str | None]:
        """
        Returns (allowed, skip_reason).
        Checks robots.txt, then applies per-domain rate limiting
        (using the larger of --rate-limit and the site's Crawl-delay).
        """
        p = urlparse(url)
        domain = domain_of(url)

        # Robots check — cached per domain
        parser = await get_robots(p.scheme or 'https', domain, args.timeout)
        if not robots_can_fetch(parser, url, USER_AGENT):
            return False, 'robots_disallow'

        # Rate limit — honor Crawl-delay if present
        site_delay = robots_crawl_delay(parser, USER_AGENT)
        effective_delay = max(args.rate_limit, site_delay or 0.0)

        now = time.monotonic()
        wait = effective_delay - (now - last_hit[domain])
        if wait > 0:
            await asyncio.sleep(wait)
        last_hit[domain] = time.monotonic()

        return True, None

    results = []

    if args.no_js or not HAS_PLAYWRIGHT:
        if not HAS_PLAYWRIGHT and not args.no_js:
            print("playwright not installed — falling back to plain HTTP")
        for url in urls:
            allowed, reason = await gate(url)
            if not allowed:
                url_id = ensure_url(conn, url)
                record_reject(conn, url_id, url, reason, None, None)
                conn.commit()
                print(f"  rejected   {url[:80]}  ({reason})")
                results.append({'url': url, 'status': 'rejected', 'reason': reason})
                continue
            r = await process_one(url, run_id, out_dir, conn, None, args.timeout, args.max_retries)
            results.append(r)
            print(f"  {r['status']:9s}  {url[:80]}")
    else:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT)
            page = await context.new_page()

            for url in urls:
                allowed, reason = await gate(url)
                if not allowed:
                    url_id = ensure_url(conn, url)
                    record_reject(conn, url_id, url, reason, None, None)
                    conn.commit()
                    print(f"  rejected   {url[:80]}  ({reason})")
                    results.append({'url': url, 'status': 'rejected', 'reason': reason})
                    continue
                r = await process_one(url, run_id, out_dir, conn, page, args.timeout, args.max_retries)
                results.append(r)
                print(f"  {r['status']:9s}  {url[:80]}")

            await browser.close()

    ok = sum(1 for r in results if r['status'] == 'ok')
    rejected = sum(1 for r in results if r['status'] == 'rejected')
    print(f"\ndone: {ok} ok, {rejected} rejected, {len(results)} total")

    conn.execute("""
      UPDATE pipeline_runs SET status='completed', finished_at=? WHERE run_id=?
    """, (utcnow(), run_id))
    conn.commit()
    conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--urls', required=True, help='file with one URL per line')
    ap.add_argument('--out', default='extracted', help='output directory')
    ap.add_argument('--db', default=None,
                help='override DB path; otherwise PIPELINE_DB_PATH or corpus_v1.db')
    ap.add_argument('--rate-limit', type=float, default=2.0,
                    help='min seconds between fetches to same domain')
    ap.add_argument('--timeout', type=int, default=60000, help='page timeout ms')
    ap.add_argument('--max-retries', type=int, default=2)
    ap.add_argument('--no-js', action='store_true',
                    help='disable Playwright, use plain HTTP')
    args = ap.parse_args()
    asyncio.run(run(args))


if __name__ == '__main__':
    main()