/* eslint-disable no-underscore-dangle */
/** Pipeline view-model; orchestration from UI. */

import PassResultModel from "../models/PassResultModel.js";

const DEFAULT_INTERVAL = 2000;

export class PipelineVM {
  constructor(apiClient, { pollIntervalMs = DEFAULT_INTERVAL } = {}) {
    this.api = apiClient;
    this.docId = "";
    this.passResults = [];
    this.passManifest = {};
    this.error = null;
    this.isPolling = false;
    this.lastStatus = null;
    this.pollIntervalMs = pollIntervalMs;
    this._pollTimer = null;
  }

  async refresh(docId) {
    const targetDoc = docId || this.docId;
    if (!targetDoc) {
      return null;
    }
    this.error = null;
    try {
      const statusPayload = await this.api.status(targetDoc);
      if (statusPayload && statusPayload.offline) {
        this.lastStatus = statusPayload;
        return statusPayload;
      }
      this.docId = statusPayload.doc_id || targetDoc;
      this.lastStatus = statusPayload;
      const resultsPayload = await this.api.results(this.docId);
      if (resultsPayload && resultsPayload.offline) {
        return resultsPayload;
      }
      const manifestPasses = resultsPayload?.manifest?.passes || {};
      this.passManifest = manifestPasses;
      this.passResults = Object.entries(resultsPayload.passes || {}).map(
        ([name, payload]) =>
          new PassResultModel({
            name,
            payload,
            artifactPath: manifestPasses[name] || null,
          })
      );
      return { status: statusPayload, results: resultsPayload };
    } catch (err) {
      this.error = err;
      throw err;
    }
  }

  stopPolling() {
    this.isPolling = false;
    if (this._pollTimer) {
      clearTimeout(this._pollTimer);
      this._pollTimer = null;
    }
  }

  get progressPercent() {
    if (this.passResults.length > 0) {
      return 100;
    }
    if (this.lastStatus?.pipeline_audit?.status) {
      return 95;
    }
    if (this.passManifest && Object.keys(this.passManifest).length > 0) {
      return 80;
    }
    if (this.lastStatus) {
      return 40;
    }
    return 0;
  }
}

/** Poll status and update observable state. */
export async function pollProgress(docId, options = {}) {
  if (!docId) {
    throw new Error("docId is required to poll");
  }
  const {
    intervalMs,
    onUpdate,
    signal,
  } = options;
  const delay =
    typeof intervalMs === "number" ? Math.max(intervalMs, 0) : this.pollIntervalMs;
  this.stopPolling();
  this.isPolling = true;
  this.docId = docId;

  const shouldStop = () => {
    if (signal?.aborted) {
      return true;
    }
    if (this.passResults.length > 0) {
      return true;
    }
    if (this.lastStatus?.pipeline_audit?.status) {
      return true;
    }
    return false;
  };

  try {
    while (this.isPolling) {
      if (signal?.aborted) {
        break;
      }
      const payload = await this.refresh(this.docId);
      if (payload && payload.offline) {
        this.stopPolling();
        return payload;
      }
      if (typeof onUpdate === "function") {
        onUpdate({
          docId: this.docId,
          status: this.lastStatus,
          passResults: this.passResults,
        });
      }
      if (shouldStop()) {
        this.stopPolling();
        return { status: this.lastStatus, results: this.passResults };
      }
      if (delay === 0) {
        await Promise.resolve();
      } else {
        await new Promise((resolve) => {
          this._pollTimer = setTimeout(resolve, delay);
        });
      }
    }
  } finally {
    this.stopPolling();
  }
  return { status: this.lastStatus, results: this.passResults };
}

PipelineVM.prototype.pollProgress = pollProgress;

export default PipelineVM;
