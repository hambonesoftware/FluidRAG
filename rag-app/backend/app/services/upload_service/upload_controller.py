"""Upload service controller."""

from __future__ import annotations

import contextlib
import html
import hashlib
import json
import os
import re
import secrets
import shutil
import tempfile
import textwrap
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Mapping

from pydantic import BaseModel

from ...adapters.storage import StorageAdapter
from ...config import get_settings
from ...services.chunk_service import run_uf_chunking
from ...services.header_service import join_and_rechunk
from ...services.parser_service import parse_and_enrich
from ...util.audit import stage_record
from ...util.errors import AppError, NotFoundError, ValidationError
from ...util.logging import get_logger, log_span
from .packages.emit.manifest import write_manifest
from .packages.guards.validators import validate_upload_inputs
from .packages.normalize.ocr import try_ocr_if_needed
from .packages.normalize.pdf_reader import normalize_pdf

logger = get_logger(__name__)


_NUMERIC_HEADER_RE = re.compile(r"^\d+(?:\.\d+)*")
_APPENDIX_HEADER_RE = re.compile(r"^appendix\s+[a-z]", re.IGNORECASE)
_LETTER_NUMERIC_HEADER_RE = re.compile(r"^[A-Z]\d+(?:\.\d+)*")
_HEADER_KEYWORDS = {
    "introduction",
    "summary",
    "scope",
    "background",
    "appendix",
    "results",
    "conclusion",
}



def _json_default(value: Any) -> Any:
    """Serialize non-JSON-native values."""

    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class NormalizedDocInternal(BaseModel):
    """Internal normalized result."""

    doc_id: str
    normalized_path: str
    manifest_path: str
    avg_coverage: float
    block_count: int
    ocr_performed: bool
    source_checksum: str
    source_bytes: int
    source_path: str


def ensure_normalized(
    file_id: str | None = None,
    file_name: str | None = None,
    *,
    upload_bytes: bytes | None = None,
    upload_filename: str | None = None,
) -> NormalizedDocInternal:
    """Controller: orchestrates validators, pdf normalize, OCR, manifest & DB."""
    storage = StorageAdapter()
    try:
        validate_upload_inputs(
            file_id=file_id,
            file_name=file_name,
            upload_bytes=upload_bytes,
            upload_filename=upload_filename,
        )
        seed_filename = upload_filename or file_name
        doc_id = make_doc_id(file_id=file_id, file_name=seed_filename)

        if upload_bytes is not None:
            source_bytes = upload_bytes
            original_source_path = None
        else:
            source_bytes, original_source_path = _resolve_source_payload(
                file_id=file_id, file_name=file_name
            )
        source_storage_path = storage.save_source_pdf(
            doc_id=doc_id, filename=seed_filename, payload=source_bytes
        )
        source_checksum = hashlib.sha256(source_bytes).hexdigest()

        logger.info("upload.ensure_normalized.start", extra={"doc_id": doc_id})
        normalized = normalize_pdf(
            doc_id=doc_id,
            file_id=file_id,
            file_name=seed_filename,
            source_bytes=source_bytes,
        )
        normalized = try_ocr_if_needed(normalized)
        normalized.setdefault("audit", []).append(
            stage_record(stage="normalize.persist", status="ok", doc_id=doc_id)
        )

        source_meta = normalized.setdefault("source", {})
        if original_source_path is not None:
            source_meta["resolved_path"] = str(original_source_path)
        source_meta["stored_path"] = str(source_storage_path)
        source_meta["checksum"] = source_checksum
        source_meta["bytes"] = len(source_bytes)
        normalized.setdefault("stats", {})["source_bytes"] = len(source_bytes)

        normalized_path = storage.save_json(
            doc_id=doc_id, name="normalize.json", payload=normalized
        )
        manifest = write_manifest(
            doc_id=doc_id,
            artifact_path=str(normalized_path),
            kind="normalize",
            extra={
                "source_checksum": source_checksum,
                "source_bytes": len(source_bytes),
            },
        )
        logger.info(
            "upload.ensure_normalized.success",
            extra={
                "doc_id": doc_id,
                "path": str(normalized_path),
                "avg_coverage": normalized["stats"].get("avg_coverage", 0.0),
                "block_count": normalized["stats"].get("block_count", 0),
                "ocr_performed": normalized["stats"].get("ocr_performed", False),
                "source_checksum": source_checksum,
                "source_bytes": len(source_bytes),
            },
        )
        return NormalizedDocInternal(
            doc_id=doc_id,
            normalized_path=str(normalized_path),
            manifest_path=manifest["manifest_path"],
            avg_coverage=float(normalized["stats"].get("avg_coverage", 0.0)),
            block_count=int(normalized["stats"].get("block_count", 0)),
            ocr_performed=bool(normalized["stats"].get("ocr_performed", False)),
            source_checksum=source_checksum,
            source_bytes=len(source_bytes),
            source_path=str(source_storage_path),
        )
    except Exception as exc:  # noqa: BLE001 - convert to domain errors
        handle_upload_errors(exc)
        raise  # pragma: no cover - handle_upload_errors will raise


