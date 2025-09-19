import asyncio
import json
import logging
from typing import List, Dict, Any, Tuple

from .llm import BaseLLMClient, LLMAuthError
from .preprocess import approximate_tokens
from ..prompts import PASS_PROMPTS

log = logging.getLogger("FluidRAG.passes")

PASS_KEYWORDS = {
    "Mechanical": [
        "material", "dimension", "torque", "pressure", "flow", "tolerance", "fastener",
        "ip", "nema", "mount", "weight", "temperature", "lubrication", "bearing"
    ],
    "Electrical": [
        "voltage", "current", "power", "phase", "frequency", "breaker", "fuse",
        "wire", "ground", "emc", "ul", "ce", "panel", "circuit"
    ],
    "Controls": [
        "plc", "pac", "i/o", "sensor", "actuator", "protocol", "safety", "relay",
        "interlock", "hmi", "logic", "alarm", "sequence"
    ],
    "Software": [
        "software", "code", "language", "version", "library", "os", "endpoint", "database",
        "logging", "cyber", "backup", "testing", "validation"
    ],
    "Project Management": [
        "deliverable", "milestone", "approval", "documentation", "training", "fat",
        "sat", "warranty", "responsibility", "schedule", "change", "review"
    ]
}


def _score_chunk(chunk: Dict[str, Any], pass_name: str) -> Tuple[float, int]:
    text_lower = chunk["text"].lower()
    score = 0.0
    for kw in PASS_KEYWORDS.get(pass_name, []):
        if kw in text_lower:
            score += 1.0
    score += float(chunk.get("meta", {}).get("hep_entropy", 0.0)) * 0.1
    tokens = approximate_tokens(chunk["text"])
    return score, tokens


def _select_chunks_for_pass(chunks: List[Dict[str, Any]], pass_name: str, max_tokens: int) -> List[Dict[str, Any]]:
    scored = []
    for ch in chunks:
        score, tokens = _score_chunk(ch, pass_name)
        scored.append((score, tokens, ch))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected: List[Dict[str, Any]] = []
    budget = 0
    for score, tokens, ch in scored:
        if selected and budget + tokens > max_tokens:
            continue
        selected.append(ch)
        budget += tokens
    if not selected and scored:
        selected = [scored[0][2]]
    log.debug("[passes] %s selected %s chunks (budget=%s tokens)", pass_name, len(selected), budget)
    return selected


async def _extract_for_pass(client: BaseLLMClient, model: str, chunk: Dict[str, Any], pass_name: str):
    system = (
        f"You are analyzing a technical specification for the '{pass_name}' domain. "
        f"Return ONLY a JSON array of exact quotations from the provided text."
    )
    user = PASS_PROMPTS[pass_name] + "\n\nTEXT:\n" + chunk["text"]
    try:
        content = await client.acomplete(model=model, system=system, user=user, temperature=0.0, max_tokens=800)
        specs = json.loads(content) if content.strip().startswith("[") else []
        out = []
        for s in specs:
            if isinstance(s, str):
                s2 = s.strip()
                if s2 and s2 not in out:
                    out.append(s2)
        return out
    except LLMAuthError as exc:
        log.error("[passes] Authorization failure for %s pass: %s", pass_name, exc)
        raise
    except Exception:
        log.exception(f"[passes] LLM extraction failed for {pass_name} chunk")
        return []


async def run_all_passes_async(chunks: List[Dict[str, Any]], client: BaseLLMClient, model: str, max_tokens: int = 120_000):
    """Run Mechanical/Electrical/Controls/Software/PM passes asynchronously over filtered chunks."""
    pass_names = list(PASS_PROMPTS.keys())
    tasks = []
    job_meta = []
    for pn in pass_names:
        selected = _select_chunks_for_pass(chunks, pn, max_tokens)
        for ch in selected:
            tasks.append(_extract_for_pass(client, model, ch, pn))
            job_meta.append((pn, ch))
    log.debug(f"[passes] launching {len(tasks)} async LLM extractions")
    results = await asyncio.gather(*tasks)

    rows = []
    for (pn, ch), specs in zip(job_meta, results):
        for spec in specs:
            rows.append({
                "document": ch["document"],
                "section_number": ch["section_number"],
                "section_name": ch["section_name"],
                "specification": spec,
                "pass": pn
            })
    log.debug(f"[passes] extracted rows={len(rows)}")
    return rows
