/* View for pipeline status + pass results. */

import ResultsView from "./ResultsView.js";

export class PipelineView {
  constructor(vm, root) {
    this.vm = vm;
    this.root = root;
    this.statusEl = root ? root.querySelector("[data-pipeline-status]") : null;
    this.refreshButton = root
      ? root.querySelector("[data-pipeline-refresh]")
      : null;
    this.resultsRoot = root ? root.querySelector("[data-pass-results]") : null;
    this.resultsView = new ResultsView(this.resultsRoot);
    if (this.refreshButton) {
      this.refreshButton.addEventListener("click", () => {
        const docId = this.vm.docId || this.root.dataset.docId || "";
        if (docId) {
          void this.refresh(docId);
        }
      });
    }
  }

  async refresh(docId) {
    if (!docId) return;
    if (this.statusEl) {
      this.statusEl.textContent = "Refreshing...";
    }
    try {
      const payload = await this.vm.refresh(docId);
      if (payload && payload.offline && this.statusEl) {
        this.statusEl.textContent = "Offline mode";
        return;
      }
      if (this.statusEl) {
        this.statusEl.textContent = `Updated: ${new Date().toLocaleTimeString()}`;
      }
      this.resultsView.render(this.vm.passResults);
    } catch (err) {
      if (this.statusEl) {
        this.statusEl.textContent = `Error: ${err.message}`;
      }
    }
  }
}

export default PipelineView;
