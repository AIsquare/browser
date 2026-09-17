"""
AST-aware markdown ingestion — v2.

Fixes applied from review of a real sample:
  - token_count / char_count instead of misleading word_count
  - content_hash per block (needed for cross-document boilerplate detection)
  - section_id / parent_block_id / prev_block_id / next_block_id for cheap
    context expansion at retrieval time, without re-parsing anything
  - image-only blocks get block_type="image" with clean caption content,
    not raw markdown syntax sitting in `content`
  - list blocks are split into individual `list_item` atoms, each still
    linked back to the others via `list_id` so the original grouping is
    never lost
  - is_orphan flag for headings that skip levels (DOM/scraper artifacts)
  - is_boilerplate flag, populated by two SEPARATE mechanisms:
      1. deterministic single-doc rules (known extraction artifacts)
      2. cross-document frequency detection (site chrome / CTAs), which
         requires a full corpus pass — see detect_cross_document_boilerplate()

Still no LLM calls, no semantic judgment. Purely structural + statistical.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode


# ----------------------------------------------------------------------
# Tokenizer — swap this for your real downstream tokenizer.
# tiktoken wasn't installable in this sandbox (no network); this is a
# documented approximation (chars/4, English-text average) so the field
# exists and behaves sanely until you drop in the real one.
# ----------------------------------------------------------------------

def count_tokens(text: str) -> int:
    """
    Placeholder token counter. Replace the body with e.g.:
        import tiktoken
        _enc = tiktoken.get_encoding("cl100k_base")
        return len(_enc.encode(text))
    Approximation below: ~4 chars/token for English prose. Good enough for
    relative chunk-sizing decisions, NOT accurate enough for hard context
    limits — swap before you rely on it for that.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


# ----------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------

@dataclass
class Block:
    block_id: str
    doc_id: str
    block_type: str                 # heading | paragraph | list_item | table | code | image | blockquote
    heading_path: list[str]
    heading_level: int | None
    section_id: str | None          # block_id of nearest ancestor heading
    parent_block_id: str | None     # structural parent (heading, or list_id for list_items)
    list_id: str | None             # groups list_items back to their source list
    prev_block_id: str | None = None
    next_block_id: str | None = None
    position_index: int = 0
    char_start: int = 0
    char_end: int = 0
    char_count: int = 0
    token_count: int = 0
    content: str = ""
    content_hash: str = ""
    image_refs: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    language: str | None = None     # for code blocks, e.g. "python"
    is_orphan: bool = False         # heading that skips levels (scraper artifact)
    is_boilerplate: bool = False    # populated by deterministic + cross-doc passes


# ----------------------------------------------------------------------
# Core parser setup
# ----------------------------------------------------------------------

MD = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])

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


def _hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def _node_text(node: SyntaxTreeNode) -> str:
    parts = []
    for child in node.walk():
        if child.type == "text":
            parts.append(child.content)
        elif child.type == "code_inline":
            parts.append(child.content)
        elif child.type == "softbreak":
            parts.append(" ")
    return "".join(parts).strip()


def _extract_images(node: SyntaxTreeNode) -> list[dict]:
    images = []
    for child in node.walk():
        if child.type == "image":
            alt = child.attrGet("alt") or "".join(
                c.content for c in child.children or [] if hasattr(c, "content")
            )
            images.append({"alt": alt, "url": child.attrGet("src")})
    return images


def _extract_links(node: SyntaxTreeNode) -> list[dict]:
    links = []
    for child in node.walk():
        if child.type == "link_open":
            href = child.attrGet("href")
            links.append({"url": href, "text": None})  # text filled below if easy to pair
    return links


