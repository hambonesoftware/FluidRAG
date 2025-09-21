# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import logging

import uuid

from flask import Blueprint, request, jsonify, make_response

from ..pipeline.passes import run_all_passes_async
from ..utils.envsafe import env
from ..utils.strings import s

log = logging.getLogger("FluidRAG.api.process")

bp = Blueprint("process", __name__)

@bp.route("/api/process", methods=["POST", "OPTIONS"])
def process_route():
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return resp

    try:
        data = request.get_json(force=True) or {}
        try:
            payload_repr = json.dumps(data, ensure_ascii=False)
        except TypeError:
            payload_repr = repr(data)
        log.info("[/api/process] payload=%s", payload_repr)
        log.info("ENV OPENROUTER_API_KEY set: %s", bool(env("OPENROUTER_API_KEY")))
        log.info("ENV OPENROUTER_HTTP_REFERER=%r", env("OPENROUTER_HTTP_REFERER") or None)
        log.info("ENV OPENROUTER_SITE_URL=%r", env("OPENROUTER_SITE_URL") or None)
        log.info("ENV OPENROUTER_APP_TITLE=%r", env("OPENROUTER_APP_TITLE") or None)

        req_id = uuid.uuid4().hex[:8]
        data.setdefault("_req_id", req_id)
        data.setdefault("_debug", bool(data.get("debug")))
        data.setdefault("_debug_llm_io", bool(data.get("debug_llm_io")))
        data.setdefault("_only_mechanical", bool(data.get("only_mechanical")))

        if "provider" in data:
            data["provider"] = s(data.get("provider"))
        if "model" in data:
            data["model"] = s(data.get("model"))

        import asyncio
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            out = loop.run_until_complete(run_all_passes_async(data))
        finally:
            asyncio.set_event_loop(None)
            loop.close()

        status = 200 if out.get("ok", False) else out.get("httpStatus", 500)
        if "httpStatus" not in out:
            out["httpStatus"] = status

        response = jsonify(out)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response, status

    except Exception as e:
        return jsonify({"ok": False, "httpStatus": 500, "error": str(e)}), 500
