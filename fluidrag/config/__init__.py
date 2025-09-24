from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Dict

_CONFIG_CACHE: Dict[str, Any] = {}


def _parse_simple_yaml(text: str) -> Dict[str, Any]:
    """Parse a small subset of YAML used in project defaults.

    The parser understands dictionaries with indentation and inline JSON-like
    dictionaries/lists. It deliberately avoids pulling in a heavy YAML
    dependency so tests can run without extra installation steps.
    """

    def parse_value(raw: str) -> Any:
        raw = raw.strip()
        if raw == "":
            return None
        lowered = raw.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            if "." in raw:
                return float(raw)
            return int(raw)
        except ValueError:
            pass
        if raw.startswith("{"):
            return parse_inline_mapping(raw)
        if raw.startswith("["):
            replaced = raw.replace("true", "True").replace("false", "False")
            try:
                return ast.literal_eval(replaced)
            except Exception:
                return json.loads(raw)
        return raw

    root: Dict[str, Any] = {}
    stack: list[tuple[int, Dict[str, Any]]] = [(-1, root)]

    def parse_inline_mapping(value: str) -> Dict[str, Any]:
        inner = value.strip()[1:-1].strip()
        if not inner:
            return {}
        parts: list[str] = []
        depth = 0
        start = 0
        for idx, char in enumerate(inner):
            if char in "{[":
                depth += 1
            elif char in "]}":
                depth -= 1
            elif char == "," and depth == 0:
                parts.append(inner[start:idx].strip())
                start = idx + 1
        parts.append(inner[start:].strip())
        mapping: Dict[str, Any] = {}
        for part in parts:
            if ":" not in part:
                continue
            key, val = part.split(":", 1)
            mapping[key.strip()] = parse_value(val)
        return mapping

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        while stack and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]
        if ":" not in stripped:
            raise ValueError(f"Unsupported line in YAML: {line}")
        key, value = stripped.split(":", 1)
        key = key.strip()
        parsed = parse_value(value)
        if parsed is None:
            new_map: Dict[str, Any] = {}
            current[key] = new_map
            stack.append((indent, new_map))
        else:
            current[key] = parsed
    return root


def load_config(config_path: str | Path | None = None) -> Dict[str, Any]:
    """Load the FluidRAG configuration as a nested dictionary."""

    if config_path is None:
        config_path = Path(__file__).with_name("defaults.yaml")
    path = Path(config_path)
    cache_key = str(path.resolve())
    if cache_key not in _CONFIG_CACHE:
        _CONFIG_CACHE[cache_key] = _parse_simple_yaml(path.read_text())
    return _CONFIG_CACHE[cache_key]


__all__ = ["load_config"]
