import { language, problem, t } from "./i18n.js";

export const $ = (id) => document.getElementById(id);
export const NA = "N/A";
const paths = {
  overview: "M3 10.5 12 3l9 7.5V21h-6v-7H9v7H3Z",
  connections: "M9 3v5m6-5v5M6 8h12v3a6 6 0 0 1-12 0Zm6 9v4",
  containers: "M12 2 3 7v10l9 5 9-5V7Zm0 10v10M3 7l9 5 9-5",
  images: "M12 3 2 8l10 5 10-5Zm-9 9.5 9 4.5 9-4.5M3 17l9 4.5 9-4.5",
  volumes: "M21 6c0 2-4 4-9 4s-9-2-9-4 4-4 9-4 9 2 9 4ZM3 6v12c0 2 4 4 9 4s9-2 9-4V6M3 12c0 2 4 4 9 4s9-2 9-4",
  networks: "M12 11v5M6 18l6-3 6 3M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM4 17a3 3 0 1 0 0 6 3 3 0 0 0 0-6Zm16 0a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z",
  compose: "m12 2 4 2.3v4.5L12 11 8 8.8V4.3Zm-6 10 4 2.3v4.5L6 21l-4-2.2v-4.5Zm12 0 4 2.3v4.5L18 21l-4-2.2v-4.5Z",
  monitoring: "M2 13h5l3-9 5 16 2-7h5",
  diagnostics: "M8 4H5v18h14V4h-3M9 2h6v5H9Zm0 13 2 2 4-5",
  settings: "M10 3h4l.7 2.5 2 .9 2.3-1.2 2 3.6-1.8 1.8v2.8l1.8 1.8-2 3.6-2.3-1.2-2 .9L14 21h-4l-.7-2.5-2-.9L5 18.8l-2-3.6 1.8-1.8v-2.8L3 8.8l2-3.6 2.3 1.2 2-.9ZM12 9a3 3 0 1 0 0 6 3 3 0 1 0 0-6Z",
  logout: "M11 3H4v18h7m2-15 6 6-6 6M8 12h11",
  refresh: "M20 7a9 9 0 1 0 1 9M20 3v5h-5",
  moon: "M20.4 15a8.8 8.8 0 0 1-11.6-11A9 9 0 1 0 20.4 15Z",
  sun: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0-6v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2",
  menu: "M4 6h16M4 12h16M4 18h16",
  close: "m6 6 12 12m0-12L6 18",
  plus: "M12 5v14M5 12h14",
  check: "m5 12 4 4L19 6",
  arrow: "M5 12h14m-6-6 6 6-6 6",
};

export function icon(name) {
  return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] ?? paths.connections}"></path></svg>`;
}

export function esc(value) {
  return String(value ?? NA).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

export function elButton(label, action, { symbol = "", cls = "", key = "", disabled = false } = {}) {
  return `<button type="button" class="${cls}" data-action="${action}" data-key="${esc(key)}" ${disabled ? "disabled" : ""}>${symbol ? icon(symbol) : ""}${esc(label)}</button>`;
}

export function badge(label, color = "") {
  return `<span class="badge ${color}">${esc(label)}</span>`;
}

export function opening() {
  return `<div class="skeleton" aria-label="${esc(t("connecting"))}" role="status"><span></span><span></span></div>`;
}

export function empty(title, explanation, action = "", symbol = "connections") {
  return `<section class="card empty stack-sm">${icon(symbol)}<h2>${esc(title)}</h2><p>${esc(explanation)}</p>${action ? `<div>${action}</div>` : ""}</section>`;
}

export function failure(code, retry = false) {
  return empty(t(code === "unsupported" ? "unavailable" : "offline"), problem(code), retry ? elButton(t("retry"), "refresh", {symbol: "refresh"}) : "", "diagnostics");
}

export function facts(fields, cls = "facts") {
  return `<dl class="${cls}">${fields.map(([label, value]) => `<div><dt>${esc(label)}</dt><dd>${esc(value ?? NA)}</dd></div>`).join("")}</dl>`;
}

export function fmtDate(value) {
  if (value == null || value === 0 || String(value).startsWith("0001-")) return NA;
  const date = new Date(typeof value === "number" ? 1000 * value : value);
  return Number.isFinite(date.valueOf()) ? date.toLocaleString(language, {dateStyle: "medium", timeStyle: "short"}) : NA;
}

export function fmtTime(value) {
  return value ? new Date(value * 1000).toLocaleTimeString(language) : NA;
}

export function bytes(amount) {
  if (amount == null) return NA;
  const units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB"];
  const unit = amount > 0 ? Math.min(units.length - 1, Math.max(0, Math.floor(Math.log(amount) / Math.log(1024)))) : 0;
  return `${new Intl.NumberFormat(language, {maximumFractionDigits: 1}).format(amount / 1024 ** unit)} ${units[unit]}`;
}

export function state(value) {
  const label = value === "created" ? t("createdState") : t(value ?? "unknown");
  return badge(label, {running: "good", healthy: "good", unhealthy: "bad", dead: "bad",
                       restarting: "warn", starting: "warn", paused: "warn"}[value] ?? "");
}

export function ports(value) {
  return value?.length ? value.map((port) =>
    `${port.public == null ? "" : `${port.public} → `}${port.private ?? NA}/${port.protocol ?? NA}`).join(", ") : "—";
}

export function select(field, values, selected, label = t(field), required = true) {
  return `<label>${esc(label)}<select name="${field}" ${required ? "required" : ""}>${values.map(([value, title]) =>
    `<option value="${esc(value)}"${String(value) === String(selected) ? " selected" : ""}>${esc(title)}</option>`).join("")}</select></label>`;
}

export function navLink(view, cls = "button primary") {
  return `<a class="${cls}" href="#${view}">${icon(view)}${esc(t(view))}</a>`;
}
