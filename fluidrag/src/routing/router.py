from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict

STANDARD_REGEX = re.compile(r"\b(?:ISO|IEC|NFPA|UL|IEEE|EN)\s?[0-9A-Za-z:\-]+\b", re.IGNORECASE)
CLAUSE_REGEX = re.compile(r"\b\d+(?:\.\d+){1,}\b")
NARRATIVE_REGEX = re.compile(r"\b(overview|summary|narrative|background)\b", re.IGNORECASE)


@dataclass
class RoutingDecision:
    view: str
    use_graph: bool


class Router:
    def __init__(self, config: dict) -> None:
        self.config = config

    def decide(self, query: str) -> RoutingDecision:
        query_lower = query.lower()
        if len(STANDARD_REGEX.findall(query)) >= 2:
            return RoutingDecision(view="hep", use_graph=self.config["graph"]["summaries"].get("trigger_multi_standard", False))
        if STANDARD_REGEX.search(query) or CLAUSE_REGEX.search(query):
            return RoutingDecision(view="hep", use_graph=False)
        if NARRATIVE_REGEX.search(query_lower):
            return RoutingDecision(view="fluid", use_graph=False)
        return RoutingDecision(view="standard", use_graph=False)


__all__ = ["Router", "RoutingDecision"]
