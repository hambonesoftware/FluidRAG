"""Domain prompts for the RAG pass service."""

from .controls import Prompt as ControlsPrompt
from .electrical import Prompt as ElectricalPrompt
from .mechanical import Prompt as MechanicalPrompt
from .project_mgmt import Prompt as ProjectManagementPrompt
from .software import Prompt as SoftwarePrompt

__all__ = [
    "MechanicalPrompt",
    "ElectricalPrompt",
    "SoftwarePrompt",
    "ControlsPrompt",
    "ProjectManagementPrompt",
]
