"""Pre-commit helper to ensure source files stay within the 500-line policy."""

from __future__ import annotations

import sys
from pathlib import Path

MAX_LINES = 500


def file_too_long(path: Path) -> bool:
    """Return True if ``path`` exceeds ``MAX_LINES`` text lines."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            for idx, _ in enumerate(handle, start=1):
                if idx > MAX_LINES:
                    return True
    except UnicodeDecodeError:
        # Binary or non-text file; skip enforcement.
        return False
    return False


def main(argv: list[str]) -> int:
    """Validate all provided files are within policy."""
    violations: list[str] = []
    for arg in argv:
        path = Path(arg)
        if not path.exists():
            continue
        if file_too_long(path):
            violations.append(f"{path} exceeds {MAX_LINES} lines")
    if violations:
        for violation in violations:
            print(violation)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
