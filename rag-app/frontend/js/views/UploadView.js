/** Upload UI view; DOM-only. */

export class UploadView {
  constructor(vm, root, { pipelineView, onRun } = {}) {
    this.vm = vm;
    this.root = root;
    this.pipelineView = pipelineView || null;
    this.onRun = onRun || null;
    this.input = root ? root.querySelector("[data-upload-input]") : null;
    this.statusEl = root ? root.querySelector("[data-upload-status]") : null;
    this.button = root ? root.querySelector("[data-upload-run]") : null;

    if (this.root) {
      this.root.addEventListener("submit", (event) => {
        event.preventDefault();
        void this.submit();
      });
    }

    if (this.input) {
      this.input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          void this.submit();
        }
      });
    }
  }

  _setStatus(message) {
    if (this.statusEl) {
      this.statusEl.textContent = message;
    }
  }

  _persistDocId(docId) {
    try {
      window.localStorage.setItem("fluidrag:lastDocId", docId);
    } catch (err) {
      console.warn("Unable to persist doc id", err);
    }
  }

  async submit() {
    if (!this.vm || this.vm.loading) {
      return null;
    }
    const value = this.input ? this.input.value.trim() : "";
    if (!value) {
      this._setStatus("Enter a document path or id.");
      return null;
    }
    try {
      this._setStatus("Running pipeline...");
      if (this.button) {
        this.button.disabled = true;
      }
      const response = await this.vm.run({ fileName: value, fileId: null });
      if (!response) {
        return null;
      }
      if (response.offline) {
        this._setStatus("Offline mode — no network calls made.");
        return response;
      }
      this._setStatus(`Completed. Doc ${this.vm.job.docId}`);
      if (this.pipelineView && this.vm.job.docId) {
        this.pipelineView.poll(this.vm.job.docId).catch(() => {
          /* swallow */
        });
      }
      if (this.onRun && this.vm.job.docId) {
        this.onRun(this.vm.job.docId, response);
      }
      if (this.vm.job.docId) {
        this._persistDocId(this.vm.job.docId);
      }
      if (this.input) {
        this.input.value = "";
      }
      return response;
    } catch (err) {
      this._setStatus(`Error: ${err.message}`);
      throw err;
    } finally {
      if (this.button) {
        this.button.disabled = false;
      }
    }
  }
}

export default UploadView;
