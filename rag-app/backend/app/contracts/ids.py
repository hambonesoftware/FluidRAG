"""Canonical ID helpers used across pipeline stages."""

from __future__ import annotations

import re

DOC_ID_PATTERN = re.compile(r"[^a-z0-9]+", re.IGNORECASE)


def normalize_doc_id(raw: str) -> str:
    """Normalize arbitrary doc identifiers into filesystem-safe slug."""

    if not raw:
        raise ValueError("doc_id cannot be blank")
    slug = DOC_ID_PATTERN.sub("-", raw.strip())
    slug = slug.strip("-").lower()
    if not slug:
        raise ValueError("doc_id must contain alphanumeric characters")
    return slug


def pass_artifact_name(pass_name: str) -> str:
    """Return canonical filename for a pass output."""

    return f"{normalize_doc_id(pass_name)}.json"


def make_pass_id(doc_id: str, pass_name: str) -> str:
    """Return deterministic pass identifier."""

    return f"{normalize_doc_id(doc_id)}:{normalize_doc_id(pass_name)}"


__all__ = ["normalize_doc_id", "pass_artifact_name", "make_pass_id"]
