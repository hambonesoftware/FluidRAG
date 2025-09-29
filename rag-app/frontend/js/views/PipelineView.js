/** Pipeline UI view. */

import ResultsView from "./ResultsView.js";

export class PipelineView {
  constructor(vm, root) {
    this.vm = vm;
    this.root = root;
    this.statusEl = root ? root.querySelector("[data-pipeline-status]") : null;
    this.docEl = root ? root.querySelector("[data-pipeline-doc]") : null;
    this.updatedEl = root ? root.querySelector("[data-pipeline-updated]") : null;
    this.progressEl = root ? root.querySelector("[data-pipeline-progress]") : null;
    this.emptyEl = root ? root.querySelector("[data-pipeline-empty]") : null;
    this.refreshButton = root
      ? root.querySelector("[data-pipeline-refresh]")
      : null;
    this.resultsRoot = root ? root.querySelector("[data-pass-results]") : null;
    this.resultsView = new ResultsView(this.resultsRoot, { apiClient: this.vm.api });
    this.abortController = null;

    if (this.refreshButton) {
      this.refreshButton.addEventListener("click", () => {
        const docId = this.vm.docId || this.root?.dataset?.docId || "";
        if (docId) {
          void this.refresh(docId);
        }
      });
    }
  }

  _setStatus(message) {
    if (this.statusEl) {
      this.statusEl.textContent = message;
    }
  }

  render() {
    if (!this.root) {
      return;
    }
    if (this.docEl) {
      this.docEl.textContent = this.vm.docId || "—";
    }
    if (this.root) {
      this.root.dataset.docId = this.vm.docId || "";
    }
    const statusLabel = this._deriveStatus();
    this._setStatus(statusLabel);
    if (this.updatedEl) {
      const updated = this.vm.lastStatus?.pipeline_audit?.timestamp
        ? new Date(this.vm.lastStatus.pipeline_audit.timestamp)
        : new Date();
      this.updatedEl.textContent = updated.toLocaleTimeString();
    }
    if (this.progressEl) {
      const progress = this.vm.progressPercent;
      this.progressEl.style.width = `${progress}%`;
      this.progressEl.setAttribute("aria-valuenow", String(progress));
    }
    if (this.emptyEl) {
      this.emptyEl.hidden = this.vm.passResults.length > 0;
    }
    this.resultsView.render(this.vm.passResults, this.vm.passManifest);
  }

  _deriveStatus() {
    if (this.vm.error) {
      return `Error: ${this.vm.error.message}`;
    }
    if (this.vm.lastStatus?.pipeline_audit?.status) {
      return this.vm.lastStatus.pipeline_audit.status;
    }
    if (this.vm.isPolling) {
      return "Polling...";
    }
    if (this.vm.passResults.length > 0) {
      return "Completed";
    }
    if (this.vm.lastStatus) {
      return "Processing";
    }
    return "Idle";
  }

  async refresh(docId) {
    const target = docId || this.vm.docId;
    if (!target) {
      return null;
    }
    this._setStatus("Refreshing...");
    try {
      const payload = await this.vm.refresh(target);
      if (payload && payload.offline) {
        this._setStatus("Offline mode");
        return payload;
      }
      this.render();
      return payload;
    } catch (err) {
      this._setStatus(`Error: ${err.message}`);
      throw err;
    }
  }

  async poll(docId) {
    const target = docId || this.vm.docId;
    if (!target) {
      return null;
    }
    this._setStatus("Polling...");
    this.vm.stopPolling();
    if (this.abortController) {
      this.abortController.abort();
    }
    this.abortController = new AbortController();
    try {
      const payload = await this.vm.pollProgress(target, {
        signal: this.abortController.signal,
        onUpdate: () => this.render(),
      });
      if (payload && payload.offline) {
        this._setStatus("Offline mode");
        return payload;
      }
      this.render();
      return payload;
    } catch (err) {
      this._setStatus(`Error: ${err.message}`);
      throw err;
    }
  }

  teardown() {
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
    this.vm.stopPolling();
  }
}

export default PipelineView;
