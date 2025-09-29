/** Manual stage runner view-model. */

export class StageRunnerVM {
  constructor(apiClient) {
    this.api = apiClient;
    this.docId = "";
    this.normalizedArtifact = "";
    this.enrichedArtifact = "";
    this.chunkArtifact = "";
    this.headerChunksArtifact = "";
    this.upload = this._defaultStageState();
    this.preprocess = this._defaultStageState();
    this.headers = this._defaultStageState();
    this.passes = this._defaultStageState();
  }

  _defaultStageState() {
    return {
      status: "idle",
      error: null,
      payload: null,
      lastUpdated: null,
    };
  }

  _resetDownstreamStages() {
    this.preprocess = this._defaultStageState();
    this.headers = this._defaultStageState();
    this.passes = this._defaultStageState();
    this.enrichedArtifact = "";
    this.chunkArtifact = "";
    this.headerChunksArtifact = "";
  }

  _markStage(stage, updates) {
    const current = this[stage] || this._defaultStageState();
    this[stage] = {
      ...current,
      ...updates,
      lastUpdated: new Date(),
    };
  }

  _snapshot(stage) {
    const source = this[stage] || this._defaultStageState();
    return {
      status: source.status,
      error: source.error,
      payload: source.payload,
      lastUpdated: source.lastUpdated,
    };
  }

  get state() {
    return {
      docId: this.docId,
      normalizedArtifact: this.normalizedArtifact,
      enrichedArtifact: this.enrichedArtifact,
      chunkArtifact: this.chunkArtifact,
      headerChunksArtifact: this.headerChunksArtifact,
      upload: this._snapshot("upload"),
      preprocess: this._snapshot("preprocess"),
      headers: this._snapshot("headers"),
      passes: this._snapshot("passes"),
    };
  }

  async runUpload({ fileId = null, fileName = "" } = {}) {
    this._markStage("upload", { status: "running", error: null });
    try {
      const response = await this.api.normalizeUpload({ fileId, fileName });
      if (response && response.offline) {
        this._markStage("upload", { status: "offline", payload: response });
        return response;
      }
      this.docId = response?.doc_id || "";
      this.normalizedArtifact = response?.normalized_path || "";
      this._resetDownstreamStages();
      this._markStage("upload", { status: "completed", payload: response });
      return response;
    } catch (err) {
      this._markStage("upload", { status: "error", error: err });
      throw err;
    }
  }

  async runPreprocess() {
    if (!this.docId || !this.normalizedArtifact) {
      const error = new Error("Run the upload stage first.");
      this._markStage("preprocess", { status: "error", error });
      throw error;
    }
    this._markStage("preprocess", { status: "running", error: null });
    let parseResult = null;
    let chunkResult = null;
    try {
      parseResult = await this.api.parseDocument({
        docId: this.docId,
        normalizeArtifact: this.normalizedArtifact,
      });
      if (parseResult && parseResult.offline) {
        this._markStage("preprocess", {
          status: "offline",
          payload: { parse: parseResult, chunk: null },
        });
        return { parse: parseResult, chunk: null };
      }
      this.enrichedArtifact = parseResult?.enriched_path || "";
      chunkResult = await this.api.chunkDocument({
        docId: this.docId,
        normalizeArtifact: this.enrichedArtifact,
      });
      if (chunkResult && chunkResult.offline) {
        this._markStage("preprocess", {
          status: "offline",
          payload: { parse: parseResult, chunk: chunkResult },
        });
        return { parse: parseResult, chunk: chunkResult };
      }
      this.chunkArtifact = chunkResult?.chunks_path || "";
      this._markStage("preprocess", {
        status: "completed",
        payload: { parse: parseResult, chunk: chunkResult },
      });
      return { parse: parseResult, chunk: chunkResult };
    } catch (err) {
      this._markStage("preprocess", {
        status: "error",
        error: err,
        payload: { parse: parseResult, chunk: chunkResult },
      });
      throw err;
    }
  }

  async runHeaders() {
    if (!this.docId || !this.chunkArtifact) {
      const error = new Error("Run preprocess to generate chunks first.");
      this._markStage("headers", { status: "error", error });
      throw error;
    }
    this._markStage("headers", { status: "running", error: null });
    try {
      const response = await this.api.joinHeaders({
        docId: this.docId,
        chunksArtifact: this.chunkArtifact,
      });
      if (response && response.offline) {
        this._markStage("headers", { status: "offline", payload: response });
        return response;
      }
      this.headerChunksArtifact = response?.header_chunks_path || "";
      this._markStage("headers", { status: "completed", payload: response });
      return response;
    } catch (err) {
      this._markStage("headers", { status: "error", error: err });
      throw err;
    }
  }

  async runPasses() {
    if (!this.docId || !this.headerChunksArtifact) {
      const error = new Error("Run header search before executing passes.");
      this._markStage("passes", { status: "error", error });
      throw error;
    }
    this._markStage("passes", { status: "running", error: null });
    try {
      const response = await this.api.runPasses({
        docId: this.docId,
        rechunkArtifact: this.headerChunksArtifact,
      });
      if (response && response.offline) {
        this._markStage("passes", { status: "offline", payload: response });
        return response;
      }
      this._markStage("passes", { status: "completed", payload: response });
      return response;
    } catch (err) {
      this._markStage("passes", { status: "error", error: err });
      throw err;
    }
  }
}

export default StageRunnerVM;
