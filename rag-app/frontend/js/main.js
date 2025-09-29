import ApiClient from "./apiClient.js";
import UploadVM from "./viewmodels/UploadVM.js";
import PipelineVM from "./viewmodels/PipelineVM.js";
import UploadView from "./views/UploadView.js";
import PipelineView from "./views/PipelineView.js";

const button = document.getElementById("ping-backend");
const output = document.getElementById("health-response");

const backendPort = document.body.dataset.backendPort || "8000";
const backendHost = window.location.hostname || "localhost";
const backendProtocol = window.location.protocol.startsWith("http")
  ? window.location.protocol
  : "http:";
const baseUrl = `${backendProtocol}//${backendHost}:${backendPort}`;
const healthEndpoint = `${baseUrl}/health`;

const apiClient = new ApiClient({ baseUrl });
const offline = apiClient.offline;

const offlineNotice = document.getElementById("offlineNotice");
if (offlineNotice) {
  offlineNotice.hidden = !offline;
}

async function pingBackend() {
  if (offline) {
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
  button.addEventListener("click", () => {
    void pingBackend();
  });
}

function restoreLastDocId() {
  try {
    return window.localStorage.getItem("fluidrag:lastDocId");
  } catch (err) {
    console.warn("Unable to read stored doc id", err);
    return null;
  }
}

const pipelineRoot = document.querySelector("[data-pipeline-root]");
const uploadRoot = document.querySelector("[data-upload-root]");
let pipelineView = null;
if (pipelineRoot) {
  const pipelineVM = new PipelineVM(apiClient);
  pipelineView = new PipelineView(pipelineVM, pipelineRoot);
}

if (uploadRoot && pipelineView) {
  const uploadVM = new UploadVM(apiClient);
  new UploadView(uploadVM, uploadRoot, {
    pipelineView,
    onRun: (docId) => {
      if (!offline && docId) {
        pipelineView.poll(docId).catch((err) => {
          console.warn("Polling failed", err);
        });
      }
    },
  });
}

if (pipelineView && !offline) {
  const lastDocId = restoreLastDocId();
  if (lastDocId) {
    pipelineView.poll(lastDocId).catch(() => {
      void pipelineView.refresh(lastDocId);
    });
  }
}