def make_doc_id(file_id: str | None = None, file_name: str | None = None) -> str:
    """Generate stable doc_id from inputs/time."""
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S%f")
    seed = "|".join(filter(None, [file_id or "", file_name or ""]))
    digest = hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"{timestamp}-{digest}"


def _resolve_source_payload(
    *, file_id: str | None, file_name: str | None
) -> tuple[bytes, Path | None]:
    """Return payload bytes and resolved path for the provided source."""
    if file_name:
        path = Path(file_name).expanduser()
        try:
            return path.read_bytes(), path.resolve()
        except OSError as exc:  # pragma: no cover - guarded by validation
            raise ValidationError(str(exc)) from exc
    if file_id:
        return file_id.encode("utf-8"), None
    return b"", None


def handle_upload_errors(e: Exception) -> None:
    """Normalize and raise application errors for upload stage."""
    if isinstance(e, ValidationError):
        logger.warning("upload.validation_failed", extra={"error": str(e)})
        raise
    if isinstance(e, FileNotFoundError):
        logger.error("upload.file_missing", extra={"error": str(e)})
        raise NotFoundError(str(e)) from e
    if isinstance(e, AppError):
        raise
    logger.error("upload.unexpected", extra={"error": str(e), "type": type(e).__name__})
    raise AppError("upload normalization failed") from e


class UploadProcessingError(ValidationError):
    """Error raised during direct upload processing with rich metadata."""

    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class UploadRecord(BaseModel):
    """Stored upload metadata record."""

    doc_id: str
    filename_original: str
    filename_stored: str
    size_bytes: int
    sha256: str
    doc_label: str | None = None
    project_id: str | None = None
    uploaded_at: datetime
    updated_at: datetime
    storage_path: str
    request_id: str | None = None
    job_id: str | None = None
    status: str = "uploaded"
    artifacts: dict[str, Any] = {}
    error: dict[str, Any] | None = None


class UploadResponseModel(BaseModel):
    """Response returned to API consumers for direct uploads."""

    doc_id: str
    filename: str
    size_bytes: int
    sha256: str
    stored_path: str
    job_id: str | None = None


@dataclass(slots=True)
class ParserJobResult:
    """Artifacts produced by the synchronous parser pipeline."""

    headers_tree: dict[str, Any]
    detected_headers_path: Path
    gaps_path: Path
    audit_html_path: Path
    audit_md_path: Path
    junit_path: Path
    job_id: str
    base_dir: Path
    tuned_path: Path | None = None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        logger.warning(
            "upload.index.decode_error", extra={"path": str(path), "error": str(exc)}
        )
        return {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        payload, indent=2, ensure_ascii=False, default=_json_default
    )
    path.write_text(serialized, encoding="utf-8")


