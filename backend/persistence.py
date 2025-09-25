# -*- coding: utf-8 -*-
"""Simple SQLite-backed cache for preprocessing, header detection, and pass outputs."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, Optional

_DB_PATH = os.environ.get("FLUIDRAG_DB_PATH")
if not _DB_PATH:
    base_dir = os.path.join(os.getcwd(), "data")
    os.makedirs(base_dir, exist_ok=True)
    _DB_PATH = os.path.join(base_dir, "fluidrag_cache.sqlite3")

_DB_LOCK = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS document_cache (
            file_hash TEXT PRIMARY KEY,
            filename TEXT,
            data TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    return conn


def _load_payload(file_hash: Optional[str]) -> Dict[str, Any]:
    if not file_hash:
        return {}
    with _DB_LOCK:
        with _connect() as conn:
            row = conn.execute(
                "SELECT data FROM document_cache WHERE file_hash = ?", (file_hash,)
            ).fetchone()
    if not row or not row[0]:
        return {}
    try:
        payload = json.loads(row[0])
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    return {}


def _write_payload(file_hash: str, payload: Dict[str, Any], filename: Optional[str]) -> None:
    if not file_hash:
        return
    stored = dict(payload or {})
    if filename:
        stored.setdefault("filename", filename)
    stored.setdefault("updated_at", time.time())
    data = json.dumps(stored, ensure_ascii=False)
    with _DB_LOCK:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO document_cache (file_hash, filename, data, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(file_hash) DO UPDATE SET
                    filename = excluded.filename,
                    data = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (file_hash, stored.get("filename"), data, time.time()),
            )


def load_document_cache(file_hash: Optional[str]) -> Dict[str, Any]:
    """Return the cached payload for ``file_hash`` (may be empty)."""
    return _load_payload(file_hash)


def save_preprocess_cache(
    file_hash: Optional[str],
    filename: Optional[str],
    response: Dict[str, Any],
    macro_chunks: Optional[list],
    micro_chunks: Optional[list],
) -> None:
    if not file_hash:
        return
    payload = _load_payload(file_hash)
    payload.setdefault("passes", {})
    payload["preprocess"] = {
        "response": response,
        "chunks": macro_chunks or [],
        "macro_chunks": macro_chunks or [],
        "micro_chunks": micro_chunks or [],
        "stored_at": time.time(),
    }
    _write_payload(file_hash, payload, filename)


def get_preprocess_cache(file_hash: Optional[str]) -> Optional[Dict[str, Any]]:
    payload = _load_payload(file_hash)
    entry = payload.get("preprocess") if isinstance(payload, dict) else None
    if isinstance(entry, dict) and (
        entry.get("macro_chunks")
        or entry.get("micro_chunks")
        or entry.get("chunks")
    ):
        return entry
    return None


def save_headers_cache(
    file_hash: Optional[str],
    filename: Optional[str],
    results: Any,
    response: Dict[str, Any],
) -> None:
    if not file_hash:
        return
    payload = _load_payload(file_hash)
    payload.setdefault("passes", {})
    payload["headers"] = {
        "results": results,
        "response": response,
        "stored_at": time.time(),
    }
    _write_payload(file_hash, payload, filename)


def get_headers_cache(file_hash: Optional[str]) -> Optional[Dict[str, Any]]:
    payload = _load_payload(file_hash)
    entry = payload.get("headers") if isinstance(payload, dict) else None
    if isinstance(entry, dict) and isinstance(entry.get("results"), list):
        return entry
    return None


def clear_headers_cache(file_hash: Optional[str]) -> None:
    if not file_hash:
        return
    payload = _load_payload(file_hash)
    if not isinstance(payload, dict):
        return
    if "headers" not in payload:
        return
    payload.pop("headers", None)
    filename = payload.get("filename")
    _write_payload(file_hash, payload, filename)


def save_pass_cache(
    file_hash: Optional[str],
    filename: Optional[str],
    pass_name: str,
    payload: Dict[str, Any],
) -> None:
    if not file_hash or not pass_name:
        return
    existing = _load_payload(file_hash)
    passes = existing.setdefault("passes", {})
    passes[pass_name] = {
        "payload": payload,
        "stored_at": time.time(),
    }
    _write_payload(file_hash, existing, filename)


def get_pass_cache(file_hash: Optional[str]) -> Dict[str, Dict[str, Any]]:
    payload = _load_payload(file_hash)
    passes = payload.get("passes") if isinstance(payload, dict) else None
    if isinstance(passes, dict):
        return passes
    return {}
