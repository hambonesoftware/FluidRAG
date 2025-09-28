/* Model representing a single pass result. */

export class PassResultModel {
  constructor({ name, payload }) {
    this.name = name;
    this.payload = payload || {};
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
}

export default PassResultModel;
