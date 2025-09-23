# FluidRAG

FluidRAG is a standalone RAG-style specification extraction tool with a Flask backend and an ESM frontend. It applies a **standard → Fluid → HEP** preprocessing pipeline, then runs five asynchronous LLM passes (Mechanical, Electrical, Controls, Software, and Project Management) to collect exact specification statements. Duplicate specifications found by multiple passes are merged and exported as a CSV with the columns **Document**, **(Sub)Section #**, **(Sub)Section Name**, **Specification**, and **Pass**.

The UI follows a light Microsoft 365 Copilot-inspired theme and surfaces detailed progress logs in both the Flask console and the browser DevTools console.


## Quick start

```bash
# 1. Create and activate a virtual environment (Windows example)
py -3.12 -m venv .venv
.\.venv\Scripts\activate

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Configure LLM credentials
copy .env.example .env
# edit .env and set OPENROUTER_API_KEY for OpenRouter (optional but recommended)
# optionally set OPENROUTER_HTTP_REFERER / OPENROUTER_APP_TITLE if your key is
# restricted to a specific domain/application name
# optionally set LLAMACPP_URL / LLAMACPP_MODELS / LLAMACPP_DEFAULT_MODEL for llama.cpp

# 4. Run the development server
python run.py  # starts Flask and opens the frontend
```

> Without `OPENROUTER_API_KEY`, network calls fall back to mocked responses so you can exercise the UI end-to-end.


## Guided workflow

1. **Upload & model selection**  
   Choose an LLM provider (OpenRouter cloud or a local llama.cpp endpoint) and select a model. Upload `.pdf`, `.docx`, or `.txt` files; the backend stores them in a session-specific temp directory. Use the **Test LLM** button to verify connectivity with the provider using the legacy concatenated role/message prompt format.
2. **Preprocess (standard chunking)**  
   Split the document into overlapping ~4k-token coarse chunks while persisting per-page strings for subsequent stages.
3. **Determine headers**  
   Run hybrid heading detection (regex + LLM confirmation) in ≤120k-token batches to produce section/subsection spans. The API returns an outline preview and full LLM debug logs for DevTools inspection.
4. **Fluid → HEP refinement**  
   Refine the section chunks toward ~1–2k tokens with Fluid and attach entropy/cluster metadata via HEP to inform downstream weighting.
5. **Async passes & merge**
   Rank chunks per pass using entropy and keyword heuristics, enforce a 120k-token request budget, and dispatch asynchronous LLM calls staggered five seconds apart to protect the upstream model while keeping all passes in flight. Exact specifications are deduplicated across passes, rendered in-app, and offered as `FluidRAG_results.csv` for download.

## Configuration notes

- Update `backend/app.py` → `OPENROUTER_FREE_MODELS` to adjust the OpenRouter shortlist; popular free models such as DeepSeek, Ollama, and Mistral are included by default.
- Use `.env` to configure OpenRouter metadata headers if your API key requires them (e.g. `OPENROUTER_HTTP_REFERER`, `OPENROUTER_APP_TITLE`).
- Environment variables (`LLAMACPP_URL`, `LLAMACPP_MODELS`, `LLAMACPP_DEFAULT_MODEL`) control llama.cpp connectivity.
- Prompts live in `backend/prompts/__init__.py` for reuse across passes.
- Frontend modules live under `frontend/js/` and are loaded as ES modules.


## Dev containers / Codespaces

1. Install the **Dev Containers** extension in VS Code.
2. Open this folder and accept **Reopen in Container** when prompted.
3. Inside the container, run:
   ```bash
   pip install -r backend/requirements.txt
   python run.py
   ```

## License

MIT
