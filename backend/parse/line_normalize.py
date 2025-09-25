# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Dict, Any
import csv
import os

from . import header_config


def _codepoints(text: str) -> str:
    return " ".join(f"U+{ord(ch):04X}" for ch in text)


def _caps_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(c.isupper() for c in letters) / max(1, len(letters))


def _coerce_style(style: Dict[str, Any], text: str) -> Dict[str, Any]:
    style = dict(style or {})
    bbox = style.get("bbox")
    if bbox and len(bbox) >= 4:
        style.setdefault("x_left", bbox[0])
        style.setdefault("y_top", bbox[1])
        style.setdefault("x_right", bbox[2])
    style.setdefault("font_name", style.get("font") or "")
    style.setdefault("font_size", style.get("font_size"))
    style.setdefault("bold", bool(style.get("bold")))
    style.setdefault("italics", bool(style.get("italics")))
    style.setdefault("span_count", style.get("span_count"))
    if style.get("caps_ratio") is None:
        style["caps_ratio"] = _caps_ratio(text)
    return style


def normalize_page_lines(
    doc_id: str,
    page_idx: int,
    page_lines: List[str],
    page_styles: List[Dict[str, Any]] | None,
) -> List[Dict[str, Any]]:
    styles = page_styles or [{} for _ in page_lines]
    doc_component = header_config.sanitize_component(doc_id or "document")
    base_dir = header_config.DEBUG_DIR or "./_debug/headers"
    page_dir = os.path.join(base_dir, doc_component, f"page_{page_idx:04d}")

    rows: List[Dict[str, Any]] = []
    pre_rows: List[List[Any]] = []
    post_rows: List[List[Any]] = []

    for idx, raw in enumerate(page_lines or []):
        text_raw = raw or ""
        text_trim = text_raw.rstrip()
        style = _coerce_style(styles[idx] if idx < len(styles) else {}, text_trim)
        text_norm = header_config.normalize_text_for_regex(text_trim)
        row = {
            "line_idx": idx,
            "text_raw": text_raw,
            "text_trim": text_trim.strip(),
            "text_norm": text_norm.strip(),
            "style": style,
            "codepoints_hex": _codepoints(text_raw),
            "codepoints_hex_norm": _codepoints(text_norm),
        }
        rows.append(row)

        if header_config.DEBUG_HEADERS:
            pre_rows.append([
                idx,
                text_raw,
                row["codepoints_hex"],
                style.get("x_left"),
                style.get("x_right"),
                style.get("y_top"),
                style.get("font_name", ""),
                style.get("font_size"),
                style.get("bold"),
                style.get("italics"),
                style.get("span_count"),
            ])
            post_rows.append([
                idx,
                row["text_norm"],
                row["codepoints_hex_norm"],
                style.get("x_left"),
                style.get("x_right"),
                style.get("y_top"),
                style.get("font_name", ""),
                style.get("font_size"),
                style.get("bold"),
                style.get("italics"),
            ])

    if header_config.DEBUG_HEADERS:
        header_config._ensure_dir(page_dir)
        pre_path = os.path.join(page_dir, "lines_pre_norm.csv")
        post_path = os.path.join(page_dir, "lines_post_norm.csv")
        with open(pre_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "line_idx",
                    "text_raw",
                    "codepoints_hex",
                    "x_left",
                    "x_right",
                    "y_top",
                    "font_name",
                    "font_size",
                    "bold",
                    "italics",
                    "span_count",
                ]
            )
            writer.writerows(pre_rows)
        with open(post_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "line_idx",
                    "text_norm",
                    "codepoints_hex_norm",
                    "x_left",
                    "x_right",
                    "y_top",
                    "font_name",
                    "font_size",
                    "bold",
                    "italics",
                ]
            )
            writer.writerows(post_rows)

    return rows


__all__ = ["normalize_page_lines"]
