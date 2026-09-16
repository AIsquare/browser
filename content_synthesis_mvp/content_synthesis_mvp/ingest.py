from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from schema import Content, Document, SourceMetadata


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _html_to_markdownish(html: str, base_url: str) -> tuple[str, list[str], list[dict[str, str]], list[dict[str, str]], str]:
    """Lightweight extraction for the MVP.

    This is deliberately conservative: preserve headings, paragraphs, lists, links and
    images rather than attempting aggressive semantic cleanup.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    root = soup.body or soup

    headings: list[str] = []
    links: list[dict[str, str]] = []
    images: list[dict[str, str]] = []
    blocks: list[str] = []

    for node in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre", "img", "figure"]):
        name = node.name
        if name.startswith("h"):
            text = node.get_text(" ", strip=True)
            if text:
                level = int(name[1])
                headings.append(text)
                blocks.append(f"{'#' * level} {text}")
        elif name == "img":
            src = node.get("src") or node.get("data-src") or ""
            alt = node.get("alt") or ""
            if src:
                images.append({"src": urljoin(base_url, src), "alt": alt})
            if alt:
                blocks.append(f"![{alt}]({urljoin(base_url, src)})")
        else:
            text = node.get_text(" ", strip=True)
            if not text:
                continue
            if name == "li":
                blocks.append(f"- {text}")
            elif name == "blockquote":
                blocks.append(f"> {text}")
            elif name == "pre":
                blocks.append(f"```\n{text}\n```")
            else:
                blocks.append(text)

    for a in root.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        href = urljoin(base_url, a["href"])
        if href:
            links.append({"text": text, "url": href})

    # De-duplicate adjacent blocks while preserving order.
    cleaned: list[str] = []
    for block in blocks:
        if not cleaned or block != cleaned[-1]:
            cleaned.append(block)

    markdown = "\n\n".join(cleaned)
    return markdown, headings, links, images, title


def load_markdown(path: str | Path, url: str | None = None) -> Document:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    title = ""
    headings = []
    for line in text.splitlines():
        m = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if m:
            headings.append(m.group(1))
            if not title:
                title = m.group(1)

    doc_url = url or p.resolve().as_uri()
    now = datetime.now(timezone.utc).isoformat()
    return Document(
        document_id=_hash_text(doc_url)[:16],
        source=SourceMetadata(url=doc_url, title=title),
        content=Content(markdown=text, headings=headings),
        fetched_at=now,
        content_hash=_hash_text(text),
    )


def load_html(path: str | Path, url: str) -> Document:
    p = Path(path)
    html = p.read_text(encoding="utf-8")
    markdown, headings, links, images, title = _html_to_markdownish(html, url)
    now = datetime.now(timezone.utc).isoformat()
    return Document(
        document_id=_hash_text(url)[:16],
        source=SourceMetadata(url=url, title=title),
        content=Content(markdown=markdown, headings=headings, links=links, images=images),
        fetched_at=now,
        content_hash=_hash_text(markdown),
    )
