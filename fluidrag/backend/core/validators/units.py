"""Unit extraction helpers used by the validators pipeline."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

UNIT_PATTERN = r"(mm|cm|m|in|ft|psi|bar|kPa|MPa|A|mA|kA|V|VAC|VDC|kV|kW|kVA|°C|°F|Hz|rpm|N|kN|lbf)"
VALUE_PATTERN = r"[-+]?\d+(?:\.\d+)?"
OP_PATTERN = r"(≥|<=|≤|>=|=|==|>|<|±)"

TOKEN_RE = re.compile(rf"(?P<op>{OP_PATTERN})?\s*(?P<value>{VALUE_PATTERN})\s*(?P<unit>{UNIT_PATTERN})", re.IGNORECASE)
TOLERANCE_RE = re.compile(
    rf"(?P<value>{VALUE_PATTERN})\s*(?P<unit>{UNIT_PATTERN})?\s*±\s*(?P<tol>{VALUE_PATTERN})\s*(?P<tol_unit>{UNIT_PATTERN})?",
    re.IGNORECASE,
)
RANGE_RE = re.compile(
    rf"(?P<low>{VALUE_PATTERN})\s*(?:-|to)\s*(?P<high>{VALUE_PATTERN})\s*(?P<unit>{UNIT_PATTERN})?",
    re.IGNORECASE,
)


@dataclass
class ParsedUnits:
    values: List[float]
    units: List[str]
    ops: List[str]

    value: Optional[float] = None
    unit: Optional[str] = None
    op: Optional[str] = None
    tol: Optional[float] = None
    range: Optional[Tuple[float, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "values": self.values,
            "units": self.units,
            "ops": self.ops,
            "tol": self.tol,
            "range": self.range,
        }
        if self.value is not None:
            data["value"] = self.value
        if self.unit is not None:
            data["unit"] = self.unit
        if self.op is not None:
            data["op"] = self.op
        return data


def parse_units(text: str) -> Dict[str, Any]:
    """Extract unit-bearing values from ``text``.

    The helper is intentionally simple; it surfaces the first recognised trio to
    support atomic extraction while keeping the full lists available for richer
    analysis.
    """

    values: List[float] = []
    units: List[str] = []
    ops: List[str] = []

    for match in TOKEN_RE.finditer(text):
        value = float(match.group("value"))
        unit = match.group("unit")
        op = match.group("op") or "="
        values.append(value)
        units.append(unit)
        ops.append(op)

    parsed = ParsedUnits(values=values, units=units, ops=ops)
    if values:
        parsed.value = values[0]
        parsed.unit = units[0]
        parsed.op = ops[0]

    tol_match = TOLERANCE_RE.search(text)
    if tol_match:
        parsed.tol = float(tol_match.group("tol"))
        base_value = float(tol_match.group("value"))
        base_unit = tol_match.group("unit") or tol_match.group("tol_unit")
        if parsed.value is None:
            parsed.value = base_value
        if parsed.unit is None and base_unit:
            parsed.unit = base_unit
        if parsed.op is None:
            parsed.op = "="
        if not parsed.ops:
            parsed.ops.append(parsed.op)
        if base_unit and base_unit not in parsed.units:
            parsed.units.append(base_unit)
        if base_value not in parsed.values:
            parsed.values.insert(0, base_value)

    range_match = RANGE_RE.search(text)
    if range_match:
        low = float(range_match.group("low"))
        high = float(range_match.group("high"))
        parsed.range = (low, high)
        range_unit = range_match.group("unit")
        if parsed.value is None:
            parsed.value = low
        if parsed.unit is None and range_unit:
            parsed.unit = range_unit
        if parsed.op is None:
            parsed.op = "="
        if not parsed.ops:
            parsed.ops.append(parsed.op)
        if range_unit and range_unit not in parsed.units:
            parsed.units.append(range_unit)
        if low not in parsed.values:
            parsed.values.insert(0, low)
    return parsed.to_dict()


_DIMENSION_GROUPS = {
    "length": {"mm", "cm", "m", "in", "ft"},
    "pressure": {"psi", "bar", "kPa", "MPa"},
    "voltage": {"V", "VAC", "VDC", "kV"},
    "current": {"A", "mA", "kA"},
    "temperature": {"°C", "°F"},
    "speed": {"rpm", "Hz"},
    "force": {"N", "kN", "lbf"},
}
_DIMENSION_GROUPS_NORMALISED = [{unit.lower() for unit in units} for units in _DIMENSION_GROUPS.values()]


def dimension_sanity(unit: str, *, property_hint: Optional[str] = None) -> bool:
    """Validate that ``unit`` belongs to one of the known dimension groups."""

    if not unit:
        return False

    canonical = unit.strip()
    for group_units, group_norm in zip(_DIMENSION_GROUPS.values(), _DIMENSION_GROUPS_NORMALISED):
        if canonical in group_units or canonical.lower() in group_norm:
            return True
    return False


__all__ = ["dimension_sanity", "parse_units", "ParsedUnits"]
