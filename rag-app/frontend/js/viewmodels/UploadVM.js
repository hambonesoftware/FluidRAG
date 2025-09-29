/** Upload view-model; exposes state/actions. */

import JobModel from "../models/JobModel.js";

export class UploadVM {
  constructor(apiClient) {
    this.api = apiClient;
    this.job = new JobModel();
    this.loading = false;
    this.error = null;
  }

  async run({ fileId, fileName } = {}) {
    if (this.loading) {
      return null;
    }
    this.loading = true;
    this.error = null;
    this.job.markRunning();
    try {
      const response = await this.api.runPipeline({ fileId, fileName });
      if (response && response.offline) {
        this.job.markOffline();
        return response;
      }
      this.job.updateFromStatus({
        doc_id: response?.doc_id,
        passes: response?.passes?.passes || {},
        status: "completed",
      });
      return response;
    } catch (err) {
      this.error = err;
      this.job.markError(err);
      throw err;
    } finally {
      this.loading = false;
    }
  }
}

export default UploadVM;
