from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from backend.headers import config as cfg
from backend.headers.pipeline import HeaderIndex, run_headers


def _tokens_for_text(text: str, font_size: float = 12.0, indent: float = 0.0) -> List[Dict[str, object]]:
    tokens: List[Dict[str, object]] = []
    for match in re.finditer(r"\S+\s*", text):
        tokens.append(
            {
                "text": match.group(0),
                "start": match.start(),
                "end": match.end(),
                "font_size": font_size,
                "bold": match.group(0).strip().endswith("."),
                "indent": indent,
            }
        )
    return tokens


def run_header_pipeline(
    doc_id: str,
    text: str,
    tmp_path: Path,
    *,
    call_llm: Optional[Callable[[Iterable[Dict[str, str]]], str]] = None,
) -> HeaderIndex:
    page = {
        "text": text,
        "tokens": _tokens_for_text(text),
    }
    decomp = {"pages": [page], "output_dir": tmp_path}

    original_mode = cfg.HEADER_MODE
    legacy_profile_supported = hasattr(cfg, "HEADER_LEGACY_PROFILE")
    original_profile = getattr(cfg, "HEADER_LEGACY_PROFILE", None)
    cfg.HEADER_MODE = "legacy"
    if legacy_profile_supported:
        cfg.HEADER_LEGACY_PROFILE = "raw_truth"

    if call_llm is None:
        try:
            return run_headers(doc_id, decomp)
        finally:
            cfg.HEADER_MODE = original_mode
            if legacy_profile_supported:
                cfg.HEADER_LEGACY_PROFILE = original_profile

    from backend.headers import pipeline as pipeline_module

    original_call = pipeline_module.call_llm
    pipeline_module.call_llm = call_llm  # type: ignore[assignment]
    try:
        return run_headers(doc_id, decomp)
    finally:
        pipeline_module.call_llm = original_call  # type: ignore[assignment]
        cfg.HEADER_MODE = original_mode
        if legacy_profile_supported:
            cfg.HEADER_LEGACY_PROFILE = original_profile


__all__ = ["run_header_pipeline"]
