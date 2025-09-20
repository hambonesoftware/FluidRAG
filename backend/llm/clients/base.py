from typing import Any, Dict, List

class BaseLLMClient:
    def __init__(self) -> None:
        self._debug_records: List[Dict[str, Any]] = []

    def _push_debug(self, record: Dict[str, Any]) -> None:
        self._debug_records.append(record)

    def drain_debug_records(self) -> List[Dict[str, Any]]:
        out = list(self._debug_records)
        self._debug_records.clear()
        return out
