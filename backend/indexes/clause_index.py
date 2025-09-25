"""Clause index supporting constant-time lookups for standards clauses."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import DefaultDict, Dict, Iterable, List, Optional, Set

_NORMALIZE_RE = re.compile(r"[^a-z0-9.]+")
_CLAUSE_NORMALIZE_RE = re.compile(r"(?:^clause\s+|^§\s*)", re.I)
_DOC_ID_SPLIT_RE = re.compile(r"[\s_]+")


def _normalize_key(value: str) -> str:
    lowered = value.strip().lower()
    cleaned = _NORMALIZE_RE.sub(" ", lowered)
    return " ".join(cleaned.split())


def _normalize_clause(value: str) -> str:
    cleaned = _CLAUSE_NORMALIZE_RE.sub("", value.strip())
    return cleaned.replace("§", "").strip()


@dataclass
class ClauseIndex:
    """Index mapping clause identifiers to chunk IDs."""

    _store: DefaultDict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))

    def put(self, doc_id: str, clause_id: Optional[str], chunk_id: str) -> None:
        if not clause_id:
            return
        doc_norm = _normalize_key(doc_id)
        clause_norm = _normalize_key(clause_id)
        clause_clean = _normalize_clause(clause_id)
        keys = {
            f"{doc_norm}|{clause_norm}",
            f"{doc_norm}|{clause_clean}",
            f"{doc_norm} {clause_clean}",
            clause_norm,
            clause_clean,
            f"clause {clause_clean}",
            f"§{clause_clean}",
        }
        doc_variants = {
            doc_norm,
            _normalize_key(_DOC_ID_SPLIT_RE.sub(" ", doc_id)),
            doc_norm.replace(" iso", " iso ").strip(),
        }
        for variant in doc_variants:
            keys.add(f"{variant}|{clause_clean}")
            keys.add(f"{variant} {clause_clean}")
            keys.add(f"{variant}.{clause_clean}")
        for key in keys:
            if not key.strip():
                continue
            self._store[key].add(chunk_id)

    def get_any(self, key: str) -> List[str]:
        normalized = _normalize_key(key)
        clean_clause = _normalize_clause(key)
        doc_part = ""
        clause_part = ""
        if "|" in key:
            doc_part, clause_part = key.split("|", 1)
        elif " §" in key:
            doc_part, clause_part = key.split(" §", 1)
        elif ":" in key:
            doc_part, clause_part = key.split(":", 1)
        elif " clause " in normalized:
            doc_part, clause_part = normalized.split(" clause ", 1)
        elif normalized.split():
            tail = normalized.split()[-1]
            if tail.replace(".", "").isdigit():
                doc_part = " ".join(normalized.split()[:-1])
                clause_part = tail
        if clause_part:
            doc_norm = _normalize_key(doc_part)
            clause_norm = _normalize_clause(clause_part)
        else:
            doc_norm = ""
            clause_norm = ""
        candidates = {
            normalized,
            clean_clause,
            f"clause {clean_clause}",
            f"§{clean_clause}",
        }
        if doc_norm and clause_norm:
            candidates.update(
                {
                    f"{doc_norm}|{clause_norm}",
                    f"{doc_norm}|{clean_clause}",
                    f"{doc_norm} {clause_norm}",
                    f"{doc_norm} {clean_clause}",
                }
            )
        results: Set[str] = set()
        for candidate in candidates:
            results.update(self._store.get(candidate, set()))
        return sorted(results)

    def bulk_put(self, records: Iterable[Dict[str, str]]) -> None:
        for record in records:
            self.put(record.get("doc_id", ""), record.get("clause_id"), record.get("chunk_id", ""))


__all__ = ["ClauseIndex"]