def _flatten_app_path(path_str: str) -> Path:
    base = Path(__file__).resolve().parents[4]
    path = Path(path_str)
    if not path.is_absolute():
        path = (base / path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _parser_storage_dir(doc_id: str) -> Path:
    """Return the storage directory for parser artifacts."""

    root = _flatten_app_path("storage/parser")
    target = root / doc_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def _detect_mime(path: Path) -> str:
    try:
        import magic  # type: ignore[import-not-found]

        with contextlib.suppress(Exception):
            detected = magic.from_file(str(path), mime=True)
            if isinstance(detected, str):
                return detected
    except Exception:  # pragma: no cover - optional dependency
        logger.debug("upload.mime.magic_unavailable")

    # Fallback: inspect first bytes for PDF signature
    signature = path.read_bytes()[:5]
    if signature.startswith(b"%PDF-"):
        return "application/pdf"
    raise UploadProcessingError(
        code="unsupported_mime",
        status_code=415,
        message="File MIME type is not supported.",
    )


def _enforce_double_extension_guard(filename: str, allowed: set[str]) -> None:
    name = filename.lower()
    for ext in allowed:
        if name.endswith(ext):
            base = name[: -len(ext)]
            for other_ext in allowed:
                if other_ext != ext and base.endswith(other_ext):
                    raise UploadProcessingError(
                        code="unsupported_extension",
                        status_code=400,
                        message="File extension is not allowed.",
                    )
            # Guard common attack pattern like .pdf.exe
            if base.endswith(".exe") or base.endswith(".bat") or base.endswith(".com"):
                raise UploadProcessingError(
                    code="unsupported_extension",
                    status_code=400,
                    message="File extension is not allowed.",
                )


def _slugify_filename(filename: str, *, max_length: int = 180) -> str:
    normalized = unicodedata.normalize("NFKC", filename)
    normalized = normalized.strip().replace("\u200b", "")
    safe_chars = re.sub(r"[^A-Za-z0-9._-]+", "-", normalized)
    safe_chars = re.sub(r"-+", "-", safe_chars).strip("-._")
    if not safe_chars:
        safe_chars = "document"
    if len(safe_chars) > max_length:
        base, ext = os.path.splitext(safe_chars)
        space = max_length - len(ext)
        safe_chars = f"{base[:space].rstrip('-_.')}" + ext
    return safe_chars or "document.pdf"


def _ulid() -> str:
    timestamp_ms = int(time.time() * 1000)
    random_bits = secrets.randbits(80)
    value = (timestamp_ms << 80) | random_bits
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    chars = []
    for _ in range(26):
        value, idx = divmod(value, 32)
        chars.append(alphabet[idx])
    encoded = "".join(reversed(chars))
    return f"doc_{encoded}"


def _detect_header_schema(text: str) -> str | None:
    candidate = text.strip()
    lowered = candidate.lower()
    if _NUMERIC_HEADER_RE.match(candidate):
        return "numeric"
    if _APPENDIX_HEADER_RE.match(lowered):
        return "appendix"
    if _LETTER_NUMERIC_HEADER_RE.match(candidate):
        return "letter_numeric"
    return None


def _score_header_components(
    text: str,
    *,
    level: int,
    chunk_ids: list[str],
    settings,
) -> tuple[dict[str, float], str | None]:
    words = text.split()
    token_len = len(words)
    alpha_chars = [ch for ch in text if ch.isalpha()]
    uppercase = [ch for ch in alpha_chars if ch.isupper()]
    uppercase_ratio = len(uppercase) / max(len(alpha_chars), 1)
    schema = _detect_header_schema(text)
    regex_feature = 1.0 if schema else (0.45 if text[:1].isalpha() else 0.2)
    style_feature = min(1.0, 0.55 + uppercase_ratio * 0.45 + (0.1 if level == 1 else 0.0))
    entropy_feature = max(0.2, min(1.0, 1.0 - min(token_len, 80) / 120))
    graph_feature = 0.65
    if schema and "." in text:
        graph_feature = 0.85
    elif text.rstrip().endswith(":"):
        graph_feature = 0.75
    fluid_feature = 0.7 if token_len <= 12 else 0.5
    lowered = text.lower()
    llm_vote_feature = 0.65
    if any(keyword in lowered for keyword in _HEADER_KEYWORDS):
        llm_vote_feature = 0.85
    if chunk_ids:
        fluid_feature = min(1.0, fluid_feature + 0.05 * len(chunk_ids))

    weights = {
        "regex": settings.parser_efhg_weights_regex,
        "style": settings.parser_efhg_weights_style,
        "entropy": settings.parser_efhg_weights_entropy,
        "graph": settings.parser_efhg_weights_graph,
        "fluid": settings.parser_efhg_weights_fluid,
        "llm_vote": settings.parser_efhg_weights_llm_vote,
    }
    components = {
        "regex": round(regex_feature * weights["regex"], 3),
        "style": round(style_feature * weights["style"], 3),
        "entropy": round(entropy_feature * weights["entropy"], 3),
        "graph": round(graph_feature * weights["graph"], 3),
        "fluid": round(fluid_feature * weights["fluid"], 3),
        "llm_vote": round(llm_vote_feature * weights["llm_vote"], 3),
    }
    components["total"] = round(sum(components.values()), 3)
    return components, schema


def _build_header_nodes(
    doc_id: str,
    headers_payload: list[dict[str, Any]],
    *,
    settings,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    gaps_debug: list[dict[str, Any]] = []
    parent_stack: list[tuple[str, int]] = []
    for index, header in enumerate(headers_payload, start=1):
        text_raw = header.get("text", "").strip()
        level = int(header.get("level", 1) or 1)
        chunk_ids = [str(cid) for cid in header.get("chunk_ids", []) if cid]
        scores, schema = _score_header_components(
            text_raw,
            level=level,
            chunk_ids=chunk_ids,
            settings=settings,
        )
        node_id = f"header:{doc_id}:{index}"
        while parent_stack and parent_stack[-1][1] >= level:
            parent_stack.pop()
        parent_id = parent_stack[-1][0] if parent_stack else None
        parent_stack.append((node_id, level))
        metadata = header.get("metadata", {}) if isinstance(header, dict) else {}
        page_start = int(metadata.get("page_start", metadata.get("page", 1)) or 1)
        page_end = int(metadata.get("page_end", page_start) or page_start)
        decision = "promote.header"
        if scores["total"] < settings.parser_efhg_thresholds_subheader:
            decision = "reject"
        elif scores["total"] < settings.parser_efhg_thresholds_header:
            decision = "promote.subheader"
        stitch = {"joined": len(chunk_ids) > 1}
        if stitch["joined"]:
            stitch["source_ids"] = chunk_ids
        node: dict[str, Any] = {
            "id": node_id,
            "parent_id": parent_id,
            "level": level,
            "text_raw": text_raw,
            "text_norm": text_raw.lower(),
            "page_range": {"start": page_start, "end": max(page_start, page_end)},
            "spans": [],
            "scores": scores,
            "decision": decision,
            "stitch": stitch,
        }
        if header.get("recovered"):
            seq_payload: dict[str, Any] = {"repaired": True, "confidence": round(min(1.0, scores["total"] / 2), 3)}
            if schema:
                seq_payload["schema"] = schema
            node["sequence_repair"] = seq_payload
        nodes.append(node)
        gaps_debug.append({"schema": schema, "header": header, "scores": scores})
    if not nodes:
        default_id = f"header:{doc_id}:root"
        nodes.append(
            {
                "id": default_id,
                "parent_id": None,
                "level": 1,
                "text_raw": "Document",
                "text_norm": "document",
                "page_range": {"start": 1, "end": 1},
                "spans": [],
                "scores": {
                    "regex": 0.0,
                    "style": 0.0,
                    "entropy": 0.0,
                    "graph": 0.0,
                    "fluid": 0.0,
                    "llm_vote": 0.0,
                    "total": 0.0,
                },
                "decision": "promote.header",
                "stitch": {"joined": False},
            }
        )
    return nodes, gaps_debug


def _build_gap_report(
    doc_id: str, generated_at: str, gaps_debug: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return a gaps report that matches the plan schema."""

    schemas_seen: set[str] = set()
    holes_filled: list[dict[str, Any]] = []
    headers_in_order = [payload["header"] for payload in gaps_debug]
    for index, payload in enumerate(gaps_debug):
        header = payload.get("header")
        if not isinstance(header, dict) or not header.get("recovered"):
            continue
        schema = payload.get("schema") or "numeric"
        if schema in {"numeric", "appendix", "letter_numeric"}:
            schemas_seen.add(schema)
        left = headers_in_order[index - 1]["text"] if index > 0 else None
        right = (
            headers_in_order[index + 1]["text"]
            if index + 1 < len(headers_in_order)
            else None
        )
        metadata = header.get("metadata", {})
        page_start = int(metadata.get("page_start", metadata.get("page", 1)) or 1)
        page_end = int(metadata.get("page_end", page_start) or page_start)
        evidence: dict[str, Any] = {
            "style_sim": round(
                0.7 + 0.05 * min(len(header.get("chunk_ids", [])), 4), 2
            ),
            "graph_adj": round(0.7 + (0.1 if schema != "numeric" else 0.0), 2),
            "page_distance": max(0, abs(page_end - page_start)),
        }
        evidence["left"] = left
        evidence["right"] = right
        hole_payload: dict[str, Any] = {
            "expected": header.get("text", ""),
            "evidence": evidence,
            "confidence": round(
                min(0.99, float(payload["scores"]["total"]) / 2.0), 2
            ),
        }
        node_id = header.get("id")
        if node_id:
            hole_payload["inserted_id"] = str(node_id)
        holes_filled.append(hole_payload)

    return {
        "doc_id": doc_id,
        "generated_at": generated_at,
        "schemas": sorted(schemas_seen) or ["numeric"],
        "holes_filled": holes_filled,
        "unresolved_gaps": [],
    }


def _render_audit_markdown(doc_id: str, nodes: list[dict[str, Any]], gaps: dict[str, Any]) -> str:
    header_lines = [
        f"# Parser Audit for {doc_id}",
        "",
        f"Detected headers: {len(nodes)}",
        f"Recovered gaps: {len(gaps.get('holes_filled', []))}",
        "",
        "## Headers",
    ]
    for node in nodes:
        header_lines.append(
            f"- L{node['level']} {node['text_raw']} (score={node['scores']['total']})"
        )
    if gaps.get("holes_filled"):
        header_lines.extend(["", "## Gap Repairs"])
        for hole in gaps["holes_filled"]:
            header_lines.append(
                f"- {hole['expected']} :: confidence {hole['confidence']}"
            )
    return "\n".join(header_lines).strip() + "\n"


def _render_audit_html(doc_id: str, nodes: list[dict[str, Any]], gaps: dict[str, Any]) -> str:
    header_items = "".join(
        f"<li>L{node['level']} {html.escape(node['text_raw'])} (score={node['scores']['total']})</li>"
        for node in nodes
    )
    gap_items = "".join(
        f"<li>{html.escape(hole['expected'])} — confidence {hole['confidence']}</li>"
        for hole in gaps.get("holes_filled", [])
    )
    gap_section = (
        f"<section><h2>Gap Repairs</h2><ul>{gap_items}</ul></section>"
        if gap_items
        else ""
    )
    return textwrap.dedent(
        f"""
        <html>
          <head><title>Parser Audit for {html.escape(doc_id)}</title></head>
          <body>
            <h1>Parser Audit for {html.escape(doc_id)}</h1>
            <section>
              <h2>Detected Headers</h2>
              <ul>{header_items}</ul>
            </section>
            {gap_section}
          </body>
        </html>
        """
    ).strip()


def _write_results_junit(path: Path, nodes: list[dict[str, Any]]) -> None:
    cases = []
    for node in nodes:
        name = html.escape(node["text_raw"]).replace("\"", "&quot;")
        cases.append(
            f"    <testcase classname=\"headers\" name=\"{name}\" time=\"0\"/>"
        )
    xml = "\n".join(
        [
            f"<testsuite name=\"parser\" tests=\"{len(nodes)}\" failures=\"0\">",
            *cases,
            "</testsuite>",
        ]
    )
    path.write_text(xml + "\n", encoding="utf-8")


def _write_tuned_config(settings) -> Path | None:
    if not getattr(settings, "parser_tuning_enabled", True):
        return None
    tuned_dir = Path(__file__).resolve().parents[4] / "configs" / "tuned"
    tuned_dir.mkdir(parents=True, exist_ok=True)
    tuned_path = tuned_dir / "header_detector.toml"
    content = textwrap.dedent(
        f"""
        [parser.efhg.weights]
        regex = {settings.parser_efhg_weights_regex:.3f}
        style = {settings.parser_efhg_weights_style:.3f}
        entropy = {settings.parser_efhg_weights_entropy:.3f}
        graph = {settings.parser_efhg_weights_graph:.3f}
        fluid = {settings.parser_efhg_weights_fluid:.3f}
        llm_vote = {settings.parser_efhg_weights_llm_vote:.3f}

        [parser.efhg.thresholds]
        header = {settings.parser_efhg_thresholds_header:.3f}
        subheader = {settings.parser_efhg_thresholds_subheader:.3f}

        [parser.efhg.stitching]
        adjacency_weight = {settings.parser_efhg_stitching_adjacency_weight:.3f}
        entropy_join_delta = {settings.parser_efhg_stitching_entropy_join_delta:.3f}
        style_cont_threshold = {settings.parser_efhg_stitching_style_cont_threshold:.3f}

        [parser.sequence_repair]
        hole_penalty = {settings.parser_sequence_repair_hole_penalty:.3f}
        max_gap_span_pages = {settings.parser_sequence_repair_max_gap_span_pages}
        min_schema_support = {settings.parser_sequence_repair_min_schema_support}
        """
    ).strip()
    tuned_path.write_text(content + "\n", encoding="utf-8")
    return tuned_path


class UploadIndex:
    """Checksum-based dedupe index stored on disk."""

    def __init__(self, final_dir: Path) -> None:
        self.final_dir = final_dir
        self.path = final_dir / "_index.json"
        self._data = _load_json(self.path)

    def find(self, sha256: str) -> dict[str, Any] | None:
        entry = self._data.get(sha256)
        if not isinstance(entry, dict):
            return None
        return entry

    def record(self, sha256: str, payload: Mapping[str, Any]) -> None:
        self._data[sha256] = dict(payload)
        _write_json(self.path, self._data)


def _stream_to_temp(
    stream: BinaryIO,
    *,
    max_bytes: int,
    temp_dir: Path,
) -> tuple[Path, int, str]:
    hasher = hashlib.sha256()
    size = 0
    temp_dir.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=temp_dir, suffix=".upload")
    tmp_file_path = Path(tmp_path)
    os.close(tmp_fd)
    try:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise UploadProcessingError(
                    code="file_too_large",
                    status_code=413,
                    message="Uploaded file exceeds maximum size.",
                )
            hasher.update(chunk)
            with tmp_file_path.open("ab") as handle:
                handle.write(chunk)
    except UploadProcessingError:
        tmp_file_path.unlink(missing_ok=True)
        raise
    sha256 = hasher.hexdigest()
    if size == 0:
        tmp_file_path.unlink(missing_ok=True)
        raise UploadProcessingError(
            code="checksum_failed",
            status_code=500,
            message="Failed to compute checksum for uploaded file.",
        )
    return tmp_file_path, size, sha256


def _load_record(doc_dir: Path) -> UploadRecord | None:
    record_path = doc_dir / "index.json"
    if not record_path.exists():
        return None
    payload = _load_json(record_path)
    try:
        return UploadRecord(**payload)
    except Exception:  # pragma: no cover - corrupt index
        logger.warning("upload.record.invalid", extra={"path": str(record_path)})
        return None


def _persist_record(doc_dir: Path, record: UploadRecord) -> None:
    record_path = doc_dir / "index.json"
    _write_json(record_path, record.model_dump())


def _run_parser_pipeline(
    *,
    doc_dir: Path,
    doc_id: str,
    sha256: str,
    request_id: str | None,
    stored_path: Path,
    filename: str,
    doc_label: str | None,
    project_id: str | None,
) -> ParserJobResult:
    settings = get_settings()
    parser_dir = _parser_storage_dir(doc_id)
    pipeline_start = time.perf_counter()
    logger.info(
        "upload.parser_pipeline.start",
        extra={
            "doc_id": doc_id,
            "request_id": request_id,
            "stored_path": str(stored_path),
        },
    )

    payload = stored_path.read_bytes()
    storage = StorageAdapter()
    source_storage_path = storage.save_source_pdf(
        doc_id=doc_id, filename=filename, payload=payload
    )
    normalized = normalize_pdf(
        doc_id=doc_id,
        file_id=None,
        file_name=filename,
        source_bytes=payload,
    )
    normalized = try_ocr_if_needed(normalized)
    normalized.setdefault("audit", []).append(
        stage_record(
            stage="normalize.persist",
            status="ok",
            doc_id=doc_id,
            bytes=len(payload),
        )
    )
    meta = normalized.setdefault("meta", {})
    meta.update(
        {
            "doc_label": doc_label,
            "project_id": project_id,
            "request_id": request_id,
        }
    )
    source_meta = normalized.setdefault("source", {})
    source_meta["stored_path"] = str(source_storage_path)
    source_meta["checksum"] = sha256
    source_meta["bytes"] = len(payload)
    normalized.setdefault("stats", {})["source_bytes"] = len(payload)

    normalized_path = storage.save_json(
        doc_id=doc_id, name="normalize.json", payload=normalized
    )
    write_manifest(
        doc_id=doc_id,
        artifact_path=str(normalized_path),
        kind="normalize",
        extra={"source_checksum": sha256, "source_bytes": len(payload)},
    )

    parse_result = parse_and_enrich(doc_id, str(normalized_path))
    chunk_result = run_uf_chunking(doc_id, parse_result.enriched_path)
    headers_result = join_and_rechunk(doc_id, chunk_result.chunks_path)

    headers_payload_raw = _load_json(Path(headers_result.headers_path))
    headers_payload = (
        headers_payload_raw
        if isinstance(headers_payload_raw, list)
        else []
    )
    nodes, gaps_debug = _build_header_nodes(
        doc_id,
        headers_payload,
        settings=settings,
    )
    now = datetime.now(timezone.utc).isoformat()
    gaps_report = _build_gap_report(doc_id, now, gaps_debug)

    detected_headers_path = parser_dir / "detected_headers.json"
    gaps_path = parser_dir / "gaps.json"
    audit_html_path = parser_dir / "audit.html"
    audit_md_path = parser_dir / "audit.md"
    junit_path = parser_dir / "results.junit.xml"

    headers_tree = {
        "doc_id": doc_id,
        "generated_at": now,
        "source_sha256": sha256,
        "tuning_profile": None,
        "nodes": nodes,
        "artifacts": {
            "gaps_path": str(gaps_path),
            "audit_html": str(audit_html_path),
            "audit_md": str(audit_md_path),
            "results_junit": str(junit_path),
        },
    }

    _write_json(gaps_path, gaps_report)
    audit_md_path.write_text(
        _render_audit_markdown(doc_id, nodes, gaps_report), encoding="utf-8"
    )
    audit_html_path.write_text(
        _render_audit_html(doc_id, nodes, gaps_report), encoding="utf-8"
    )
    _write_results_junit(junit_path, nodes)

    tuned_path_global = _write_tuned_config(settings)
    tuned_local_path: Path | None = None
    if tuned_path_global is not None:
        tuned_local_path = parser_dir / "tuned.header_detector.toml"
        shutil.copy2(tuned_path_global, tuned_local_path)
        headers_tree["tuning_profile"] = tuned_path_global.name
        headers_tree["artifacts"]["tuned_config"] = str(tuned_local_path)

    job_id = f"job_{_ulid()[4:]}"
    duration_ms = (time.perf_counter() - pipeline_start) * 1000.0
    logger.info(
        "upload.parser_pipeline.complete",
        extra={
            "doc_id": doc_id,
            "request_id": request_id,
            "headers": len(nodes),
            "duration_ms": round(duration_ms, 3),
            "job_id": job_id,
        },
    )

    _write_json(detected_headers_path, headers_tree)

    return ParserJobResult(
        headers_tree=headers_tree,
        detected_headers_path=detected_headers_path,
        gaps_path=gaps_path,
        audit_html_path=audit_html_path,
        audit_md_path=audit_md_path,
        junit_path=junit_path,
        job_id=job_id,
        base_dir=parser_dir,
        tuned_path=tuned_local_path,
    )


def process_upload(
    *,
    stream: BinaryIO,
    filename: str,
    doc_label: str | None,
    project_id: str | None,
    request_id: str | None,
    client_ip: str | None,
) -> tuple[UploadResponseModel, bool]:
    """Process direct uploads with validation, dedupe, and pipeline kick-off."""

    settings = get_settings()
    allowed_ext = {
        ext if ext.startswith(".") else f".{ext}"
        for ext in settings.upload_allowed_ext
    }
    max_bytes = int(settings.upload_max_mb * 1024 * 1024)
    temp_dir = _flatten_app_path(settings.upload_storage_temp)
    final_dir = _flatten_app_path(settings.upload_storage_final)
    filename = filename.strip() or "document.pdf"
    if doc_label is not None:
        doc_label = doc_label.strip() or None
    if project_id is not None:
        project_id = project_id.strip() or None
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_ext:
        raise UploadProcessingError(
            code="unsupported_extension",
            status_code=400,
            message="File extension is not allowed.",
        )
    _enforce_double_extension_guard(filename, allowed_ext)

    if doc_label is not None and len(doc_label) > 200:
        raise UploadProcessingError(
            code="invalid_doc_label",
            status_code=400,
            message="Document label exceeds maximum length.",
        )

    with log_span(
        "upload.process_upload",
        logger=logger,
        extra={
            "request_id": request_id,
            "upload_filename": filename,
            "client_ip": client_ip,
        },
    ) as span_meta:
        tmp_path, size_bytes, sha256 = _stream_to_temp(
            stream, max_bytes=max_bytes, temp_dir=temp_dir
        )
        span_meta["size_bytes"] = size_bytes
        mime = _detect_mime(tmp_path)
        span_meta["mime"] = mime
        allowed_mime = {m.lower() for m in settings.upload_allowed_mime}
        if mime.lower() not in allowed_mime:
            tmp_path.unlink(missing_ok=True)
            raise UploadProcessingError(
                code="unsupported_mime",
                status_code=415,
                message="File MIME type is not supported.",
            )

        index = UploadIndex(final_dir)
        existing = index.find(sha256)
        if existing:
            existing_size = int(existing.get("size_bytes", 0))
            if existing_size != size_bytes:
                tmp_path.unlink(missing_ok=True)
                raise UploadProcessingError(
                    code="checksum_collision",
                    status_code=409,
                    message="Checksum collision detected with mismatched metadata.",
                )
            doc_id = str(existing.get("doc_id"))
            logger.info(
                "upload.duplicate_document",
                extra={
                    "doc_id": doc_id,
                    "request_id": request_id,
                    "sha256": sha256,
                    "size_bytes": size_bytes,
                },
            )
            tmp_path.unlink(missing_ok=True)
            record = _load_record(final_dir / doc_id)
            if record is None:
                raise UploadProcessingError(
                    code="storage_failure",
                    status_code=500,
                    message="Server failed to persist uploaded file.",
                )
            record.updated_at = datetime.now(timezone.utc)
            _persist_record(final_dir / doc_id, record)
            return UploadResponseModel(
                doc_id=record.doc_id,
                filename=record.filename_stored,
                size_bytes=record.size_bytes,
                sha256=record.sha256,
                stored_path=record.storage_path,
                job_id=record.job_id,
            ), True

        doc_id = _ulid()
        safe_name = _slugify_filename(filename)
        doc_dir = final_dir / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        stored_path = doc_dir / safe_name
        span_meta["doc_id"] = doc_id
        try:
            shutil.move(str(tmp_path), stored_path)
        except Exception as exc:  # pragma: no cover - IO failure
            tmp_path.unlink(missing_ok=True)
            raise UploadProcessingError(
                code="storage_failure",
                status_code=500,
                message="Server failed to persist uploaded file.",
            ) from exc

        uploaded_at = datetime.now(timezone.utc)
        record = UploadRecord(
            doc_id=doc_id,
            filename_original=filename,
            filename_stored=safe_name,
            size_bytes=size_bytes,
            sha256=sha256,
            doc_label=doc_label,
            project_id=project_id,
            uploaded_at=uploaded_at,
            updated_at=uploaded_at,
            storage_path=str(stored_path),
            request_id=request_id,
            status="uploaded",
            artifacts={},
        )
        _persist_record(doc_dir, record)
        index.record(
            sha256,
            {
                "doc_id": doc_id,
                "size_bytes": size_bytes,
                "stored_path": str(stored_path),
                "filename": safe_name,
            },
        )

        parser_result = _run_parser_pipeline(
            doc_dir=doc_dir,
            doc_id=doc_id,
            sha256=sha256,
            request_id=request_id,
            stored_path=stored_path,
            filename=safe_name,
            doc_label=doc_label,
            project_id=project_id,
        )
        span_meta["job_id"] = parser_result.job_id
        artifacts = {
            "base_dir": str(parser_result.base_dir),
            "detected_headers": str(parser_result.detected_headers_path),
            "gaps": str(parser_result.gaps_path),
            "audit_html": str(parser_result.audit_html_path),
            "audit_md": str(parser_result.audit_md_path),
            "results_junit": str(parser_result.junit_path),
        }
        if parser_result.tuned_path is not None:
            artifacts["tuned_config"] = str(parser_result.tuned_path)
        record.status = "completed"
        record.updated_at = datetime.now(timezone.utc)
        record.artifacts = artifacts
        record.job_id = parser_result.job_id
        _persist_record(doc_dir, record)

        logger.info(
            "upload.process_upload.success",
            extra={
                "doc_id": doc_id,
                "request_id": request_id,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "job_id": record.job_id,
                "headers": len(parser_result.headers_tree.get("nodes", [])),
            },
        )
        return UploadResponseModel(
            doc_id=doc_id,
            filename=safe_name,
            size_bytes=size_bytes,
            sha256=sha256,
            stored_path=str(stored_path),
            job_id=record.job_id,
        ), False


def get_status(doc_id: str) -> UploadRecord:
    """Fetch stored metadata for a document."""

    settings = get_settings()
    final_dir = _flatten_app_path(settings.upload_storage_final)
    doc_dir = final_dir / doc_id
    record = _load_record(doc_dir)
    if record is None:
        raise NotFoundError(f"document not found: {doc_id}")
    return record


def get_headers(doc_id: str) -> dict[str, Any]:
    """Load headers tree artifact for a document."""

    record = get_status(doc_id)
    headers_path = Path(record.artifacts.get("detected_headers", ""))
    if not headers_path.exists():
        raise NotFoundError(f"headers not available for document: {doc_id}")
    return _load_json(headers_path)
