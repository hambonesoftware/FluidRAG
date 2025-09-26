"""Unit extraction helpers used by the validators pipeline."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

UNIT_PATTERN = r"(mm|cm|m|in|ft|psi|bar|kPa|MPa|A|mA|kA|V|VAC|VDC|kV|kW|kVA|°C|°F|Hz|rpm|N|kN|lbf)"
VALUE_PATTERN = r"[-+]?\d+(?:\.\d+)?"
OP_PATTERN = r"(≥|<=|≤|>=|=|==|>|<|±)"

TOKEN_RE = re.compile(rf"(?P<op>{OP_PATTERN})?\s*(?P<value>{VALUE_PATTERN})\s*(?P<unit>{UNIT_PATTERN})", re.IGNORECASE)


@dataclass
class ParsedUnits:
    values: List[float]
    units: List[str]
    ops: List[str]

    value: Optional[float] = None
    unit: Optional[str] = None
    op: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "values": self.values,
            "units": self.units,
            "ops": self.ops,
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
