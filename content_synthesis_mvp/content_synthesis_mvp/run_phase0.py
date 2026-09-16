from __future__ import annotations

import json
import sys
from pathlib import Path

from discovery import discover_topics
from ingest import load_html, load_markdown
from dotenv import load_dotenv

load_dotenv() 

def load_documents(folder: Path) -> list:
    docs = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() in {".md", ".markdown"}:
            docs.append(load_markdown(path))
        elif path.suffix.lower() in {".html", ".htm"}:
            docs.append(load_html(path, url=f"file://{path.resolve()}"))
            
    # Fix the "Source" title issue globally so the embedding model gets real titles
    for doc in docs:
        if not doc.source.title or doc.source.title.strip() == "Source":
            real_title = None
            
            # Search headings for the first real title
            for h in getattr(doc.content, "headings", []):
                if h.strip() and h.strip() != "Source":
                    real_title = h.strip()
                    break
            
            # Fallback to URL formatting if no headings exist
            if not real_title and getattr(doc.source, "url", None):
                real_title = doc.source.url.split("?")[0].rstrip("/").split("/")[-1]
                
            doc.source.title = real_title or doc.document_id
            
    return docs

DEFAULT_FOLDER = Path(__file__).resolve().parent / "sample_docs"

def main(folder: str | Path | None = None) -> None:
    if folder is None:
        folder = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FOLDER

    folder = Path(folder)
    docs = load_documents(folder)
    result = discover_topics(docs)
    summaries = result.topic_summaries

    print(f"Documents discovered: {len(docs)}")
    print("\nTopic groups:\n")
    for cid, summary in sorted(summaries.items()):
        print(f"Cluster {cid} ({summary['document_count']} docs)")
        print(f"  terms: {', '.join(summary['top_terms'])}")
        
        # Look up actual documents to print their URLs and newly fixed titles
        for doc_id in summary["document_ids"]:
            doc = next((d for d in docs if d.document_id == doc_id), None)
            if doc:
                display_name = doc.source.title
                url = getattr(doc.source, "url", "No URL")
                print(f"  - [{display_name}] {url}")
        print()

    output = Path("phase0_discovery.json")
    output.write_text(
        json.dumps([d.to_dict() for d in docs], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nWrote: {output.resolve()}")


if __name__ == "__main__":
    main()