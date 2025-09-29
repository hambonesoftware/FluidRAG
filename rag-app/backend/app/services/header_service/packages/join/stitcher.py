"""Header stitching utilities."""

from __future__ import annotations

from typing import Any

from .....util.logging import get_logger

logger = get_logger(__name__)


def stitch_headers(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """EFHG stitching merges split headers across UF boundaries."""

    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda item: item.get("chunk_index", 0))
    stitched: list[dict[str, Any]] = []
    for candidate in ordered:
        candidate.setdefault("chunk_ids", [])
        candidate.setdefault("chunk_id", None)
        if stitched:
            previous = stitched[-1]
            same_series = previous.get("section_key") == candidate.get(
                "section_key"
            ) and previous.get("ordinal") == candidate.get("ordinal")
            contiguous = (
                candidate.get("chunk_index", 0) == previous.get("chunk_index", 0) + 1
            )
            short_text = len(candidate.get("text", "")) <= 40
            dangling = previous.get("text", "").rstrip().endswith(("-", "–", ":"))
            if same_series and contiguous and (short_text or dangling):
                merged_text = " ".join(
                    part.strip(" -:\n")
                    for part in [previous.get("text", ""), candidate.get("text", "")]
                    if part
                )
                previous["text"] = merged_text.strip()
                previous["raw_text"] = previous["text"]
                previous["score"] = max(
                    float(previous.get("score", 0.0)),
                    float(candidate.get("score", 0.0)),
                )
                previous.setdefault("chunk_ids", [])
                if candidate.get("chunk_id"):
                    previous["chunk_ids"].append(candidate["chunk_id"])
                previous["sentence_end"] = max(
                    int(previous.get("sentence_end", 0)),
                    int(candidate.get("sentence_end", 0)),
                )
                previous["chunk_index"] = max(
                    int(previous.get("chunk_index", 0)),
                    int(candidate.get("chunk_index", 0)),
                )
                continue
        stitched_candidate = dict(candidate)
        stitched_candidate.setdefault("chunk_ids", [])
        if (
            candidate.get("chunk_id")
            and candidate["chunk_id"] not in stitched_candidate["chunk_ids"]
        ):
            stitched_candidate["chunk_ids"].append(candidate["chunk_id"])
        stitched.append(stitched_candidate)
    dedup_index: dict[tuple[str | None, int | None], int] = {}
    deduped: list[dict[str, Any]] = []
    for candidate in stitched:
        key = (candidate.get("section_key"), candidate.get("ordinal"))
        idx = dedup_index.get(key)
        if idx is None:
            dedup_index[key] = len(deduped)
            deduped.append(candidate)
        else:
            existing = deduped[idx]
            if float(candidate.get("score", 0.0)) >= float(existing.get("score", 0.0)):
                deduped[idx] = candidate
    logger.debug(
        "headers.join.stitched",
        extra={"input": len(candidates), "output": len(deduped)},
    )
    return deduped


__all__ = ["stitch_headers"]
