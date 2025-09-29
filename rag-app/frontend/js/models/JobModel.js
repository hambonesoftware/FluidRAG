/** Represents pipeline job state. */

export class JobModel {
  constructor({ docId = "", status = "idle", passes = {}, error = null } = {}) {
    this.docId = docId;
    this.status = status;
    this.passes = passes;
    this.error = error;
    this.lastUpdated = new Date();
  }

  markRunning() {
    this.status = "running";
    this.error = null;
    this.lastUpdated = new Date();
  }

  markError(err) {
    this.status = "error";
    this.error = err;
    this.lastUpdated = new Date();
  }

  markOffline() {
    this.status = "offline";
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

  get isCompleted() {
    return this.status === "completed";
  }
}

export default JobModel;
