import { getModels, uploadDocument, preprocessDocument, determineHeaders, processPasses, testLLM } from "./api.mjs";
import { renderTable, renderHeaderPreview } from "./ui.mjs";

const el = (id)=>document.getElementById(id);
const state = {
  sessionId:null,
  model:null,
  hasPre:false,
  hasHeaders:false,
  rows:[]
};

const log = (msg)=>{
  const pre = el("log");
  const line = `[UI] ${new Date().toLocaleTimeString()} ${msg}`;
  console.log(line);
  pre.textContent += line + "\n";
  pre.scrollTop = pre.scrollHeight;
};

function setStatus(node, message, tone){
  node.textContent = message;
  node.classList.remove("success","warn");
  if(tone === "success") node.classList.add("success");
  else if(tone === "warn") node.classList.add("warn");
}

function dumpLLMDebug(debug){
  if(!Array.isArray(debug) || debug.length === 0){
    console.debug("[LLM] No debug entries to display");
    return;
  }
  debug.forEach((entry, idx)=>{
    const label = entry?.model || `LLM ${idx+1}`;
    console.groupCollapsed(`[LLM ${idx+1}] ${label}`);
    console.groupCollapsed("Request");
    console.log(entry?.request || {});
    console.groupEnd();
    console.groupCollapsed("Response");
    console.log(entry?.response || {});
    console.groupEnd();
    console.groupEnd();
  });
}

function requireSession(){
  if(!state.sessionId){
    alert("Upload a document first.");
    return false;
  }
  return true;
}

function updateModel(){
  state.model = el("model").value;
}

function resetAfterUpload(){
  state.hasPre = false;
  state.hasHeaders = false;
  state.rows = [];
  renderTable(el("tableWrap"), []);
  el("downloadWrap").classList.add("hidden");
  el("headersPreview").innerHTML = "";
  setStatus(el("preprocessStatus"), "Pre-chunking pending…");
  setStatus(el("headersStatus"), "Awaiting header detection…");
  setStatus(el("processStatus"), "Processing not started.");
}

async function onUpload(){
  updateModel();
  const file = el("file").files[0];
  if(!file){ alert("Choose a .pdf, .docx, or .txt file first."); return; }
  setStatus(el("uploadStatus"), `Uploading ${file.name}…`);
  log(`Uploading ${file.name}`);
  const res = await uploadDocument(file);
  if(!res.ok){
    const msg = res.error || "Upload failed";
    setStatus(el("uploadStatus"), `Upload error: ${msg}`, "warn");
    log(`Upload error: ${msg}`);
    return;
  }
  state.sessionId = res.session_id;
  resetAfterUpload();
  setStatus(el("uploadStatus"), `Uploaded ${res.filename}. Session ${state.sessionId.slice(0,8)}…`, "success");
  log(`Upload ok. session=${state.sessionId}`);
}

async function onTestLLM(){
  updateModel();
  log(`Testing LLM connectivity via ${state.model}`);
  const res = await testLLM(state.model);
  dumpLLMDebug(res.llm_debug);
  if(!res.ok){
    let msg = res.error || "LLM test failed";
    if(res.needs_api_key) msg += " — set OPENROUTER_API_KEY";
    if(res.httpStatus) msg += ` (HTTP ${res.httpStatus})`;
    setStatus(el("uploadStatus"), msg, "warn");
    log(`LLM test error: ${msg}`);
    return;
  }
  setStatus(el("uploadStatus"), `LLM connectivity confirmed: ${res.response?.status || "ok"}`, "success");
  log("LLM test succeeded");
}

async function onPreprocess(){
  if(!requireSession()) return;
  updateModel();
  setStatus(el("preprocessStatus"), "Running standard chunking…");
  log("Preprocess start");
  const res = await preprocessDocument(state.sessionId, state.model);
  if(!res.ok){
    const msg = res.error || "Preprocess failed";
    setStatus(el("preprocessStatus"), msg, "warn");
    log(`Preprocess error: ${msg}`);
    return;
  }
  state.hasPre = true;
  setStatus(el("preprocessStatus"), `Pages=${res.pages}, pre-chunks=${res.pre_chunks}`, "success");
  log(`Preprocess complete pages=${res.pages} chunks=${res.pre_chunks}`);
}

async function onHeaders(){
  if(!requireSession()) return;
  if(!state.hasPre){ alert("Run preprocess before header detection."); return; }
  updateModel();
  setStatus(el("headersStatus"), "Detecting headers via OpenRouter…");
  log("Header detection start");
  const res = await determineHeaders(state.sessionId, state.model);
  dumpLLMDebug(res.llm_debug);
  if(!res.ok){
    let msg = res.error || "Header detection failed";
    if(res.needs_api_key) msg += " — set OPENROUTER_API_KEY";
    if(res.httpStatus) msg += ` (HTTP ${res.httpStatus})`;
    setStatus(el("headersStatus"), msg, "warn");
    log(`Headers error: ${msg}`);
    return;
  }
  state.hasHeaders = true;
  setStatus(el("headersStatus"), `Sections detected: ${res.sections}`, "success");
  renderHeaderPreview(el("headersPreview"), res.preview || []);
  log(`Headers detected sections=${res.sections}`);
}

async function onProcess(){
  if(!requireSession()) return;
  if(!state.hasHeaders){ alert("Detect headers before running the passes."); return; }
  updateModel();
  setStatus(el("processStatus"), "Running asynchronous passes…");
  log("Passes start");
  const res = await processPasses(state.sessionId, state.model);
  dumpLLMDebug(res.llm_debug);
  if(!res.ok){
    let msg = res.error || "Process failed";
    if(res.needs_api_key) msg += " — set OPENROUTER_API_KEY";
    if(res.httpStatus) msg += ` (HTTP ${res.httpStatus})`;
    setStatus(el("processStatus"), msg, "warn");
    log(`Process error: ${msg}`);
    return;
  }
  state.rows = res.rows || [];
  setStatus(el("processStatus"), `Rows=${state.rows.length} • total=${res.metrics_ms?.total ?? "?"} ms`, "success");
  renderTable(el("tableWrap"), state.rows);
  if(res.csv_base64){
    const blob = b64ToBlob(res.csv_base64, "text/csv");
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = res.filename || "FluidRAG_results.csv";
    link.textContent = "Download CSV";
    const wrap = el("downloadWrap");
    wrap.innerHTML = "";
    wrap.appendChild(link);
    wrap.classList.remove("hidden");
  }
  log("Process complete");
}

function b64ToBlob(b64, mime){
  const b = atob(b64);
  const arr = new Uint8Array(b.length);
  for(let i=0;i<b.length;i++) arr[i] = b.charCodeAt(i);
  return new Blob([arr], {type: mime});
}

async function boot(){
  log("Boot start");
  renderTable(el("tableWrap"), []);
  const modelSel = el("model");
  const models = await getModels();
  if(models.ok && Array.isArray(models.models)){
    models.models.forEach((m, idx)=>{
      const opt = document.createElement("option");
      opt.value = m; opt.textContent = m;
      modelSel.appendChild(opt);
      if(idx === 0) state.model = m;
    });
  }
  modelSel.addEventListener("change", updateModel);
  el("uploadBtn").addEventListener("click", onUpload);
  el("testBtn").addEventListener("click", onTestLLM);
  el("preprocessBtn").addEventListener("click", onPreprocess);
  el("headersBtn").addEventListener("click", onHeaders);
  el("processBtn").addEventListener("click", onProcess);
  log("Boot complete");
}

boot();
