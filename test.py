# or_probe.py
import os, json, time, uuid, httpx
# put at the very top of your entry script
from dotenv import load_dotenv, find_dotenv
dotenv_path = find_dotenv(usecwd=True)  # searches from CWD upward
loaded = load_dotenv(dotenv_path, override=False)
print(f"[dotenv] loaded={loaded} path={dotenv_path!r}")

API_BASE = "https://openrouter.ai/api/v1"
CHAT_URL = f"{API_BASE}/chat/completions"
MODELS_URL = f"{API_BASE}/models"

# === configurable bits ===
MODEL = os.environ.get("OPENROUTER_DEFAULT_MODEL", "openrouter/auto")  # safe default router
REFERER = os.environ.get("OPENROUTER_HTTP_REFERER") or os.environ.get("OPENROUTER_SITE_URL") or "http://localhost:5142"
APP_TITLE = os.environ.get("OPENROUTER_APP_TITLE", "FluidRAG")
API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
TIMEOUT = httpx.Timeout(60.0, connect=20.0)
CID = uuid.uuid4().hex[:8]  # correlation id

def mask(k):  # mask API key
    if not k: return "(missing)"
    return k[:10] + "..." + k[-4:]

def curl(url, headers, payload=None):
    parts = [f'curl -sS "{url}"']
    for k, v in headers.items():
        val = v if k.lower() != "authorization" else "Bearer ***"
        parts.append(f'-H "{k}: {val}"')
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        parts.append(f"--data '{body}'")
    return " \\\n  ".join(parts)

def dump(title, obj):
    print(f"\n=== {title} (cid={CID}) ===")
    if isinstance(obj, (dict, list)):
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    else:
        print(obj)

def main():
    # 0) Preflight
    if not API_KEY:
        print("ERROR: OPENROUTER_API_KEY is not set.")
        return

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": REFERER,   # optional but recommended for attribution
        "X-Title": APP_TITLE,      # optional but recommended
    }

    # A) List models to confirm catalog access (and catch obvious auth issues)
    dump("GET /models headers", {**headers, "Authorization": f"Bearer {mask(API_KEY)}"})
    dump("GET /models curl", curl(MODELS_URL, headers))
    t0 = time.time()
    with httpx.Client(timeout=TIMEOUT) as s:
        r = s.get(MODELS_URL, headers=headers)
        dt = round((time.time() - t0) * 1000, 1)
        dump(f"/models → {r.status_code} in {dt}ms", r.json() if "application/json" in r.headers.get("content-type","") else r.text)
        r.raise_for_status()
        model_ids = [m.get("id") for m in r.json().get("data", []) if m.get("id")]
        if MODEL not in model_ids:
            print(f"\nNOTE: Selected MODEL='{MODEL}' not present; switching to first available.")
            if not model_ids:
                print("ERROR: No models returned for this key. Check account/credits.")
                return
            model = model_ids[0]
        else:
            model = MODEL

    # B) Minimal chat to a known-good model (default: openrouter/auto)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a connectivity probe."},
            {"role": "user", "content": "Return exactly: {\"ok\":true}"},
        ],
        "max_tokens": 16,
        "temperature": 0.0,
    }

    dump("POST /chat headers", {**headers, "Authorization": f"Bearer {mask(API_KEY)}"})
    dump("POST /chat payload", payload)
    dump("POST /chat curl", curl(CHAT_URL, headers, payload))

    with httpx.Client(timeout=TIMEOUT, http2=True) as s:
        t1 = time.time()
        r = s.post(CHAT_URL, headers=headers, json=payload)
        dt = round((time.time() - t1) * 1000, 1)
        body = None
        try:
            body = r.json()
        except Exception:
            pass
        resp_meta = {
            "status": r.status_code,
            "elapsed_ms": dt,
            "body_meta": {
                "id": body.get("id") if isinstance(body, dict) else None,
                "model": body.get("model") if isinstance(body, dict) else None,
                "usage": body.get("usage") if isinstance(body, dict) else None,
            } if body else None,
            "content_preview": (body.get("choices",[{}])[0].get("message",{}).get("content","")[:200] if isinstance(body, dict) else None),
        }
        dump("POST /chat response meta", resp_meta)
        dump("POST /chat raw body", body if body is not None else r.text)
        r.raise_for_status()

        # Parse the content
        content = body.get("choices",[{}])[0].get("message",{}).get("content","")
        print("\n=== RESULT ===")
        print(content)

if __name__ == "__main__":
    main()
