/** Fetch wrapper for orchestrator endpoints. */

function detectOffline() {
  const meta = document.querySelector('meta[name="fluidrag-offline"]');
  return meta && String(meta.getAttribute("content")).toLowerCase() === "true";
}

function resolveBaseUrl(baseUrl) {
  if (baseUrl) {
    return baseUrl;
  }
  const host = window.location.hostname || "localhost";
  const protocol = window.location.protocol.startsWith("http")
    ? window.location.protocol
    : "http:";
  const port = document.body?.dataset?.backendPort || "8000";
  return `${protocol}//${host}:${port}`;
}

export class ApiClient {
  /** Initialize with base URL. */
  constructor({ baseUrl } = {}) {
    this.baseUrl = resolveBaseUrl(baseUrl);
    this.offline = detectOffline();
  }

  _fullPath(path) {
    const normalized = path.startsWith("/") ? path : `/${path}`;
    return `${this.baseUrl}${normalized}`;
  }

  async _request(path, options = {}) {
    if (this.offline) {
      return { offline: true };
    }
    const response = await fetch(this._fullPath(path), {
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
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return response.json();
    }
    return response.text();
  }

  /** POST pipeline run. */
  async runPipeline({ fileId, fileName } = {}) {
    return this._request("/pipeline/run", {
      method: "POST",
      body: JSON.stringify({ file_id: fileId, file_name: fileName }),
    });
  }

  /** GET status. */
  async status(docId) {
    return this._request(`/pipeline/status/${encodeURIComponent(docId)}`);
  }

  /** GET results. */
  async results(docId) {
    return this._request(`/pipeline/results/${encodeURIComponent(docId)}`);
  }

  /** Resolve artifact download URL. */
  artifact(path) {
    if (this.offline) {
      return { offline: true };
    }
    if (!path) {
      return null;
    }
    const url = new URL(this._fullPath("/pipeline/artifacts"));
    url.searchParams.set("path", path);
    return url.toString();
  }
}

export default ApiClient;
