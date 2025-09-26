"""Helpers to convert extraction records into overlay payloads."""
from __future__ import annotations

from typing import Dict


def to_overlay(record: Dict) -> Dict:
    bboxes = record.get("provenance", {}).get("bboxes", [])
    return {"page": record.get("page"), "bboxes": bboxes}


__all__ = ["to_overlay"]
