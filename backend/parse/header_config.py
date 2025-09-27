# -*- coding: utf-8 -*-
CONFIG = {
    # Heuristic pass
    "page_mode": True,
    "use_font_clusters": True,
    "accept_score_threshold": 2.25,   # slightly stricter than before
    "ambiguous_score_threshold": 1.10,
    "max_candidates_per_page": 40,
    "dedup_fuzzy_threshold": 90,      # rapidfuzz ratio threshold

    # LLM adjudication controls (reruns rely purely on heuristics)
    "llm_enabled": False,
    "llm_temperature": 0.0,
    "context_chars_per_candidate": 700,

    # NEW: batch adjudication across multiple pages to avoid 429s
    "llm_batch_pages": 4,             # pages per LLM call
    "llm_max_batches": 5,             # absolute cap per document (protects API)
    "llm_backoff_initial_ms": 600,    # backoff start for 429
    "llm_backoff_factor": 1.7,        # multiplier
    "llm_backoff_max_ms": 4500,       # cap

    # Appendix handling
    "appendix_forces_doc_end": True,

    # Fallbacks
    "fallback_if_llm_low_quality": True,
    "fallback_top_k_per_page": 3,     # return top-k best heuristic headers if LLM not available

    # Debugging helpers
    "debug": False,
    "debug_dir": "./_debug/headers",
    "audit_dir": "./debug/headers",
}
