# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Dict, Any, Iterable, Optional
from backend.parse.header_detector import is_header_line

def sections_from_lines(pages_lines: List[List[str]], page_line_styles: Optional[List[List[dict]]]=None) -> List[dict]:
    sections = []
    cur = {'title':'Preamble', 'id':'0', 'content':[], 'page_start':1, 'page_end':1}
    for pi, lines in enumerate(pages_lines or [], start=1):
        styles = page_line_styles[pi-1] if page_line_styles and pi-1 < len(page_line_styles) else [None]*len(lines)
        for li, line in enumerate(lines):
            style = styles[li] or {}
            ok, _ = is_header_line(line, style=style)
            if ok:
                if cur['content']:
                    cur['page_end'] = pi
                    sections.append(cur)
                cur = {'title': line.strip(), 'id': str(len(sections)+1), 'content': [], 'page_start': pi, 'page_end': pi}
            else:
                cur['content'].append(line)
    if cur['content']:
        sections.append(cur)
    return sections

def yield_section_chunks(sections: List[dict], tok_budget_chars:int=6400, overlap_lines:int=3) -> Iterable[Dict[str,Any]]:
    for sec in sections:
        lines = sec.get('content') or []
        if not lines:
            continue
        buf, size, idx = [], 0, 0
        for line in lines:
            l = (line or '') + '\n'
            if size + len(l) > tok_budget_chars and buf:
                yield _emit(buf, sec, idx); idx += 1
                buf = buf[-overlap_lines:] if overlap_lines>0 else []
                size = sum(len(t) for t in buf)
            buf.append(l); size += len(l)
        if buf:
            yield _emit(buf, sec, idx)

def _emit(buf: List[str], sec: dict, idx:int) -> Dict[str,Any]:
    return {'text': ''.join(buf).strip(),
            'section_title': sec['title'],
            'section_id': sec['id'],
            'page_start': sec['page_start'],
            'page_end': sec['page_end'],
            'chunk_index_in_section': idx,
            'chunk_type': 'paragraph'}
