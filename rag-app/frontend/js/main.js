import ApiClient from "./apiClient.js";
import UploadVM from "./viewmodels/UploadVM.js";
import PipelineVM from "./viewmodels/PipelineVM.js";
import UploadView from "./views/UploadView.js";
import PipelineView from "./views/PipelineView.js";

const button = document.getElementById("ping-backend");
const output = document.getElementById("health-response");

function isOffline() {
  const meta = document.querySelector('meta[name="fluidrag-offline"]');
  return (
    meta && String(meta.getAttribute("content")).toLowerCase() === "true"
  );
}

const offline = isOffline();
const offlineNotice = document.getElementById("offlineNotice");
if (offline && offlineNotice) {
  offlineNotice.style.display = "block";
}

const backendPort = document.body.dataset.backendPort || "8000";
const backendHost = window.location.hostname || "localhost";
const backendProtocol = window.location.protocol.startsWith("http")
  ? window.location.protocol
  : "http:";
const healthEndpoint = `${backendProtocol}//${backendHost}:${backendPort}/health`;

async function pingBackend() {
  if (offline) {
    console.log("Offline mode: skipping network request");
    if (output) {
      output.textContent = "Offline mode: skipping network request";
    }
    return;
  }

  if (output) {
    output.textContent = "Pinging backend...";
  }
  try {
    const response = await fetch(healthEndpoint);
    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }
    const payload = await response.json();
    if (output) {
      output.textContent = JSON.stringify(payload, null, 2);
    }
  } catch (error) {
    if (output) {
      output.textContent = `Error: ${error.message}`;
    }
  }
}

if (button) {
  button.addEventListener("click", pingBackend);
}

const apiClient = new ApiClient({
  baseUrl: `${backendProtocol}//${backendHost}:${backendPort}`,
});
const pipelineRoot = document.querySelector("[data-pipeline-root]");
const uploadRoot = document.querySelector("[data-upload-root]");
if (pipelineRoot) {
  const pipelineVM = new PipelineVM(apiClient);
  const pipelineView = new PipelineView(pipelineVM, pipelineRoot);
  if (uploadRoot) {
    const uploadVM = new UploadVM(apiClient);
    new UploadView(uploadVM, uploadRoot, { pipelineView });
  }
}
