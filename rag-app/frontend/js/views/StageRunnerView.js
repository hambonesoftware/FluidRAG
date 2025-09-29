/** Manual stage controls view. */

export class StageRunnerView {
  constructor(vm, root, { pipelineView = null, getInputValue = null } = {}) {
    this.vm = vm;
    this.root = root;
    this.pipelineView = pipelineView;
    this.getInputValue = typeof getInputValue === "function" ? getInputValue : () => "";

    this.docDisplay = root ? root.querySelector("[data-stage-doc]") : null;

    this.uploadButton = root ? root.querySelector("[data-stage-upload-run]") : null;
    this.uploadStatus = root ? root.querySelector("[data-stage-upload-status]") : null;
    this.uploadDetails = root ? root.querySelector("[data-stage-upload-details]") : null;
    this.uploadDoc = root ? root.querySelector("[data-stage-upload-doc]") : null;
    this.uploadPath = root ? root.querySelector("[data-stage-upload-path]") : null;
    this.uploadManifest = root
      ? root.querySelector("[data-stage-upload-manifest]")
      : null;

    this.preprocessButton = root
      ? root.querySelector("[data-stage-preprocess-run]")
      : null;
    this.preprocessStatus = root
      ? root.querySelector("[data-stage-preprocess-status]")
      : null;
    this.preprocessDetails = root
      ? root.querySelector("[data-stage-preprocess-details]")
      : null;
    this.preprocessParse = root
      ? root.querySelector("[data-stage-preprocess-parse]")
      : null;
    this.preprocessChunks = root
      ? root.querySelector("[data-stage-preprocess-chunks]")
      : null;

    this.headersButton = root ? root.querySelector("[data-stage-headers-run]") : null;
    this.headersStatus = root ? root.querySelector("[data-stage-headers-status]") : null;
    this.headersDetails = root
      ? root.querySelector("[data-stage-headers-details]")
      : null;
    this.headersPath = root ? root.querySelector("[data-stage-headers-path]") : null;
    this.headersCount = root
      ? root.querySelector("[data-stage-headers-count]")
      : null;

    this.passesButton = root ? root.querySelector("[data-stage-passes-run]") : null;
    this.passesStatus = root ? root.querySelector("[data-stage-passes-status]") : null;
    this.passesDetails = root
      ? root.querySelector("[data-stage-passes-details]")
      : null;
    this.passesManifest = root
      ? root.querySelector("[data-stage-passes-manifest]")
      : null;
    this.passesCount = root
      ? root.querySelector("[data-stage-passes-count]")
      : null;

    this._bindEvents();
    this.render();
  }

  _bindEvents() {
    if (this.uploadButton) {
      this.uploadButton.addEventListener("click", () => {
        void this._handleUpload();
      });
    }
    if (this.preprocessButton) {
      this.preprocessButton.addEventListener("click", () => {
        void this._handlePreprocess();
      });
    }
    if (this.headersButton) {
      this.headersButton.addEventListener("click", () => {
        void this._handleHeaders();
      });
    }
    if (this.passesButton) {
      this.passesButton.addEventListener("click", () => {
        void this._handlePasses();
      });
    }
  }

  _setText(node, value) {
    if (node) {
      node.textContent = value;
    }
  }

  _toggle(node, shouldShow) {
    if (node) {
      node.hidden = !shouldShow;
    }
  }

  _formatStatus(stageState) {
    if (!stageState) {
      return "Idle";
    }
    if (stageState.status === "error" && stageState.error) {
      return `Error: ${stageState.error.message || String(stageState.error)}`;
    }
    switch (stageState.status) {
      case "running":
        return "Running...";
      case "completed":
        return "Completed";
      case "offline":
        return "Offline mode";
      case "idle":
      default:
        return "Idle";
    }
  }

  _persistDocId(docId) {
    if (!docId) {
      return;
    }
    try {
      window.localStorage.setItem("fluidrag:lastDocId", docId);
    } catch (err) {
      console.warn("Unable to persist doc id", err);
    }
  }

  async _handleUpload() {
    if (!this.uploadButton) {
      return;
    }
    const source = this.getInputValue() || "";
    if (!source.trim()) {
      this._setText(this.uploadStatus, "Enter a document path or ID.");
      return;
    }
    this.uploadButton.disabled = true;
    const promise = this.vm.runUpload({ fileName: source.trim(), fileId: null });
    this.render();
    try {
      const response = await promise;
      if (!response?.offline && this.vm.docId) {
        this._persistDocId(this.vm.docId);
      }
    } catch (err) {
      console.warn("Upload stage failed", err);
    } finally {
      this.uploadButton.disabled = false;
      this.render();
    }
  }

