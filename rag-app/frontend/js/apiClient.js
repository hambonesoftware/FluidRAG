/* Fetch wrapper for orchestrator endpoints. */

function detectOffline() {
  const meta = document.querySelector('meta[name="fluidrag-offline"]');
  return meta && String(meta.getAttribute("content")).toLowerCase() === "true";
}

export class ApiClient {
  constructor({ baseUrl } = {}) {
    /* Initialize with base URL. */
    const host = window.location.hostname || "localhost";
    const protocol = window.location.protocol.startsWith("http")
      ? window.location.protocol
      : "http:";
    const port = document.body.dataset.backendPort || "8000";
    this.baseUrl = baseUrl || `${protocol}//${host}:${port}`;
    this.offline = detectOffline();
  }

  async _request(path, options = {}) {
    if (this.offline) {
      return { offline: true };
    }
    const response = await fetch(`${this.baseUrl}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`Request failed: ${response.status} ${detail}`);
    }
    if (response.status === 204) {
      return {};
    }
    return response.json();
  }

  async runPipeline({ fileId, fileName }) {
    /* POST pipeline run. */
    return this._request("/pipeline/run", {
      method: "POST",
      body: JSON.stringify({ file_id: fileId, file_name: fileName }),
    });
  }

  async status(docId) {
    /* GET status. */
    return this._request(`/pipeline/status/${encodeURIComponent(docId)}`);
  }

  async results(docId) {
    /* GET results. */
    return this._request(`/pipeline/results/${encodeURIComponent(docId)}`);
  }
}

export default ApiClient;
