"""Upload controller orchestrating guards/normalize/emit."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from backend.app.adapters.storage import storage
from backend.app.contracts.ids import make_document_id
from backend.app.util.audit import stage_record
from backend.app.util.errors import AppError

from .packages.emit.manifest import write_manifest
from .packages.guards.validators import validate_upload_inputs
from .packages.normalize.ocr import try_ocr_if_needed
from .packages.normalize.pdf_reader import normalize_pdf


@dataclass(slots=True)
class NormalizedDocInternal:
    doc_id: str
    pages: list[str]
    manifest_path: str
    meta: Dict[str, str]


def make_doc_id(file_name: str) -> str:
    return make_document_id(file_name)


def handle_upload_errors(exc: Exception) -> Dict[str, str]:
    if isinstance(exc, AppError):
        return exc.to_dict()
    return {"message": str(exc), "type": exc.__class__.__name__}


def ensure_normalized(*, file_name: str, content: bytes, content_type: str) -> NormalizedDocInternal:
    validate_upload_inputs(file_name, content_type, len(content))
    doc_id = make_doc_id(file_name)
    storage.write_bytes(f"{doc_id}/source.bin", content)
    pages = normalize_pdf(content)
    if not pages:
        pages = try_ocr_if_needed(content)
    if not pages:
        raise AppError("Unable to extract text from document")
    meta = {"file_name": file_name, "content_type": content_type, "page_count": str(len(pages))}
    manifest_path = str(write_manifest(doc_id, pages, meta))
    stage_record(storage.base_dir / f"{doc_id}/upload_audit.json", {"doc_id": doc_id, "meta": meta})
    return NormalizedDocInternal(doc_id=doc_id, pages=pages, manifest_path=manifest_path, meta=meta)
