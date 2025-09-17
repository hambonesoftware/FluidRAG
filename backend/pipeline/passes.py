import asyncio
import json
import logging
from typing import List, Dict, Any

from .llm import OpenRouterClient
from ..prompts import PASS_PROMPTS

log = logging.getLogger("FluidRAG.passes")

async def _extract_for_pass(client: OpenRouterClient, model: str, chunk: Dict[str, Any], pass_name: str):
    system = f"You are analyzing a technical specification for the '{pass_name}' domain. "              f"Return ONLY a JSON array of exact quotations from the provided text."
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
    except Exception as e:
        log.exception(f"[passes] LLM extraction failed for {pass_name} chunk")
        return []

async def run_all_passes_async(chunks: List[Dict[str, Any]], client: OpenRouterClient, model: str):
    """Run Mechanical/Electrical/Controls/Software/PM passes asynchronously over chunks."""
    pass_names = list(PASS_PROMPTS.keys())
    tasks = []
    for ch in chunks:
        for pn in pass_names:
            tasks.append(_extract_for_pass(client, model, ch, pn))

    log.debug(f"[passes] launching {len(tasks)} async LLM extractions")
    results = await asyncio.gather(*tasks)

    rows = []
    idx = 0
    for ch in chunks:
        for pn in pass_names:
            specs = results[idx]
            idx += 1
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
