import {
  uploadDocument,
  preprocessDocument,
  determineHeaders,
  determineLocalHeaders,
  processPasses,
  testLLM
} from "./api.mjs";
import { renderTable, renderHeaderPreview, renderLocalHeaders } from "./ui.mjs";
import {
  state,
  el,
  providerLabel,
  providerAuthHint,
  requireSession,
  updateModel,
  resetCacheState
} from "./state.mjs";
import { log, openGroup, withGroup } from "./logging.mjs";
import { setStatus, updateStatus } from "./status.mjs";

const PASS_PROGRESS_MAX_MS = 6 * 60 * 1000;
let passProgressTimer = null;
let passProgressStartAt = 0;
let passProgressHandled = true;

function clearPassProgressTimer() {
  if (passProgressTimer) {
    clearInterval(passProgressTimer);
    passProgressTimer = null;
  }
}

function showPassProgressWrap() {
  const wrap = el("passesProgressWrap");
  if (wrap) wrap.classList.remove("hidden");
}

function hidePassProgressWrap() {
  const wrap = el("passesProgressWrap");
  if (wrap) wrap.classList.add("hidden");
}

function setPassProgressFraction(fraction) {
  const fill = el("passesProgressFill");
  if (!fill) return;
  const clamped = Math.max(0, Math.min(1, Number.isFinite(fraction) ? fraction : 0));
  fill.style.width = `${clamped * 100}%`;
}

function startPassProgressBar() {
  passProgressHandled = false;
  clearPassProgressTimer();
  passProgressStartAt = Date.now();
  showPassProgressWrap();
  setPassProgressFraction(0);
  passProgressTimer = setInterval(() => {
    const elapsed = Date.now() - passProgressStartAt;
    const ratio = Math.min(elapsed / PASS_PROGRESS_MAX_MS, 1);
    setPassProgressFraction(ratio);
    if (ratio >= 1) {
      clearPassProgressTimer();
    }
  }, 200);
}

function completePassProgressBar() {
  passProgressHandled = true;
  clearPassProgressTimer();
  showPassProgressWrap();
  setPassProgressFraction(1);
}

function failPassProgressBar() {
  passProgressHandled = true;
  clearPassProgressTimer();
  setPassProgressFraction(0);
  hidePassProgressWrap();
}

function ensurePassProgressStopped() {
  if (passProgressTimer) {
    clearPassProgressTimer();
  }
  if (!passProgressHandled) {
    failPassProgressBar();
  }
}

export function resetAfterUpload() {
  resetCacheState();

  const tableWrap = el("tableWrap");
  if (tableWrap) renderTable(tableWrap, []);
  const downloadWrap = el("downloadWrap");
  if (downloadWrap) downloadWrap.classList.add("hidden");
  const headersPreview = el("headersPreview");
  if (headersPreview) headersPreview.innerHTML = "";

  const preStatus = el("preprocessStatus");
  if (preStatus) setStatus(preStatus, "Micro/macro preprocessing pending…");
  const headerStatus = el("headersStatus");
  if (headerStatus) setStatus(headerStatus, "Header detection pending…");
  const processStatus = el("processStatus");
  if (processStatus) setStatus(processStatus, "Processing not started.");
  failPassProgressBar();
}

export function dumpLLMDebug(debug) {
  if (!Array.isArray(debug) || debug.length === 0) {
    console.debug("[LLM] No debug entries to display");
    return;
  }
  debug.forEach((entry, idx) => {
    const label = entry?.model || `LLM ${idx + 1}`;
    withGroup(`[LLM Debug] Entry ${idx + 1}: ${label}`, () => {
      withGroup("Request", () => {
        if (entry?.request?.curl) {
          console.log(entry.request.curl);
        }
        console.log(entry?.request || {});
      }, true);
      withGroup("Response", () => {
        console.log(entry?.response || {});
      }, true);
      if (entry?.error) {
        console.warn("Error", entry.error);
      }
    }, true);
  });
}

