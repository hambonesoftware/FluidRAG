"""Identifier helpers."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Optional


def make_document_id(file_name: str, *, salt: Optional[str] = None) -> str:
    seed = f"{file_name}:{salt or uuid.uuid4()}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()[:16]


def make_run_id(doc_id: str) -> str:
    return f"{doc_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
