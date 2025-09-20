# Search Engine – Integration Guide
## Minimal example
```python
from backend.rag.indexer import Index
from backend.rag.search import hybrid_search
from backend.rag.embeddings import Embedder

chunks = [
  {'text':'The panel SCCR shall be 50 kA at 480 V.', 'chunk_type':'paragraph', 'section_id':'5.2', 'page_start':12, 'page_end':12, 'normative_strength':'Binding', 'referenced_standards':['UL 508A SB'], 'heading_level':2},
  {'text':'Table 3 – Conductor sizes: 10 AWG, THHN, 90°C', 'chunk_type':'table', 'section_id':'5.3', 'page_start':13, 'page_end':13, 'heading_level':3}
]
def dummy_embed(texts):
    # Replace with your production embedder
    return [[float(len(t)%10)]*8 for t in texts]
idx = Index(chunks)
embedder = Embedder(dummy_embed)
results = hybrid_search(idx, 'UL 508A SB SCCR 50 kA at 480V', embedder=embedder)
for r in results:
    print(r['score'], r['text'][:60])
```