export async function onUpload() {
  updateModel();
  const end = openGroup("[Flow] Upload", false);
  try {
    const fileInput = el("file");
    const file = fileInput?.files?.[0];
    if (!file) {
      console.warn("[Flow] Upload aborted: no file selected");
      alert("Choose a .pdf, .docx, or .txt file first.");
      return;
    }
    console.log("Selected file", { name: file.name, size: file.size, type: file.type });
    console.log("State before upload", { ...state });
    updateStatus("uploadStatus", `Uploading ${file.name}…`);
    log(`Uploading ${file.name}`);
    const res = await uploadDocument(file);
    withGroup("[Flow] Upload → API response", () => {
      console.log(res);
    }, true);
    if (!res.ok) {
      const msg = res.error || "Upload failed";
      updateStatus("uploadStatus", `Upload error: ${msg}`, "warn");
      log(`Upload error: ${msg}`);
      return;
    }
    state.sessionId = res.session_id;
    resetAfterUpload();
    state.fileHash = res.file_hash || null;
    state.cacheInfo = {
      preprocess: Boolean(res.cache?.preprocess),
      headers: Boolean(res.cache?.headers),
      passes: Array.isArray(res.cache?.passes) ? res.cache.passes : []
    };
    updateStatus(
      "uploadStatus",
      `Uploaded ${res.filename}. Session ${state.sessionId.slice(0, 8)}…`,
      "success"
    );
    log(`Upload ok. session=${state.sessionId}`);

    const cacheBits = [];
    if (state.cacheInfo.preprocess) cacheBits.push("preprocess");
    if (state.cacheInfo.headers) cacheBits.push("headers");
    if (state.cacheInfo.passes.length) cacheBits.push(`passes(${state.cacheInfo.passes.join(", ")})`);
    if (cacheBits.length) {
      log(`[Cache] Available: ${cacheBits.join(", ")}`);
    }

    const canAutoLoad = Boolean(state.provider && state.model);
    if (state.cacheInfo.preprocess) {
      if (canAutoLoad) {
        updateStatus("preprocessStatus", "Loading cached pre-chunks…");
        await onPreprocess();
      } else {
        updateStatus(
          "preprocessStatus",
          "Micro/macro preprocessing cached — select provider/model to load.",
          "success"
        );
      }
    }

    if (state.cacheInfo.headers) {
      if (canAutoLoad && state.hasPre) {
        await onHeaders();
      } else if (canAutoLoad && !state.cacheInfo.preprocess) {
        const headerStatus = el("headersStatus");
        if (headerStatus)
          setStatus(headerStatus, "Headers cached — run preprocess, then header detection.", "success");
      } else {
        const headerStatus = el("headersStatus");
        if (headerStatus)
          setStatus(headerStatus, "Headers cached — rerun heuristics to refresh.", "success");
      }
    }

    if (state.cacheInfo.passes.length) {
      const processNode = el("processStatus");
      if (processNode) {
        const cachedList = state.cacheInfo.passes.join(", ") || "cached";
        setStatus(processNode, `Pass results cached for: ${cachedList}.`, "success");
      }
    }

    console.log("State after upload", { ...state });
  } finally {
    end();
  }
}

export async function handleTestLLM() {
  updateModel();
  if (!state.provider) {
    alert("Select an LLM provider first.");
    return;
  }
  if (!state.model) {
    alert("Select a model first.");
    return;
  }
  const providerName = providerLabel();
  const end = openGroup("[Flow] Test LLM", false);
  try {
    console.log("State before test", { ...state });
    log(`Testing ${providerName} connectivity via ${state.model}`);
    withGroup("[Flow] Test LLM → Request payload", () => {
      console.log({ model: state.model, provider: state.provider });
    }, true);
    const res = await testLLM(state.model, state.provider);
    withGroup(`[Flow] Test LLM → Raw response (${res.httpStatus ?? "?"})`, () => {
      console.log(res);
    }, true);
    dumpLLMDebug(res.llm_debug);
    if (!res.ok) {
      let msg = res.error || "LLM test failed";
      if (res.needs_api_key) msg += ` — ${providerAuthHint()}`;
      if (res.httpStatus) msg += ` (HTTP ${res.httpStatus})`;
      updateStatus("uploadStatus", msg, "warn");
      log(`LLM test error: ${msg}`);
      return;
    }
    updateStatus(
      "uploadStatus",
      `LLM connectivity confirmed (${providerName}): ${res.response?.status || "ok"}`,
      "success"
    );
    log(`LLM test succeeded via ${providerName}`);
  } finally {
    end();
  }
}

