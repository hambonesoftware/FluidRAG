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
    const bits = [];
    const pageLabel = item.page_start ?? item.page_found ?? item.page;
    if(pageLabel) bits.push(`p.${pageLabel}`);
    if(item.heading_level) bits.push(`L${item.heading_level}`);
    bits.push(`${item.chars || 0} chars`);
    meta.textContent = bits.join(" • ");
    div.appendChild(title);
    div.appendChild(meta);
    if(item.content !== undefined){
      const pre = document.createElement("pre");
      pre.textContent = item.content || "(no captured content)";
      div.appendChild(pre);
    }
    target.appendChild(div);
  });

}

export function renderLocalHeaders(target, headers){
  if(!target) return;
  if(!Array.isArray(headers) || headers.length === 0){
    target.innerHTML = "";
    return;
  }
  target.innerHTML = "";
  headers.forEach(item=>{
    const div = document.createElement("div");
    div.className = "preview-item";
    const title = document.createElement("strong");
    title.textContent = item.text || "";
    const bits = [];
    if(item.page) bits.push(`p.${item.page}`);
    if(item.level) bits.push(`L${item.level}`);
    if(item.is_bold) bits.push("bold");
    if(item.font_size) bits.push(`${item.font_size}px`);
    const meta = document.createElement("span");
    meta.textContent = bits.join(" · ");
    div.appendChild(title);
    div.appendChild(meta);
    target.appendChild(div);
  });
}

