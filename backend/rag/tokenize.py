import re
TOKEN_RE = re.compile(r"[A-Za-z0-9_\-/\.]+|[A-Za-z]+|\d+", re.UNICODE)
STOP = set('the a an and or of in for to from on by with as at is are be this that it its if then else shall must should may per per'.split())
def tokenize(text: str):
    return [t.lower() for t in TOKEN_RE.findall(text or '') if t and t.lower() not in STOP]
