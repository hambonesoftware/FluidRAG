# Central prompt library for FluidRAG

HEADER_DETECTION_SYSTEM = """You are a precise technical assistant. Given a document excerpt,
identify logical section and subsection headings of the form "1", "1.1", "2.3.4", etc. and their titles.
Return a compact JSON array where each item is:
{"section_number": "...", "section_name": "..."}.
Do not include any other commentary."""

# Per-pass extraction prompts. Each prompt should return a JSON array of strings,
# each string being an exact quotation from the input text that matches the pass criteria.
PASS_PROMPTS = {
    "Mechanical": """Extract exact sentences/clauses that describe mechanical specifications:
materials, dimensions, torque, pressure, flow, mechanical tolerances, fasteners, IP/NEMA ratings,
mounting, weight, temperature limits, lubrication, bearings, moving parts. Return JSON array of strings only.""",
    "Electrical": """Extract exact sentences/clauses that describe electrical specifications:
voltage, current, power, phase, frequency, protection (fuse/breaker), wire gauge, control voltage,
enclosure, grounding, EMC, UL/CE, panel specs. Return JSON array of strings only.""",
    "Controls": """Extract exact sentences/clauses that describe controls specifications:
PLCs, PACs, I/O, sensors/actuators, network protocols, safety relays, interlocks, HMI,
control logic, alarms, sequence of operations. Return JSON array of strings only.""",
    "Software": """Extract exact sentences/clauses that describe software specifications:
programming languages, versions, libraries, OS requirements, network endpoints, databases,
logging, cybersecurity, backups, testing/validation. Return JSON array of strings only.""",
    "Project Management": """Extract exact sentences/clauses that describe project management specifications:
deliverables, milestones, approvals, documentation, training, FAT/SAT, warranty,
roles/responsibilities, change management, schedule. Return JSON array of strings only."""
}
