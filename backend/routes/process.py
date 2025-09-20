# -*- coding: utf-8 -*-
from __future__ import annotations
from flask import Blueprint, request, jsonify, make_response

from ..pipeline.passes import run_all_passes_async

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
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            out = loop.run_until_complete(run_all_passes_async(data))
        finally:
            loop.close()

        status = 200 if out.get("ok", False) else out.get("httpStatus", 500)
        if "httpStatus" not in out:
            out["httpStatus"] = status

        response = jsonify(out)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response, status

    except Exception as e:
        return jsonify({"ok": False, "httpStatus": 500, "error": str(e)}), 500
