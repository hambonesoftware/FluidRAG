# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import httpx
from flask import Blueprint, jsonify, make_response, request

from .. import config

log = logging.getLogger("FluidRAG.api.models")

# Expose a standalone blueprint so app.py can register `models_route.bp`
bp = Blueprint("models", __name__)

@bp.route("/api/models", methods=["GET", "OPTIONS"])
def list_models():
    # Handle CORS preflight explicitly (some browsers require this for custom headers)
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return resp

    """Return live models for OpenRouter + local llama.cpp, same shape as legacy endpoint."""
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}" if config.OPENROUTER_API_KEY else "",
        "HTTP-Referer": config.OPENROUTER_HTTP_REFERER,
        "X-Title": config.OPENROUTER_APP_TITLE,
    }

    openrouter_models = []
    try:
        r = httpx.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=20.0)
        r.raise_for_status()
        data = r.json()
        openrouter_models = [m.get("id") for m in data.get("data", []) if m.get("id")]
    except Exception as e:
        log.exception("[/api/models] OpenRouter list failed: %s", e)

    default_openrouter = config.OPENROUTER_DEFAULT_MODEL or (openrouter_models[0] if openrouter_models else None)

    llamacpp_models = [config.LLAMACPP_DEFAULT_MODEL]
    default_llamacpp = config.LLAMACPP_DEFAULT_MODEL

    providers = {
        "openrouter": {
            "label": "OpenRouter",
            "models": openrouter_models,
            "default_model": default_openrouter,
        },
        "llamacpp": {
            "label": "llama.cpp",
            "models": llamacpp_models,
            "default_model": default_llamacpp,
        },
    }

    payload = {"ok": True, "providers": providers, "default_provider": "openrouter"}
    resp = jsonify(payload)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp, 200
