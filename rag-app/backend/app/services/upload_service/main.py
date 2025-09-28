"""Public upload service API."""
from __future__ import annotations

from dataclasses import dataclass

from backend.app.contracts.ingest import NormalizedText

from .upload_controller import NormalizedDocInternal, ensure_normalized as controller_ensure


@dataclass(slots=True)
class NormalizedDoc:
    doc_id: str
    pages: list[str]
    manifest_path: str
    meta: dict[str, str]

    def to_contract(self) -> NormalizedText:
        return NormalizedText(doc_id=self.doc_id, text="\n\n".join(self.pages), pages=self.pages, meta=self.meta)


def ensure_normalized(*, file_name: str, content: bytes, content_type: str) -> NormalizedDoc:
    internal: NormalizedDocInternal = controller_ensure(file_name=file_name, content=content, content_type=content_type)
    return NormalizedDoc(
        doc_id=internal.doc_id,
        pages=internal.pages,
        manifest_path=internal.manifest_path,
        meta=internal.meta,
    )
