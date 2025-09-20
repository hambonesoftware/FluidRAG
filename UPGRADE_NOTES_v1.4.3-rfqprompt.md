# v1.4.3-rfqprompt – Force using backend/prompts/__init__.py HEADER_DETECTION_SYSTEM
- preprocess now dynamically reloads `backend.prompts` before header detection.
- any hardcoded fallback prompt references replaced with `_get_header_system_prompt()`.
- a debug line prints the first 120 chars so you can verify your RFQ prompt is active.
