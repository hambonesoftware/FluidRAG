"""Version 2 retrieval augmented generation pipeline primitives."""

from .config import CFG, RagV2Config
from .types import Chunk, EvidenceScore, EvidenceBand, ExtractionField, ExtractionJSON
from .retrieval import Retriever
from .rerank import Reranker
from .graph import GraphIndex
from .agents import StandardAgent, FluidAgent, HEPAgent
from .entropy import (
    entropy_linear_band,
    entropy_graph_band,
    entropy_changepoint_band,
)
from .fusion import fuse_scores, intersect_or_tightest_band
from .pack import pack_context
from .prompts import EXTRACT_PROMPT, VERIFY_PROMPT, EDITION_ARBITER_PROMPT
from .orchestrate import macro_pass

__all__ = [
    "CFG",
    "RagV2Config",
    "Chunk",
    "EvidenceScore",
    "EvidenceBand",
    "ExtractionField",
    "ExtractionJSON",
    "Retriever",
    "Reranker",
    "GraphIndex",
    "StandardAgent",
    "FluidAgent",
    "HEPAgent",
    "entropy_linear_band",
    "entropy_graph_band",
    "entropy_changepoint_band",
    "fuse_scores",
    "intersect_or_tightest_band",
    "pack_context",
    "EXTRACT_PROMPT",
    "VERIFY_PROMPT",
    "EDITION_ARBITER_PROMPT",
    "macro_pass",
]
