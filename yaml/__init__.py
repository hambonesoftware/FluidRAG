"""Minimal YAML loader supporting the subset required for tests."""

from __future__ import annotations

from typing import Any, List


def safe_load(stream: str) -> Any:
    if hasattr(stream, "read"):
        text = stream.read()
    else:
        text = stream
    lines = text.splitlines()
    return _parse_block(lines, 0)


def _parse_block(lines: List[str], indent: int):
    items = None
    result = None
    while lines:
        raw = lines[0]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            lines.pop(0)
            continue
        cur_indent = len(raw) - len(raw.lstrip(" "))
        if cur_indent < indent:
            break
        if cur_indent > indent:
            raise ValueError("Unexpected indentation")
        lines.pop(0)
        if stripped.startswith("- "):
            if result is None:
                result = []
            value_text = stripped[2:].strip()
            if value_text:
                result.append(_parse_value(value_text))
            else:
                result.append(_parse_block(lines, indent + 2))
        else:
            if result is None:
                result = {}
            if ":" not in stripped:
                raise ValueError(f"Invalid mapping entry: {stripped}")
            key, value_text = stripped.split(":", 1)
            key = key.strip()
            value_text = value_text.strip()
            if value_text:
                result[key] = _parse_value(value_text)
            else:
                result[key] = _parse_block(lines, indent + 2)
    if result is None:
        return {}
    return result


def _parse_value(value: str):
    if value.startswith("{") and value.endswith("}"):
        inner = value[1:-1].strip()
        if not inner:
            return {}
        mapping = {}
        parts = _split_inline(inner)
        for part in parts:
            key, val = part.split(":", 1)
            mapping[key.strip()] = _parse_value(val.strip())
        return mapping
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_value(part.strip()) for part in _split_inline(inner)]
    if value.startswith(('"', "'")) and value.endswith(('"', "'")):
        inner = value[1:-1]
        try:
            return bytes(inner, "utf-8").decode("unicode_escape")
        except Exception:
            return inner
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    if any(ch.isdigit() for ch in value) and _is_number(value):
        num = float(value)
        if num.is_integer():
            return int(num)
        return num
    return value


def _split_inline(text: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    current = []
    for ch in text:
        if ch == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        current.append(ch)
    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts


def _is_number(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        try:
            float(value.replace(".", "0."))
            return True
        except ValueError:
            pass
    if value.startswith("."):
        try:
            float("0" + value)
            return True
        except ValueError:
            return False
    return False
