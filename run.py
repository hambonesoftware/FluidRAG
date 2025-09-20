
import os
import sys
import threading
import time
import webbrowser
import socket

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
    
from dotenv import load_dotenv, find_dotenv
dotenv_path = find_dotenv(usecwd=True)
loaded = load_dotenv(dotenv_path, override=False)

import os, logging
k = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
mask = (k[:12] + "..." + k[-4:]) if k else "(missing)"
print(f"[dotenv] loaded={loaded} path={dotenv_path!r} OPENROUTER_API_KEY={bool(k)} {mask}")


# Respect PORT from .env (or default 5142)
PORT = int(os.environ.get("PORT", "5142"))
HOST = "127.0.0.1"
URL = f"http://{HOST}:{PORT}/"

def _wait_and_open():
    """Poll the port until the server is accepting connections, then open browser."""
    for _ in range(120):  # up to ~60s (0.5s * 120)
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                try:
                    webbrowser.open(URL)
                except Exception:
                    pass
                return
        except OSError:
            time.sleep(0.5)

def main():
    # Import here so Flask app doesn't start before we attach the opener thread.
    from backend.app import app

    print(f"[RUN] FluidRAG — starting Flask backend on {URL}")
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("[RUN][WARN] OPENROUTER_API_KEY is not set. The backend will return mock [] outputs.")
        print("             Edit .env or set the environment variable to enable real extraction via OpenRouter.\n")

    t = threading.Thread(target=_wait_and_open, daemon=True)
    t.start()

    # Start Flask (serves the ESM frontend from /frontend)
    # use_reloader=False to avoid double-start when launched via a script.
    app.run(host=HOST, port=PORT, debug=True, use_reloader=False)

if __name__ == "__main__":
    main()
