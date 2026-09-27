"""
AST-aware markdown ingestion.

Reads every .md file in extracted/ and writes a block AST to
data/blocks/<doc_id>.json. The loader (ingest.py) then reads those
JSONs and populates the DB.

New vs. previous version:
  - is_math flag: detects LaTeX/math blocks so the loader emits them
    as single atoms (never sentence-splits them)
  - Footnote handling: strips [^N] markers from text, records refs
  - _extract_links: now pairs link_open with the following text
  - Offset verification: flags blocks whose char span doesn't match
    the source slice

Still no LLM, no semantic judgment. Purely structural.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode


# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------

INPUT_DIR  = Path('extracted')
OUTPUT_DIR = Path('data/blocks')

MD = MarkdownIt('commonmark', {'html': False}).enable(['table', 'strikethrough'])

BLOCK_NODE_TYPES = {
    'heading':      'heading',
    'paragraph':    'paragraph',
    'bullet_list':  'list',
    'ordered_list': 'list',
    'table':        'table',
    'code_block':   'code',
    'fence':        'code',
    'blockquote':   'blockquote',
}


# ----------------------------------------------------------------------
# Math detection — one regex, no parsing
# ----------------------------------------------------------------------

MATH_RE = re.compile(
    r'\{\\displaystyle'          # Wikipedia's math wrapper
    r'|\\frac|\\sum|\\int|\\sqrt|\\cdot|\\left\(|\\right\)|\\tilde|\\displaystyle'
    r'|^\s*\$\$.*\$\$\s*$'        # block math on its own line
    r'|^\s*\\\[.*\\\]\s*$'        # \[ ... \]
)


def is_math(text: str) -> bool:
    if not text:
        return False
    # Heuristic: math if regex matches AND the block has more backslashes
    # than typical prose (avoids false positives on stray "frac" in prose)
    if not MATH_RE.search(text):
        return False
    return text.count('\\') >= 2


# ----------------------------------------------------------------------
# Footnote handling
# ----------------------------------------------------------------------

FOOTNOTE_REF_RE = re.compile(r'\[\^([^\]]+)\]')


def strip_footnote_refs(text: str) -> tuple[str, list[str]]:
    """Return (clean_text, [marker1, marker2, ...])."""
    markers = FOOTNOTE_REF_RE.findall(text)
    clean = FOOTNOTE_REF_RE.sub('', text)
    return clean, markers


# ----------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------

@dataclass
class Block:
    block_id: str
    doc_id: str
    block_type: str
    heading_path: list[str]
    heading_level: int | None
    section_id: str | None
    parent_block_id: str | None
    list_id: str | None
    prev_block_id: str | None
    next_block_id: str | None
    position_index: int
    char_start: int
    char_end: int
    char_count: int
    token_count: int
    content: str                 # raw markdown slice
    text: str                    # cleaned text (footnote refs stripped)
    content_hash: str
    image_refs: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    footnote_refs: list[str] = field(default_factory=list)
    language: str | None = None
    is_orphan: bool = False
    is_boilerplate: bool = False
    is_math: bool = False
    is_footnote: bool = False


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode('utf-8')).hexdigest()[:16]


def count_tokens(text: str) -> int:
    """Approximation. Swap for the real tokenizer if precision matters."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _scrub(value):
    if isinstance(value, str):
        return ''.join(
            '\ufffd' if 0xD800 <= ord(char) <= 0xDFFF else char
            for char in value
        )
    if isinstance(value, dict):
        return {_scrub(key): _scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def _node_text(node: SyntaxTreeNode) -> str:
    parts = []
    for child in node.walk():
        if child.type == 'text':
            parts.append(child.content)
        elif child.type == 'code_inline':
            parts.append(child.content)
        elif child.type in ('softbreak', 'hardbreak'):
            parts.append(' ')

    # Inline markup (bold/italic) separates text nodes without a space.
    # Insert one where two alphanumeric characters would collide.
    out = ''
    for p in parts:
        if out and p:
            if out[-1].isalnum() and p[0].isalnum():
                out += ' '
        out += p
    return re.sub(r'\s+', ' ', out).strip()


def _extract_images(node: SyntaxTreeNode) -> list[dict]:
    images = []
    for child in node.walk():
        if child.type == 'image':
            alt = child.attrGet('alt') or ''.join(
                c.content for c in child.children or [] if hasattr(c, 'content')
            )
            images.append({'alt': alt, 'url': child.attrGet('src')})
    return images


def _extract_links(node: SyntaxTreeNode) -> list[dict]:
    """
    Pair each link_open with its anchor text by walking children in order.
    Fills 'text' on the previous link_open when a text node follows.
    """
    links = []
    current = None
    for child in node.walk():
        if child.type == 'link_open':
            current = {'url': child.attrGet('href'), 'text': ''}
            links.append(current)
        elif child.type == 'link_close':
            current = None
        elif child.type == 'text' and current is not None:
            current['text'] += child.content
    for l in links:
        l['text'] = l['text'].strip()
    return links


def _is_image_only_paragraph(node: SyntaxTreeNode, images: list[dict]) -> bool:
    if not images or len(images) != 1:
        return False
    inline = next((c for c in node.children if c.type == 'inline'), None)
    if inline is None:
        return False
    sibling_text = ''.join(
        c.content for c in inline.children if c.type in ('text', 'code_inline')
    )
    return len(sibling_text.strip()) == 0


def _find_char_span(source: str, node: SyntaxTreeNode, search_from: int) -> tuple[int, int, int]:
    if node.map:
        line_start, line_end = node.map
        lines = source.splitlines(keepends=True)
        char_start = sum(len(l) for l in lines[:line_start])
        char_end = sum(len(l) for l in lines[:line_end])
        return char_start, char_end, char_end
    return search_from, search_from, search_from


# ----------------------------------------------------------------------
# Deterministic single-doc boilerplate rules
# ----------------------------------------------------------------------

_URL_ONLY_RE = re.compile(r'^https?://\S+$')


def apply_deterministic_boilerplate(blocks: list[Block]) -> None:
    for i, b in enumerate(blocks):
        if b.block_type == 'heading' and b.content.strip('# ').strip().lower() == 'source':
            b.is_boilerplate = True
            if i + 1 < len(blocks) and _URL_ONLY_RE.match(blocks[i + 1].content.strip()):
                blocks[i + 1].is_boilerplate = True
        if b.block_type == 'paragraph' and _URL_ONLY_RE.match(b.content.strip()):
            b.is_boilerplate = True


# ----------------------------------------------------------------------
# Frontmatter (only if present — safe no-op otherwise)
# ----------------------------------------------------------------------

_FM_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)


