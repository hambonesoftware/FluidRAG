# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
import csv
import unicodedata
import re
from typing import Optional


DEBUG_HEADERS = os.getenv("FLUIDRAG_DEBUG_HEADERS", "0") == "1"
DEBUG_DIR = os.getenv("FLUIDRAG_DEBUG_DIR", "./_debug/headers") or "./_debug/headers"
ACCEPT_SCORE_THRESHOLD = float(os.getenv("FLUIDRAG_ACCEPT_SCORE", "2.25"))


def _ensure_dir(path: Optional[str]) -> None:
    if not path:
        return
    os.makedirs(path, exist_ok=True)


def nfkc(value: Optional[str]) -> str:
    return unicodedata.normalize("NFKC", value or "")


TRANSLATE = str.maketrans({
    "．": "",
    "｡": ".",
    "・": ".",
})


def normalize_text_for_regex(text: Optional[str]) -> str:
    cleaned = nfkc(text).translate(TRANSLATE)
    cleaned = (
        cleaned.replace("\u00A0", " ")
        .replace("\u200B", "")
        .replace("\u200C", "")
        .replace("\u200D", "")
    )
    return cleaned


SAFE_COMPONENT_RX = re.compile(r"[^0-9A-Za-z._-]+")


def sanitize_component(value: Optional[str], default: str = "document") -> str:
    base = nfkc(value or "").strip() or default
    safe = SAFE_COMPONENT_RX.sub("_", base)
    safe = safe.strip("_") or default
    return safe


SECTION_PREFIX_RX = re.compile(
    r"^\s*((?:Appendix\s+[A-Z])|(?:[A-Z]\d+)|\d+(?:\.\d+)*|\d+\))",
    re.IGNORECASE,
)


CONFIG = {
    # Heuristic pass
    "page_mode": True,
    "use_font_clusters": True,
    "accept_score_threshold": ACCEPT_SCORE_THRESHOLD,
    "ambiguous_score_threshold": 1.10,
    "max_candidates_per_page": 40,
    "dedup_fuzzy_threshold": 90,

    # LLM adjudication controls
    "llm_enabled": True,
    "llm_temperature": 0.0,
    "context_chars_per_candidate": 700,

    # NEW: batch adjudication across multiple pages to avoid 429s
    "llm_batch_pages": 4,
    "llm_max_batches": 5,
    "llm_backoff_initial_ms": 600,
    "llm_backoff_factor": 1.7,
    "llm_backoff_max_ms": 4500,

    # Appendix handling
    "appendix_forces_doc_end": True,

    # Fallbacks
    "fallback_if_llm_low_quality": True,
    "fallback_top_k_per_page": 3,

    # Debugging helpers
    "debug": DEBUG_HEADERS,
    "debug_dir": DEBUG_DIR,
    "audit_dir": "./debug/headers",
}


__all__ = [
    "DEBUG_HEADERS",
    "DEBUG_DIR",
    "ACCEPT_SCORE_THRESHOLD",
    "CONFIG",
    "TRANSLATE",
    "normalize_text_for_regex",
    "nfkc",
    "_ensure_dir",
    "sanitize_component",
    "SECTION_PREFIX_RX",
]
