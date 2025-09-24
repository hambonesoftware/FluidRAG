"""Prompt constants used by the RAG v2 orchestrator."""

EXTRACT_PROMPT = """You extract technical specs from standards and project docs.
Use ONLY the provided passages. Every field MUST include a cite = passage_id.

Buckets:
[Standards]: authoritative clauses (ISO/NFPA/RIA/OSHA) with {standard, year, clause}.
[ProjectSpec]: RFQ/spec requirements, thresholds, acceptance criteria.
[Risk]: notes, exceptions, options.

Task: Fill this JSON exactly:
{"requirements":[],"thresholds":[],"units":[],"standards":[],"exceptions":[],"acceptance_criteria":[]}

Rules:
- Quote numbers/units exactly from a passage; you may paraphrase surrounding text.
- Keep dual-units if present (e.g., "18 in (457 mm)").
- If edition or clause is ambiguous, add to "exceptions" and set "edition_ambiguous": true.
- If a field lacks evidence, do not guess; leave it out and add the field name to a top-level "missing":[...] array.
Return ONLY the final JSON."""

VERIFY_PROMPT = """You verify an extracted JSON against the provided passages.
List fields lacking a directly supporting span or with mismatched numbers/units.
Propose the MINIMAL follow-up query to fix each gap.

Return:
{"missing_fields":[...], "followups":[ "...", "..." ], "weak_citations":[{"field":"...","reason":"..."}]}"""

EDITION_ARBITER_PROMPT = """Multiple editions appear. Decide the governing edition using policy:
- Prefer the latest edition unless a specific edition is pinned in [ProjectSpec].
Return JSON:
{"governing":{"NFPA 79":"2024", ...}, "reasons":[ "...", "..." ]}"""
