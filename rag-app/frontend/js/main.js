const button = document.getElementById("ping-backend");
const output = document.getElementById("health-response");
const backendPort = document.body.dataset.backendPort || "8000";
const backendHost = window.location.hostname || "localhost";
const backendProtocol = window.location.protocol.startsWith("http")
  ? window.location.protocol
  : "http:";
const healthEndpoint = `${backendProtocol}//${backendHost}:${backendPort}/health`;

async function pingBackend() {
  output.textContent = "Pinging backend...";
  try {
    const response = await fetch(healthEndpoint);
    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }
    const payload = await response.json();
    output.textContent = JSON.stringify(payload, null, 2);
  } catch (error) {
    output.textContent = `Error: ${error.message}`;
  }
}

if (button) {
  button.addEventListener("click", pingBackend);
}
