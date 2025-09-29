"""Pass service public API."""

from __future__ import annotations

from pydantic import BaseModel

from .passes_controller import PassJobsInternal
from .passes_controller import run_all as controller_run_all


class PassJobs(BaseModel):
    """Pass job identifiers or artifact paths."""

    doc_id: str
    manifest_path: str
    passes: dict[str, str]


def run_all(doc_id: str, rechunk_artifact: str) -> PassJobs:
    """Execute five domain passes asynchronously."""

    internal: PassJobsInternal = controller_run_all(
        doc_id=doc_id, rechunk_artifact=rechunk_artifact
    )
    return PassJobs(**internal.model_dump())


__all__ = ["PassJobs", "run_all"]
