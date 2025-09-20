export function renderTable(target, rows){
  if(!Array.isArray(rows) || rows.length === 0){
    target.innerHTML = '<div class="empty">No specifications yet. Run the passes to populate results.</div>';
    return;
  }
  const cols = ["Document","(Sub)Section #","(Sub)Section Name","Specification","Pass"];
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const trh = document.createElement("tr");
  cols.forEach(c=>{
    const th = document.createElement("th");
    th.textContent = c; trh.appendChild(th);
  });
  thead.appendChild(trh);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  rows.forEach(r=>{
    const tr = document.createElement("tr");
    cols.forEach(c=>{
      const td = document.createElement("td");
      td.textContent = r[c] ?? "";
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  target.innerHTML = "";
  target.appendChild(table);
}

export function renderHeaderPreview(target, preview){
  if(!Array.isArray(preview) || preview.length === 0){
    target.innerHTML = "";
    return;
  }
  target.innerHTML = "";
  preview.forEach(item=>{
    const div = document.createElement("div");
    div.className = "preview-item";
    const title = document.createElement("strong");
    title.textContent = `${item.section_number || '—'} ${item.section_name || ''}`.trim();
    const meta = document.createElement("span");
    meta.textContent = `${item.chars || 0} chars`;
    div.appendChild(title);
    div.appendChild(meta);
    target.appendChild(div);
  });
}

export function renderLocalHeaderPreview(target, headers){
  if(!Array.isArray(headers) || headers.length === 0){
    target.innerHTML = "";
    return;
  }
  target.innerHTML = "";
  headers.slice(0, 10).forEach((item)=>{
    const div = document.createElement("div");
    div.className = "preview-item";
    const title = document.createElement("strong");
    title.textContent = item.text || "(untitled)";
    const meta = document.createElement("span");
    const parts = [];
    if(typeof item.page === "number") parts.push(`Page ${item.page}`);
    if(typeof item.level === "number") parts.push(`Level ${item.level}`);
    if(typeof item.font_size === "number") parts.push(`${item.font_size.toFixed(2)} pt`);
    meta.textContent = parts.join(" • ");
    div.appendChild(title);
    div.appendChild(meta);
    target.appendChild(div);
  });
}
