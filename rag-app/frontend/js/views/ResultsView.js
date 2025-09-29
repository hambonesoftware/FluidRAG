/** Results UI view. */

export class ResultsView {
  constructor(root, { apiClient } = {}) {
    this.root = root;
    this.api = apiClient || null;
  }

  render(passResults, manifest = {}) {
    if (!this.root) {
      return;
    }
    this.root.innerHTML = "";
    passResults.forEach((result) => {
      const section = document.createElement("section");
      section.className = "pass-result";

      const title = document.createElement("h3");
      title.textContent = result.name;
      section.appendChild(title);

      const answer = document.createElement("p");
      answer.className = "pass-answer";
      answer.textContent = result.answer;
      section.appendChild(answer);

      const metadata = document.createElement("div");
      metadata.className = "pass-metadata";

      if (result.hasCitations) {
        const citationsList = document.createElement("ul");
        citationsList.className = "pass-citations";
        result.citations.forEach((citation) => {
          const item = document.createElement("li");
          const header = citation.header_path ? ` @ ${citation.header_path}` : "";
          item.textContent = `${citation.chunk_id}${header}`;
          citationsList.appendChild(item);
        });
        metadata.appendChild(citationsList);
      }

      if (result.hasRetrieval) {
        const retrievalList = document.createElement("ul");
        retrievalList.className = "pass-retrieval";
        result.retrieval.slice(0, 5).forEach((trace) => {
          const item = document.createElement("li");
          item.textContent = `${trace.chunk_id} (${trace.score.toFixed(2)})`;
          retrievalList.appendChild(item);
        });
        metadata.appendChild(retrievalList);
      }

      if (metadata.children.length > 0) {
        section.appendChild(metadata);
      }

      const artifactPath = manifest[result.name] || result.artifactPath;
      if (artifactPath) {
        const actions = document.createElement("div");
        actions.className = "pass-actions";
        const downloadButton = document.createElement("button");
        downloadButton.type = "button";
        downloadButton.textContent = "Download artifact";
        downloadButton.addEventListener("click", () => {
          this.downloadArtifact(artifactPath);
        });
        actions.appendChild(downloadButton);
        section.appendChild(actions);
      }

      this.root.appendChild(section);
    });
  }

  /** Trigger browser download from streaming endpoint. */
  downloadArtifact(path) {
    if (!path || !this.api) {
      this._dispatch("artifact-missing", { path });
      return;
    }
    if (this.api.offline) {
      this._dispatch("artifact-offline", { path });
      return;
    }
    const url = this.api.artifact(path);
    if (!url || typeof url !== "string") {
      this._dispatch("artifact-missing", { path });
      return;
    }
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.target = "_blank";
    anchor.rel = "noopener";
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    try {
      anchor.click();
      this._dispatch("artifact-download", { path, url });
    } finally {
      document.body.removeChild(anchor);
    }
  }

  _dispatch(type, detail) {
    if (this.root && typeof this.root.dispatchEvent === "function") {
      this.root.dispatchEvent({ type, detail });
    }
  }
}

export default ResultsView;