def split_frontmatter(source: str) -> tuple[dict, str]:
    m = _FM_RE.match(source)
    if not m:
        return {}, source
    fm_text = m.group(1)
    body = source[m.end():]
    try:
        import yaml
        fm = yaml.safe_load(fm_text) or {}
        if not isinstance(fm, dict):
            fm = {}
    except Exception:
        fm = {}
    return fm, body


# ----------------------------------------------------------------------
# Main parser
# ----------------------------------------------------------------------

def parse_markdown(source: str, doc_id: str) -> tuple[list[Block], dict]:
    frontmatter, body = split_frontmatter(source)
    # offsets are relative to `body` now — prepend frontmatter length
    offset_shift = len(source) - len(body)

    tokens = MD.parse(body)
    root = SyntaxTreeNode(tokens)

    blocks: list[Block] = []
    heading_stack: list[tuple[int, str, str]] = []
    position = 0
    search_cursor = 0

    def current_heading_path() -> list[str]:
        return [text for _, text, _ in heading_stack]

    def current_section_id() -> str | None:
        return heading_stack[-1][2] if heading_stack else None

    def next_id() -> str:
        return f"{doc_id}_b{position}"

    for node in root.children:
        node_type = BLOCK_NODE_TYPES.get(node.type)
        if node_type is None:
            continue

        cs, ce, search_cursor = _find_char_span(body, node, search_cursor)
        cs += offset_shift
        ce += offset_shift
        raw_content = source[cs:ce].strip()

        # ---- Heading ----
        if node_type == 'heading':
            level = int(node.tag[1])
            text = _node_text(node)
            is_orphan = bool(heading_stack) and level > heading_stack[-1][0] + 1
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            block_id = next_id()
            parent_id = heading_stack[-1][2] if heading_stack else None

            blocks.append(Block(
                block_id=block_id, doc_id=doc_id, block_type='heading',
                heading_path=current_heading_path(), heading_level=level,
                section_id=parent_id, parent_block_id=parent_id, list_id=None,
                prev_block_id=None, next_block_id=None,
                position_index=position,
                char_start=cs, char_end=ce,
                char_count=len(text), token_count=count_tokens(text),
                content=raw_content, text=text,
                content_hash=_hash(raw_content),
                is_orphan=is_orphan,
            ))
            heading_stack.append((level, text, block_id))
            position += 1
            continue

        section_id = current_section_id()

        # ---- List -> split into list_item atoms ----
        if node_type == 'list':
            list_id = next_id()
            items = [c for c in node.children if c.type == 'list_item']
            for item in items:
                item_cs, item_ce, search_cursor = _find_char_span(body, item, search_cursor)
                item_cs += offset_shift
                item_ce += offset_shift
                item_text = _node_text(item)
                item_content = source[item_cs:item_ce].strip()
                images = _extract_images(item)
                links = _extract_links(item)

                blocks.append(Block(
                    block_id=next_id(), doc_id=doc_id, block_type='list_item',
                    heading_path=current_heading_path(), heading_level=None,
                    section_id=section_id, parent_block_id=list_id, list_id=list_id,
                    prev_block_id=None, next_block_id=None,
                    position_index=position,
                    char_start=item_cs, char_end=item_ce,
                    char_count=len(item_text), token_count=count_tokens(item_text),
                    content=item_content, text=item_text,
                    content_hash=_hash(item_content),
                    image_refs=images, links=links,
                ))
                position += 1
            continue

        # ---- Paragraph / table / code / blockquote ----
        text_raw = _node_text(node)
        images = _extract_images(node)
        links = _extract_links(node)
        language = node.attrGet('info') if node_type == 'code' and node.type == 'fence' else None

        if node_type == 'paragraph' and _is_image_only_paragraph(node, images):
            block_type = 'image'
            content_value = images[0]['alt'] or ''
            text_value = content_value
        else:
            block_type = node_type
            content_value = raw_content
            text_value = text_raw

        # Math detection
        math_flag = is_math(content_value) or is_math(text_value)

        # Footnote refs (only for non-math text)
        footnote_refs = []
        if not math_flag:
            text_value, footnote_refs = strip_footnote_refs(text_value)

        blocks.append(Block(
            block_id=next_id(), doc_id=doc_id, block_type=block_type,
            heading_path=current_heading_path(), heading_level=None,
            section_id=section_id, parent_block_id=section_id, list_id=None,
            prev_block_id=None, next_block_id=None,
            position_index=position,
            char_start=cs, char_end=ce,
            char_count=len(text_value), token_count=count_tokens(text_value),
            content=content_value, text=text_value,
            content_hash=_hash(content_value),
            image_refs=images, links=links, footnote_refs=footnote_refs,
            language=language, is_math=math_flag,
        ))
        position += 1

    # Link prev/next
    for i, b in enumerate(blocks):
        b.prev_block_id = blocks[i - 1].block_id if i > 0 else None
        b.next_block_id = blocks[i + 1].block_id if i < len(blocks) - 1 else None

    apply_deterministic_boilerplate(blocks)

    # Verify offsets
    for b in blocks:
        expected = source[b.char_start:b.char_end].strip()
        if expected and b.content and expected[:50] != b.content[:50]:
            # Store but flag
            b.__dict__['_offset_mismatch'] = True

    return blocks, frontmatter


