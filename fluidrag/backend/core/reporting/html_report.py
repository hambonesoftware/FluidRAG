"""HTML reporting scaffolding for reviewer overlays."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable, Mapping

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>FluidRAG Review Report – {doc_id}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 1.5rem; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; }}
    th, td {{ border: 1px solid #ccc; padding: 0.5rem; text-align: left; }}
    th {{ background: #f3f3f3; }}
    .meta {{ color: #555; font-size: 0.85rem; margin-bottom: 1rem; }}
  </style>
</head>
<body>
  <h1>Review report for {doc_id}</h1>
  <p class=\"meta\">Generated at {generated_at}</p>
  {extractions_table}
  {overlays_section}
</body>
</html>"""


def _render_extractions_table(extractions: Iterable[Mapping[str, object]]) -> str:
    rows = []
    for record in extractions:
        rows.append(
            "<tr>"
            f"<td>{record.get('section_id', '')}</td>"
            f"<td>{record.get('text', '')}</td>"
            f"<td>{record.get('value', '')}</td>"
            f"<td>{record.get('unit', '')}</td>"
            f"<td>{record.get('op', '')}</td>"
            "</tr>"
        )
    if not rows:
        return "<p>No extractions produced.</p>"
    header = "<tr><th>Section</th><th>Text</th><th>Value</th><th>Unit</th><th>Op</th></tr>"
    return f"<table>{header}{''.join(rows)}</table>"


def _render_overlays(overlays: Iterable[Mapping[str, object]]) -> str:
    rows = []
    for overlay in overlays:
        page = overlay.get("page", "?")
        bboxes = overlay.get("bboxes", [])
        rows.append(f"<li>Page {page}: {bboxes}</li>")
    if not rows:
        return ""
    return "<section><h2>Overlays</h2><ul>" + "".join(rows) + "</ul></section>"


def render(doc_id: str, extractions: Iterable[Mapping[str, object]], overlays: Iterable[Mapping[str, object]]) -> str:
    """Render a basic HTML report for reviewers.

    The scaffold focuses on determinism and ease of testing rather than visual
    fidelity. The function returns an HTML string; callers can persist it to the
    desired location.
    """

    generated_at = datetime.now(UTC).isoformat()
    table_html = _render_extractions_table(extractions)
    overlays_html = _render_overlays(overlays)
    return HTML_TEMPLATE.format(
        doc_id=doc_id,
        generated_at=generated_at,
        extractions_table=table_html,
        overlays_section=overlays_html,
    )


__all__ = ["render"]
