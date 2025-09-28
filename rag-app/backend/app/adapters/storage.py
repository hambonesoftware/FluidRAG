"""Local filesystem storage adapter."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List

from ..config import settings
from ..util.logging import get_logger

logger = get_logger(__name__)


class StorageAdapter:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = (base_dir or settings.storage_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, relative: str | Path) -> Path:
        path = (self.base_dir / relative).resolve()
        if not str(path).startswith(str(self.base_dir)):
            raise ValueError("Path traversal detected")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def write_bytes(self, relative: str | Path, data: bytes) -> Path:
        path = self._resolve(relative)
        path.write_bytes(data)
        return path

    def write_text(self, relative: str | Path, text: str) -> Path:
        path = self._resolve(relative)
        path.write_text(text, encoding="utf-8")
        return path

    def read_text(self, relative: str | Path) -> str:
        path = self._resolve(relative)
        return path.read_text(encoding="utf-8")

    def write_json(self, relative: str | Path, payload: Dict[str, Any]) -> Path:
        path = self._resolve(relative)
        with path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2, sort_keys=True)
        return path

    def write_jsonl(self, relative: str | Path, rows: Iterable[Dict[str, Any]]) -> Path:
        path = self._resolve(relative)
        with path.open("w", encoding="utf-8") as fp:
            for row in rows:
                fp.write(json.dumps(row, sort_keys=True) + "\n")
        return path

    def iter_jsonl(self, relative: str | Path) -> Iterator[Dict[str, Any]]:
        path = self._resolve(relative)
        with path.open("r", encoding="utf-8") as fp:
            for line in fp:
                if line.strip():
                    yield json.loads(line)

    def exists(self, relative: str | Path) -> bool:
        return self._resolve(relative).exists()

    def list_artifacts(self, relative: str | Path) -> List[Path]:
        path = self._resolve(relative)
        if not path.exists():
            return []
        if path.is_file():
            return [path]
        return sorted(p for p in path.iterdir())


storage = StorageAdapter()
