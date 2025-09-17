export function renderTable(target, rows){
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
