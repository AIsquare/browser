"""
DOM-based extraction prototype

Pipeline:
    Playwright
        ↓
    Rendered HTML
        ↓
    BeautifulSoup DOM traversal
        ↓
    Structured blocks
        ↓
    Markdown + JSON

Keeps raw HTML as the source of truth.

Install:
    pip install playwright beautifulsoup4 lxml
    playwright install chromium

Run:
    python dom_extract.py
"""

import asyncio
import json
import os
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from playwright.async_api import async_playwright


# ---------------------------------------------------------------------
# TEST URLS
# ---------------------------------------------------------------------

# TEST_URLS = [
#     "https://developers.openai.com/api/docs/guides/evals?api-mode=responses",
#     "https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents",
#     "https://www.langchain.com/resources/llm-evals",
#     "https://index.parallel.ai/the-visibility-value-gap?utm_source=linkedin&utm_medium=social-organic",
#     "https://martinuke0.github.io/posts/2026-09-02-the-llm-inference-roadmap-i-wish-more-engineers-followed/",
#     "https://www.chillinterview.com/learn/system-design/design-job-scheduler",
#     "https://outcomeschool.com/blog/kv-cache-compression",
#     "https://muratbuffalo.blogspot.com/2026/09/jetpack-consensus-made-generally-fast.html"
# ]
TEST_URLS = [
    "https://www.nist.gov/how-do-you-measure-it/how-do-you-measure-your-location-using-gps",
    "https://spaceplace.nasa.gov/gps/en/",
    "https://www.geotab.com/blog/what-is-gps/",
    "https://novatel.com/tech-talk/an-introduction-to-gnss/resources/how-does-gps-work",
    "https://www.reddit.com/r/explainlikeimfive/comments/1som2a6/eli5_how_does_gps_know_your_exact_location/",
    "https://www.faa.gov/about/office_org/headquarters_offices/ato/service_units/techops/navservices/gnss/gps/howitworks",
    "https://en.wikipedia.org/wiki/Global_Positioning_System",
    "https://oceanservice.noaa.gov/education/tutorial_geodesy/geo09_gps.html"
]
OUTPUT_DIR = "extracted_dom"


# ---------------------------------------------------------------------
# ELEMENTS THAT ARE VERY LIKELY BOILERPLATE
# ---------------------------------------------------------------------

BOILERPLATE_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "iframe",
    "form",
    "nav",
    "aside",
    "header",
    "footer",
}

BOILERPLATE_ROLES = {
    "navigation",
    "banner",
    "contentinfo",
}

BOILERPLATE_CLASS_HINTS = [
    "cookie",
    "consent",
    "newsletter",
    "subscribe",
    "advert",
    "advertisement",
    "social-share",
    "share-buttons",
    "breadcrumb",
    "pagination",
]


# ---------------------------------------------------------------------
# PLAYWRIGHT
# ---------------------------------------------------------------------

