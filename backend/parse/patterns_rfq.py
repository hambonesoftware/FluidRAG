# backend/parse/patterns_rfq.py
# -*- coding: utf-8 -*-
import re

RFQ_SECTION_RES = [re.compile(p, re.IGNORECASE) for p in [
    r'^\s*(\d{1,3})\)\s+(.+?)\s*$',                                 # 1) Scope
    r'^\s*(\d{1,3}(?:\.\d{1,3}){0,4})\s+([A-Z].{3,})\s*$',          # 1.2 Subsection Title
    r'^\s*([A-Z])\.(\d{1,3})\s+(.+?)\s*$',                          # A.1 Heading
    r'^\s*(Appendix|Annex)\s+([A-Z])(?:\s*[-:]\s*(.+))?\s*$',       # Appendix A - ...
    r'^[A-Z0-9][A-Z0-9\s\-/&,\.]{4,}$'                              # ALLCAPS line (coarse)
]]

UNIT_NEARBY_RX  = re.compile(r'(±|⌀|Ø|mm|cm|m|in\b|inch|ft\b|°C|°F|A\b|V\b|Hz\b|psi|kPa|IP\d{2})')
ADDRESS_HINT_RX = re.compile(r'(Street|St\.|Road|Rd\.|Drive|Dr\.|Ave\.|Avenue|Suite|MI\s*\d{5}|USA|Tel|Fax)', re.IGNORECASE)
PAGE_ART_RX     = re.compile(r'Page\s+\d+\s+of\s+\d+', re.IGNORECASE)
