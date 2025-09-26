import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

@dataclass
class PipelineState:
    tmpdir: str
    filename: str
    file_path: str
    pages: Optional[List[str]] = None
    pre_chunks: Optional[List[Dict[str, Any]]] = None
    micro_chunks: Optional[List[Dict[str, Any]]] = None
    macro_chunks: Optional[List[Dict[str, Any]]] = None
    section_chunks: Optional[List[Dict[str, Any]]] = None
    refined_chunks: Optional[List[Dict[str, Any]]] = None
    clustered_chunks: Optional[List[Dict[str, Any]]] = None
    chunk_stage_snapshots: Optional[Dict[str, List[Dict[str, Any]]]] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    headers: Optional[List[Dict[str, Any]]] = None
    debug: Optional[Dict[str, Any]] = None
    file_hash: Optional[str] = None

PIPELINE_STATES: Dict[str, PipelineState] = {}

def new_session_id() -> str:
    return uuid.uuid4().hex

def get_state(session_id: str) -> Optional[PipelineState]:
    return PIPELINE_STATES.get(session_id)
