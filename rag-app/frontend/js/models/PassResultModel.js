/** Represents a pass result. */

export class PassResultModel {
  constructor({ name, payload, artifactPath = null }) {
    this.name = name;
    this.payload = payload || {};
    this.artifactPath = artifactPath;
  }

  get answer() {
    return this.payload.answer || "";
  }

  get citations() {
    return this.payload.citations || [];
  }

  get retrieval() {
    return this.payload.retrieval || [];
  }

  get hasCitations() {
    return this.citations.length > 0;
  }

  get hasRetrieval() {
    return this.retrieval.length > 0;
  }
}

export default PassResultModel;
