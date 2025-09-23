"""Constants used by the pass execution pipeline."""
from __future__ import annotations

ALL_PASSES = [
    "Mechanical",
    "Electrical",
    "Controls",
    "Software",
    "Project Management",
]
CHUNK_GROUP_TOKEN_LIMIT = 120000
DEFAULT_PASS_CONCURRENCY = 5
DEFAULT_PASS_TIMEOUT_S = 360
DEFAULT_PASS_TEMPERATURE = 0.0
DEFAULT_PASS_MAX_TOKENS = 120000

DEFAULT_PASS_MAX_ATTEMPTS = 4
DEFAULT_PASS_BACKOFF_INITIAL_MS = 600
DEFAULT_PASS_BACKOFF_FACTOR = 1.7
DEFAULT_PASS_BACKOFF_MAX_MS = 4500

CSV_COLUMNS = ["Document", "(Sub)Section #", "(Sub)Section Name", "Specification", "Pass"]

# Delay between pass submissions (seconds). Five seconds keeps LLM load manageable while
# allowing all passes to overlap in flight.
PASS_STAGGER_SECONDS = 5.0

PASS_FLAG_TO_NAME = {
    "only_mechanical": "Mechanical",
    "only_mech": "Mechanical",
    "only_electrical": "Electrical",
    "only_controls": "Controls",
    "only_control": "Controls",
    "only_software": "Software",
    "only_pm": "Project Management",
    "only_project_management": "Project Management",
}