def _is_image_only_paragraph(node: SyntaxTreeNode, images: list[dict]) -> bool:
    """
    A paragraph whose only meaningful content is a single image (a figure).
    Must inspect only the DIRECT children of the paragraph's inline node —
    walk() would recurse into the image's own alt-text tokens and wrongly
    count them as sibling caption text.
    """
    if not images or len(images) != 1:
        return False
    inline = next((c for c in node.children if c.type == "inline"), None)
    if inline is None:
        return False
    sibling_text = "".join(
        c.content for c in inline.children
        if c.type in ("text", "code_inline")
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
# Deterministic (single-document) boilerplate rules
# ----------------------------------------------------------------------

_URL_ONLY_RE = re.compile(r"^https?://\S+$")


def apply_deterministic_boilerplate_rules(blocks: list[Block]) -> None:
    """
    Known, single-document extraction artifacts — not a statistical guess,
    a fix for specific patterns known to come from the scrape/extract tool.
    Mutates blocks in place.
    """
    for i, b in enumerate(blocks):
        # Rule: a heading literally "Source" followed by a bare URL paragraph.
        if b.block_type == "heading" and b.content.strip("# ").strip().lower() == "source":
            b.is_boilerplate = True
            if i + 1 < len(blocks) and _URL_ONLY_RE.match(blocks[i + 1].content.strip()):
                blocks[i + 1].is_boilerplate = True

        # Rule: a bare URL as a paragraph's entire content, anywhere.
        if b.block_type == "paragraph" and _URL_ONLY_RE.match(b.content.strip()):
            b.is_boilerplate = True


# ----------------------------------------------------------------------
# Tree walk -> flat block list
# ----------------------------------------------------------------------

def parse_markdown_to_blocks(source: str, doc_id: str) -> list[Block]:
    tokens = MD.parse(source)
    root = SyntaxTreeNode(tokens)

    blocks: list[Block] = []
    heading_stack: list[tuple[int, str, str]] = []  # (level, text, block_id)
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

        char_start, char_end, search_cursor = _find_char_span(source, node, search_cursor)
        raw_content = source[char_start:char_end].strip()

        # ---- Heading ----
        if node_type == "heading":
            level = int(node.tag[1])
            text = _node_text(node)
            is_orphan = bool(heading_stack) and level > heading_stack[-1][0] + 1

            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()

            block_id = next_id()
            parent_id = heading_stack[-1][2] if heading_stack else None

            blocks.append(Block(
                block_id=block_id,
                doc_id=doc_id,
                block_type="heading",
                heading_path=current_heading_path(),
                heading_level=level,
                section_id=parent_id,
                parent_block_id=parent_id,
                list_id=None,
                position_index=position,
                char_start=char_start,
                char_end=char_end,
                char_count=len(text),
                token_count=count_tokens(text),
                content=raw_content,
                content_hash=_hash(raw_content),
                is_orphan=is_orphan,
            ))
            heading_stack.append((level, text, block_id))
            position += 1
            continue

        section_id = current_section_id()

        # ---- List -> split into list_item atoms ----
        if node_type == "list":
            list_id = next_id()
            items = [c for c in node.children if c.type == "list_item"]
            for item in items:
                item_start, item_end, search_cursor = _find_char_span(source, item, search_cursor)
                item_text = _node_text(item)
                item_content = source[item_start:item_end].strip()
                images = _extract_images(item)
                links = _extract_links(item)

                blocks.append(Block(
                    block_id=next_id(),
                    doc_id=doc_id,
                    block_type="list_item",
                    heading_path=current_heading_path(),
                    heading_level=None,
                    section_id=section_id,
                    parent_block_id=list_id,
                    list_id=list_id,
                    position_index=position,
                    char_start=item_start,
                    char_end=item_end,
                    char_count=len(item_text),
                    token_count=count_tokens(item_text),
                    content=item_content,
                    content_hash=_hash(item_content),
                    image_refs=images,
                    links=links,
                ))
                position += 1
            continue

        # ---- Everything else (paragraph / table / code / blockquote) ----
        text = _node_text(node)
        images = _extract_images(node)
        links = _extract_links(node)
        language = node.attrGet("info") if node_type == "code" and node.type == "fence" else None

        # Image-only paragraph -> retype as "image", content becomes the caption.
        if node_type == "paragraph" and _is_image_only_paragraph(node, images):
            block_type = "image"
            content_value = images[0]["alt"] or ""
        else:
            block_type = node_type
            content_value = raw_content

        blocks.append(Block(
            block_id=next_id(),
            doc_id=doc_id,
            block_type=block_type,
            heading_path=current_heading_path(),
            heading_level=None,
            section_id=section_id,
            parent_block_id=section_id,
            list_id=None,
            position_index=position,
            char_start=char_start,
            char_end=char_end,
            char_count=len(content_value if block_type == "image" else text),
            token_count=count_tokens(content_value if block_type == "image" else text),
            content=content_value,
            content_hash=_hash(content_value),
            image_refs=images,
            links=links,
            language=language,
        ))
        position += 1

    # Link prev/next across the whole flat sequence.
    for i, b in enumerate(blocks):
        b.prev_block_id = blocks[i - 1].block_id if i > 0 else None
        b.next_block_id = blocks[i + 1].block_id if i < len(blocks) - 1 else None

    apply_deterministic_boilerplate_rules(blocks)
    return blocks


# ----------------------------------------------------------------------
# Cross-document boilerplate detection (site chrome / repeated CTAs)
# Separate pass, run AFTER a batch of documents has been ingested —
# needs multiple docs (ideally same domain) to have any signal.
# ----------------------------------------------------------------------

def detect_cross_document_boilerplate(
    output_dir: Path,
    group_key_fn=lambda doc_id: doc_id.split("_")[0],  # crude domain grouping by doc_id prefix
    frequency_threshold: float = 0.15,
) -> dict:
    """
    Reads every ingested doc in output_dir, groups by group_key_fn(doc_id)
    (default: first underscore-token of doc_id — replace with real domain
    extraction once you have that field), and flags any block whose
    content_hash repeats across more than `frequency_threshold` fraction
    of documents in the same group as is_boilerplate=True.

    Rewrites each doc's JSON in place with updated flags. Returns a summary.
    """
    doc_files = sorted(output_dir.glob("*.json"))
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in doc_files]

    groups: dict[str, list[dict]] = defaultdict(list)
    for doc in docs:
        groups[group_key_fn(doc["doc_id"])].append(doc)

    summary = {}
    for group_key, group_docs in groups.items():
        hash_doc_counts: dict[str, set] = defaultdict(set)
        for doc in group_docs:
            for b in doc["blocks"]:
                hash_doc_counts[b["content_hash"]].add(doc["doc_id"])

        n_docs = len(group_docs)
        # A hash needs to repeat across a real number of documents, not just
        # clear a fraction — with a small n_docs, a fraction alone (e.g.
        # 1/3 = 0.33) flags content that only ever appeared in ONE document.
        # Require both: relative frequency AND an absolute minimum of 2 docs.
        import math
        min_docs_required = max(2, math.ceil(frequency_threshold * n_docs))
        flagged_hashes = {
            h for h, doc_ids in hash_doc_counts.items()
            if len(doc_ids) >= min_docs_required and n_docs > 1
        }

        flagged_count = 0
        for doc in group_docs:
            for b in doc["blocks"]:
                if b["content_hash"] in flagged_hashes:
                    b["is_boilerplate"] = True
                    flagged_count += 1

        summary[group_key] = {
            "docs_in_group": n_docs,
            "blocks_flagged": flagged_count,
        }

    for path, doc in zip(doc_files, docs):
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    return summary


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
        "boilerplate_block_count": sum(1 for b in blocks if b.is_boilerplate),
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
        print(f"{doc_id}: {result['total_blocks']} blocks {result['block_type_counts']} "
              f"(deterministic boilerplate: {result['boilerplate_block_count']})")


if __name__ == "__main__":
    # Set these to your actual paths and run the file directly.
    INPUT_DIR = Path(r"C:\Users\lenovo\Downloads\browser_based_agent\dom_extract_fixed_pkg\extracted_dom")
    OUTPUT_DIR = Path("data/blocks")

    ingest_directory(INPUT_DIR, OUTPUT_DIR)

    # Cross-document pass — only meaningful once you have multiple docs,
    # ideally several from the same domain. Comment out if running on a
    # single test document.
    summary = detect_cross_document_boilerplate(OUTPUT_DIR)
    print("\nCross-document boilerplate detection:")
    for group, stats in summary.items():
        print(f"  {group}: {stats}")
