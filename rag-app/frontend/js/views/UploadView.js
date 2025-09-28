/* View binding for upload/run interactions. */

export class UploadView {
  constructor(vm, root, { pipelineView } = {}) {
    this.vm = vm;
    this.root = root;
    this.pipelineView = pipelineView;
    this.input = root ? root.querySelector("[data-upload-input]") : null;
    this.statusEl = root ? root.querySelector("[data-upload-status]") : null;
    this.button = root ? root.querySelector("[data-upload-run]") : null;
    if (this.button) {
      this.button.addEventListener("click", () => {
        void this.submit();
      });
    }
  }

  async submit() {
    if (!this.vm || this.vm.loading) {
      return;
    }
    const value = this.input ? this.input.value.trim() : "";
    if (!value) {
      if (this.statusEl) {
        this.statusEl.textContent = "Enter a document path or id.";
      }
      return;
    }
    try {
      if (this.statusEl) {
        this.statusEl.textContent = "Running pipeline...";
      }
      const response = await this.vm.run({ fileName: value });
      if (this.statusEl) {
        this.statusEl.textContent = this.vm.job.status;
      }
      if (response && response.doc_id && this.pipelineView) {
        this.pipelineView.refresh(response.doc_id).catch(() => {
          /* no-op */
        });
      }
    } catch (err) {
      if (this.statusEl) {
        this.statusEl.textContent = `Error: ${err.message}`;
      }
    }
  }
}

export default UploadView;
