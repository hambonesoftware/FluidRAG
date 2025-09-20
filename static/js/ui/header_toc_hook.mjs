export function maybeRenderTOC(preview, mountId = 'toc-preview') {
  try {
    const el = document.getElementById(mountId);
    if (!el || !Array.isArray(preview) || preview.length === 0) return;
    el.innerHTML = '';
    const ul = document.createElement('ul');
    ul.style.listStyle = 'none';
    ul.style.paddingLeft = '0';
    preview.forEach(p => {
      const li = document.createElement('li');
      li.style.margin = '4px 0';
      li.textContent = `${p.section_number || ''} ${p.section_name || ''}`.trim();
      ul.appendChild(li);
    });
    el.appendChild(ul);
  } catch {}
}
