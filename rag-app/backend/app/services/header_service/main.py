"""Header service API."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel

from backend.app.contracts.headers import Header, HeaderArtifact

from .header_controller import HeaderJoinInternal, join_and_rechunk as controller_join


class HeaderResult(BaseModel):
    doc_id: str
    headers: List[Header]
    sections: dict[str, list[str]]

    def to_contract(self) -> HeaderArtifact:
        return HeaderArtifact(doc_id=self.doc_id, headers=self.headers, sections=self.sections)


def join_and_rechunk(doc_id: str, chunks_artifact: str) -> HeaderResult:
    internal: HeaderJoinInternal = controller_join(doc_id=doc_id, chunks_artifact=chunks_artifact)
    return HeaderResult(doc_id=internal.doc_id, headers=internal.headers, sections=internal.sections)