# ----------------------------------------------------------------------
# I/O
# ----------------------------------------------------------------------

def ingest_file(md_path: Path) -> dict:
    doc_id = md_path.stem
    source = md_path.read_text(encoding='utf-8')
    blocks, frontmatter = parse_markdown(source, doc_id)

    type_counts: dict[str, int] = {}
    for b in blocks:
        type_counts[b.block_type] = type_counts.get(b.block_type, 0) + 1

    return {
        'doc_id': doc_id,
        'source_path': str(md_path),
        'frontmatter': frontmatter,
        'total_blocks': len(blocks),
        'block_type_counts': type_counts,
        'boilerplate_count': sum(1 for b in blocks if b.is_boilerplate),
        'math_count':       sum(1 for b in blocks if b.is_math),
        'blocks': [asdict(b) for b in blocks],
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    md_files = sorted(INPUT_DIR.glob('*.md'))
    if not md_files:
        print(f"no .md files in {INPUT_DIR}")
        return

    for md_path in md_files:
        result = ingest_file(md_path)
        result = _scrub(result)
        out_path = OUTPUT_DIR / f"{result['doc_id']}.json"
        out_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding='utf-8',
        )
        print(f"{result['doc_id'][:60]:60s}  "
              f"{result['total_blocks']:4d} blocks  "
              f"boiler: {result['boilerplate_count']:2d}  "
              f"math: {result['math_count']:2d}")


if __name__ == '__main__':
    main()