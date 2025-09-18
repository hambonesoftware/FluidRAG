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

function openGroup(label, collapsed=false){
  if(collapsed) console.groupCollapsed(label);
  else console.group(label);
  return ()=>console.groupEnd();
}

function withGroup(label, fn, collapsed=false){
  const end = openGroup(label, collapsed);
  try{
    fn();
  }finally{
    end();
  }
}

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
    withGroup(`[LLM Debug] Entry ${idx+1}: ${label}`, ()=>{
      withGroup("Request", ()=>{
        console.log(entry?.request || {});
      }, true);
      withGroup("Response", ()=>{
        console.log(entry?.response || {});
      }, true);
      if(entry?.error){
        console.warn("Error", entry.error);
      }
    }, true);
  });
}

function requireSession(){
  if(!state.sessionId){
    console.warn("[Guard] Session required but missing", {state});
    alert("Upload a document first.");
    return false;
  }
  return true;
}

function updateModel(){
  state.model = el("model").value;
  console.debug("[State] Model updated", {model: state.model});
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
  const end = openGroup("[Flow] Upload", false);
  try{
    const file = el("file").files[0];
    if(!file){
      console.warn("[Flow] Upload aborted: no file selected");
      alert("Choose a .pdf, .docx, or .txt file first.");
      return;
    }
    console.log("Selected file", {name:file.name, size:file.size, type:file.type});
    console.log("State before upload", {...state});
    setStatus(el("uploadStatus"), `Uploading ${file.name}…`);
    log(`Uploading ${file.name}`);
    const res = await uploadDocument(file);
    withGroup("[Flow] Upload → API response", ()=>{
      console.log(res);
    }, true);
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
    console.log("State after upload", {...state});
  }finally{
    end();
  }
}

async function handleTestLLM(){
  updateModel();
  const end = openGroup("[Flow] Test LLM", false);
  try{
    console.log("State before test", {...state});
    log(`Testing LLM connectivity via ${state.model}`);
    withGroup("[Flow] Test LLM → Request payload", ()=>{
      console.log({model: state.model});
    }, true);
    const res = await testLLM(state.model);
    withGroup(`[Flow] Test LLM → Raw response (${res.httpStatus ?? "?"})`, ()=>{
      console.log(res);
    }, true);
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
  }finally{
    end();
  }
}

async function onPreprocess(){
  if(!requireSession()) return;
  updateModel();
  const end = openGroup("[Flow] Preprocess", false);
  try{
    console.log("State before preprocess", {...state});
    setStatus(el("preprocessStatus"), "Running standard chunking…");
    log("Preprocess start");
    withGroup("[Flow] Preprocess → Request payload", ()=>{
      console.log({session_id: state.sessionId, model: state.model});
    }, true);
    const res = await preprocessDocument(state.sessionId, state.model);
    withGroup(`[Flow] Preprocess → Raw response (${res.httpStatus ?? "?"})`, ()=>{
      console.log(res);
    }, true);
    if(!res.ok){
      const msg = res.error || "Preprocess failed";
      setStatus(el("preprocessStatus"), msg, "warn");
      log(`Preprocess error: ${msg}`);
      return;
    }
    state.hasPre = true;
    setStatus(el("preprocessStatus"), `Pages=${res.pages}, pre-chunks=${res.pre_chunks}`, "success");
    log(`Preprocess complete pages=${res.pages} chunks=${res.pre_chunks}`);
    console.log("State after preprocess", {...state});
  }finally{
    end();
  }
}

async function onHeaders(){
  if(!requireSession()) return;
  if(!state.hasPre){ alert("Run preprocess before header detection."); return; }
  updateModel();
  const end = openGroup("[Flow] Header detection", false);
  try{
    console.log("State before header detection", {...state});
    setStatus(el("headersStatus"), "Detecting headers via OpenRouter…");
    log("Header detection start");
    withGroup("[Flow] Header detection → Request payload", ()=>{
      console.log({session_id: state.sessionId, model: state.model});
    }, true);
    const res = await determineHeaders(state.sessionId, state.model);
    withGroup(`[Flow] Header detection → Raw response (${res.httpStatus ?? "?"})`, ()=>{
      console.log(res);
    }, true);
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
    console.log("State after header detection", {...state});
  }finally{
    end();
  }
}

async function onProcess(){
  if(!requireSession()) return;
  if(!state.hasHeaders){ alert("Detect headers before running the passes."); return; }
  updateModel();
  const end = openGroup("[Flow] Pass processing", false);
  try{
    console.log("State before process", {...state});
    setStatus(el("processStatus"), "Running asynchronous passes…");
    log("Passes start");
    withGroup("[Flow] Pass processing → Request payload", ()=>{
      console.log({session_id: state.sessionId, model: state.model});
    }, true);
    const res = await processPasses(state.sessionId, state.model);
    withGroup(`[Flow] Pass processing → Raw response (${res.httpStatus ?? "?"})`, ()=>{
      console.log(res);
    }, true);
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
    console.log("State after process", {...state});
  }finally{
    end();
  }
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
  el("testBtn").addEventListener("click", handleTestLLM);
  el("preprocessBtn").addEventListener("click", onPreprocess);
  el("headersBtn").addEventListener("click", onHeaders);
  el("processBtn").addEventListener("click", onProcess);
  log("Boot complete");
}

boot();
