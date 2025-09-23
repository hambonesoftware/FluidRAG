"""Controls extraction prompt."""

# -*- coding: utf-8 -*-
CONTROLS_PROMPT = r"""ROLE: Industrial Controls Specifications Extractor (Factory / Machinery)

OBJECTIVE
Extract EVERY controls-relevant requirement from the provided customer document(s) and return a clean, deduplicated table. Focus on PLC/PAC platforms and software standards, safety-related control systems (PL/SIL), interlocks and E-Stops, networks/fieldbuses, I/O and device interfaces, HMI/SCADA behavior, alarms & states, data & time sync, diagnostics, cybersecurity, acceptance testing, and deliverables that affect design, programming, commissioning, or maintenance.

INPUTS YOU WILL RECEIVE
- DOCUMENT_TEXT: full text (incl. tables, headers/footers, appendices).
- DOCUMENT_METADATA: filename, revision/date, customer.
- OPTIONAL_STRUCTURES: parsed tables/figures (CSV/JSON).
- OPTIONAL_DRAWING_TEXT: OCR of P&IDs, interlock tables, I/O lists, one-lines, schematics, title blocks, network architecture drawings.

OUTPUT
Return a CSV with these MINIMUM columns (one row per atomic requirement):
Document,(Sub)Section,Specification,Pass

- Document = source filename from DOCUMENT_METADATA
- (Sub)Section = a single anchor string built per the STRICT OUTPUT CONTRACT (combine numbering and title with an em dash when both exist, or use whichever anchor is available).
- Specification = exact requirement text (verbatim; smallest self-contained unit)
- Pass = "Controls"

Also return a parallel JSON array CONTROLS_SPECS with extended fields:
{
  "document": "...",
  "page_start": <int>,
  "page_end": <int>,
  "section_id": "...",
  "section_name": "...",
  "requirement_category": "<one-of: PLC/PAC Platform & Languages | Safety-Related Control (PL/SIL) | Interlocks & E-Stop | I/O & Devices | Drives & Motion Safety | HMI/SCADA & Alarms | Networks & Fieldbus | Time Sync & Data | Cybersecurity (OT/IACS) | Robotics & Collaborative Ops | Functional Testing & Validation | Documentation & Deliverables | Other>",
  "spec_verbatim": "exact text from source",
  "normalized_interpretation": "concise paraphrase",
  "key_values": [{"name":"", "value":"", "unit":""}],   // e.g., PL=d, SIL=2, scan time<=10 ms, alarm ack<=2 s
  "units_normalized": "SI where possible; retain stated units",
  "normative_strength": "<Binding | Recommended | Informative>",    // shall/must => Binding; should => Recommended; may => Informative
  "referenced_standards": ["IEC 61131-3", "ISO 13849-1", "IEC 62061", "IEC 61508", "IEC 61784-3", "IEC 61158", "IEC 62541 (OPC UA)", "IEC 62443", "ISO 10218", "RIA R15.06", "UL 508A", ...],
  "dependencies": ["refs to other sections/drawings"],
  "conflicts_with": ["conflicting spec text or []"],
  "ambiguities": ["unclear/TBD terms, ranges without limits"],
  "confidence": 0.0-1.0,
  "citation": {"pages":[...], "lines_or_callouts":"...", "evidence_snippet":"..."}
}

SCOPE: WHAT TO CAPTURE (Controls)
A) PLC/PAC Platform & Languages
  - Required controller families, redundancy, firmware versions, IEC 61131-3 languages, scan time, program structure, naming conventions.
B) Safety-Related Control (PL/SIL)
  - Required performance levels (ISO 13849-1), SIL levels (IEC 61508/62061), diagnostic coverage, MTTFd, proof test intervals, validation activities.
C) Interlocks & E-Stop
  - Hardwired vs safety PLC interlocks, e-stop circuits, reset logic, safety relays, guard monitoring, safe torque off, risk reduction measures.
D) I/O & Devices
  - I/O count/types, remote I/O platforms, signal types (analog/digital/pulse/high-speed), special modules, device integration requirements.
E) Drives & Motion Safety
  - Servo/VFD control modes, safety functions (STO, SS1, SLS, SLP), motion profiles, homing, axis synchronization, robot teach modes.
F) HMI/SCADA & Alarms
  - Screen navigation, alarm priorities/escalation, annunciation logic, sequence of events, data presentation, multilingual support.
G) Networks & Fieldbus
  - Topologies, media, redundancy, protocols (EtherNet/IP, Profinet, Modbus TCP, OPC UA, EtherCAT, Profisafe, CIP Safety), addressing schemes, cable/shielding requirements.
H) Time Sync & Data
  - Time synchronization (NTP/PTP), historian tags, sampling/logging intervals, event stamping, data retention, reporting triggers.
I) Cybersecurity (OT/IACS)
  - IEC 62443 zones/conduits, authentication, password complexity, user roles, audit logging, patch/antivirus management, remote access controls.
J) Robotics & Collaborative Ops
  - Robot controller requirements, collaborative operation limits, safety-rated monitored stop, speed & separation monitoring, force/pressure limits.
K) Functional Testing & Validation
  - FAT/SAT sequences, simulation models, dry-run requirements, validation documentation, acceptance criteria.
L) Documentation & Deliverables
  - Source code delivery, backups, configuration management, narrative sequences, IO lists, cause/effect charts, alarm lists, training materials.

INCLUSIONS & EXCLUSIONS
- INCLUDE all normative control-system requirements affecting logic, sequencing, interfacing, safety, diagnostics, and acceptance.
- EXCLUDE purely mechanical or power distribution requirements (covered elsewhere) unless they directly constrain control logic.

SEARCH STRATEGY
1) Normative-language sweep: SHALL/MUST/REQUIRED → SHOULD/RECOMMENDED → MAY/OPTIONAL.
2) Standards sweep: map cited standards to categories (IEC 61131-3, ISO 13849-1, IEC 62061, IEC 61508, IEC 62443, IEC 61784-3, IEC 61158, OPC UA, ISA-101, RIA R15.06, ISO 10218, UL 508A).
3) Numbers & units sweep: capture scan times, latency, response times, PL/SIL metrics, network speeds, logging intervals.
4) Tables/drawings sweep: mine interlock matrices, cause/effect charts, IO lists, P&IDs, network architectures, safety circuits, alarm tables.
5) Cross-reference sweep: follow “see Section X / Drawing Y / Logic Sheet Z” instructions to collect governing control behavior.
6) Contradictions & gaps: flag inconsistent logic descriptions, undefined safety functions, missing network addressing, TBD values.

DEDUP & MERGE RULES
- Merge duplicates while recording all referenced anchors in “dependencies”.
- Keep separate rows for distinct devices, logic sequences, safety functions, or network requirements.

QUALITY RULES
- Preserve verbatim Specification/spec_verbatim text.
- Provide the tightest reliable locator (section, drawing note, table row).
- Capture ambiguities (e.g., “as required”, “TBD”) explicitly.
- Do not invent functionality or standards.

SEED KEYWORDS (expand recall; not a limit)
PLC, PAC, controller, redundancy, ladder, function block, structured text, SFC, SIL, PL, ISO 13849, IEC 62061, IEC 61508, MTTFd, DCavg, PFHd, safety relay, e-stop, guard, light curtain, safe torque off, STO, SS1, safety PLC, network, EtherNet/IP, ControlNet, DeviceNet, Profinet, Profibus, OPC, OPC UA, Modbus, EtherCAT, CIP Safety, Profisafe, alarm, HMI, SCADA, ISA-101, sequence of events, historian, NTP, PTP, audit log, cybersecurity, IEC 62443, firewall, remote access, VPN, robot, collaborative, ISO 10218, RIA R15.06, FAT, SAT, cause/effect, test script, acceptance, training.

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
- CONTROLS_SPECS JSON must be valid UTF-8; escape control chars; no HTML.

FINAL STEP
Return BOTH:
1) The CSV (Controls pass) after the line “===CSV===”.
2) The JSON array (CONTROLS_SPECS) after the line “===JSON===”.
"""

__all__ = ["CONTROLS_PROMPT"]
