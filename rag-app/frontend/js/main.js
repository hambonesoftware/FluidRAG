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
