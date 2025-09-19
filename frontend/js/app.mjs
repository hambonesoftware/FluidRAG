import { getModels, uploadDocument, preprocessDocument, determineHeaders, processPasses, testLLM } from "./api.mjs";
import { renderTable, renderHeaderPreview } from "./ui.mjs";

const el = (id)=>document.getElementById(id);
const state = {

  sessionId: null,
  provider: null,
  model: null,
  hasPre: false,
  hasHeaders: false,
  rows: [],
  providers: {}

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


function providerLabel(providerId = state.provider){
  if(!providerId) return "provider";
  const info = state.providers?.[providerId];
  return info?.label || providerId;
}

function providerAuthHint(){
  if(state.provider === "openrouter") return "set OPENROUTER_API_KEY";
  if(state.provider === "llamacpp") return "ensure llama.cpp endpoint credentials are valid";
  return "verify LLM credentials";
}

function refreshModelOptions(preferredModel = null){
  const modelSel = el("model");
  modelSel.innerHTML = "";
  const providerId = state.provider;
  const info = state.providers?.[providerId];
  if(!info){
    state.model = null;
    console.warn("[State] Missing provider info; unable to populate models", {providerId});
    return;
<
  }
  const models = Array.isArray(info.models) ? info.models : [];
  models.forEach((m)=>{
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    modelSel.appendChild(opt);
  });
  let selected = null;
  if(preferredModel && models.includes(preferredModel)){
    selected = preferredModel;
  }else if(info.default_model && models.includes(info.default_model)){
    selected = info.default_model;
  }else if(models.length > 0){
    selected = models[0];
  }
  if(selected){
    modelSel.value = selected;
    state.model = selected;
  }else{
    state.model = null;
  }

  console.debug("[State] Model options updated", {provider: providerId, model: state.model});
}

function updateProvider(){
  const providerSel = el("provider");
  const newProvider = providerSel.value;
  if(!newProvider) return;
  if(!state.providers?.[newProvider]){
    console.warn("[State] Unknown provider selected", {newProvider});
    return;
  }
  state.provider = newProvider;
  console.debug("[State] Provider updated", {provider: state.provider});
  refreshModelOptions();
  updateModel();
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
  const modelSel = el("model");
  state.model = modelSel.value || null;
  console.debug("[State] Model updated", {provider: state.provider, model: state.model});
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
  if(!state.provider){ alert("Select an LLM provider first."); return; }
  if(!state.model){
    alert("Select a model first.");
    return;
  }
  const providerName = providerLabel();
  const end = openGroup("[Flow] Test LLM", false);
  try{
    console.log("State before test", {...state});
    log(`Testing ${providerName} connectivity via ${state.model}`);
    withGroup("[Flow] Test LLM → Request payload", ()=>{
      console.log({model: state.model, provider: state.provider});
    }, true);
    const res = await testLLM(state.model, state.provider);
    withGroup(`[Flow] Test LLM → Raw response (${res.httpStatus ?? "?"})`, ()=>{
      console.log(res);
    }, true);
    dumpLLMDebug(res.llm_debug);
    if(!res.ok){
      let msg = res.error || "LLM test failed";
      if(res.needs_api_key) msg += ` — ${providerAuthHint()}`;
      if(res.httpStatus) msg += ` (HTTP ${res.httpStatus})`;
      setStatus(el("uploadStatus"), msg, "warn");
      log(`LLM test error: ${msg}`);
      return;
    }
    setStatus(el("uploadStatus"), `LLM connectivity confirmed (${providerName}): ${res.response?.status || "ok"}`, "success");
    log(`LLM test succeeded via ${providerName}`);
  }finally{
    end();
  }
}

async function onPreprocess(){
  if(!requireSession()) return;
  updateModel();
  if(!state.provider){ alert("Select an LLM provider first."); return; }
  if(!state.model){ alert("Select a model first."); return; }
  const end = openGroup("[Flow] Preprocess", false);
  try{
    console.log("State before preprocess", {...state});
    setStatus(el("preprocessStatus"), "Running standard chunking…");
    log("Preprocess start");
    withGroup("[Flow] Preprocess → Request payload", ()=>{
      console.log({session_id: state.sessionId, model: state.model, provider: state.provider});
    }, true);
    const res = await preprocessDocument(state.sessionId, state.model, state.provider);
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
  if(!state.provider){ alert("Select an LLM provider first."); return; }
  if(!state.model){ alert("Select a model first."); return; }
  const providerName = providerLabel();
  const end = openGroup("[Flow] Header detection", false);
  try{
    console.log("State before header detection", {...state});
    setStatus(el("headersStatus"), `Detecting headers via ${providerName}…`);
    log(`Header detection start via ${providerName}`);
    withGroup("[Flow] Header detection → Request payload", ()=>{
      console.log({session_id: state.sessionId, model: state.model, provider: state.provider});
    }, true);
    const res = await determineHeaders(state.sessionId, state.model, state.provider);
    withGroup(`[Flow] Header detection → Raw response (${res.httpStatus ?? "?"})`, ()=>{
      console.log(res);
    }, true);
    dumpLLMDebug(res.llm_debug);
    if(!res.ok){
      let msg = res.error || "Header detection failed";
      if(res.needs_api_key) msg += ` — ${providerAuthHint()}`;
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
  if(!state.provider){ alert("Select an LLM provider first."); return; }
  if(!state.model){ alert("Select a model first."); return; }
  const providerName = providerLabel();
  const end = openGroup("[Flow] Pass processing", false);
  try{
    console.log("State before process", {...state});
    setStatus(el("processStatus"), `Running asynchronous passes via ${providerName}…`);
    log(`Passes start via ${providerName}`);
    withGroup("[Flow] Pass processing → Request payload", ()=>{
      console.log({session_id: state.sessionId, model: state.model, provider: state.provider});
    }, true);
    const res = await processPasses(state.sessionId, state.model, state.provider);
    withGroup(`[Flow] Pass processing → Raw response (${res.httpStatus ?? "?"})`, ()=>{
      console.log(res);
    }, true);
    dumpLLMDebug(res.llm_debug);
    if(!res.ok){
      let msg = res.error || "Process failed";
      if(res.needs_api_key) msg += ` — ${providerAuthHint()}`;
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
  const providerSel = el("provider");
  const modelSel = el("model");
  const models = await getModels();
  if(models.ok && models.providers){
    state.providers = models.providers;
    const entries = Object.entries(state.providers);
    entries.forEach(([id, info])=>{
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = info?.label || id;
      providerSel.appendChild(opt);
    });
    const defaultProvider = (models.default_provider && state.providers[models.default_provider])
      ? models.default_provider
      : (entries.length ? entries[0][0] : null);
    if(defaultProvider){
      state.provider = defaultProvider;
      providerSel.value = defaultProvider;
      refreshModelOptions(state.providers[defaultProvider]?.default_model);
      updateModel();
    }
  }
  providerSel.addEventListener("change", updateProvider);
  modelSel.addEventListener("change", updateModel);
  el("uploadBtn").addEventListener("click", onUpload);
  el("testBtn").addEventListener("click", handleTestLLM);

  el("preprocessBtn").addEventListener("click", onPreprocess);
  el("headersBtn").addEventListener("click", onHeaders);
  el("processBtn").addEventListener("click", onProcess);
  log("Boot complete");
}

boot();
