from dataclasses import dataclass


@dataclass(frozen=True)
class RAGContext:
    doc_id: str
    ppass: str  # Mechanical | Electrical | Controls | Software | Project Management
    intent: str  # HEADER | RETRIEVE | COMPARE | NUMERIC | STANDARDS
    domain: str  # mirror ppass (kept for clarity)
    version: str  # hash of config to bust caches
