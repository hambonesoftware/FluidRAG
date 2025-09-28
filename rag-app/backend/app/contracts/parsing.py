"""Parsing stage contracts."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(slots=True)
class TextBlock:
    page: int
    content: str
    language: str
    order: int


@dataclass(slots=True)
class TableBlock:
    page: int
    rows: List[List[str]]
    caption: Optional[str]


@dataclass(slots=True)
class ImageBlock:
    page: int
    description: str
    path: Optional[Path]


@dataclass(slots=True)
class LinkBlock:
    page: int
    text: str
    target: str


@dataclass(slots=True)
class ParsedDocument:
    doc_id: str
    texts: List[TextBlock]
    tables: List[TableBlock]
    images: List[ImageBlock]
    links: List[LinkBlock]
    meta: Dict[str, str]
