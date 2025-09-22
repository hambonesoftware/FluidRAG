import { el } from "./state.mjs";

export function log(msg) {
  const pre = el("log");
  if (!pre) {
    console.warn("[UI] Missing log element", { msg });
    return;
  }
  const line = `[UI] ${new Date().toLocaleTimeString()} ${msg}`;
  console.log(line);
  pre.textContent += line + "\n";
  pre.scrollTop = pre.scrollHeight;
}

export function openGroup(label, collapsed = false) {
  if (collapsed) console.groupCollapsed(label);
  else console.group(label);
  return () => console.groupEnd();
}

export function withGroup(label, fn, collapsed = false) {
  const end = openGroup(label, collapsed);
  try {
    fn();
  } finally {
    end();
  }
}
