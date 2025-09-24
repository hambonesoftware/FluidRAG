"""Configuration helpers for the RAG v2 pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "no", "off", "none"}:
            return False
        if normalized in {"1", "true", "yes", "on"}:
            return True
        return default
    return bool(value) if value is not None else default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


@dataclass
class RagV2Config:
    """Mutable configuration shared across the RAG v2 modules."""

    rag_v2_enabled: bool = True

    # --- Retrieval fanout -------------------------------------------------
    k_dense: int = 40
    k_sparse: int = 40
    k_regex: int = 20
    k_colbert: int = 50
    k_sentence: int = 40
    cross_encoder_top_k: int = 20
    hyde_hypotheses: int = 2
    hyde_sparse_min_hits: int = 5
    query_short_chars: int = 48

    topK_for_synthesis: int = 10

    w_std: float = 0.50
    w_flu: float = 0.30
    w_hep: float = 0.20

    tau_sim_edge: float = 0.78
    max_neighbors: int = 16

    entropy_window_chunks: int = 3
    tau_entropy_abs: float = 0.75
    tau_entropy_grad: float = 0.10
    entropy_buffer_chunks: int = 1

    w_num: float = 1.0
    w_unit: float = 1.2
    w_stdID: float = 1.5
    hep_entropy_kappa: float = 0.25
    facet_window_tokens: int = 64

    min_confidence: float = 0.70
    max_refine_loops: int = 1

    tau_entropy_frontier: float = 0.80
    section_diversity: int = 3

    telemetry_enabled: bool = True

    # --- Feature toggles --------------------------------------------------
    enable_hyde: bool = True
    enable_colbert: bool = True
    enable_cross_encoder: bool = False
    enable_graph_summaries: bool = True
    enable_sentence_window: bool = True
    enable_pelt: bool = False

    # --- Header detection -------------------------------------------------
    header_weight_entropy: float = 0.25
    header_weight_drift: float = 0.30
    header_weight_cluster: float = 0.15
    header_weight_regex: float = 0.20
    header_weight_numbering: float = 0.07
    header_weight_layout: float = 0.03
    header_threshold: float = 0.60
    header_min_gap: int = 2
    header_entropy_window: int = 3

    # --- Sentence merge thresholds ---------------------------------------
    sentence_merge_threshold: float = 0.55
    sentence_max_tokens: int = 120
    sentence_neighbor_radius: int = 1

    def update_from_env(self, env: Dict[str, Any]) -> None:
        """Update the configuration in-place using an environment-like mapping."""

        if not isinstance(env, dict):
            return
        if "RAG_V2_ENABLED" in env:
            self.rag_v2_enabled = _bool(env.get("RAG_V2_ENABLED"), self.rag_v2_enabled)
        if "RAG_V2_K_DENSE" in env:
            self.k_dense = _int(env.get("RAG_V2_K_DENSE"), self.k_dense)
        if "RAG_V2_K_SPARSE" in env:
            self.k_sparse = _int(env.get("RAG_V2_K_SPARSE"), self.k_sparse)
        if "RAG_V2_K_REGEX" in env:
            self.k_regex = _int(env.get("RAG_V2_K_REGEX"), self.k_regex)
        if "RAG_V2_K_COLBERT" in env:
            self.k_colbert = _int(env.get("RAG_V2_K_COLBERT"), self.k_colbert)
        if "RAG_V2_K_SENTENCE" in env:
            self.k_sentence = _int(env.get("RAG_V2_K_SENTENCE"), self.k_sentence)
        if "RAG_V2_CE_TOPK" in env:
            self.cross_encoder_top_k = _int(
                env.get("RAG_V2_CE_TOPK"), self.cross_encoder_top_k
            )
        if "RAG_V2_HYDE_HYPOTHESES" in env:
            self.hyde_hypotheses = _int(
                env.get("RAG_V2_HYDE_HYPOTHESES"), self.hyde_hypotheses
            )
        if "RAG_V2_HYDE_MIN_SPARSE" in env:
            self.hyde_sparse_min_hits = _int(
                env.get("RAG_V2_HYDE_MIN_SPARSE"), self.hyde_sparse_min_hits
            )
        if "RAG_V2_QUERY_SHORT" in env:
            self.query_short_chars = _int(
                env.get("RAG_V2_QUERY_SHORT"), self.query_short_chars
            )
        if "RAG_V2_TOPK_SYNTH" in env:
            self.topK_for_synthesis = _int(
                env.get("RAG_V2_TOPK_SYNTH"), self.topK_for_synthesis
            )
        if "RAG_V2_W_STD" in env:
            self.w_std = _float(env.get("RAG_V2_W_STD"), self.w_std)
        if "RAG_V2_W_FLU" in env:
            self.w_flu = _float(env.get("RAG_V2_W_FLU"), self.w_flu)
        if "RAG_V2_W_HEP" in env:
            self.w_hep = _float(env.get("RAG_V2_W_HEP"), self.w_hep)
        if "RAG_V2_TAU_SIM" in env:
            self.tau_sim_edge = _float(env.get("RAG_V2_TAU_SIM"), self.tau_sim_edge)
        if "RAG_V2_MAX_NEIGH" in env:
            self.max_neighbors = _int(env.get("RAG_V2_MAX_NEIGH"), self.max_neighbors)
        if "RAG_V2_ENTROPY_WIN" in env:
            self.entropy_window_chunks = _int(
                env.get("RAG_V2_ENTROPY_WIN"), self.entropy_window_chunks
            )
        if "RAG_V2_TAU_ENTROPY_ABS" in env:
            self.tau_entropy_abs = _float(
                env.get("RAG_V2_TAU_ENTROPY_ABS"), self.tau_entropy_abs
            )
        if "RAG_V2_TAU_ENTROPY_GRAD" in env:
            self.tau_entropy_grad = _float(
                env.get("RAG_V2_TAU_ENTROPY_GRAD"), self.tau_entropy_grad
            )
        if "RAG_V2_ENTROPY_BUFFER" in env:
            self.entropy_buffer_chunks = _int(
                env.get("RAG_V2_ENTROPY_BUFFER"), self.entropy_buffer_chunks
            )
        if "RAG_V2_W_NUM" in env:
            self.w_num = _float(env.get("RAG_V2_W_NUM"), self.w_num)
        if "RAG_V2_W_UNIT" in env:
            self.w_unit = _float(env.get("RAG_V2_W_UNIT"), self.w_unit)
        if "RAG_V2_W_STDID" in env:
            self.w_stdID = _float(env.get("RAG_V2_W_STDID"), self.w_stdID)
        if "RAG_V2_HEP_KAPPA" in env:
            self.hep_entropy_kappa = _float(
                env.get("RAG_V2_HEP_KAPPA"), self.hep_entropy_kappa
            )
        if "RAG_V2_FACET_WINDOW" in env:
            self.facet_window_tokens = _int(
                env.get("RAG_V2_FACET_WINDOW"), self.facet_window_tokens
            )
        if "RAG_V2_MIN_CONF" in env:
            self.min_confidence = _float(
                env.get("RAG_V2_MIN_CONF"), self.min_confidence
            )
        if "RAG_V2_MAX_REFINE" in env:
            self.max_refine_loops = _int(
                env.get("RAG_V2_MAX_REFINE"), self.max_refine_loops
            )
        if "RAG_V2_SECTION_DIVERSITY" in env:
            self.section_diversity = _int(
                env.get("RAG_V2_SECTION_DIVERSITY"), self.section_diversity
            )
        if "RAG_V2_TELEMETRY" in env:
            self.telemetry_enabled = _bool(
                env.get("RAG_V2_TELEMETRY"), self.telemetry_enabled
            )
        if "RAG_V2_ENABLE_HYDE" in env:
            self.enable_hyde = _bool(env.get("RAG_V2_ENABLE_HYDE"), self.enable_hyde)
        if "RAG_V2_ENABLE_COLBERT" in env:
            self.enable_colbert = _bool(
                env.get("RAG_V2_ENABLE_COLBERT"), self.enable_colbert
            )
        if "RAG_V2_ENABLE_CE" in env:
            self.enable_cross_encoder = _bool(
                env.get("RAG_V2_ENABLE_CE"), self.enable_cross_encoder
            )
        if "RAG_V2_ENABLE_GRAPH" in env:
            self.enable_graph_summaries = _bool(
                env.get("RAG_V2_ENABLE_GRAPH"), self.enable_graph_summaries
            )
        if "RAG_V2_ENABLE_SENTENCE" in env:
            self.enable_sentence_window = _bool(
                env.get("RAG_V2_ENABLE_SENTENCE"), self.enable_sentence_window
            )
        if "RAG_V2_ENABLE_PELT" in env:
            self.enable_pelt = _bool(env.get("RAG_V2_ENABLE_PELT"), self.enable_pelt)
        if "RAG_V2_HEAD_THRESH" in env:
            self.header_threshold = _float(
                env.get("RAG_V2_HEAD_THRESH"), self.header_threshold
            )
        if "RAG_V2_HEAD_MINGAP" in env:
            self.header_min_gap = _int(
                env.get("RAG_V2_HEAD_MINGAP"), self.header_min_gap
            )
        if "RAG_V2_HEAD_ENTROPY_WIN" in env:
            self.header_entropy_window = _int(
                env.get("RAG_V2_HEAD_ENTROPY_WIN"), self.header_entropy_window
            )
        if "RAG_V2_SENT_MERGE" in env:
            self.sentence_merge_threshold = _float(
                env.get("RAG_V2_SENT_MERGE"), self.sentence_merge_threshold
            )
        if "RAG_V2_SENT_MAXTOK" in env:
            self.sentence_max_tokens = _int(
                env.get("RAG_V2_SENT_MAXTOK"), self.sentence_max_tokens
            )
        if "RAG_V2_SENT_RADIUS" in env:
            self.sentence_neighbor_radius = _int(
                env.get("RAG_V2_SENT_RADIUS"), self.sentence_neighbor_radius
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rag_v2_enabled": self.rag_v2_enabled,
            "k_dense": self.k_dense,
            "k_sparse": self.k_sparse,
            "k_regex": self.k_regex,
            "k_colbert": self.k_colbert,
            "k_sentence": self.k_sentence,
            "cross_encoder_top_k": self.cross_encoder_top_k,
            "hyde_hypotheses": self.hyde_hypotheses,
            "hyde_sparse_min_hits": self.hyde_sparse_min_hits,
            "query_short_chars": self.query_short_chars,
            "topK_for_synthesis": self.topK_for_synthesis,
            "w_std": self.w_std,
            "w_flu": self.w_flu,
            "w_hep": self.w_hep,
            "tau_sim_edge": self.tau_sim_edge,
            "max_neighbors": self.max_neighbors,
            "entropy_window_chunks": self.entropy_window_chunks,
            "tau_entropy_abs": self.tau_entropy_abs,
            "tau_entropy_grad": self.tau_entropy_grad,
            "entropy_buffer_chunks": self.entropy_buffer_chunks,
            "w_num": self.w_num,
            "w_unit": self.w_unit,
            "w_stdID": self.w_stdID,
            "hep_entropy_kappa": self.hep_entropy_kappa,
            "facet_window_tokens": self.facet_window_tokens,
            "min_confidence": self.min_confidence,
            "max_refine_loops": self.max_refine_loops,
            "tau_entropy_frontier": self.tau_entropy_frontier,
            "section_diversity": self.section_diversity,
            "telemetry_enabled": self.telemetry_enabled,
            "enable_hyde": self.enable_hyde,
            "enable_colbert": self.enable_colbert,
            "enable_cross_encoder": self.enable_cross_encoder,
            "enable_graph_summaries": self.enable_graph_summaries,
            "enable_sentence_window": self.enable_sentence_window,
            "enable_pelt": self.enable_pelt,
            "header_weight_entropy": self.header_weight_entropy,
            "header_weight_drift": self.header_weight_drift,
            "header_weight_cluster": self.header_weight_cluster,
            "header_weight_regex": self.header_weight_regex,
            "header_weight_numbering": self.header_weight_numbering,
            "header_weight_layout": self.header_weight_layout,
            "header_threshold": self.header_threshold,
            "header_min_gap": self.header_min_gap,
            "header_entropy_window": self.header_entropy_window,
            "sentence_merge_threshold": self.sentence_merge_threshold,
            "sentence_max_tokens": self.sentence_max_tokens,
            "sentence_neighbor_radius": self.sentence_neighbor_radius,
        }


CFG = RagV2Config()
