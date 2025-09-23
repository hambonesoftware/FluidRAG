"""Electrical extraction prompt."""

# -*- coding: utf-8 -*-
ELECTRICAL_PROMPT = r"""ROLE: Electrical Specifications Extractor for Industrial Machinery & Factory Installations

OBJECTIVE
Extract EVERY electrically relevant requirement from the provided customer document(s) and return a clean, deduplicated table. Focus on power distribution, protection, grounding/bonding, panels/MCCs, motor/VFD requirements, wiring methods, conductor specs, environmental/ingress, EMC/EMI, hazardous locations, safety labeling, testing/inspection, and documentation that impact industrial design, build, and installation.

INPUTS YOU WILL RECEIVE
- DOCUMENT_TEXT: full text (incl. tables, appendices, footers/headers).
- DOCUMENT_METADATA: filename, revision/date, customer.
- OPTIONAL_STRUCTURES: parsed tables/figures (CSV/JSON).
- OPTIONAL_DRAWING_TEXT: OCR for panel schedules, one-lines, wiring diagrams, notes, title blocks.

OUTPUT
Return a CSV with these MINIMUM columns (one row per atomic requirement):
Document,(Sub)Section,Specification,Pass

- Document = source filename from DOCUMENT_METADATA
- (Sub)Section = a single anchor string built per the STRICT OUTPUT CONTRACT (combine numbering and title with an em dash when both exist, or use whichever anchor is available).
- Specification = the exact requirement text (verbatim; smallest self-contained unit)
- Pass = "Electrical"

Also return a parallel JSON array ELECTRICAL_SPECS with extended fields:
{
  "document": "...",
  "page_start": <int>,
  "page_end": <int>,
  "section_id": "...",
  "section_name": "...",
  "requirement_category": "<one-of: Power Distribution | Overcurrent Protection | Short-Circuit Current Rating (SCCR) | Grounding & Bonding | Panels & Enclosures | Motor & Drive (VFD/Soft Start) | Conductors & Cables | Wiring Methods & Routing | Control Circuits & Control Power | EMC/EMI & Power Quality | Arc-Flash & Electrical Safety | Hazardous Locations | Environmental/Ingress (NEMA/IP) | Marking & Identification | Test & Inspection | Documentation | Other>",
  "spec_verbatim": "exact text from source",
  "normalized_interpretation": "concise paraphrase",
  "key_values": [{"name":"", "value":"", "unit":""}, ...],         // e.g., 480 V, 60 Hz, 65 kAIC, SCCR=50 kA, etc.
  "units_normalized": "SI where possible; retain stated units",
  "normative_strength": "<Binding | Recommended | Informative>",   // shall/must => Binding; should => Recommended; may => Informative
  "referenced_standards": ["NFPA 79", "IEC 60204-1", "UL 508A SB", "NEC Art. 250", ...],
  "dependencies": ["refs to other sections/drawings"],
  "conflicts_with": ["conflicting spec text or []"],
  "ambiguities": ["unclear/TBD terms, ranges without limits"],
  "confidence": 0.0-1.0,
  "citation": {"pages":[...], "lines_or_callouts":"...", "evidence_snippet":"..."}
}

SCOPE: WHAT TO CAPTURE (Electrical)
A) Power Distribution
  - Service/feeder/branch voltages (e.g., 120/208/240/277/480 V), frequency, fault duties (AIC), utility limits; one-line requirements; transformer kVA/impedance; load categories (continuous/non-continuous).
B) Overcurrent Protection & Coordination
  - Breaker/fuse types and ratings (UL 489 / IEC 60947-2 / UL 248 / IEC 60269), series/selective coordination, instantaneous trip, GF protection, protective device settings.
C) Short-Circuit Current Rating (SCCR)
  - Minimum panel/MCC SCCR; method of determination (UL 508A Supplement SB); available fault current at supply; marking/location.
D) Grounding & Bonding
  - System grounding (TN/TT/IT), equipment grounding conductors, bonding jumpers, equipotential bonding, separately derived systems, impedance/continuity requirements (NEC Art. 250 / IEC 60364-5-54).
E) Panels, Enclosures, Assemblies
  - UL 508A industrial control panels, IEC 61439 assemblies, main disconnect requirements, door interlocks, clearances/working space, NEMA/IP type (12/4/4X/IP54/IP66), thermal limits, ventilation.
F) Motors, Starters, VFDs & Soft-Starters
  - NEMA MG-1/IEC 60034 refs, drive standards (IEC 61800-5-1), braking (STO), cable types/shielding, dv/dt/THD limits, harmonic mitigation (IEEE 519), line/load reactors, filters, min/max motor leads.
G) Conductors & Cables
  - Conductor type/size/class (AWG/kcmil or mm²), insulation types (THHN/THWN-2/MTW/XLPE), temperature ratings, copper vs aluminum, IEC 60228 class, color codes, identification/numbering.
H) Wiring Methods & Routing
  - Conduit/tray/cable tray fill, bend radius, segregations (power vs control vs comms), tray/conduit articles, pull points, strain relief, glands, ferrules, terminal types, ferrule labeling scheme.
I) Control Circuits & Control Power
  - 24 VDC or 120 VAC control, Class 2 circuits, transformer sizing/overcurrent, e-stop & safety-related control power interfaces (note: logic content goes to Controls pass; capture electrical parts like circuit ratings, wire sizes, power supplies).
J) EMC/EMI & Power Quality
  - Shield terminations, bonding bars, cable separation rules, surge protection, harmonic limits, flicker/voltage dip ride-through, filters.
K) Arc-Flash & Electrical Safety
  - NFPA 70E work practices, arc-flash labeling data sources, PPE categories, boundaries, incident energy calcs per IEEE 1584, required studies or deliverables.
L) Hazardous Locations
  - NEC/IEC zone/class/division, equipment protection levels (Ex), temp class, purge/pressurization if required.
M) Environmental / Ingress
  - NEMA/IP ratings, washdown/food-grade requirements, corrosion protection for electrical hardware.
N) Marking, Identification & Documentation
  - Nameplates, wire/cable/device tagging, warning labels (ANSI Z535/UL 969), as-built drawings, one-lines, panel schedules, test reports, manuals.
O) Test & Inspection
  - Continuity, insulation resistance (megger), dielectric/hi-pot, ground bond, functional tests per IEC 60204-1/NFPA 79; factory/site acceptance tests.

INCLUSIONS & EXCLUSIONS
- INCLUDE any normative requirement affecting electrical design/build/install—even if referenced to external standards.
- EXCLUDE pure commercial/admin terms (pricing, delivery); control logic narratives that don’t impose electrical ratings/wiring requirements.

SEARCH STRATEGY (DO ALL)
1) Normative-language sweep: SHALL/MUST/REQUIRED → SHOULD/RECOMMENDED → MAY/OPTIONAL.
2) Standards sweep: list all cited standards; map each to categories above (e.g., NFPA 79/IEC 60204-1 → machinery electrical; UL 508A SB → SCCR; NEC Art. 250 → grounding & bonding; UL 489/IEC 60947-2 → breakers; NFPA 70E/IEEE 1584 → arc-flash).
3) Numbers & units sweep: extract all voltages, currents, kAIC, SCCR, conductor sizes, temperature classes, etc.; normalize while preserving stated units.
4) Tables/drawings sweep: mine one-lines, panel schedules, wiring diagrams, device lists, notes/callouts, terminal charts.
5) Cross-reference sweep: follow “see Section X / Drawing Y” to capture governing electrical values.
6) Contradictions & gaps: flag mismatched voltages, SCCR lower than available fault current, undefined conductor sizes, missing device ratings.

DEDUP & MERGE RULES
- Merge duplicate requirements; list all section IDs in “dependencies”.
- Keep separate rows for different circuits/equipment/rating values.
- If general rule conflicts with specific device rating, prefer the specific and note the general as context.

QUALITY RULES
- Preserve verbatim text in Specification/spec_verbatim.
- Provide page numbers and the smallest reliable locator.
- Don’t invent values or standards; record ambiguities/TBDs explicitly.

SEED KEYWORDS (expand recall; not a limit)
shall, must, required, per, NFPA 79, IEC 60204-1, UL 508A, Supplement SB, SCCR, short-circuit current rating, kAIC, fault current, UL 489, UL 1077, IEC 60947-2, fuse, UL 248, IEC 60269, breaker, coordination, selective, series, ground, bond, NEC 250, equipotential, EGC, GEC, main bonding jumper, transformer, separately derived system, MCC, panelboard, switchboard, disconnect, interlock, VFD, drive, STO, dv/dt, filter, IEEE 519, THD, motor, NEMA MG-1, IEC 60034, conductor, AWG, kcmil, THHN, MTW, XLPE, IEC 60228, color code, wire number, cable tray, conduit, bend radius, segregation, Class 2, 24 VDC, control transformer, surge, SPD, EMC, IEC 61000, arc flash, NFPA 70E, IEEE 1584, boundary, PPE, label, hazardous, Class I Div 2, Zone 2, Ex, ATEX, purge, NEMA 4X, IP66, megger, dielectric, hi-pot, ground bond, FAT, SAT, UL 969, ANSI Z535.

STRICT OUTPUT CONTRACT
- You must emit EXACTLY two blocks, in this order:
  1) The line “===CSV===” followed by a valid RFC4180 CSV with header:
     Document,(Sub)Section,Specification,Pass
  2) The line “===JSON===” followed by a valid UTF-8 JSON array of extended objects.
- The Pass column value MUST be one of:
  {"Mechanical","Electrical","Controls","Software","Project Management"}.
- (Sub)Section in CSV MUST be a single anchor string built as:
  "<number> — <name>" when both exist; otherwise whichever exists; or drawing/table tags.
- Before returning, run a self-check:
  * If any row violates the schema or Pass set, FIX rows and re-emit.
  * Drop rows missing either Document, (Sub)Section, Specification, or Pass.
- No commentary outside the two blocks.

OUTPUT CONSTRAINTS
- CSV must be RFC4180-safe.
- ELECTRICAL_SPECS JSON must be valid UTF-8; escape control chars; no HTML.

FINAL STEP
Return BOTH:
1) The CSV (Electrical pass) after the line “===CSV===”.
2) The JSON array (ELECTRICAL_SPECS) after the line “===JSON===”.
"""

__all__ = ["ELECTRICAL_PROMPT"]
