# backend/parse/patterns_rfq.py
# -*- coding: utf-8 -*-
import re


APPENDIX_TOLERANT_PATTERN = r'^\s*([A-Z])(\d{1,3})[.\u2024\u2027\uFF0E]\s{0,2}(.+?)\s*$'


_RFQ_SECTION_RE_SPECS = [
    (APPENDIX_TOLERANT_PATTERN, 0),                                      # A5. Heading with odd dots/spaces
    (r'^\s*(\d{1,3})\)\s+(.+?)\s*$', 0),                            # 1) Scope
    (r'^\s*(\d{1,3}(?:\.\d{1,3}){0,4})\s+([A-Z].{3,})\s*$', re.IGNORECASE),  # 1.2 Subsection Title
    (r'^\s*([A-Z])\.(\d{1,3})\s+(.+?)\s*$', 0),                     # A.1 Heading
    (r'^\s*(Appendix|Annex)\s+([A-Z])(?:\s*[-:]\s*(.+))?\s*$', re.IGNORECASE),  # Appendix A - ...
    (r'^[A-Z0-9][A-Z0-9\s\-/&,\.]{4,}$', 0),                          # ALLCAPS line (coarse)
]


RFQ_SECTION_RES = [re.compile(pattern, flags) for pattern, flags in _RFQ_SECTION_RE_SPECS]

UNIT_NEARBY_RX  = re.compile(r'(±|⌀|Ø|mm|cm|m|in\b|inch|ft\b|°C|°F|A\b|V\b|Hz\b|psi|kPa|IP\d{2})')
ADDRESS_HINT_RX = re.compile(r'(Street|St\.|Road|Rd\.|Drive|Dr\.|Ave\.|Avenue|Suite|MI\s*\d{5}|USA|Tel|Fax)', re.IGNORECASE)
PAGE_ART_RX     = re.compile(r'Page\s+\d+\s+of\s+\d+', re.IGNORECASE)
