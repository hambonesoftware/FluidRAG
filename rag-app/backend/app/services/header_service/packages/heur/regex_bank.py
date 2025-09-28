"""Header regex heuristics."""
from __future__ import annotations

import re
from typing import List, Pattern


def header_patterns() -> List[Pattern[str]]:
    """Return permissive regexes to identify potential headings."""

    return [
        re.compile(r"(\d+(?:\.\d+)*)\s+[A-Z][^\n]{2,}"),
        re.compile(r"[A-Z]{3,}(?:\s+[A-Z]{3,})*"),
    ]
