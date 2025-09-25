"""Utility functions for the requirements register pipeline."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ALLOWED_PASSES: Tuple[str, ...] = (
    "Controls",
    "Electrical",
    "Mechanical",
    "Project Management",
    "Software",
    "Header",
)

TAG_KEYWORDS: Dict[str, Sequence[str]] = {
    "Safety": ("safety", "iso 14120", "safe torque", "guard"),
    "Vision": ("vision", "camera"),
    "EOAT": ("eoat", "end of arm"),
    "HMI": ("hmi", "alarm", "diagnostic", "recipe"),
    "Docs": ("documentation", "manual", "drawing", "procedure"),
    "Energy": ("energy", "power"),
    "Schedule": ("week", "milestone", "timeline"),
}

REQTYPE_KEYWORDS: Dict[str, Sequence[str]] = {
    "Safety": ("safety", "guard", "safe torque", "iso 13849", "iso 14120"),
    "Performance": ("throughput", "cycle", "availability", "speed", "alignment", "payload"),
    "Documentation": ("document", "manual", "report", "drawing", "procedure"),
    "Utility": ("diagnostic", "recipe", "alarm", "history", "dashboard"),
    "Commercial": ("payment", "commercial", "terms", "tco"),
    "Schedule": ("week", "milestone", "timeline", "schedule"),
}

REQTYPE_DEFAULT_BY_PASS: Dict[str, str] = {
    "Controls": "Utility",
    "Electrical": "Safety",
    "Mechanical": "Performance",
    "Project Management": "Schedule",
    "Software": "Utility",
    "Header": "Documentation",
}

EVAL_BUCKET_BY_REQTYPE: Dict[str, str] = {
    "Performance": "Performance20",
    "Safety": "Safety15",
    "Documentation": "Documentation5",
    "Utility": "Maintenance10",
    "Commercial": "Commercial20",
    "Schedule": "Schedule15",
}

UNIT_CANONICAL: Dict[str, str] = {
    "%": "%",
    "percent": "%",
    "percentage": "%",
    "in": "in",
    "inch": "in",
    "inches": "in",
    "mm": "mm",
    "millimeter": "mm",
    "millimeters": "mm",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "a": "A",
    "amp": "A",
    "amps": "A",
    "ampere": "A",
    "amperes": "A",
    "hz": "Hz",
    "hertz": "Hz",
    "cpm": "cpm",
    "s": "s",
    "sec": "s",
    "secs": "s",
    "second": "s",
    "seconds": "s",
    "min": "min",
    "minute": "min",
    "minutes": "min",
    "hr": "hr",
    "hour": "hr",
    "hours": "hr",
    "day": "day",
    "days": "day",
}

OPERATOR_MAP: Dict[str, str] = {
    ">=": ">=",
    "≤": "<=",
    "<=": "<=",
    "≥": ">=",
    "at least": ">=",
    "greater than or equal": ">=",
    "greater than": ">=",
    "no less than": ">=",
    "at most": "<=",
    "less than or equal": "<=",
    "less than": "<=",
    "no more than": "<=",
    "equal to": "=",
    "=": "=",
    "exactly": "=",
}

TEST_METHOD_KEYWORDS: Dict[str, str] = {
    "fat": "FAT",
    "sat": "SAT",
    "visual": "VisualInspect",
    "inspect": "VisualInspect",
    "witness": "FAT",
    "measurement": "Measurement",
    "document": "DocReview",
}

SCHEDULE_WEEK_PATTERN = re.compile(r"week\s+(?P<week>\d{1,2})", re.IGNORECASE)
PAYMENT_PATTERN = re.compile(r"(?P<term>\d{1,2}(?:/\d{1,2}){1,3})")
MEASUREMENT_PATTERN = re.compile(
    r"(?P<prefix>[A-Za-z\s]{0,40})"
    r"(?P<operator>>=|<=|≥|≤|=|at least|at most|greater than|greater than or equal|less than|less than or equal|no more than|no less than|equal to|exactly)\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>[A-Za-z%/°]+)?",
    re.IGNORECASE,
)


@dataclass
class Measurement:
    metric: str
    operator: str
    value: float
    unit: str
    acceptance_window: str = ""


def canonical_pass(pass_name: str) -> str:
    """Return a normalized pass that fits the allowed swimlanes."""
    if not pass_name:
        return "Header"
    normalized = pass_name.strip().title()
    if normalized in ALLOWED_PASSES:
        return normalized
    # Allow matching by lowercase comparison
    for candidate in ALLOWED_PASSES:
        if candidate.lower() == normalized.lower():
            return candidate
    return "Header"


def compute_anchor(text: str) -> str:
    """Return the first eight characters of a content hash."""
    digest = hashlib.sha1(text.strip().encode("utf-8")).hexdigest()
    return digest[:8]


def generate_req_id(section_id: Optional[str], text: str, suffix: str = "") -> str:
    section_part = section_id.strip() if section_id else "000"
    digest = compute_anchor(text)
    return f"EPF-{section_part}-{digest}{suffix}"


def infer_tags(spec: str) -> str:
    spec_lower = spec.lower()
    tags: List[str] = []
    for tag, keywords in TAG_KEYWORDS.items():
        if any(keyword in spec_lower for keyword in keywords):
            tags.append(tag)
    return ",".join(sorted(dict.fromkeys(tags)))


def infer_req_type(pass_name: str, spec: str) -> str:
    spec_lower = spec.lower()
    for req_type, keywords in REQTYPE_KEYWORDS.items():
        if any(keyword in spec_lower for keyword in keywords):
            return req_type
    return REQTYPE_DEFAULT_BY_PASS.get(canonical_pass(pass_name), "Utility")


def infer_eval_bucket(req_type: str) -> str:
    return EVAL_BUCKET_BY_REQTYPE.get(req_type, "")


def normalize_unit(raw_unit: Optional[str]) -> str:
    if not raw_unit:
        return ""
    cleaned = raw_unit.strip().lower().strip("./")
    return UNIT_CANONICAL.get(cleaned, "")


def _normalize_operator(raw_operator: str) -> str:
    lowered = raw_operator.lower()
    for key, canonical in OPERATOR_MAP.items():
        if lowered == key:
            return canonical
    for key, canonical in OPERATOR_MAP.items():
        if key in lowered:
            return canonical
    return ""


def _infer_metric_from_context(prefix: str, spec: str) -> str:
    tokens = prefix.strip() or spec
    tokens_lower = tokens.lower()
    keyword_map = {
        "alignment": "Alignment",
        "availability": "Availability",
        "throughput": "Throughput",
        "cycle": "CycleTime",
        "payload": "Payload",
        "torque": "Torque",
        "temperature": "Temperature",
        "humidity": "Humidity",
        "voltage": "Voltage",
        "current": "Current",
        "alarm": "AlarmHistory",
        "recipe": "RecipeCapacity",
        "diagnostic": "Diagnostics",
        "payment": "PaymentMilestone",
    }
    for keyword, metric in keyword_map.items():
        if keyword in tokens_lower:
            return metric
    return tokens.strip().title()[:40]


def extract_measurement(spec: str) -> Optional[Measurement]:
    for match in MEASUREMENT_PATTERN.finditer(spec):
        operator = _normalize_operator(match.group("operator"))
        if not operator:
            continue
        value = float(match.group("value"))
        unit = normalize_unit(match.group("unit"))
        metric = _infer_metric_from_context(match.group("prefix"), spec)
        window = ""
        # Look for trailing durations such as "for 30 days"
        trailing = spec[match.end():]
        duration_match = re.search(r"for\s+(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>days?|hours?|minutes?|seconds?)", trailing, re.IGNORECASE)
        if duration_match:
            duration_value = duration_match.group("value")
            duration_unit = normalize_unit(duration_match.group("unit"))
            window = f">={duration_value} {duration_unit}" if duration_unit else f">={duration_value}"
        return Measurement(metric=metric, operator=operator, value=value, unit=unit, acceptance_window=window)
    return None


def infer_test_method(spec: str, req_type: str) -> str:
    spec_lower = spec.lower()
    for keyword, method in TEST_METHOD_KEYWORDS.items():
        if keyword in spec_lower:
            return method
    if req_type in {"Performance", "Safety"}:
        return "Measurement"
    if req_type in {"Schedule", "Commercial"}:
        return "DocReview"
    if req_type == "Documentation":
        return "DocReview"
    return "FAT"


def infer_schedule_fields(spec: str, req_type: str) -> Tuple[str, Optional[int], str]:
    milestone = ""
    week = None
    payment_term = ""
    if req_type in {"Schedule", "Commercial"} or "milestone" in spec.lower():
        milestone = spec
        week_match = SCHEDULE_WEEK_PATTERN.search(spec)
        if week_match:
            week = int(week_match.group("week"))
    payment_match = PAYMENT_PATTERN.search(spec)
    if payment_match:
        payment_term = payment_match.group("term")
    return milestone, week, payment_term


def extract_machine_fields(spec: str, pass_name: str) -> Dict[str, object]:
    req_type = infer_req_type(pass_name, spec)
    measurement = extract_measurement(spec)
    metric = measurement.metric if measurement else ""
    operator = measurement.operator if measurement else ""
    target_value = measurement.value if measurement else None
    units = measurement.unit if measurement else ""
    acceptance_window = measurement.acceptance_window if measurement else ""
    test_method = infer_test_method(spec, req_type)
    return {
        "ReqType": req_type,
        "Metric": metric,
        "Operator": operator,
        "TargetValue": target_value,
        "Units": units,
        "TestMethod": test_method,
        "AcceptanceWindow": acceptance_window,
    }


def detect_atomicity(spec: str) -> str:
    spec_lower = spec.lower()
    if spec_lower.count(" shall ") > 1:
        return "suspect"
    if ";" in spec or "\n" in spec:
        return "suspect"
    if any(delim in spec for delim in ("•", "- ")):
        return "suspect"
    if re.search(r"\b(?:and|or)\b", spec_lower) and re.search(r"\b(?:shall|must|include|provide)\b", spec_lower):
        return "suspect"
    return "atomic"


def _dedupe_preserve(items: List[str]) -> List[str]:
    seen = set()
    unique: List[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def split_spec_into_atoms(spec: str, context: str = "") -> List[str]:
    def _keywords(text: str) -> set[str]:
        return {token for token in re.findall(r"[A-Za-z0-9]+", text.lower()) if len(token) > 3}

    spec_keywords = _keywords(spec)

    text = spec.replace("•", "\n•")
    candidates: List[str] = []
    for part in re.split(r"[\n\r]+", text):
        cleaned = part.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^[•\-\d\)\.\s]+", "", cleaned).strip()
        if cleaned:
            candidates.append(cleaned)
    candidates = _dedupe_preserve([c for c in candidates if len(c) > 8 and not c.endswith(":")])
    if len(candidates) > 1:
        return candidates

    semis = [segment.strip() for segment in spec.split(";") if segment.strip()]
    semis = _dedupe_preserve([segment for segment in semis if len(segment) > 8])
    if len(semis) > 1:
        return semis

    shall_match = re.search(r"(?P<subject>.+?\bshall)\s+(?P<verb>[a-z]+)\s*(?P<items>.+)", spec, re.IGNORECASE)
    if shall_match:
        subject = shall_match.group("subject").strip()
        verb = shall_match.group("verb").strip()
        items_segment = shall_match.group("items")
        raw_items = re.split(r",|\band\b", items_segment)
        normalized_items = _dedupe_preserve(
            [item.strip(" .") for item in raw_items if len(item.strip(" .")) > 3]
        )
        if len(normalized_items) > 1:
            enumerated: List[str] = []
            for item in normalized_items:
                if re.match(r"^(provide|include|maintain|retain|withstand|occur|support)", item, re.IGNORECASE):
                    enumerated.append(f"{subject} {item}.")
                else:
                    enumerated.append(f"{subject} {verb} {item}.")
            return enumerated

    conj_split = re.split(r"\b(?:and|or)\b", spec)
    conj_split = [seg.strip(", .") for seg in conj_split if seg.strip(", .")]
    conj_split = _dedupe_preserve([
        seg
        for seg in conj_split
        if len(seg) > 8 and (
            re.search(r"\b(shall|must|provide|include|maintain|retain|withstand|occur)\b", seg.lower())
            or re.search(r"\d", seg)
        )
    ])
    if len(conj_split) > 1:
        return conj_split

    context_text = context.replace("•", "\n•")
    context_candidates: List[str] = []
    for part in re.split(r"[\n\r]+", context_text):
        cleaned = part.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^[•\-\d\)\.\s]+", "", cleaned).strip()
        if not cleaned or len(cleaned) <= 8 or cleaned.endswith(":"):
            continue
        if not spec_keywords.intersection(_keywords(cleaned)):
            continue
        if re.search(r"\b(shall|must|provide|include|maintain|retain|withstand|occur)\b", cleaned.lower()):
            context_candidates.append(cleaned)
    context_candidates = _dedupe_preserve(context_candidates)
    if context_candidates:
        return context_candidates

    return [spec.strip()]
