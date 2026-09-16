# Content Synthesis MVP

Current scope: Phase 0 only.

Pipeline:

URLs / Markdown
-> cheap extraction
-> titles + headings + TF-IDF + embeddings representation
-> topic discovery
-> user selects research scope
-> Research Brief
-> LLM #1 (next phase)

The MVP deliberately keeps storage and API infrastructure out of scope.

## Run

```bash
python run_phase0.py sample_docs
```

The current local baseline uses TF-IDF vectors for discovery. The embedding and clustering interfaces are intentionally isolated so stronger local embedding models / HDBSCAN can be added later without changing the document contract.
