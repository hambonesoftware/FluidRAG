# FluidRAG v1.5-FULL – Frontend wired to page-mode headers

Date: 2025-09-20

- `/api/determine-headers` now invokes **page-mode** header detection with deterministic-first scoring and heuristic reruns (LLM adjudication disabled).
- Response remains backward compatible for `sections` and `preview`; the debug payload now surfaces heuristic stats via `debug.heuristics`.
- Optional UI helper `static/js/ui/header_toc_hook.mjs` can render a quick TOC list if you add `<div id="toc-preview"></div>` to your page and call:
  ```js
  import { maybeRenderTOC } from '/static/js/ui/header_toc_hook.mjs';
  maybeRenderTOC(response.preview);
  ```
