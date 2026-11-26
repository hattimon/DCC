import { language, problem, t } from "./i18n.js";
import { badge, bytes, elButton, empty, esc, facts, fmtDate, fmtTime, icon, NA, ports, select, state } from "./ui.js";

const columns = {
  containers: ["name", "image", "state", "ports", "created"],
  images: ["tag", "size", "architecture", "created"],
  volumes: ["name", "driver", "scope", "created"],
  networks: ["name", "driver", "scope", "subnets"],
};
const STATES = ["running", "exited", "created", "paused", "restarting", "dead", "removing"];

function table(headers, rows) {
  return `<table class="table responsive" role="table"><thead role="rowgroup"><tr role="row">${headers.map((key) =>
    `<th scope="col" role="columnheader">${esc(t(key))}</th>`).join("")}</tr></thead>
    <tbody role="rowgroup">${rows.map((cells) => `<tr role="row">${cells.map((cell, index) =>
      `<td role="cell" data-label="${esc(t(headers[index]))}"><div>${cell}</div></td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function subject(item, label, kind) {
  return `${item.id ? elButton(label ?? NA, "detail", {cls: "row-button", key: `${kind}:${item.id}`}) : esc(label)}
    ${item.id && kind !== "volumes" ? `<small class="mono" title="${esc(item.id)}">${esc(item.id.replace("sha256:", "").slice(0, 12))}</small>` : ""}`;
}

export function inventoryRows(kind, items) {
  if (!items.length) return `<p class="empty">${esc(t("noMatches"))}</p>`;
  const render = {
    containers: (row) => [subject(row, row.name, kind), esc(row.image),
      `${state(row.state)}${row.health ? `<small>${state(row.health)}</small>` : ""}`, esc(ports(row.ports)), esc(fmtDate(row.created))],
    images: (row) => [subject(row, row.tags.join(", ") || row.id, kind), esc(bytes(row.bytes)), esc(row.architecture), esc(fmtDate(row.created))],
    volumes: (row) => [subject(row, row.name, kind), esc(row.driver), esc(row.scope), esc(fmtDate(row.created))],
    networks: (row) => [subject(row, row.name, kind), esc(row.driver), esc(row.scope), esc(row.subnets?.join(", ") || NA)],
  };
  return table(columns[kind], items.map(render[kind]));
}

function rowName(row) {
  return row.name ?? row.tags?.[0] ?? row.id ?? "";
}

export function filtered(items, { search, state: filter, sort }) {
  const query = search.trim().toLocaleLowerCase(language);
  return items.filter((row) => (!filter || row.state === filter)
      && [rowName(row), row.image, row.id, row.tags?.join(" "), row.driver].some((v) => v?.toLocaleLowerCase(language).includes(query)))
    .toSorted((a, b) => {
      if (sort === "largest") return (b.bytes ?? 0) - (a.bytes ?? 0);
      if (sort === "newest") {
        const time = (value) => (typeof value === "number" ? value * 1000 : Date.parse(value)) || 0;
        return time(b.created) - time(a.created);
      }
      return rowName(a).localeCompare(rowName(b), language, {numeric: true});
    });
}

export function inventory(kind, items, filter, title = t(kind)) {
  if (!items.length) return empty(t("empty"), t("noRows"), "", kind);
  const display = filtered(items, filter);
  return `<section class="card inventory-panel">
    <header class="panel-head"><h2>${icon(kind)}${esc(title)}</h2><small id="row-count" aria-live="polite">${esc(t("rowCount", {count: display.length}))}</small></header>
    <div class="toolbar">
      <label>${esc(t("search"))}<input type="search" id="search" maxlength="140" value="${esc(filter.search)}" placeholder="${esc(t("searchBy"))}"></label>
      ${kind !== "containers" ? "" : select("state", [["", t("allStates")], ...STATES.map((v) => [v, t(v === "created" ? "createdState" : v)])], filter.state, t("state"), false)}
      ${select("sort", [["name", t("name")], ["newest", t("newest")], ...(kind === "images" ? [["largest", t("largest")]] : [])], filter.sort)}
    </div>
    <div id="rows">${inventoryRows(kind, display)}</div>
  </section>`;
}

export function composeView(projects) {
  if (!projects.length) return empty(t("empty"), t("noCompose"), "", "compose");
  return `<div class="stack">${projects.map((project) => `<section class="card">
    <header class="panel-head"><h2>${icon("compose")}${esc(project.name)}</h2><small>${esc(t("rowCount", {count: project.services.length}))}</small></header>
    ${table(["service", "containers", "image", "state", "version"], project.services.flatMap(({name, containers}) => containers.map((row) =>
      [esc(name), subject(row, row.name, "containers"), esc(row.image), state(row.state), esc(row.compose.version)])))}
    </section>`).join("")}</div>`;
}

export function detail(kind, item, canManage = false) {
  const actionNames = item.name === "dcc-kiri-manager" ? [] : ({
    running: ["stop", "restart", "pause"], paused: ["unpause"],
    exited: ["start", "remove"], created: ["start", "remove"], dead: ["remove"],
  }[item.state] ?? []);
  const controls = canManage && kind === "containers" && actionNames.length ?
    `<section class="stack-sm"><h3>${esc(t("manageContainer"))}</h3>
    <p>${esc(t("manageHint"))}</p><div class="actions">
    ${actionNames.map((action) => elButton(t("action_" + action), "container-action",
      {key: action, cls: action === "remove" ? "danger" : ""})).join("")}
    </div><p id="container-action-status" role="status" class="error"></p></section>` : "";
  const labels = Object.entries(item.compose ?? {}).map(([key, value]) => [t(key), value]);
  const fields = {
    containers: [["id", item.id], ["image", item.image], ["state", item.state ? t(item.state === "created" ? "createdState" : item.state) : NA],
      ["health", item.health ? t(item.health) : NA], ["created", fmtDate(item.created)], ["started", fmtDate(item.started)],
      ["exit_code", item.exit_code], ["ports", ports(item.ports)], ["networks", item.networks?.join(", ") || "—"]],
    images: [["id", item.id], ["tag", item.tags?.join(", ") || NA], ["size", bytes(item.bytes)], ["os", item.os],
      ["architecture", item.architecture], ["created", fmtDate(item.created)]],
    volumes: [["name", item.name], ["driver", item.driver], ["scope", item.scope], ["created", fmtDate(item.created)],
      ["attached", item.containers?.join(", ") || (item.containers ? "—" : NA)]],
    networks: [["id", item.id], ["driver", item.driver], ["scope", item.scope], ["created", fmtDate(item.created)],
      ["subnets", item.subnets?.join(", ") || NA], ["attached", item.containers?.join(", ") || (item.containers ? "—" : NA)],
      ["internal", item.internal == null ? NA : t(item.internal ? "yes" : "no")]],
  };
  const logControls = `<form id="logs-form" class="stack-sm">
    <h3>${esc(t("logs"))}</h3><p>${esc(t("logRedaction"))}</p>
    <div class="actions">${select("tail", [25, 50, 100, 200].map((n) => [n, n]), 100, t("logTail"))}
    <button type="submit">${esc(t("loadLogs"))}</button></div><div id="log-output" aria-live="polite"></div>
    </form>`;
  return `${facts([...fields[kind].map(([label, value]) => [t(label), value]), ...labels], "details")}
    ${item.attachments_error ? `<p class="error">${esc(problem(item.attachments_error))}</p>` : ""}
    ${controls}${kind === "containers" ? logControls : ""}`;
}

export function engineCard(engine, profile, counts, connection = "online", compact = false) {
  return `<section class="card engine ${compact ? "engine-compact" : ""}"><div class="engine-title">${icon("containers")}
    <div><h2>${esc(t("engine"))}</h2>${badge(t(connection), connection === "online" ? "good" : connection === "offline" ? "bad" : "warn")}</div></div>
    ${facts([[t("profile"), profile?.name], [t("engineVersion"), engine?.version],
      [t("api"), engine?.api], [t("architecture"), engine ? [engine.os, engine.arch].filter(Boolean).join("/") || NA : NA],
      [t("expectedEngine"), t(engine?.kind ?? "kiri")], [t("permission"), t("managePermission")], ...(counts ? [[t("projects"), counts.compose]] : [])])}</section>`;
}

function countCards(counts, running, stopped, checks) {
  return `<div class="metric-grid">${["containers", "images", "volumes", "networks"].map((key) => `<article class="card metric">
    ${icon(key)}<div><span>${esc(t(key))}</span><b>${esc(counts[key])}</b>
    ${key === "containers" && running != null ? `<small>${esc(t("runCount", {count: running}))} · ${esc(t("stopCount", {count: stopped}))}</small>` : ""}
    ${checks[key] && checks[key] !== "available" ? `<small>${esc(problem(checks[key]))}</small>` : ""}</div></article>`).join("")}</div>`;
}

function chart(title, items, field, format, error) {
  const current = items.at(-1)?.[field];
  if (error || current == null) return `<article class="card pad chart">
    <h2>${esc(t(title))}</h2><p class="chart-unavailable"><span><b>${NA}</b>${esc(error ? problem(error) : items.length ? t("metricNA") : t("metricWaiting"))}</span></p></article>`;
  const max = Math.max(...items.map((entry) => entry[field] ?? 0), 1);
  const points = items.map((entry, index) => entry[field] == null ? null : [items.length === 1 ? 472 : (index * 470) / (items.length - 1) + 2,
    90 - (entry[field] / max) * 74]);
  const segments = [];
  let segment = [];
  for (const point of [...points, null]) {
    if (point) segment.push(point);
    else if (segment.length) {
      segments.push(segment);
      segment = [];
    }
  }
  const [x, y] = points.at(-1);
  return `<article class="card pad chart"><div class="line"><h2>${esc(t(title))}</h2><strong>${esc(format(current))}</strong></div>
    <div class="plot"><span class="scale" aria-hidden="true"><span>${esc(format(max))}</span><span>${esc(format(0))}</span></span><svg viewBox="0 0 475 95" preserveAspectRatio="none" aria-hidden="true">
    <path class="grid-line" d="M0 17H475M0 41H475M0 65H475M0 90H475"></path>
    ${segments.map((run) => `<polygon class="area" points="${run[0][0]},90 ${run.join(" ")} ${run.at(-1)[0]},90"></polygon>
    <polyline class="trace" points="${run.join(" ")}"></polyline>`).join("")}
    <circle class="point" cx="${x}" cy="${y}" r="3"></circle></svg></div>
    <div class="axis"><span>${esc(fmtTime(items[0]?.at))}</span><span>${esc(t("sampleTime", {time: fmtTime(items.at(-1)?.at)}))}</span></div>
    </article>`;
}

export function metrics(containers, samples, chosen, error, expanded = false, disk = {}) {
  const running = containers.filter((row) => row.state === "running" && row.id);
  if (!running.length) return empty(t("monitoring"), t("noRowsMonitoring"), "", "monitoring");
  const sample = samples.at(-1);
  return `<div class="stack">
    <div class="chart-tools">
      ${select("selectedContainer", running.map((row) => [row.id, row.name]), chosen)}
      ${expanded ? "" : `<small>${esc(t("received"))} ${esc(bytes(error ? null : sample?.rx_bytes))} · ${esc(t("sent"))} ${esc(bytes(error ? null : sample?.tx_bytes))}</small>`}
    </div>
    <div class="grid2">
      ${chart("containerCPU", samples, "cpu_percent", (value) => `${new Intl.NumberFormat(language, {maximumFractionDigits: 2}).format(value)}%`, error)}
      ${chart("containerMemory", samples, "memory_bytes", bytes, error)}
    </div>
    ${expanded ? `<section class="card pad stack-sm">
      <h2>${esc(t("monitoring"))}</h2><p>${esc(t("cumulative"))}</p>
      ${facts([["received", "rx_bytes"], ["sent", "tx_bytes"], ["read", "read_bytes"], ["written", "write_bytes"],
        ["memoryLimit", "limit_bytes"]].map(([label, key]) => [t(label), bytes(error ? null : sample?.[key])]))}
    </section>` : ""}
    ${expanded ? `<section class="card pad stack-sm"><h2>${esc(t("storage"))}</h2><p>${esc(t("storageExplain"))}</p>
      ${facts([[t("layerBytes"), bytes(disk.image_layers_bytes)]])}
      ${disk.error ? `<p class="error">${esc(problem(disk.error))}</p>` : ""}
      <div>${elButton(t("checkStorage"), "disk", {symbol: "volumes"})}</div>
    </section>` : ""}
  </div>`;
}

export function capabilityChecks(snapshot, compact = false) {
  const engine = snapshot?.engine;
  if (!engine) return `<p>${esc(t("pending"))}</p>`;
  const checks = [[t("transport"), "available"], [t("identity"), "available"], [t("api"), engine.api],
    ...Object.entries(snapshot.checks ?? {}).map(([key, value]) => [t(key === "info" ? "engine" : key), value])];
  if (!compact) checks.push([t("logs"), "onDemand"], [t("monitoring"), "onDemand"], [t("storage"), "onDemand"]);
  return `<dl class="checks">${checks.map(([label, status]) => `<div><dt>${esc(label)}</dt><dd>${
    status === "available" ? badge(t("available"), "good") :
      status === "onDemand" || /^\d+\.\d+$/.test(status) ? esc(t(status)) : `<span class="error">${esc(problem(status))}</span>`
  }</dd></div>`).join("")}</dl>`;
}

export function overview(snapshot, profile, samples, filter, monitored, metricError) {
  const { values, counts, checks, running, stopped, engine } = snapshot;
  return `<div class="stack">
    ${engineCard(engine, profile, counts)}
    ${countCards(counts, running, stopped, checks)}
    ${values.containers ? metrics(values.containers, samples, monitored, metricError) : empty(t("monitoring"), problem(checks.containers))}
    ${values.containers ? inventory("containers", values.containers, filter, t("containerInventory")) : empty(t("containers"), problem(checks.containers))}
    ${values.info ? `<section class="card pad stack-sm"><h2>${esc(t("engine"))}</h2>${facts([
      [t("host"), t(profile.host)], [t("reportedCpus"), values.info.cpus], [t("reportedMemory"), bytes(values.info.memory_bytes)],
      [t("kernel"), values.info.kernel], [t("driver"), values.info.driver], [t("warningCount"), values.info.warning_count],
    ])}</section>` : ""}
  </div>`;
}