export async function onPreprocess(options = {}) {
  if (!requireSession()) return false;
  updateModel();
  if (!state.provider) {
    alert("Select an LLM provider first.");
    return false;
  }
  if (!state.model) {
    alert("Select a model first.");
    return false;
  }
  const forceRefresh = Boolean(options?.forceRefresh);
  const end = openGroup(forceRefresh ? "[Flow] Preprocess (force)" : "[Flow] Preprocess", false);
  let success = false;
  try {
    console.log("State before preprocess", { ...state });
    if (forceRefresh) {
      state.hasHeaders = false;
      state.cacheInfo.headers = false;
      state.hasLocalHeaders = false;
      state.localHeaders = [];
      const previewTarget = el("headersPreview");
      if (previewTarget) renderHeaderPreview(previewTarget, []);
      const localPreviewTarget = el("headersLocalPreview");
      if (localPreviewTarget) renderLocalHeaders(localPreviewTarget, []);
      const headerStatus = el("headersStatus");
      if (headerStatus) setStatus(headerStatus, "Header detection pending…");
    }
    const statusLabel = forceRefresh
      ? "Re-running micro → macro chunking…"
      : "Running micro → macro chunking…";
    updateStatus("preprocessStatus", statusLabel);
    log(forceRefresh ? "Preprocess rerun start" : "Preprocess start");
    withGroup("[Flow] Preprocess → Request payload", () => {
      console.log({
        session_id: state.sessionId,
        model: state.model,
        provider: state.provider,
        force_refresh: forceRefresh || undefined
      });
    }, true);
    const res = await preprocessDocument(state.sessionId, state.model, state.provider, { forceRefresh });
    withGroup(`[Flow] Preprocess → Raw response (${res.httpStatus ?? "?"})`, () => {
      console.log(res);
    }, true);
    if (!res.ok) {
      const msg = res.error || "Preprocess failed";
      updateStatus("preprocessStatus", msg, "warn");
      log(`Preprocess error: ${msg}`);
      return false;
    }
    state.hasPre = true;
    state.cacheInfo.preprocess = true;
    const cacheTag = res.cache?.hit ? " [cached]" : forceRefresh ? " [refreshed]" : "";
    const microCount = typeof res.micro_chunks === "number" ? res.micro_chunks : null;
    const macroCount = typeof res.macro_chunks === "number" ? res.macro_chunks : res.pre_chunks;
    const microLabel = microCount !== null ? `micro=${microCount}` : null;
    const macroLabel = macroCount !== null ? `macro=${macroCount}` : null;
    const parts = [`Pages=${res.pages}`];
    if (microLabel) parts.push(microLabel);
    if (macroLabel) parts.push(macroLabel);
    updateStatus("preprocessStatus", `${parts.join(", ")}${cacheTag}`, "success");
    if (res.cache?.hit) {
      log("Preprocess complete via cache");
    } else if (forceRefresh) {
      log(`Preprocess rerun complete pages=${res.pages} chunks=${res.pre_chunks}`);
    } else {
      log(`Preprocess complete pages=${res.pages} chunks=${res.pre_chunks}`);
    }
    console.log("State after preprocess", { ...state });
    success = true;
  } finally {
    end();
  }
  return success;
}

