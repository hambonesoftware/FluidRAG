export const el = (id) => document.getElementById(id);

export const state = {
  sessionId: null,
  provider: null,
  model: null,
  fileHash: null,
  hasPre: false,
  hasLocalHeaders: false,
  hasHeaders: false,
  localHeaders: [],
  rows: [],
  providers: {},
  cacheInfo: { preprocess: false, headers: false, passes: [] }
};

export function providerLabel(providerId = state.provider) {
  if (!providerId) return "provider";
  const info = state.providers?.[providerId];
  return info?.label || providerId;
}

export function providerAuthHint() {
  if (state.provider === "openrouter") return "set OPENROUTER_API_KEY";
  if (state.provider === "llamacpp") return "ensure llama.cpp endpoint credentials are valid";
  return "verify LLM credentials";
}

export function refreshModelOptions(preferredModel = null) {
  const modelSel = el("model");
  if (!modelSel) {
    console.warn("[UI] Missing model select element");
    return;
  }
  modelSel.innerHTML = "";
  const providerId = state.provider;
  const info = state.providers?.[providerId];
  if (!info) {
    state.model = null;
    console.warn("[State] Missing provider info; unable to populate models", { providerId });
    return;
  }
  const models = Array.isArray(info.models) ? info.models : [];
  models.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    modelSel.appendChild(opt);
  });
  let selected = null;
  if (preferredModel && models.includes(preferredModel)) {
    selected = preferredModel;
  } else if (info.default_model && models.includes(info.default_model)) {
    selected = info.default_model;
  } else if (models.length > 0) {
    selected = models[0];
  }
  if (selected) {
    modelSel.value = selected;
    state.model = selected;
  } else {
    state.model = null;
  }

  console.debug("[State] Model options updated", { provider: providerId, model: state.model });
}

export function updateModel() {
  const modelSel = el("model");
  if (!modelSel) {
    console.warn("[UI] Missing model select element");
    state.model = null;
    return;
  }
  state.model = modelSel.value || null;
  console.debug("[State] Model updated", { provider: state.provider, model: state.model });
}

export function updateProvider() {
  const providerSel = el("provider");
  if (!providerSel) {
    console.warn("[UI] Missing provider select element");
    return;
  }
  const newProvider = providerSel.value;
  if (!newProvider) return;
  if (!state.providers?.[newProvider]) {
    console.warn("[State] Unknown provider selected", { newProvider });
    return;
  }
  state.provider = newProvider;
  console.debug("[State] Provider updated", { provider: state.provider });
  refreshModelOptions();
  updateModel();
}

export function requireSession() {
  if (!state.sessionId) {
    console.warn("[Guard] Session required but missing", { state: { ...state } });
    alert("Upload a document first.");
    return false;
  }
  return true;
}

export function resetCacheState() {
  state.fileHash = null;
  state.hasPre = false;
  state.hasLocalHeaders = false;
  state.hasHeaders = false;
  state.localHeaders = [];
  state.rows = [];
  state.cacheInfo = { preprocess: false, headers: false, passes: [] };
}
