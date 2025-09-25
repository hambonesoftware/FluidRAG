"""Prompt templates for section-scoped refinement."""
from __future__ import annotations

from typing import Dict


SYSTEM_PROMPT = """
You are an expert requirements refinement assistant. Your task is to turn a
non-atomic parent specification into a concise parent summary and a list of
atomic child requirements. Each child must contain exactly one measurable or
verifiable expectation expressed as Metric, Operator (>=, <=, = only), Target
Value, Units when applicable, and a concrete TestMethod from
{FAT, SAT, Measurement, VisualInspect, DocReview}. Return strictly formatted
JSON that conforms to the provided schema. Do not invent information that is
missing from the context, and never change numeric values unless explicitly
stated. If the source requirement is already atomic, return a single child
mirroring the source without alteration. Do not include prose outside of the
JSON payload.
""".strip()


GRANULARITY_GUIDES: Dict[str, str] = {
    "Mechanical": """
Break complex mechanical statements into individual physical expectations.
Focus on measurable geometry, force/torque limits, payload capacities, and
protective hardware features. Avoid mixing safety and performance in one child.
""".strip(),
    "Electrical": """
Split electrical specifications so each child covers one circuit, load, or
power quality requirement. Keep voltage, current, and protection criteria
independent.
""".strip(),
    "Controls": """
Ensure every child captures exactly one controls function or logic behaviour.
Separate HMI, alarms, recipes, and diagnostics into distinct children with
explicit performance thresholds when provided.
""".strip(),
    "Software": """
Isolate software behaviours or interfaces by feature. Each child should align
with a single workflow or API contract. Capture timing/throughput metrics when
available.
""".strip(),
    "Project Management": """
Treat scheduling, deliverables, and documentation milestones individually. Use
calendar-based metrics and ensure acceptance is verifiable by review.
""".strip(),
    "Header": """
Preserve the document header intent. Summaries should remain high level while
children enumerate concrete obligations referenced in the header context.
""".strip(),
}


def get_granularity_guide(pass_name: str) -> str:
    """Return the swimlane-specific granularity guidance."""

    return GRANULARITY_GUIDES.get(pass_name, "")


__all__ = ["SYSTEM_PROMPT", "GRANULARITY_GUIDES", "get_granularity_guide"]

