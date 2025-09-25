# -*- coding: utf-8 -*-
"""Layout-aware PDF extractor with fallbacks; dumps tables to CSV sidecars.
Now captures **per-line font size/bold/bbox** using PyMuPDF get_text('dict').
Produces:
- pages_linear: list[str]
- pages_lines: list[list[str]]
- page_line_styles: list[list[dict]]  # aligned with pages_lines by index
- layout_blocks: list[dict]
- tables: list[dict]
- engines: list[str]
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional
import os, csv, hashlib, math, json

from ..parse import header_config

def _stats(nums):
    if not nums: 
        return (0.0, 1.0)
    m = sum(nums)/len(nums)
    v = sum((x-m)*(x-m) for x in nums)/max(1,len(nums))
    return (m, math.sqrt(v) if v>0 else 1.0)

def extract(pdf_path: str, out_dir: Optional[str]=None) -> Dict[str, Any]:
    pages_linear: List[str] = []
    pages_lines: List[List[str]] = []
    page_line_styles: List[List[Dict[str,Any]]] = []
    layout_blocks: List[Dict[str,Any]] = []
    tables: List[Dict[str,Any]] = []
    tried = []

    # 1) PyMuPDF detailed dict (preferred)
    try:
        import fitz  # PyMuPDF
        tried.append("pymupdf")
        doc = fitz.open(pdf_path)
        doc_tag = header_config.sanitize_component(os.path.splitext(os.path.basename(pdf_path or ""))[0])
        for i, page in enumerate(doc, start=1):
            d = page.get_text('dict')  # blocks -> lines -> spans
            # Reconstruct lines with style metrics
            lines_text: List[str] = []
            lines_style: List[Dict[str,Any]] = []
            font_sizes = []
            debug_spans: List[Dict[str, Any]] = []
            span_counter = 0
            for b in d.get('blocks', []):
                for l in b.get('lines', []):
                    spans = l.get('spans', [])
                    if not spans:
                        continue
                    # Concatenate span text; take max font size & bold if any span bold
                    text = "".join(s.get('text','') for s in spans).rstrip()
                    if not text:
                        continue
                    fs = max((s.get('size', 0.0) for s in spans), default=0.0)
                    is_bold = any('Bold' in (s.get('font','') or '') or s.get('flags',0) & 2 for s in spans)
                    is_italic = any('Italic' in (s.get('font','') or '') or s.get('flags',0) & 1 for s in spans)
                    bbox = l.get('bbox', [0,0,0,0])
                    x0, y0, x1, y1 = (bbox + [0,0,0,0])[:4]
                    font_names = [s.get('font') for s in spans if s.get('font')]
                    primary_font = font_names[0] if font_names else ''
                    letters = [c for c in text if c.isalpha()]
                    caps_ratio = (sum(c.isupper() for c in letters)/max(1,len(letters))) if letters else 0.0
                    lines_text.append(text)
                    lines_style.append({
                        'font_size': fs,
                        'bold': bool(is_bold),
                        'italics': bool(is_italic),
                        'caps_ratio': caps_ratio,
                        'bbox': bbox,
                        'x_left': x0,
                        'x_right': x1,
                        'y_top': y0,
                        'font_name': primary_font,
                        'span_count': len(spans),
                    })
                    font_sizes.append(fs)
                    if header_config.DEBUG_HEADERS:
                        for span in spans:
                            bbox_span = span.get('bbox') or [x0, y0, x1, y1]
                            debug_spans.append({
                                'span_idx': span_counter,
                                'text_raw': span.get('text', ''),
                                'bbox': list(bbox_span),
                                'font': span.get('font'),
                                'size': span.get('size'),
                                'bold': bool('Bold' in (span.get('font','') or '') or span.get('flags',0) & 2),
                                'italics': bool('Italic' in (span.get('font','') or '') or span.get('flags',0) & 1),
                                'source': 'pdf',
                            })
                            span_counter += 1
            # Per-page font sigma rank
            mu, sigma = _stats(font_sizes)
            if sigma <= 0:
                sigma = 1.0
            for st in lines_style:
                st['font_sigma_rank'] = (st['font_size'] - mu)/sigma
            pages_lines.append(lines_text)
            page_line_styles.append(lines_style)
            # Also keep plain text for backward compatibility
            pages_linear.append("\n".join(lines_text))

            if header_config.DEBUG_HEADERS:
                base_dir = header_config.DEBUG_DIR or "./_debug/headers"
                header_config._ensure_dir(base_dir)
                page_dir = os.path.join(base_dir, doc_tag, f"page_{i-1:04d}")
                header_config._ensure_dir(page_dir)
                spans_path = os.path.join(page_dir, "spans.jsonl")
                with open(spans_path, 'w', encoding='utf-8') as fh:
                    for entry in debug_spans:
                        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

            # Blocks for coarse layout view
            blocks = page.get_text('blocks') or []
            for b in blocks:
                vals = list(b)+['']*(5-len(b))
                x0,y0,x1,y1,txt = vals[:5]
                letters = [c for c in (txt or '') if c.isalpha()]
                caps_ratio = (sum(c.isupper() for c in letters)/max(1,len(letters))) if letters else 0.0
                layout_blocks.append({
                    'page': i,
                    'bbox': [x0,y0,x1,y1],
                    'text': txt or '',
                    'style': {'bold': any(t.isupper() for t in (txt or '')[:20]) if txt else False,
                              'font_sigma_rank': 0.0,
                              'caps_ratio': caps_ratio},
                    'type': 'block'
                })
        doc.close()
    except Exception:
        pass

    # 2) Tables via pdfplumber
    try:
        import pdfplumber
        tried.append('pdfplumber')
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                try:
                    tbs = page.extract_tables()
                except Exception:
                    tbs = []
                for ti, tbl in enumerate(tbs or []):
                    csv_path = None
                    if out_dir:
                        os.makedirs(out_dir, exist_ok=True)
                        name = f'table_p{i}_{ti}.csv'
                        csv_path = os.path.join(out_dir, name)
                        with open(csv_path, 'w', newline='', encoding='utf-8') as fh:
                            w = csv.writer(fh)
                            for row in tbl:
                                w.writerow([(c if c is not None else '') for c in row])
                    tables.append({'page': i, 'index': ti, 'csv': csv_path, 'rows': len(tbl or [])})
    except Exception:
        pass

    # 3) Fallback linear text
    if not pages_linear:
        try:
            from pypdf import PdfReader
            tried.append('pypdf')
            reader = PdfReader(pdf_path)
            for p in reader.pages:
                pages_linear.append(p.extract_text() or '')
                pages_lines.append((p.extract_text() or '').splitlines())
                page_line_styles.append([{} for _ in pages_lines[-1]])
        except Exception:
            pages_linear = []
            pages_lines = []
            page_line_styles = []

    return {
        'pages_linear': pages_linear,
        'pages_lines': pages_lines,
        'page_line_styles': page_line_styles,
        'layout_blocks': layout_blocks,
        'tables': tables,
        'engines': tried
    }
