import { getModels } from "./api.mjs";
import { renderTable } from "./ui.mjs";
import {
  state,
  el,
  refreshModelOptions,
  updateProvider,
  updateModel
} from "./state.mjs";
import { log } from "./logging.mjs";
import {
  onUpload,
  handleTestLLM,
  onPreprocess,
  onHeaders,
  onLocalHeaders,
  onProcess
} from "./flows.mjs";

async function boot() {
  log("Boot start");
  const tableWrap = el("tableWrap");
  if (tableWrap) renderTable(tableWrap, []);
  const providerSel = el("provider");
  const modelSel = el("model");
  if (!providerSel || !modelSel) {
    console.error("[UI] Missing provider/model select elements");
    return;
  }

  const models = await getModels();
  if (models.ok && models.providers) {
    state.providers = models.providers;
    const entries = Object.entries(state.providers);
    entries.forEach(([id, info]) => {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = info?.label || id;
      providerSel.appendChild(opt);
    });
    const defaultProvider = (models.default_provider && state.providers[models.default_provider])
      ? models.default_provider
      : (entries.length ? entries[0][0] : null);
    if (defaultProvider) {
      state.provider = defaultProvider;
      providerSel.value = defaultProvider;
      refreshModelOptions(state.providers[defaultProvider]?.default_model);
      updateModel();
    }
  }

  providerSel.addEventListener("change", updateProvider);
  modelSel.addEventListener("change", updateModel);

  const uploadBtn = el("uploadBtn");
  if (uploadBtn) uploadBtn.addEventListener("click", onUpload);
  const testBtn = el("testBtn");
  if (testBtn) testBtn.addEventListener("click", handleTestLLM);
  const preprocessBtn = el("preprocessBtn");
  if (preprocessBtn) preprocessBtn.addEventListener("click", onPreprocess);
  const localHeadersBtn = el("localHeadersBtn");
  if (localHeadersBtn) localHeadersBtn.addEventListener("click", onLocalHeaders);
  const headersBtn = el("headersBtn");
  if (headersBtn) headersBtn.addEventListener("click", onHeaders);
  const processBtn = el("processBtn");
  if (processBtn) processBtn.addEventListener("click", onProcess);

  log("Boot complete");
}

boot();
