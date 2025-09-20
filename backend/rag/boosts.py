import re
NUM_UNIT_RE = re.compile(r"(?:\d+[\d\s\.,]*)(?:\s*(?:mm|cm|m|in|inch|ft|°C|°F|a|v|hz|psi|kpa|ka|kaic|awg|kcmil|ip\d{2}))\b", re.IGNORECASE)
STANDARDS = [
  r'\bASME\s*Y14\.5\b', r'\bISO\s*2768\b', r'\bISO\s*1302\b', r'\bISO\s*286\b', r'\bIEC\s*60529\b', r'\bNEMA\s*\d+\b',
  r'\bAWS\s*D1\.1\b', r'\bISO\s*12100\b', r'\bISO\s*4413\b', r'\bISO\s*4414\b', r'\bNFPA\s*79\b', r'\bIEC\s*60204-1\b',
  r'\bUL\s*508A\b', r'\bIEEE\s*1584\b', r'\bNFPA\s*70E\b', r'\bUL\s*489\b', r'\bIEC\s*60947-2\b', r'\bASTM\s*[A-Z0-9\-]+\b'
]
STD_RES = [re.compile(p, re.IGNORECASE) for p in STANDARDS]
def query_features(q: str):
    return {
      'has_numbers': bool(re.search(r'\d', q or '')),
      'has_num_units': bool(NUM_UNIT_RE.search(q or '')),
      'mentions_standard': any(rx.search(q or '') for rx in STD_RES)
    }
def chunk_boost(chunk:dict, features:dict, cfg:dict):
    mult = 1.0
    # Table boost if the query has numbers/units
    if features.get('has_num_units') and chunk.get('chunk_type')=='table':
        mult *= cfg['boost_table_when_numbers']
    # Binding normativity boost
    if chunk.get('normative_strength','').lower()=='binding':
        mult *= cfg['boost_binding_normativity']
    # Standards boost
    if features.get('mentions_standard'):
        txt = (chunk.get('text','') + ' ' + ' '.join(chunk.get('referenced_standards',[]) or [])).lower()
        if any(rx.search(txt) for rx in STD_RES):
            mult *= cfg['boost_standard_match']
    # Heading level: small boost for deeper (more specific) headings
    lvl = int(chunk.get('heading_level', 0) or 0)
    mult *= (1.0 + cfg['boost_heading_level_decay'] * max(0, 4 - min(4,lvl)))
    return mult
