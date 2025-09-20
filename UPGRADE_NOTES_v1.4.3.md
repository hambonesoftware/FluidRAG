# FluidRAG v1.4.3 – Production Hybrid Retrieval with Structure-Aware Boosts

Date: 2025-09-20

## What’s new
- Pure-Python **BM25** + pluggable **embedding** scoring.
- **Hybrid fusion** with configurable weight (`alpha_embed`).
- **Structure-aware boosts**: tables for numeric queries, Binding normativity, standards mentions, heading-level specificity.
- **Neighborhood expansion** (prev/next chunk in section) + **xref expansion** (1 hop).
- Clean **config** in `backend/rag/config.py` and minimal **docs/tests**.

## Quickstart
```python
from backend.rag.indexer import Index
from backend.rag.search import hybrid_search
from backend.rag.embeddings import Embedder
from backend.pipeline.preprocess import section_bounded_chunks_from_pdf

pdf = 'path/to/customer_rfq.pdf'
chunks = list(section_bounded_chunks_from_pdf(pdf, sidecar_dir='sidecars'))
idx = Index(chunks)
embedder = Embedder(your_embedding_fn)  # supply your prod embedder
hits = hybrid_search(idx, 'SCCR 50 kA per UL 508A SB', embedder=embedder)
```
