/* Pipeline job view model. */

export class JobModel {
  constructor({ docId = "", status = "idle", passes = {} } = {}) {
    this.docId = docId;
    this.status = status;
    this.passes = passes;
    this.lastUpdated = new Date();
  }

  updateFromStatus(payload) {
    if (!payload) return;
    this.status = payload.status || this.status;
    if (payload.doc_id) {
      this.docId = payload.doc_id;
    }
    if (payload.passes) {
      this.passes = payload.passes;
    }
    this.lastUpdated = new Date();
  }
}

export default JobModel;
