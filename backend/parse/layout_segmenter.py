# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Dict, Any, Tuple
import csv
import os
import re

from . import header_config


LEFT_MARGIN_LIMIT = 360.0
MIN_FONT_SIZE = 7.0
MAX_LINE_LENGTH = 160

MEASURE_RX = re.compile(
    r"\b(?:\d{1,4}(?:\.\d+)?)(?:\s*(?:mm|cm|m|in|inch|ft|°c|°f|a|v|hz|psi|kpa|ip\d{2}))\b",
    re.IGNORECASE,
)
ADDRESS_RX = re.compile(
    r"\b(?:Street|St\.|Road|Rd\.|Drive|Dr\.|Ave\.|Avenue|Suite|USA|Tel|Fax)\b",
    re.IGNORECASE,
)
TOO_LONG_RX = re.compile(r"^\s*.{161,}\s*$")


def apply_prefilter(
    doc_id: str,
    page_idx: int,
    lines: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    kept: List[Dict[str, Any]] = []
    ledger: List[Dict[str, Any]] = []

    for row in lines:
        text_norm = (row.get("text_norm") or "").strip()
        style = row.get("style") or {}
        x_left = style.get("x_left")
        font_size = style.get("font_size")
        bold = bool(style.get("bold"))
        caps_ratio = float(style.get("caps_ratio") or 0.0)

        passes_left_margin = x_left is None or float(x_left) <= LEFT_MARGIN_LIMIT
        passes_min_font = font_size is None or float(font_size) >= MIN_FONT_SIZE
        passes_bold = bold
        passes_max_len = len(text_norm) <= MAX_LINE_LENGTH if text_norm else False
        passes_caps = caps_ratio >= 0.15 if text_norm else False

        drop_reason = ""
        if not text_norm:
            drop_reason = "blank"
        elif not passes_left_margin:
            drop_reason = f"left_margin>{LEFT_MARGIN_LIMIT:.0f}px"
        elif not passes_min_font:
            drop_reason = f"font_size<{MIN_FONT_SIZE}"
        elif len(text_norm) < 6:
            drop_reason = "min_length<6"
        elif not passes_max_len:
            drop_reason = f"max_length>{MAX_LINE_LENGTH}"
        elif ADDRESS_RX.search(text_norm):
            drop_reason = "address_hint"
        elif MEASURE_RX.search(text_norm):
            drop_reason = "measurement_hint"
        elif TOO_LONG_RX.match(text_norm):
            drop_reason = "too_long"

        row["drop_reason"] = drop_reason
        row["passes_left_margin"] = passes_left_margin
        row["passes_min_font"] = passes_min_font
        row["passes_bold"] = passes_bold
        row["passes_max_len"] = passes_max_len
        row["passes_caps"] = passes_caps
        row["caps_ratio"] = caps_ratio

        ledger.append(
            {
                "line_idx": row.get("line_idx"),
                "text_norm": text_norm,
                "x_left": x_left,
                "font_size": font_size,
                "bold": bold,
                "caps_ratio": caps_ratio,
                "passes_left_margin": passes_left_margin,
                "passes_min_font": passes_min_font,
                "passes_bold": passes_bold,
                "passes_max_len": passes_max_len,
                "passes_caps": passes_caps,
                "drop_reason": drop_reason,
            }
        )

        if not drop_reason:
            kept.append(row)

    if header_config.DEBUG_HEADERS:
        base_dir = header_config.DEBUG_DIR or "./_debug/headers"
        page_dir = os.path.join(
            base_dir, header_config.sanitize_component(doc_id or "document"), f"page_{page_idx:04d}"
        )
        header_config._ensure_dir(page_dir)
        ledger_path = os.path.join(page_dir, "prefilter_ledger.csv")
        with open(ledger_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "line_idx",
                    "text_norm",
                    "x_left",
                    "font_size",
                    "bold",
                    "caps_ratio",
                    "passes_left_margin",
                    "passes_min_font",
                    "passes_bold",
                    "passes_max_len",
                    "passes_caps",
                    "drop_reason",
                ]
            )
            for entry in ledger:
                writer.writerow(
                    [
                        entry.get("line_idx"),
                        entry.get("text_norm"),
                        entry.get("x_left"),
                        entry.get("font_size"),
                        entry.get("bold"),
                        entry.get("caps_ratio"),
                        entry.get("passes_left_margin"),
                        entry.get("passes_min_font"),
                        entry.get("passes_bold"),
                        entry.get("passes_max_len"),
                        entry.get("passes_caps"),
                        entry.get("drop_reason"),
                    ]
                )

    return kept, ledger


__all__ = ["apply_prefilter", "MEASURE_RX", "ADDRESS_RX", "TOO_LONG_RX"]
