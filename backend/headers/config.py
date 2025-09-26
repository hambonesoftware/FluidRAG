"""Configuration flags for the header pipeline."""

from __future__ import annotations

# EFHG gate mode controls whether scoring is allowed to block promotions.
# "bypass" => strong patterns auto-promote, scores only inform logging.
# "score_gate" => legacy behaviour where EFHG scores gate weaker patterns.
HEADER_GATE_MODE = "bypass"

# When ``True`` only hard span collisions trigger suppression during
# conflict resolution. Soft disagreements (style, graph hints) are logged but
# do not demote a promoted header.
STRICT_CONFLICT_ONLY = True


__all__ = ["HEADER_GATE_MODE", "STRICT_CONFLICT_ONLY"]
