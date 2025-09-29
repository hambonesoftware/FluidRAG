"""CLI helpers for validating release readiness artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class ReleaseCheck:
    """Represents a single release readiness check."""

    name: str
    description: str
    status: bool
    detail: str = ""

    def as_dict(self) -> dict[str, str | bool]:
        """Return a serialisable representation of the check."""

        payload: dict[str, str | bool] = {
            "name": self.name,
            "description": self.description,
            "status": self.status,
        }
        if self.detail:
            payload["detail"] = self.detail
        return payload


def has_heading(path: Path, heading: str) -> bool:
    """Return ``True`` if the markdown file contains the given heading."""

    if not path.exists():
        return False
    normalized = heading.strip().lower()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip("# ").strip().lower()
        if stripped == normalized:
            return True
    return False


def discover_release_artifacts(repo_root: Path) -> list[ReleaseCheck]:
    """Collect release readiness checks for the repository."""

    readme = repo_root / "README.md"
    changelog = repo_root / "CHANGELOG.md"
    env_example = repo_root / ".env.example"
    outcome_report = repo_root / "reports" / "phase_11_outcome.md"
    backlog_report = repo_root / "reports" / "post_phase_backlog.md"
    demo_script = repo_root / "scripts" / "offline_pipeline_demo.py"

    checks: list[ReleaseCheck] = []

    readme_sections: list[str] = []
    if not readme.exists():
        readme_sections.append("README missing")
    else:
        for section in ("Quickstart", "Environment Setup", "Troubleshooting"):
            if not has_heading(readme, section):
                readme_sections.append(f"Missing '{section}' heading")
    checks.append(
        ReleaseCheck(
            name="README",
            description="Quickstart, environment, and troubleshooting guidance documented.",
            status=not readme_sections,
            detail="; ".join(readme_sections),
        )
    )

    changelog_detail = ""
    changelog_status = changelog.exists()
    if changelog_status:
        content = changelog.read_text(encoding="utf-8")
        if "Phase 11" not in content:
            changelog_status = False
            changelog_detail = "Missing Phase 11 entry"
    else:
        changelog_detail = "CHANGELOG.md missing"
    checks.append(
        ReleaseCheck(
            name="Changelog",
            description="Phase 11 entry recorded with release summary.",
            status=changelog_status,
            detail=changelog_detail,
        )
    )

    checks.append(
        ReleaseCheck(
            name="Environment Template",
            description=".env.example present for handover.",
            status=env_example.exists(),
            detail=".env.example missing" if not env_example.exists() else "",
        )
    )

    checks.append(
        ReleaseCheck(
            name="Outcome Report",
            description="Phase 11 outcome report captured under reports/",
            status=outcome_report.exists(),
            detail="Create reports/phase_11_outcome.md" if not outcome_report.exists() else "",
        )
    )

    checks.append(
        ReleaseCheck(
            name="Backlog",
            description="Future backlog triage recorded for next iteration.",
            status=backlog_report.exists(),
            detail="Create reports/post_phase_backlog.md" if not backlog_report.exists() else "",
        )
    )

    checks.append(
        ReleaseCheck(
            name="Demo Script",
            description="Offline pipeline demo script available under scripts/.",
            status=demo_script.exists(),
            detail="Create scripts/offline_pipeline_demo.py" if not demo_script.exists() else "",
        )
    )

    return checks


def render_summary(checks: Iterable[ReleaseCheck]) -> str:
    """Render the checklist as a human readable string."""

    lines: list[str] = []
    for check in checks:
        icon = "✅" if check.status else "❌"
        line = f"{icon} {check.name}: {check.description}"
        lines.append(line)
        if check.detail:
            lines.append(f"    {check.detail}")
    return "\n".join(lines)


def run_cli(args: Sequence[str] | None = None) -> int:
    """Execute the CLI and return an exit code."""

    parser = argparse.ArgumentParser(description="FluidRAG release readiness checks")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (defaults to script parent).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON summary instead of human readable text.",
    )
    parsed = parser.parse_args(list(args) if args is not None else None)

    checks = discover_release_artifacts(parsed.root)
    if parsed.json:
        print(json.dumps([check.as_dict() for check in checks], indent=2))
    else:
        print(render_summary(checks))
    return 0 if all(check.status for check in checks) else 1


def main() -> None:
    """Entry point for ``python scripts/release_checklist.py``."""

    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