async def render(url: str) -> str:
    """
    Render the page using Chromium and return the final DOM.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        print(f"Rendering: {url}")
        await page.goto(
            url,
            wait_until="networkidle",
            timeout=60000,
        )

        # Give lazy-loaded content a chance to appear.
        await page.wait_for_timeout(2000)

        # Scroll through page so lazy content/images are triggered.
        await page.evaluate(
            """
            async () => {
                await new Promise(resolve => {
                    let total = 0;
                    const distance = 500;

                    const timer = setInterval(() => {
                        window.scrollBy(0, distance);
                        total += distance;

                        if (total >= document.body.scrollHeight) {
                            clearInterval(timer);
                            resolve();
                        }
                    }, 100);
                });

                window.scrollTo(0, 0);
            }
            """
        )

        await page.wait_for_timeout(1000)
        html = await page.content()
        await browser.close()

        return html


# ---------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------

def clean_text(text: str) -> str:
    """
    Normalize whitespace while preserving readable text.
    """
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def class_string(tag: Tag) -> str:
    classes = tag.get("class", [])
    if isinstance(classes, list):
        return " ".join(classes).lower()
    return str(classes).lower()


def looks_like_boilerplate(tag: Tag) -> bool:
    """
    Conservative boilerplate detection.
    """
    if tag.name in BOILERPLATE_TAGS:
        return True

    role = tag.get("role")
    if role and role.lower() in BOILERPLATE_ROLES:
        return True

    classes = class_string(tag)
    for hint in BOILERPLATE_CLASS_HINTS:
        if hint in classes:
            return True

    return False


def is_empty(tag: Tag) -> bool:
    return not clean_text(tag.get_text(" ", strip=True))


# ---------------------------------------------------------------------
# CONTENT REGION DETECTION
# ---------------------------------------------------------------------

def score_content_candidate(tag: Tag) -> float:
    text = clean_text(tag.get_text(" ", strip=True))

    if len(text) < 200:
        return -1000

    paragraphs = tag.find_all("p")
    headings = tag.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    tables = tag.find_all("table")
    images = tag.find_all("img")
    links = tag.find_all("a")

    score = 0
    score += min(len(text) / 100, 50)
    score += len(paragraphs) * 3
    score += len(headings) * 8
    score += len(tables) * 15
    score += len(images) * 5

    if len(links) > 100:
        score -= 30

    link_text = clean_text(
        " ".join(a.get_text(" ", strip=True) for a in links)
    )

    if len(text) > 0:
        link_ratio = len(link_text) / len(text)
        if link_ratio > 0.7:
            score -= 40

    return score


def find_content_region(soup: BeautifulSoup) -> Tag:
    semantic_candidates = soup.find_all(["article", "main"])
    if semantic_candidates:
        scored = [(score_content_candidate(tag), tag) for tag in semantic_candidates]
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_tag = scored[0]

        if best_score > 0:
            print(f"Content region: <{best_tag.name}> (score={best_score:.1f})")
            return best_tag

    candidates = soup.find_all("div")
    scored = []
    for tag in candidates:
        if len(tag.find_all(recursive=False)) < 2:
            continue
        score = score_content_candidate(tag)
        if score > 0:
            scored.append((score, tag))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_tag = scored[0]
        print(f"Content region: <{best_tag.name}> (score={best_score:.1f})")
        return best_tag

    body = soup.body
    if body:
        return body

    return soup


# ---------------------------------------------------------------------
# TABLE EXTRACTION
# ---------------------------------------------------------------------

def extract_cell(cell: Tag) -> str:
    list_items = cell.find_all("li")
    if list_items:
        items = []
        for li in list_items:
            text = clean_text(li.get_text(" ", strip=True))
            if text:
                items.append(f"- {text}")
        return "<br>".join(items)

    return clean_text(cell.get_text(" ", strip=True))


def extract_table(table: Tag) -> dict:
    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            cells = tr.find_all(["th", "td"])

        row = []
        for cell in cells:
            row.append(extract_cell(cell))

        if row:
            rows.append(row)

    return {
        "type": "table",
        "rows": rows,
    }


def table_to_markdown(table_data: dict) -> str:
    rows = table_data["rows"]
    if not rows:
        return ""

    column_count = max(len(row) for row in rows)
    normalized = []
    for row in rows:
        row = row + [""] * (column_count - len(row))
        normalized.append(row)

    lines = []
    header = normalized[0]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * column_count) + " |")

    for row in normalized[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


# ---------------------------------------------------------------------
# IMAGE EXTRACTION
# ---------------------------------------------------------------------

def get_image_url(img: Tag, base_url: str) -> str | None:
    src = img.get("src")
    if src and not src.startswith("data:"):
        return urljoin(base_url, src)

    srcset = img.get("srcset")
    if srcset:
        candidates = []
        for item in srcset.split(","):
            item = item.strip()
            if not item:
                continue
            parts = item.split()
            if parts:
                candidates.append(parts[0])

        if candidates:
            return urljoin(base_url, candidates[-1])

    for attr in ["data-src", "data-lazy-src", "data-original"]:
        value = img.get(attr)
        if value and not value.startswith("data:"):
            return urljoin(base_url, value)

    return None


def extract_image(img: Tag, base_url: str) -> dict | None:
    src = get_image_url(img, base_url)
    if not src:
        return None

    alt = clean_text(img.get("alt", ""))
    return {
        "type": "image",
        "src": src,
        "alt": alt,
    }


# ---------------------------------------------------------------------
# BLOCK EXTRACTION
# ---------------------------------------------------------------------

def _class_tokens(tag: Tag) -> list[str]:
    classes = tag.get("class", [])
    if isinstance(classes, str):
        return classes.lower().split()
    return [str(x).lower() for x in classes]


def _looks_like_line_number_node(tag: Tag) -> bool:
    tokens = _class_tokens(tag)
    joined = " ".join(tokens)

    hints = (
        "line-number",
        "line-numbers",
        "linenumber",
        "line_number",
        "line-number-gutter",
        "gutter",
        "code-line-number",
    )
    if any(hint in joined for hint in hints):
        return True

    for attr in ("data-line-number", "data-line", "aria-label"):
        if tag.has_attr(attr):
            value = str(tag.get(attr, "")).lower()
            if value.isdigit() or "line" in value:
                return True

    text = clean_text(tag.get_text(" ", strip=True))
    return bool(text.isdigit() and len(text) <= 6)


def _strip_leading_line_numbers(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    expected = 1
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == str(expected):
            i += 1
            expected += 1
            continue
        break

    if expected >= 4:
        lines = lines[i:]
    return "\n".join(lines).strip("\n")


def _extract_code_language(tag: Tag) -> str:
    candidates = []

    code = tag.find("code")
    if code:
        candidates.append(code)
    candidates.append(tag)

    for node in candidates:
        if getattr(node, "attrs", None) is None:
            continue
            
        for attr in ("data-language", "data-lang", "lang"):
            value = node.get(attr)
            if value:
                return str(value).strip().lower()

        for cls in _class_tokens(node):
            if cls.startswith("language-"):
                return cls.removeprefix("language-")
            if cls.startswith("lang-"):
                return cls.removeprefix("lang-")

    return ""


def extract_code_block(element: Tag) -> dict:
    """
    Extract code while keeping the source code column separate from any
    visual line-number gutter.
    """
    # Create a detached clone so we can heavily modify it safely
    clone = BeautifulSoup(str(element), "lxml")
    
    # Prefer the <code> block if it exists, otherwise use <pre>
    target_node = clone.find("code") or clone.find("pre") or clone

    # 1. Remove line numbers
    for node in target_node.find_all(True):
        if getattr(node, "attrs", None) is None:
            continue
        if _looks_like_line_number_node(node):
            node.decompose()
            
    # 2. Add structural newlines in case the site relies on HTML tags (like <div> or <br>) 
    # instead of literal `\n` text nodes inside the code block.
    for br in target_node.find_all("br"):
        br.replace_with("\n")
        
    for block_tag in target_node.find_all(["div", "li", "tr", "p"]):
        block_tag.append("\n")

    # 3. CRITICAL: Use empty string separator! 
    # Passing "\n" as the separator forces a newline between EVERY <span> tag.
    text = target_node.get_text(separator="", strip=False)

    text = _strip_leading_line_numbers(text)
    
    # 4. Clean up any excessive accidental blank lines caused by combining literal \n and block \n
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip("\n")

    return {
        "type": "code",
        # Pass the original 'element' for language extraction to check classes on <pre>
        "language": _extract_code_language(element),
        "text": text,
    }


def should_skip(tag: Tag) -> bool:
    current = tag
    while isinstance(current, Tag):
        if current.name in BOILERPLATE_TAGS or looks_like_boilerplate(current):
            return True
        current = current.parent

    return False


def extract_blocks(
    root: Tag,
    base_url: str,
) -> list[dict]:
    blocks = []

    # We process elements in document order.
    for element in root.find_all(
        [
            "h1", "h2", "h3", "h4", "h5", "h6",
            "p", "ul", "ol", "blockquote", "pre", "table", "img",
        ]
    ):
        if getattr(element, "attrs", None) is None:
            continue

        parent = element.parent
        if parent:
            if parent.name in [
                "li", "td", "th", "blockquote", "pre", "table",
            ]:
                continue

        if should_skip(element):
            continue

        if re.fullmatch(r"h[1-6]", element.name):
            text = clean_text(element.get_text(" ", strip=True))
            if text:
                blocks.append({
                    "type": "heading",
                    "level": int(element.name[1]),
                    "text": text,
                })

        elif element.name == "p":
            text = clean_text(element.get_text(" ", strip=True))
            if text:
                blocks.append({
                    "type": "paragraph",
                    "text": text,
                })

        elif element.name in ["ul", "ol"]:
            items = []
            for li in element.find_all("li", recursive=False):
                text = clean_text(li.get_text(" ", strip=True))
                if text:
                    items.append(text)
            if items:
                blocks.append({
                    "type": "list",
                    "ordered": element.name == "ol",
                    "items": items,
                })

        elif element.name == "blockquote":
            text = clean_text(element.get_text(" ", strip=True))
            if text:
                blocks.append({
                    "type": "blockquote",
                    "text": text,
                })

        elif element.name == "pre":
            code_block = extract_code_block(element)
            if code_block["text"]:
                blocks.append(code_block)

        elif element.name == "table":
            table = extract_table(element)
            if table["rows"]:
                blocks.append(table)

        elif element.name == "img":
            image = extract_image(element, base_url)
            if image:
                blocks.append(image)

    return blocks


# ---------------------------------------------------------------------
# MARKDOWN
# ---------------------------------------------------------------------

def blocks_to_markdown(blocks: list[dict]) -> str:
    output = []
    for block in blocks:
        block_type = block["type"]

        if block_type == "heading":
            level = block["level"]
            output.append(f"{'#' * level} {block['text']}")

        elif block_type == "paragraph":
            output.append(block["text"])

        elif block_type == "list":
            for index, item in enumerate(block["items"], start=1):
                if block["ordered"]:
                    output.append(f"{index}. {item}")
                else:
                    output.append(f"- {item}")

        elif block_type == "blockquote":
            output.append("> " + block["text"])

        elif block_type == "code":
            language = block.get("language", "").strip()
            fence = "~~~" if "```" in block["text"] else "```"
            opening = fence + language
            output.append(
                opening
                + "\n"
                + block["text"].rstrip()
                + "\n"
                + fence
            )

        elif block_type == "table":
            output.append(table_to_markdown(block))

        elif block_type == "image":
            alt = block["alt"]
            output.append(f"![{alt}]({block['src']})")

    return "\n\n".join(output)


# ---------------------------------------------------------------------
# VALIDATION / DIAGNOSTICS
# ---------------------------------------------------------------------

def diagnostics(soup: BeautifulSoup, content_root: Tag, blocks: list[dict]):
    headings = [b for b in blocks if b["type"] == "heading"]
    paragraphs = [b for b in blocks if b["type"] == "paragraph"]
    tables = [b for b in blocks if b["type"] == "table"]
    images = [b for b in blocks if b["type"] == "image"]

    def counts(scope):
        return {
            "headings": len(scope.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])),
            "tables": len(scope.find_all("table")),
            "images": len(scope.find_all("img")),
        }

    whole_doc = counts(soup)
    in_region = counts(content_root)

    print()
    print("========== EXTRACTION REPORT ==========")
    print(f"{'':20s}{'whole doc':>10s}{'in region':>10s}{'extracted':>10s}")
    print(f"{'Headings':20s}{whole_doc['headings']:>10d}{in_region['headings']:>10d}{len(headings):>10d}")
    print(f"{'Tables':20s}{whole_doc['tables']:>10d}{in_region['tables']:>10d}{len(tables):>10d}")
    print(f"{'Images':20s}{whole_doc['images']:>10d}{in_region['images']:>10d}{len(images):>10d}")
    print(f"{'Paragraphs':20s}{'':>10s}{'':>10s}{len(paragraphs):>10d}")
    print(f"Total blocks: {len(blocks)}")

    if in_region["headings"] != len(headings):
        region_heading_texts = {
            h.get_text(" ", strip=True) for h in content_root.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        }
        extracted_texts = {b["text"] for b in headings}
        missing = region_heading_texts - extracted_texts
        print(f"\n{len(missing)} heading(s) present in region but NOT extracted:")
        for m in list(missing)[:15]:
            print(f"  - {m}")

    if in_region["images"] != len(images):
        region_imgs = content_root.find_all("img")
        extracted_srcs = {b["src"] for b in images}
        missing_imgs = []
        for img in region_imgs:
            resolved = get_image_url(img, "")
            if resolved not in extracted_srcs:
                missing_imgs.append((img, resolved))

        print(f"\n{len(missing_imgs)} image(s) in region were not extracted:")
        for img, resolved in missing_imgs[:5]:
            print(f"  src={img.get('src')!r}")
            print(f"  srcset={img.get('srcset')!r}")
            print(f"  resolved={resolved!r}")

    print("========================================")
    print()


# ---------------------------------------------------------------------
# URL SLUG
# ---------------------------------------------------------------------

def slugify(url: str) -> str:
    slug = re.sub(r"https?://", "", url)
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", slug)
    return slug.strip("_")[:150]


# ---------------------------------------------------------------------
# PROCESS
# ---------------------------------------------------------------------

async def process(url: str):
    slug = slugify(url)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    html = await render(url)

    raw_path = os.path.join(OUTPUT_DIR, f"{slug}.raw.html")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Raw HTML: {raw_path}")

    soup = BeautifulSoup(html, "lxml")
    content_root = find_content_region(soup)
    blocks = extract_blocks(content_root, url)
    markdown = blocks_to_markdown(blocks)

    md_path = os.path.join(OUTPUT_DIR, f"{slug}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Source\n\n{url}\n\n---\n\n")
        f.write(markdown)
    print(f"Markdown: {md_path}")

    json_path = os.path.join(OUTPUT_DIR, f"{slug}.json")
    document = {
        "source": url,
        "blocks": blocks,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(document, f, indent=2, ensure_ascii=False)
    print(f"JSON: {json_path}")

    diagnostics(soup, content_root, blocks)


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

async def main():
    for url in TEST_URLS:
        try:
            await process(url)
        except Exception as e:
            print(f"ERROR processing {url}: {e}")

if __name__ == "__main__":
    asyncio.run(main())