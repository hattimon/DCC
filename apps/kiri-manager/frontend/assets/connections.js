import { language, problem, t } from "./i18n.js";
import { badge, elButton, empty, esc, facts, icon, select } from "./ui.js";
import { capabilityChecks } from "./inventory.js";

export const hostTypes = ["linux", "wsl", "macos"];
export const runtimeTypes = ["docker", "kiri", "native"];

const hosts = { linux: "linux", wsl: "windows", macos: "install" };

function choices(name, values, selected) {
  return values.map((value) => `<label class="choice"><input type="radio" name="${name}" value="${value}" ${value === selected ? "checked" : ""} required>
    <span><strong>${esc(t(value))}</strong>${esc(t(value + "Choice"))}</span></label>`).join("");
}

function tip() {
  return `<details class="tip"><summary>${esc(t("advanced"))}</summary><p>${esc(t("advancedHint"))}</p></details>`;
}

function setupHelp(host, runtime) {
  const standard = `https://docs.runkiri.com/${hosts[host] ?? "install"}/`;
  const hint = {linux: "installLinux", wsl: "installWsl", macos: "installMacos"}[host] ?? "installLinux";
  const docs = `https://github.com/hattimon/DCC/blob/kiri-manager-v0.1.0/apps/kiri-manager/docs/installation${language === "pl" ? ".pl" : ""}.md`;
  return `<section class="card pad stack-sm notice">
    <h2 class="section-title">${icon("connections")}${esc(t("installKiri"))}</h2>
    ${badge(t("notVerified"), "warn")}<p>${esc(t(hint))}</p>
    ${runtime === "docker" ? `<p>${esc(t("dockerChoice"))}</p>` : ""}
    <p>${esc(t("installOnce"))}</p>
    <div class="actions"><a class="button" target="_blank" rel="noopener noreferrer" href="${standard}">${esc(t("upstream"))}</a>
    ${host === "linux" ? `<a class="button" download href="/api/install/linux">${esc(t("linuxHelper"))}</a>` : ""}
    <a target="_blank" rel="noopener noreferrer" href="${docs}">${esc(t("installGuide"))}</a></div>
    ${host === "linux" ? `<p><code>bash setup-kiri-linux.sh --apply</code></p>` : ""}
  </section>`;
}

function endpointFields(value, endpoints) {
  const choices = [["", "—"], ...endpoints.map((alias) => [alias, alias])];
  if (value.endpoint && !endpoints.includes(value.endpoint)) choices.push([value.endpoint, value.endpoint]);
  return `<div class="stack-sm">
    <label>${esc(t("profileName"))}<input autocomplete="off" maxlength="64" required name="name" value="${esc(value.name)}"></label>
    <div class="grid2">${select("endpoint", choices, value.endpoint)}${facts([
      [t("transport"), t("unix")], [t("authMode"), t("socketAuth")]])}</div>
    <small>${esc(t("endpointHint"))}</small>${endpoints.length ? "" : `<p class="error">${esc(t("noEndpoints"))}</p>`}
    ${tip()}
  </div>`;
}

function testReport(result) {
  if (result?.error) return `<p class="error" role="alert">${esc(problem(result.error))}</p>`;
  if (result?.engine) return `<div class="stack-sm">${badge(t("testPassed"), "good")}${capabilityChecks(result, true)}</div>`;
  return `<p>${esc(t("pending"))}</p>`;
}

