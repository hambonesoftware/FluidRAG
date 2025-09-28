"""RAG pass service."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel

from backend.app.contracts.passes import PassResult, PipelineResult

from .passes_controller import PassJobsInternal, run_all as controller_run


class PassJobs(BaseModel):
    doc_id: str
    passes: List[PassResult]

    def to_pipeline_result(self) -> PipelineResult:
        return PipelineResult(doc_id=self.doc_id, passes=self.passes)


def run_all(doc_id: str, rechunk_artifact: str) -> PassJobs:
    internal: PassJobsInternal = controller_run(doc_id=doc_id, rechunk_artifact=rechunk_artifact)
    return PassJobs(doc_id=internal.doc_id, passes=internal.passes)
