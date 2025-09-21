# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import logging
import asyncio
from flask import Blueprint, request, jsonify, make_response

from ..pipeline.llm import create_llm_client
from ..utils.envsafe import s

log = logging.getLogger("FluidRAG.api.llm_test")

bp = Blueprint("llm_test", __name__)

@bp.route("/api/llm-test", methods=["POST", "OPTIONS"])
def llm_test():
    # --- CORS preflight ---
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return resp

    try:
        payload = request.get_json(force=True) or {}
        provider = s(payload.get("provider")) or "openrouter"
        model = s(payload.get("model")) or "x-ai/grok-4-fast:free"
        message = s(payload.get("message")) or "ping"

        # Instantiate LLM client (provider currently unused; extend if you add more backends)
        client = create_llm_client(model=model)

        messages = [
            {"role": "system", "content": "You are a simple health-check. Reply with a short acknowledgement."},
            {"role": "user", "content": message},
        ]

        t0 = time.time()

        # Since Flask view is sync, run the async chat in a short-lived loop
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                client.chat(messages, temperature=0.0, max_tokens=32)
            )
        finally:
            loop.close()

        dt_ms = int((time.time() - t0) * 1000)

        # Try to normalize the response content
        text = ""
        if isinstance(result, dict):
            text = result.get("text") or result.get("data") or result.get("content") or ""
        if not isinstance(text, str):
            text = str(text)

        resp = jsonify({
            "ok": True,
            "httpStatus": 200,
            "provider": provider,
            "model": model,
            "latency_ms": dt_ms,
            "echo": message,
            "reply": text.strip(),
        })
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp, 200

    except Exception as e:
        log.exception("LLM test failed: %s", e)
        return jsonify({"ok": False, "httpStatus": 500, "error": str(e)}), 500
