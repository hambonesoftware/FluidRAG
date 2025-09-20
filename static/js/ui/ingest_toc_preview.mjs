export function renderTOCPreview(mountEl, sections=[]) {
  mountEl.innerHTML = '';
  const ul = document.createElement('ul');
  ul.style.listStyle = 'none'; ul.style.paddingLeft = '0';
  sections.forEach(sec => {
    const li = document.createElement('li'); li.style.margin = '4px 0';
    const title = document.createElement('div'); title.textContent = `${sec.section_id||''} ${sec.section_title||''}`.trim(); title.style.fontWeight='600';
    const meta = document.createElement('div'); meta.textContent = `pages ${sec.page_start}-${sec.page_end}`; meta.style.opacity='0.7'; meta.style.fontSize='12px';
    li.appendChild(title); li.appendChild(meta); ul.appendChild(li);
  });
  mountEl.appendChild(ul);
}
