"""
AST-aware markdown ingestion.

Parses a markdown file into its structural tree (via markdown-it-py's token
stream) and flattens it into an ordered list of typed "blocks" — the atomic
units that every downstream stage (chunking, claim extraction, embeddings)
will consume.

Each block carries:
  - block_type      : heading | paragraph | list | table | code | image | blockquote
  - heading_path     : list of ancestor heading texts, e.g. ["Config", "Advanced"]
  - heading_level    : depth of the nearest ancestor heading (1-6), for headings themselves
  - position_index   : order of this block within the document (0-based)
  - char_start/end   : offsets into the ORIGINAL markdown source (provenance)
  - word_count       : cheap signal for filtering near-empty / boilerplate blocks
  - content          : the raw markdown text of this block (unmodified)
  - image_refs       : list of {alt, url} for image blocks / images inside a paragraph

Nothing here is semantic — no LLM calls, no meaning extraction. Purely a
lossless structural transform: string -> tree -> flat block list.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode


# ----------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------

@dataclass
class Block:
    block_id: str
    doc_id: str
    block_type: str                 # heading | paragraph | list | table | code | image | blockquote
    heading_path: list[str]
    heading_level: int | None
    position_index: int
    char_start: int
    char_end: int
    word_count: int
    content: str
    image_refs: list[dict] = field(default_factory=list)
    language: str | None = None     # for code blocks, e.g. "python"


# ----------------------------------------------------------------------
# Core parser
# ----------------------------------------------------------------------

MD = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])

# Node types we treat as top-level block-producing nodes.
BLOCK_NODE_TYPES = {
    "heading": "heading",
    "paragraph": "paragraph",
    "bullet_list": "list",
    "ordered_list": "list",
    "table": "table",
    "code_block": "code",
    "fence": "code",
    "blockquote": "blockquote",
}


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _extract_images(node: SyntaxTreeNode) -> list[dict]:
    """Walk a node's inline children and pull out any image references."""
    images = []
    for child in node.walk():
        if child.type == "image":
            alt = child.attrGet("alt") or "".join(
                c.content for c in child.children or [] if hasattr(c, "content")
            )
            images.append({"alt": alt, "url": child.attrGet("src")})
    return images


def _node_text(node: SyntaxTreeNode) -> str:
    """Best-effort plain-text rendering of a node's inline content."""
    parts = []
    for child in node.walk():
        if child.type == "text":
            parts.append(child.content)
        elif child.type == "code_inline":
            parts.append(child.content)
        elif child.type == "softbreak":
            parts.append(" ")
    return "".join(parts).strip()


def _find_char_span(source: str, node: SyntaxTreeNode, search_from: int) -> tuple[int, int, int]:
    """
    markdown-it doesn't give us character offsets directly, only line (map)
    ranges. We recover a stable character span by locating the node's line
    range within the original source text. Returns (start, end, next_search_from).
    """
    if node.map:
        line_start, line_end = node.map
        lines = source.splitlines(keepends=True)
        char_start = sum(len(l) for l in lines[:line_start])
        char_end = sum(len(l) for l in lines[:line_end])
        return char_start, char_end, char_end
    return search_from, search_from, search_from


# ----------------------------------------------------------------------
# Tree walk -> flat block list
# ----------------------------------------------------------------------

def parse_markdown_to_blocks(source: str, doc_id: str) -> list[Block]:
    tokens = MD.parse(source)
    root = SyntaxTreeNode(tokens)

    blocks: list[Block] = []
    heading_stack: list[tuple[int, str]] = []  # (level, text)
    position = 0
    search_cursor = 0

    def current_heading_path() -> list[str]:
        return [text for _, text in heading_stack]

    for node in root.children:
        node_type = BLOCK_NODE_TYPES.get(node.type)
        if node_type is None:
            continue  # skip node types we don't model as blocks (e.g. hr)

        char_start, char_end, search_cursor = _find_char_span(source, node, search_cursor)
        raw_content = source[char_start:char_end].strip()

        if node_type == "heading":
            level = int(node.tag[1])  # "h2" -> 2
            text = _node_text(node)
            # Pop any headings at this level or deeper, then push this one —
            # this is what keeps heading_path accurate as we descend/ascend.
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()

            blocks.append(Block(
                block_id=f"{doc_id}_b{position}",
                doc_id=doc_id,
                block_type="heading",
                heading_path=current_heading_path(),
                heading_level=level,
                position_index=position,
                char_start=char_start,
                char_end=char_end,
                word_count=_word_count(text),
                content=raw_content,
            ))
            heading_stack.append((level, text))
            position += 1
            continue

        text = _node_text(node)
        images = _extract_images(node)
        language = node.attrGet("info") if node_type == "code" and node.type == "fence" else None

        blocks.append(Block(
            block_id=f"{doc_id}_b{position}",
            doc_id=doc_id,
            block_type=node_type,
            heading_path=current_heading_path(),
            heading_level=None,
            position_index=position,
            char_start=char_start,
            char_end=char_end,
            word_count=_word_count(text),
            content=raw_content,
            image_refs=images,
            language=language,
        ))
        position += 1

    return blocks


# ----------------------------------------------------------------------
# I/O
# ----------------------------------------------------------------------

def ingest_file(md_path: Path, doc_id: str) -> dict:
    source = md_path.read_text(encoding="utf-8")
    blocks = parse_markdown_to_blocks(source, doc_id)
    return {
        "doc_id": doc_id,
        "source_path": str(md_path),
        "total_blocks": len(blocks),
        "block_type_counts": _type_counts(blocks),
        "blocks": [asdict(b) for b in blocks],
    }


def _type_counts(blocks: list[Block]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for b in blocks:
        counts[b.block_type] = counts.get(b.block_type, 0) + 1
    return counts


def ingest_directory(input_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    md_files = sorted(input_dir.glob("*.md"))
    if not md_files:
        print(f"No .md files found in {input_dir}")
        return

    for md_path in md_files:
        doc_id = md_path.stem
        result = ingest_file(md_path, doc_id)
        out_path = output_dir / f"{doc_id}.json"
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{doc_id}: {result['total_blocks']} blocks {result['block_type_counts']}")


if __name__ == "__main__":
    # Set these to your actual paths and run the file directly.
    INPUT_DIR = Path(r"C:\Users\lenovo\Downloads\browser_based_agent\dom_extract_fixed_pkg\extracted_dom")
    OUTPUT_DIR = Path("data/blocks")

    ingest_directory(INPUT_DIR, OUTPUT_DIR)