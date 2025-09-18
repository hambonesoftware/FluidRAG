import { getModels, processFile } from "./api.mjs";
import { renderTable } from "./ui.mjs";

const el = (id)=>document.getElementById(id);
const log = (msg)=>{
  const pre = el("log");
  const line = `[UI] ${new Date().toLocaleTimeString()} ${msg}`;
  console.log(line);
  pre.textContent += line + "\n";
  pre.scrollTop = pre.scrollHeight;
};

async function boot(){
  log("Boot start");
  const modelSel = el("model");
  const { ok, models } = await getModels();
  if(ok){
    models.forEach(m=>{
      const opt = document.createElement("option");
      opt.value = m; opt.textContent = m;
      modelSel.appendChild(opt);
    });
  }
  log("Models loaded");
  el("runBtn").addEventListener("click", onRun);
}

async function onRun(){
  const file = el("file").files[0];
  const model = el("model").value;
  if(!file){ alert("Pick a document first."); return; }
  el("status").textContent = "Processing… please watch the log.";
  log(`Begin process: ${file.name}, model=${model}`);

  const res = await processFile(file, model, (pct)=>{});
  if(Array.isArray(res?.llm_debug)){
    res.llm_debug.forEach((entry, idx)=>{
      const label = entry?.model || `LLM call ${idx+1}`;
      console.groupCollapsed(`[LLM Request ${idx+1}] ${label}`);
      console.log(entry?.request || {});
      console.groupEnd();
      console.groupCollapsed(`[LLM Response ${idx+1}] ${label}`);
      console.log(entry?.response || {});
      console.groupEnd();
    });
  }
  if(!res.ok){
    el("status").textContent = "Error: " + (res.error||"Unknown");
    log("Process error: " + (res.error||"unknown"));
    return;
  }

  el("status").textContent = `Done • rows=${res.rows.length} • total=${res.metrics_ms.total} ms`;
  renderTable(el("tableWrap"), res.rows);

  const a = document.createElement("a");
  const blob = b64ToBlob(res.csv_base64, "text/csv");
  const url = URL.createObjectURL(blob);
  a.href = url; a.download = res.filename;
  a.textContent = "Download CSV";
  const wrap = el("downloadWrap");
  wrap.innerHTML = ""; wrap.appendChild(a); wrap.classList.remove("hidden");

  log("Process complete");
}

function b64ToBlob(b64, mime){
  const b = atob(b64);
  const arr = new Uint8Array(b.length);
  for(let i=0;i<b.length;i++) arr[i] = b.charCodeAt(i);
  return new Blob([arr], {type: mime});
}

boot();
