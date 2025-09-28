"""Contracts for upload/ingest stage."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass(slots=True)
class UploadRequest:
    file_name: str
    content: bytes
    content_type: str


@dataclass(slots=True)
class StoredDocument:
    doc_id: str
    original_name: str
    storage_path: Path
    manifest_path: Path


@dataclass(slots=True)
class UploadResponse:
    doc_id: str
    manifest_path: Path
    meta: Dict[str, str]


@dataclass(slots=True)
class NormalizedText:
    doc_id: str
    text: str
    pages: list[str]
    meta: Dict[str, str]
