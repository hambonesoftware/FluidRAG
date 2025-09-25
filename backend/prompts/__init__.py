"""Central prompt library for FluidRAG."""

from .atomic import atomic_system_prompt, atomic_user_template
from .header_detection import HEADER_DETECTION_SYSTEM
from .passes import (
    PASS_PROMPTS,
)

__all__ = [
    "HEADER_DETECTION_SYSTEM",
    "PASS_PROMPTS",
    "atomic_system_prompt",
    "atomic_user_template",
]