export function wizard(wizard, endpoints) {
  const { step, draft, result } = wizard;
  const panels = [
    `<fieldset class="stack-sm"><legend>${esc(t("nextHost"))}</legend>${choices("host", hostTypes, draft.host)}</fieldset>`,
    `<fieldset class="stack-sm"><legend>${esc(t("nextRuntime"))}</legend>${choices("runtime", runtimeTypes, draft.runtime)}</fieldset>`,
    endpointFields(draft, endpoints),
    `<div class="stack-sm">${facts([[t("profileName"), draft.name], [t("host"), t(draft.host)], [t("runtime"), t(draft.runtime)], [t("endpoint"), draft.endpoint]])}
      ${result?.engine ? "" : `<div>${elButton(t("test"), "wizard-test", {disabled: !endpoints.length, symbol: "diagnostics"})}</div>`}</div>`,
  ];
  const title = step === 0 ? t("welcome") : t("setup");
  return `<div class="wizard">
    <section class="card pad stack">
      <h2 class="section-title">${icon("connections")}${esc(title)}</h2><p>${esc(t("wizardHint"))}</p>
      <ol class="steps" aria-label="${esc(t("wizardStep", {step: step + 1}))}">${["host", "runtime", "transport", "diagnostics"].map((part, index) =>
       `<li ${index === step ? 'aria-current="step"' : ""} class="${index < step ? "done" : ""}"><b>${index < step ? icon("check") : index + 1}</b>${esc(t(part))}</li>`).join("")}</ol>
      <form id="wizard-form" class="stack">
        ${panels[step]}
        <div class="actions">
          ${step ? elButton(t("back"), "wizard-back") : ""}
          ${step < 2 ? `<button class="primary" type="submit">${esc(t("next"))}${icon("arrow")}</button>` : ""}
          ${step === 2 ? `<button class="primary" type="submit" ${endpoints.length ? "" : "disabled"}>${esc(t("test"))}${icon("arrow")}</button>` : ""}
          ${step === 3 && result?.engine ? elButton(t("finish"), "wizard-finish", {cls: "primary", symbol: "arrow"}) : ""}
          ${!(step === 3 && result?.engine) ? elButton(t("skipSetup"), "wizard-skip", {cls: "quiet"}) : ""}
        </div>
      </form>
    </section>
    <div class="stack">
      <section class="card pad stack-sm"><h2 class="section-title">${icon("diagnostics")}${esc(t("checks"))}</h2><div id="wizard-result" aria-live="polite">${testReport(result)}</div></section>
      ${step >= 1 || !endpoints.length ? setupHelp(draft.host, draft.runtime) : ""}
    </div>
    </div>`;
}

export function wizardForm(wizard, form) {
  for (const [key, value] of new FormData(form)) wizard.draft[key] = value;
  return wizard.draft;
}

export function profileForm(profile, endpoints) {
  const draft = profile ?? { name: "", host: "linux", runtime: "docker", endpoint: endpoints[0] ?? "" };
  return `<form id="profile-form" class="stack">
    <div class="grid2">${select("host", hostTypes.map((value) => [value, t(value)]), draft.host)}
    ${select("runtime", runtimeTypes.map((value) => [value, t(value)]), draft.runtime)}</div>
    ${endpointFields(draft, endpoints)}
    <div class="actions">
      ${elButton(t("test"), "profile-test", {symbol: "diagnostics", disabled: !endpoints.length})}
      <button class="primary" type="submit" ${endpoints.length ? "" : "disabled"}>${icon("check")}${esc(t("save"))}</button>
    </div><div id="profile-result" aria-live="polite"></div>
  </form>`;
}

export function connections(profiles, active, statuses, endpoints, activeStatus) {
  const start = elButton(t("wizard"), "wizard", {symbol: "connections", cls: "primary"});
  const add = elButton(t("newProfile"), "profile-edit", {symbol: "plus", disabled: !endpoints.length});
  const cards = profiles.map((profile) => {
    const status = statuses.get(profile.id);
    const connected = profile.id === active ? activeStatus === "online" : Boolean(status?.engine);
    const label = connected ? "online" : status?.error || (profile.id === active && activeStatus === "offline") ? "offline" : "untested";
    return `<section class="card pad stack-sm">
      <div class="line"><h2>${esc(profile.name)}</h2>${profile.id === active ? badge(t("active"), "good") : ""}${badge(t(label), connected ? "good" : label === "offline" ? "bad" : "")}</div>
      ${facts([[t("host"), t(profile.host)], [t("runtime"), t(profile.runtime)], [t("endpoint"), profile.endpoint], [t("transport"), t("unix")]])}
      <div class="actions">
        ${profile.id === active ? "" : elButton(t("activate"), "activate", {key: profile.id})}
        ${elButton(t("test"), "saved-test", {key: profile.id, symbol: "diagnostics"})}
        ${elButton(t("edit"), "profile-edit", {key: profile.id})}
        ${elButton(t("remove"), "profile-remove", {key: profile.id, cls: "danger quiet"})}
      </div></section>`;
  });
  return `<div class="stack"><div class="actions">${start}${add}</div>
    ${profiles.length ? `<div class="grid2">${cards.join("")}</div>` : empty(t("noProfile"), t("noProfileHint"))}
    ${endpoints.length && activeStatus !== "offline" ? "" : setupHelp(profiles.find((row) => row.id === active)?.host ?? "linux", "docker")}</div>`;
}

export { testReport };
