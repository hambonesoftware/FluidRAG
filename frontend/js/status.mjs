import { el } from "./state.mjs";

export function setStatus(node, message, tone) {
  if (!node) return;
  node.textContent = message;
  node.classList.remove("success", "warn");
  if (tone === "success") node.classList.add("success");
  else if (tone === "warn") node.classList.add("warn");
}

export function updateStatus(id, message, tone) {
  const node = el(id);
  if (!node) {
    console.warn("[UI] Missing status element", { id, message });
    return;
  }
  setStatus(node, message, tone);
}
