"""Helpers for reasoning about inequality operators."""
from __future__ import annotations

import re
from typing import List


def normalize_op(op: str | None) -> str:
    mapping = {"<=": "≤", ">=": "≥", "==": "=", None: "="}
    return mapping.get(op, op)


def extract_inequalities(text: str) -> List[str]:
    pattern = re.compile(r"(≥|<=|≤|>=|=|==|>|<|±)")
    return pattern.findall(text)


__all__ = ["extract_inequalities", "normalize_op"]
