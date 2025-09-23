"""Prompt registry for per-discipline extraction passes."""

from .mechanical import MECHANICAL_PROMPT
from .electrical import ELECTRICAL_PROMPT
from .controls import CONTROLS_PROMPT
from .software import SOFTWARE_PROMPT
from .project_management import PROJECT_MANAGEMENT_PROMPT

PASS_PROMPTS = {
    "Mechanical": MECHANICAL_PROMPT,
    "Electrical": ELECTRICAL_PROMPT,
    "Controls": CONTROLS_PROMPT,
    "Software": SOFTWARE_PROMPT,
    "Project Management": PROJECT_MANAGEMENT_PROMPT,
}

__all__ = [
    "PASS_PROMPTS",
    "MECHANICAL_PROMPT",
    "ELECTRICAL_PROMPT",
    "CONTROLS_PROMPT",
    "SOFTWARE_PROMPT",
    "PROJECT_MANAGEMENT_PROMPT",
]
