/* Pipeline VM coordinating status + results. */

import PassResultModel from "../models/PassResultModel.js";

export class PipelineVM {
  constructor(apiClient) {
    this.api = apiClient;
    this.docId = "";
    this.passResults = [];
    this.error = null;
  }

  async refresh(docId) {
    this.error = null;
    try {
      const statusPayload = await this.api.status(docId);
      if (statusPayload.offline) {
        return statusPayload;
      }
      this.docId = statusPayload.doc_id || docId;
      const resultsPayload = await this.api.results(this.docId);
      if (resultsPayload.offline) {
        return resultsPayload;
      }
      this.passResults = Object.entries(resultsPayload.passes || {}).map(
        ([name, payload]) => new PassResultModel({ name, payload })
      );
      return { status: statusPayload, results: resultsPayload };
    } catch (err) {
      this.error = err;
      throw err;
    }
  }
}

export default PipelineVM;
