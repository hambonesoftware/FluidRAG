"""Range checking helpers."""
from __future__ import annotations


def within_range(value, low, high) -> bool:
    try:
        value_f = float(value)
        low_f = float(low)
        high_f = float(high)
    except (TypeError, ValueError):
        return False
    return low_f <= value_f <= high_f


__all__ = ["within_range"]
