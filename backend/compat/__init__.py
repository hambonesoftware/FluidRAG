"""Compatibility helpers for adapting new modules to legacy interfaces."""

from .payload_adapter import to_legacy_llm_message

__all__ = ["to_legacy_llm_message"]
