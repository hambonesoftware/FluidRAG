# -*- coding: utf-8 -*-
from __future__ import annotations

import os, time, asyncio, json
from math import ceil
from flask import Blueprint, request, jsonify, make_response

from ..pipeline.preprocess import extract_pages_with_layout
from ..pipeline.llm import create_llm_client
from ..parse.header_page_mode import select_candidates, build_adjudication_prompt
from ..parse.header_config import CONFIG

bp = Blueprint("headers", __name__)

def _json_ok(data, code=200):
    resp = jsonify(data)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp, code

@bp.route("/api/determine-headers", methods=["POST", "OPTIONS"])
def determine_headers():
    # CORS preflight
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return resp

    try:
        data = request.get_json(force=True) or {}

        session_id = data.get("session_id") or data.get("session") or ""
        pdf_path   = data.get("pdf_path") or data.get("path")
        if not pdf_path and session_id:
            uploads_dir = os.getenv("UPLOAD_FOLDER", "uploads")
            pdf_path = os.path.join(uploads_dir, f"{session_id}.pdf")
        sidecar_dir = os.path.join("sidecars", session_id) if session_id else None

        layout = extract_pages_with_layout(pdf_path, sidecar_dir=sidecar_dir)
        pages_linear     = layout.get("pages_linear") or []
        pages_lines      = layout.get("pages_lines") or [p.splitlines() for p in pages_linear]
        page_line_styles = layout.get("page_line_styles") or [[{} for _ in (p or [])] for p in pages_lines]

        provider = (data.get("provider") or os.getenv("LLM_PROVIDER", "openrouter")).strip()
        model    = (data.get("model")    or os.getenv("HEADER_MODEL", "x-ai/grok-4-fast:free")).strip()
        client   = create_llm_client(provider=provider, model=model) if CONFIG.get("llm_enabled", True) else None

        # 1) Heuristic candidates by page
        all_page_cands, debug_candidates = [], []
        for pi, lines in enumerate(pages_lines):
            styles = page_line_styles[pi] if page_line_styles and pi < len(page_line_styles) else [{} for _ in lines]
            cands  = select_candidates(lines, styles)
            all_page_cands.append(cands)
            if pi < 15:  # trim debug size
                debug_candidates.append({"page": pi+1, "candidates": cands[:12]})

        # 2) Batch LLM adjudication to avoid 429s
        adjudicated = { }   # (page -> list of idx approved)
        llm_debug   = []
        if client and any(c for c in all_page_cands):
            pages = list(range(len(pages_lines)))
            batch_size = max(1, int(CONFIG.get("llm_batch_pages", 4)))
            max_batches = max(1, int(CONFIG.get("llm_max_batches", 5)))
            batches = [pages[i:i+batch_size] for i in range(0, len(pages), batch_size)][:max_batches]

            async def run_batch(batch_pages):
                msgs = [{"role": "system", "content":
                    "You adjudicate section headings. Reply ONLY JSON per page id:\n"
                    "[{\"page\":N,\"items\":[{\"section_number\":\"\",\"section_name\":\"\",\"line_idx\":0}]}]"}]
                user_payload = []
                for p in batch_pages:
                    if not all_page_cands[p]:
                        continue
                    prompt = build_adjudication_prompt(
                        pages_linear[p] if p < len(pages_linear) else "\n".join(pages_lines[p]),
                        all_page_cands[p],
                        CONFIG.get("context_chars_per_candidate", 700),
                    )
                    user_payload.append({"page": p+1, "prompt": prompt})
                msgs.append({"role": "user", "content": json.dumps(user_payload)})

                backoff = int(CONFIG.get("llm_backoff_initial_ms", 600))
                for attempt in range(4):
                    try:
                        r = await client.chat(msgs, temperature=CONFIG.get("llm_temperature", 0.0), max_tokens=1024)
                        text = r.get("text") if isinstance(r, dict) else ""
                        parsed = []
                        try:
                            parsed = json.loads(text) if isinstance(text, str) else []
                        except Exception:
                            parsed = []
                        return {"ok": True, "batch": batch_pages, "result": parsed, "raw": text}
                    except Exception as ex:
                        # naive detection of 429 or rate-limit
                        if "429" in str(ex) or "Too Many Requests" in str(ex):
                            time.sleep(backoff/1000.0)
                            backoff = min(int(backoff * CONFIG.get("llm_backoff_factor", 1.7)), int(CONFIG.get("llm_backoff_max_ms", 4500)))
                            continue
                        return {"ok": False, "batch": batch_pages, "error": str(ex), "result": []}
                return {"ok": False, "batch": batch_pages, "error": "LLM retry exhausted", "result": []}

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                outs = []
                for b in batches:
                    outs.append(loop.run_until_complete(run_batch(b)))
                for out in outs:
                    llm_debug.append(out if len(llm_debug) < 6 else {"ok": out.get("ok", False), "batch": out.get("batch")})
                    if not out.get("ok"):
                        continue
                    for item in (out.get("result") or []):
                        pg = int(item.get("page", 0))
                        arr = item.get("items") or []
                        chosen = []
                        for it in arr:
                            try:
                                li = int(it.get("line_idx"))
                                chosen.append(li)
                            except Exception:
                                continue
                        if pg >= 1:
                            adjudicated[pg-1] = chosen
            finally:
                loop.close()

        # 3) Merge: if LLM adjudicated a page, use that; else fallback to top-K heuristics
        results = []
        sections_count = 0
        topk = int(CONFIG.get("fallback_top_k_per_page", 3))
        for pi, cands in enumerate(all_page_cands):
            chosen_idx = adjudicated.get(pi)
            headers = []
            if chosen_idx:
                # keep original order on page
                for ci in cands:
                    if ci["line_idx"] in chosen_idx:
                        headers.append({
                            "line_idx": ci["line_idx"],
                            "text": ci["text"],
                            "section_number": ci.get("section_number", ""),
                            "level": ci.get("level", 3),
                            "score": max(ci.get("score", 0.0), 3.0),
                            "style": ci.get("style", {}),
                        })
            else:
                # fallback: top-K best heuristic
                for ci in cands[:topk]:
                    headers.append({
                        "line_idx": ci["line_idx"],
                        "text": ci["text"],
                        "section_number": ci.get("section_number", ""),
                        "level": ci.get("level", 3),
                        "score": ci.get("score", 0.0),
                        "style": ci.get("style", {}),
                    })

            sections_count += len(headers)
            results.append({"page": pi+1, "headers": headers})

        # Legacy "preview" for UI
        preview = []
        for page_entry in results:
            for h in page_entry.get("headers", []):
                preview.append({
                    "chars": len(h.get("text") or ""),
                    "section_name": h.get("text") or "",
                    "section_number": h.get("section_number") or "",
                })
                if len(preview) >= 5:
                    break
            if len(preview) >= 5:
                break

        return _json_ok({
            "ok": True,
            "httpStatus": 200,
            "sections": sections_count,
            "preview": preview,
            "debug": {
                "candidates": debug_candidates,  # first pages only to keep payload light
                "adjudicated_pages": sorted(list(adjudicated.keys())),
                "llm_batches": len(llm_debug),
                "llm_debug": llm_debug,
                "provider": provider,
                "model": model,
            }
        })
    except Exception as e:
        return _json_ok({"ok": False, "httpStatus": 500, "error": str(e)}, 500)
