from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence

from fluidrag.config import load_config

SECTION_REGEX = re.compile(r"^(?P<num>\d+[A-Za-z0-9\-]*)([).\s]+)(?P<title>.+)")
BULLET_REGEX = re.compile(r"^[\s\-\*•]+")
TOKEN_SPLIT_REGEX = re.compile(r"\s+")
SENTENCE_REGEX = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    chunk_id: str
    document: str
    section_number: str | None
    section_name: str | None
    page_start: int
    page_end: int
    text: str
    signals: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)
    graph: dict = field(default_factory=dict)


class StandardChunker:
    """Create fine-grained Standard chunks for a document."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config = load_config(config_path)

    @staticmethod
    def _iter_sentences(text: str) -> Iterable[str]:
        if not text.strip():
            return []
        parts = SENTENCE_REGEX.split(text.strip())
        if len(parts) == 1:
            return [text.strip()]
        return [p.strip() for p in parts if p.strip()]

    @staticmethod
    def _estimate_pages(num_chunks: int, total_sentences: int) -> Sequence[tuple[int, int]]:
        # With limited metadata we approximate uniform distribution.
        if num_chunks == 0:
            return []
        page_estimate = max(1, math.ceil(total_sentences / max(1, num_chunks)))
        return [(1, page_estimate) for _ in range(num_chunks)]

    def _detect_section(self, paragraph: str, last_number: str | None) -> tuple[str | None, str | None, str | None]:
        line = paragraph.strip().splitlines()[0].strip()
        match = SECTION_REGEX.match(line)
        if match:
            section_number = match.group("num")
            title = match.group("title").strip()
            return section_number, title, section_number
        return last_number, None, last_number

    def chunk_text(self, text: str, document_name: str, doc_id: str) -> List[Chunk]:
        sentences: list[str] = []
        for paragraph in re.split(r"\n\s*\n", text):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            sentences.extend(self._iter_sentences(paragraph))
        if not sentences:
            return []

        target_tokens = 70
        chunks: list[Chunk] = []
        current: list[str] = []
        chunk_index = 0
        section_number: str | None = None
        section_name: str | None = None

        def finalize(current_sentences: list[str]) -> None:
            nonlocal chunk_index, section_number, section_name
            if not current_sentences:
                return
            chunk_index += 1
            chunk_id = f"{doc_id}:s{chunk_index:03d}"
            text_block = " ".join(current_sentences).strip()
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    document=document_name,
                    section_number=section_number,
                    section_name=section_name,
                    page_start=1,
                    page_end=1,
                    text=text_block,
                )
            )

        token_count = 0
        for sentence in sentences:
            if SECTION_REGEX.match(sentence):
                section_number, section_name, _ = self._detect_section(sentence, section_number)
            token_count += len(TOKEN_SPLIT_REGEX.split(sentence.strip()))
            current.append(sentence)
            if token_count >= target_tokens:
                finalize(current)
                current = []
                token_count = 0
        finalize(current)

        pages = self._estimate_pages(len(chunks), len(sentences))
        for chunk, (page_start, page_end) in zip(chunks, pages):
            chunk.page_start = page_start
            chunk.page_end = page_end
        return chunks

    def chunk_file(self, file_path: str | Path, doc_id: str) -> List[Chunk]:
        path = Path(file_path)
        text = path.read_text(encoding="utf-8")
        return self.chunk_text(text, document_name=path.name, doc_id=doc_id)

    def write_chunks(self, chunks: Sequence[Chunk], output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk.__dict__, ensure_ascii=False) + "\n")


__all__ = ["StandardChunker", "Chunk"]
