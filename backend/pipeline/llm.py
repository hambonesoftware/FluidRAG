"""Compatibility shim for legacy imports.

This module re-exports the canonical LLM factory helpers so older code paths
that still import ``backend.pipeline.llm`` continue to function.
"""

from ..llm.factory import create_llm_client, provider_default_model

__all__ = ["create_llm_client", "provider_default_model"]
