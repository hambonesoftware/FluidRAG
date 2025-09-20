import json
import os
from typing import Optional, Sequence, Tuple

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_REFERER = "http://localhost:5142"
DEFAULT_APP_TITLE = "FluidRAG"
LLAMACPP_DEFAULT_URL = "http://localhost:8080/v1/chat/completions"

def env_first(*keys: str, default: Optional[str] = None) -> Optional[str]:
    for k in keys:
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return default

def log_prompt(messages) -> str:
    return "\n\n".join(f"{m['role']}: {str(m['content']).strip()}" for m in messages)

def windows_curl(url: str, headers: Sequence[Tuple[str, str]], payload: dict) -> str:
    lines = [f"curl.exe -sS {url} ^"]
    for k, v in headers:
        esc = str(v).replace('"', '\"')
        lines.append(f'  -H "{k}: {esc}" ^')
    import json as _json
    json_payload = _json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    esc_payload = json_payload.replace('"', '\"')
    lines.append(f'  -d "{esc_payload}"')
    return "\n".join(lines)
