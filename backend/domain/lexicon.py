"""Discipline keyword lexicons and thresholds used for domain scoring."""
from __future__ import annotations

from typing import Dict, List, Mapping

PASS_DOMAIN_LEXICON: Mapping[str, List[str]] = {
    "Mechanical": [
        "footprint",
        "conveyor",
        "cdlr",
        "mdr",
        "chain driven live roller",
        "end of arm",
        "eoat",
        "guard",
        "clearance",
        "frame",
        "weldment",
    ],
    "Electrical": [
        "sccr",
        "short circuit",
        "feeder",
        "transformer",
        "ul508a",
        "nfpa 79",
        "panel layout",
        "fla",
        "full load",
        "network power",
        "grounding",
    ],
    "Controls": [
        "plc",
        "controller",
        "guardlogix",
        "safety category",
        "performance level",
        "sil",
        "i/o",
        "estop",
        "interlock",
        "safety relay",
        "safety device",
    ],
    "Software": [
        "udt",
        "aoi",
        "user defined type",
        "versioning",
        "backup",
        "restore",
        "calibration",
        "hmi",
        "diagnostic",
        "alarm history",
        "source code",
    ],
    "Project Management": [
        "milestone",
        "gantt",
        "fat",
        "sat",
        "training",
        "warranty",
        "support",
        "deliverable",
        "schedule",
        "payment",
        "commercial",
    ],
}

PASS_DOMAIN_THRESHOLD: Dict[str, int] = {
    "Mechanical": 1,
    "Electrical": 1,
    "Controls": 1,
    "Software": 1,
    "Project Management": 1,
}

__all__ = ["PASS_DOMAIN_LEXICON", "PASS_DOMAIN_THRESHOLD"]
