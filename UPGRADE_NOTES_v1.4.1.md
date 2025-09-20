# FluidRAG v1.4.1 – Responsible Chunking, Layout-Aware Extraction, Tables

Date: 2025-09-20

## What's new
- RFQ-aware header detection wired end-to-end (with disqualifiers).
- Section-bounded chunking with overlap (no cross-section chunks).
- Layout-aware PDF extraction (PyMuPDF/pdfplumber) with graceful fallbacks.
- Tables → CSV sidecars, plus metadata for provenance.
- One-shot API in `preprocess.py`: `section_bounded_chunks_from_pdf(...)`.
- TOC Preview UI module ready to plug in.

## How to use
```python
from backend.pipeline.preprocess import section_bounded_chunks_from_pdf
pdf = 'path/to/customer_rfq.pdf'
for chunk in section_bounded_chunks_from_pdf(pdf, sidecar_dir='sidecars', tok_budget_chars=6400, overlap_lines=3):
    # index chunk['text'] with metadata
    pass
```