export async function onLocalHeaders() {
  if (!requireSession()) return;
  const end = openGroup("[Flow] Local header detection", false);
  try {
    const statusNode = el("headersStatus");
    if (statusNode) setStatus(statusNode, "Detecting headers via local heuristics…");
    log("Local header detection start");
    withGroup("[Flow] Local headers → Request payload", () => {
      console.log({ session_id: state.sessionId });
    }, true);
    const res = await determineLocalHeaders(state.sessionId);
    withGroup(`[Flow] Local headers → Raw response (${res.httpStatus ?? "?"})`, () => {
      console.log(res);
    }, true);
    if (!res.ok) {
      const msg = res.error || "Local header detection failed";
      if (statusNode) setStatus(statusNode, msg, "warn");
      log(`Local headers error: ${msg}`);
      return;
    }
    state.localHeaders = Array.isArray(res.headers) ? res.headers : [];
    const count = state.localHeaders.length;
    log(`Local headers detected count=${count}`);
    if (statusNode)
      setStatus(statusNode, `Local heuristics detected ${count} candidate${count === 1 ? "" : "s"}.`);
    const previewTarget = el("headersLocalPreview");
    renderLocalHeaders(previewTarget, state.localHeaders);
  } finally {
    end();
  }
}

export async function onHeaders(options = {}) {
  if (!requireSession()) return;
  if (!state.hasPre) {
    alert("Run preprocess before header detection.");
    return;
  }
  const forceRefresh = Boolean(options?.forceRefresh);
  const end = openGroup("[Flow] Header detection", false);
  try {
    console.log("State before header detection", { ...state });

    if (forceRefresh) {
      state.hasHeaders = false;
      state.cacheInfo.headers = false;
      const previewTarget = el("headersPreview");
      if (previewTarget) renderHeaderPreview(previewTarget, []);
      const downloadWrap = el("downloadWrap");
      if (downloadWrap) downloadWrap.classList.add("hidden");
    }

    const statusNode = el("headersStatus");
    if (statusNode) {
      const actionLabel = forceRefresh ? "Re-running" : "Running";
      setStatus(statusNode, `${actionLabel} heuristic header detection…`);
    }

    withGroup("[Flow] Header detection → Request payload", () => {
      console.log({ session_id: state.sessionId, force_refresh: forceRefresh || undefined });
    }, true);
    log(forceRefresh ? "Header detection rerun via heuristics" : "Header detection start via heuristics");
    const res = await determineHeaders(state.sessionId, { forceRefresh });
    withGroup(`[Flow] Header detection → Raw response (${res.httpStatus ?? "?"})`, () => {
      console.log(res);
    }, true);
    if (!res.ok) {
      let msg = res.error || "Header detection failed";
      if (res.httpStatus) msg += ` (HTTP ${res.httpStatus})`;

      if (statusNode) setStatus(statusNode, msg, "warn");
      log(`Headers error: ${msg}`);

      return;
    }
    state.hasHeaders = true;
    state.cacheInfo.headers = true;
    const sections = Number(res.sections) || 0;

    const headerTag = res.cache?.hit ? " [cached]" : forceRefresh ? " [refreshed]" : "";

    if (statusNode) setStatus(statusNode, `Sections detected: ${sections}${headerTag}`, "success");
    const previewTarget = el("headersPreview");
    renderHeaderPreview(previewTarget, res.preview || []);

    if (res.cache?.hit) {
      log("Headers loaded from cache");
    } else if (forceRefresh) {
      log(`Headers regenerated sections=${res.sections}`);
    } else {
      log(`Headers detected sections=${res.sections}`);
    }
    console.log("State after header detection", { ...state });
  } finally {
    end();
  }
}

export function onHeadersRerun() {
  return onHeaders({ forceRefresh: true });
}

export function onPreprocessRechunk() {
  return onPreprocess({ forceRefresh: true });
}

