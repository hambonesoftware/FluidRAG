# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Optional

def numbering_depth(section_number: Optional[str]) -> Optional[int]:
    if not section_number:
        return None
    s = section_number.strip()
    if s and any(ch.isdigit() for ch in s):
        return s.count(".") + 1
    if "." in s:
        return s.count(".") + 1
    return 1

def map_font_sizes_to_levels(font_sizes: List[float], max_levels: int = 4):
    uniq = sorted({round(x, 2) for x in font_sizes if x is not None}, reverse=True)
    if not uniq:
        return {}
    uniq = uniq[:max_levels]
    return {size: i + 1 for i, size in enumerate(uniq)}

def infer_heading_level(font_size: Optional[float], section_number: Optional[str],
                        size_to_level_map: dict, default_level: int = 3):
    lvl_num = numbering_depth(section_number)
    lvl_font = None
    if font_size is not None and size_to_level_map:
        nearest = min(size_to_level_map.keys(), key=lambda k: abs(k - round(font_size, 2)))
        lvl_font = size_to_level_map.get(nearest)
    if lvl_num and lvl_font:
        return min(lvl_num, lvl_font)
    if lvl_num:
        return lvl_num
    if lvl_font:
        return lvl_font
    return default_level