  async _handlePreprocess() {
    if (!this.preprocessButton) {
      return;
    }
    this.preprocessButton.disabled = true;
    const promise = this.vm.runPreprocess();
    this.render();
    try {
      await promise;
    } catch (err) {
      console.warn("Preprocess stage failed", err);
    } finally {
      this.preprocessButton.disabled = false;
      this.render();
    }
  }

  async _handleHeaders() {
    if (!this.headersButton) {
      return;
    }
    this.headersButton.disabled = true;
    const promise = this.vm.runHeaders();
    this.render();
    try {
      await promise;
    } catch (err) {
      console.warn("Header stage failed", err);
    } finally {
      this.headersButton.disabled = false;
      this.render();
    }
  }

  async _handlePasses() {
    if (!this.passesButton) {
      return;
    }
    this.passesButton.disabled = true;
    const promise = this.vm.runPasses();
    this.render();
    try {
      const payload = await promise;
      if (!payload?.offline && this.pipelineView && this.vm.docId) {
        void this.pipelineView.refresh(this.vm.docId);
      }
    } catch (err) {
      console.warn("Pass stage failed", err);
    } finally {
      this.passesButton.disabled = false;
      this.render();
    }
  }

  render() {
    if (!this.root) {
      return;
    }
    const state = this.vm.state;
    this._setText(this.docDisplay, state.docId || "—");

    this._setText(this.uploadStatus, this._formatStatus(state.upload));
    const hasUploadPayload = Boolean(
      state.upload?.payload && !state.upload.payload?.offline
    );
    this._toggle(this.uploadDetails, hasUploadPayload);
    if (hasUploadPayload) {
      this._setText(this.uploadDoc, state.docId || "—");
      this._setText(this.uploadPath, state.normalizedArtifact || "—");
      this._setText(
        this.uploadManifest,
        state.upload?.payload?.manifest_path || "—"
      );
    }

    this._setText(this.preprocessStatus, this._formatStatus(state.preprocess));
    const preprocessPayload = state.preprocess?.payload || {};
    const hasPreprocessPayload = Boolean(
      preprocessPayload.parse && !preprocessPayload.parse?.offline
    );
    this._toggle(this.preprocessDetails, hasPreprocessPayload);
    if (hasPreprocessPayload) {
      this._setText(
        this.preprocessParse,
        preprocessPayload.parse?.enriched_path || state.enrichedArtifact || "—"
      );
      this._setText(
        this.preprocessChunks,
        preprocessPayload.chunk?.chunks_path || state.chunkArtifact || "—"
      );
    }

    this._setText(this.headersStatus, this._formatStatus(state.headers));
    const hasHeadersPayload = Boolean(
      state.headers?.payload && !state.headers.payload?.offline
    );
    this._toggle(this.headersDetails, hasHeadersPayload);
    if (hasHeadersPayload) {
      this._setText(
        this.headersPath,
        state.headers.payload?.header_chunks_path || state.headerChunksArtifact || "—"
      );
      this._setText(
        this.headersCount,
        String(state.headers.payload?.header_count ?? "—")
      );
    }

    this._setText(this.passesStatus, this._formatStatus(state.passes));
    const hasPassesPayload = Boolean(
      state.passes?.payload && !state.passes.payload?.offline
    );
    this._toggle(this.passesDetails, hasPassesPayload);
    if (hasPassesPayload) {
      const passNames = Object.keys(state.passes.payload?.passes || {});
      this._setText(this.passesManifest, state.passes.payload?.manifest_path || "—");
      this._setText(this.passesCount, String(passNames.length));
    }

    if (this.uploadButton) {
      this.uploadButton.disabled = state.upload.status === "running";
    }
    if (this.preprocessButton) {
      const canRun = Boolean(state.normalizedArtifact);
      this.preprocessButton.disabled =
        !canRun || state.preprocess.status === "running";
    }
    if (this.headersButton) {
      const canRun = Boolean(state.chunkArtifact);
      this.headersButton.disabled = !canRun || state.headers.status === "running";
    }
    if (this.passesButton) {
      const canRun = Boolean(state.headerChunksArtifact);
      this.passesButton.disabled = !canRun || state.passes.status === "running";
    }
  }
}

export default StageRunnerView;