export async function onProcess(options = {}) {
  if (!requireSession()) return;
  if (!state.hasHeaders) {
    alert("Detect headers before running the passes.");
    return;
  }
  updateModel();
  if (!state.provider) {
    alert("Select an LLM provider first.");
    return;
  }
  if (!state.model) {
    alert("Select a model first.");
    return;
  }
  const providerName = providerLabel();
  const forceRefresh = Boolean(options?.forceRefresh);
  const requestedPasses = Array.isArray(options?.passes) && options.passes.length
    ? options.passes
    : undefined;
  const end = openGroup("[Flow] Pass processing", false);
  try {
    console.log("State before process", { ...state });
    const actionLabel = forceRefresh ? "Re-running" : "Running";
    updateStatus("processStatus", `${actionLabel} asynchronous passes via ${providerName}…`);
    log(forceRefresh ? `Passes rerun via ${providerName}` : `Passes start via ${providerName}`);
    startPassProgressBar();
    const requestPreview = {
      session_id: state.sessionId,
      model: state.model,
      provider: state.provider,
      only_mechanical: false,
      debug: true,
      debug_llm_io: true
    };
    if (forceRefresh) requestPreview.force_refresh = true;
    if (requestedPasses) requestPreview.passes = requestedPasses;
    withGroup("[Flow] Pass processing → Request payload", () => {
      console.log(requestPreview);
    }, true);
    const res = await processPasses(state.sessionId, state.model, state.provider, {
      forceRefresh,
      passes: requestedPasses
    });
    withGroup(`[Flow] Pass processing → Raw response (${res.httpStatus ?? "?"})`, () => {
      console.log(res);
    }, true);
    dumpLLMDebug(res.llm_debug);
    if (!res.ok) {
      failPassProgressBar();
      let msg = res.error || "Process failed";
      if (res.needs_api_key) msg += ` — ${providerAuthHint()}`;
      if (res.httpStatus) msg += ` (HTTP ${res.httpStatus})`;
      updateStatus("processStatus", msg, "warn");
      log(`Process error: ${msg}`);
      return;
    }
    state.rows = res.rows || [];
    const cacheMeta = res.cache || {};
    const passHits = Array.isArray(cacheMeta.hits) ? cacheMeta.hits : [];
    const passMisses = Array.isArray(cacheMeta.misses) ? cacheMeta.misses : [];
    const passTagBits = [];
    if (passHits.length) passTagBits.push(`cached: ${passHits.join(", ")}`);
    if (passMisses.length) passTagBits.push(`LLM: ${passMisses.join(", ")}`);
    const passTag = passTagBits.length ? ` [${passTagBits.join(" • ")}]` : "";
    updateStatus(
      "processStatus",
      `Rows=${state.rows.length} • total=${res.metrics_ms?.total ?? "?"} ms${passTag}`,
      "success"
    );
    state.cacheInfo.passes = Array.isArray(cacheMeta.stored_passes)
      ? cacheMeta.stored_passes
      : passHits;
    renderTable(el("tableWrap"), state.rows);
    if (res.csv_base64) {
      const blob = b64ToBlob(res.csv_base64, "text/csv");
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = res.filename || "FluidRAG_results.csv";
      link.textContent = "Download CSV";
      const wrap = el("downloadWrap");
      if (wrap) {
        wrap.innerHTML = "";
        wrap.appendChild(link);
        wrap.classList.remove("hidden");
      }
    }
    if (passTagBits.length) {
      log(`Process complete (${passTagBits.join(" | ")})`);
    } else {
      log("Process complete");
    }
    completePassProgressBar();
    console.log("State after process", { ...state });
  } finally {
    ensurePassProgressStopped();
    end();
  }
}

export function onProcessRerunAll() {
  return onProcess({ forceRefresh: true });
}

function b64ToBlob(b64, mime) {
  const b = atob(b64);
  const arr = new Uint8Array(b.length);
  for (let i = 0; i < b.length; i++) arr[i] = b.charCodeAt(i);
  return new Blob([arr], { type: mime });
}
