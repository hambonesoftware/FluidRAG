"""Configuration flags for the header pipeline."""

from __future__ import annotations

# Overall header mode determines the promotion strategy.
# "preprocess_only" => trust preprocess headers as the final list with zero post-processing.
# "legacy" => fall back to the historical EFHG pipeline (see ``HEADER_LEGACY_PROFILE``).
HEADER_MODE = "preprocess_only"

# When running the legacy pipeline additional strategy hints are required.
# "preprocess_truth" => promote preprocess headers directly (with optional stitching).
# "raw_truth" => union of UF anchors and LLM headers with EFHG used only for span stitching.
HEADER_LEGACY_PROFILE = "preprocess_truth"

# EFHG gate mode controls whether scoring is allowed to block promotions
# when the pipeline relies on score-based gating.
# "bypass" => strong patterns auto-promote, scores only inform logging.
# "score_gate" => legacy behaviour where EFHG scores gate weaker patterns.
HEADER_GATE_MODE = "bypass"

# When ``True`` only hard span collisions trigger suppression during
# conflict resolution. Soft disagreements (style, graph hints) are logged but
# do not demote a promoted header.
STRICT_CONFLICT_ONLY = True


__all__ = [
    "HEADER_MODE",
    "HEADER_LEGACY_PROFILE",
    "HEADER_GATE_MODE",
    "STRICT_CONFLICT_ONLY",
]
