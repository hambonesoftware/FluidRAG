export function renderTable(target, rows){
  if(!target) return;
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
  if(!target) return;
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

