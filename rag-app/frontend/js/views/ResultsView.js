/* Render pass results into DOM. */

export class ResultsView {
  constructor(root) {
    this.root = root;
  }

  render(passResults) {
    if (!this.root) return;
    this.root.innerHTML = "";
    passResults.forEach((result) => {
      const section = document.createElement("section");
      section.className = "pass-result";
      const title = document.createElement("h3");
      title.textContent = result.name;
      section.appendChild(title);

      const answer = document.createElement("p");
      answer.textContent = result.answer;
      section.appendChild(answer);

      if (result.citations.length) {
        const list = document.createElement("ul");
        result.citations.forEach((citation) => {
          const item = document.createElement("li");
          item.textContent = `${citation.chunk_id} @ ${citation.header_path || ""}`;
          list.appendChild(item);
        });
        section.appendChild(list);
      }
      this.root.appendChild(section);
    });
  }
}

export default ResultsView;
