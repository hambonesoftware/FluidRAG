from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from ..utils.strings import sn

log = logging.getLogger("FluidRAG.merge")

REQUIRED_FIELDS = ["Specification"]


def _validate_item(item: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    if not isinstance(item, dict):
        issues.append("item_not_dict")
        return issues
    for field in REQUIRED_FIELDS:
        value = item.get(field)
        if value in (None, ""):
            issues.append(f"missing_or_empty:{field}")
    return issues


def _safe_get(data: Dict[str, Any], key: str) -> Any:
    if isinstance(data, dict):
        return data.get(key)
    return None


def _to_row(pass_name: str, item: Dict[str, Any], req_id: str) -> Dict[str, str]:
    pass_value = _safe_get(item, "Pass") or pass_name
    return {
        "Pass": sn(pass_value, label="pass", req_id=req_id) or sn(pass_name, label="pass_name", req_id=req_id),
        "Document": sn(_safe_get(item, "Document"), label="document", req_id=req_id),
        "(Sub)Section #": sn(_safe_get(item, "(Sub)Section #"), label="section_number", req_id=req_id),
        "(Sub)Section Name": sn(_safe_get(item, "(Sub)Section Name"), label="section_name", req_id=req_id),
        "Specification": sn(_safe_get(item, "Specification"), label="specification", req_id=req_id),
    }


def merge_pass_outputs(pass_outputs: Dict[str, Any], req_id: str) -> Dict[str, Any]:
    rows: List[Dict[str, str]] = []
    problems: List[Dict[str, Any]] = []

    for pass_name, payload in (pass_outputs or {}).items():
        items = None
        if isinstance(payload, dict):
            items = payload.get("items")
        if not isinstance(items, list):
            problems.append({"pass": pass_name, "issue": "items_missing_or_not_list"})
            log.warning(
                "[merge %s] %s items missing/not list; payload_type=%s keys=%s",
                req_id,
                pass_name,
                type(payload).__name__,
                list(payload.keys()) if isinstance(payload, dict) else "-",
            )
            continue

        for idx, item in enumerate(items):
            issues = _validate_item(item)
            if issues:
                preview = {
                    "(Sub)Section #": _safe_get(item, "(Sub)Section #"),
                    "(Sub)Section Name": _safe_get(item, "(Sub)Section Name"),
                    "Specification": _safe_get(item, "Specification"),
                }
                problems.append(
                    {
                        "pass": pass_name,
                        "index": idx,
                        "issues": issues,
                        "preview": preview,
                    }
                )
                log.error(
                    "[merge %s] %s item#%d issues=%s preview=%s",
                    req_id,
                    pass_name,
                    idx,
                    issues,
                    json.dumps(preview, ensure_ascii=False),
                )
            rows.append(_to_row(pass_name, item, req_id))

    return {"rows": rows, "problems": problems}
