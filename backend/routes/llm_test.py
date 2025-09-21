# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
import time
from flask import Blueprint, request, jsonify, make_response

from ..llm.factory import create_llm_client
from ..utils.strings import s


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

        client = create_llm_client(provider)

        t0 = time.time()

        # Since Flask view is sync, run the async chat in a short-lived loop
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                asyncio.wait_for(
                    client.acomplete(
                        model=model,
                        system="You are a simple health-check. Reply with a short acknowledgement.",
                        user=message,
                        temperature=0.0,
                        max_tokens=128,
                        extra={"stream": False},
                    ),
                    timeout=45.0,
                )
            )
        finally:
            loop.close()

        dt_ms = int((time.time() - t0) * 1000)

        text = result if isinstance(result, str) else str(result)

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
