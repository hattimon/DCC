import { client } from "./api.js";
import { connections, profileForm, testReport, wizard, wizardForm } from "./connections.js";
import { language, problem, setLanguage, t } from "./i18n.js";
import { capabilityChecks, composeView, detail, engineCard, filtered, inventory, inventoryRows, metrics, overview } from "./inventory.js";
import { $, badge, elButton, empty, esc, failure, facts, fmtTime, icon, navLink, opening, select } from "./ui.js";

const navigation = {
  workspace: ["overview", "connections"],
  inventory: ["containers", "images", "volumes", "networks", "compose"],
  system: ["monitoring", "diagnostics", "settings"],
};
const routes = new Set([...Object.values(navigation).flat(), "wizard"]);
const dataViews = new Set(["overview", "monitoring", "diagnostics", ...navigation.inventory]);
const intervalOptions = [0, 15, 30, 60, 120];
const filters = () => ({search: "", state: "", sort: "name"});
const state = {
  auth: null, view: null, status: "disconnected", payload: null, error: null,
  preferences: {language: "en", theme: "dark", interval: 30, active: null},
  profiles: [], endpoints: [], checked: new Map(), query: filters(), wizard: null,
  discovery: null,
  monitor: {id: null, samples: [], error: null}, disk: {},
  lastRead: null, request: null, timer: null, toast: null, modalRef: null,
};
const api = client(() => state.auth?.csrf, () => signInAgain());
const currentProfile = () => state.profiles.find((row) => row.id === state.preferences.active);
const path = (id, suffix) => `/api/profiles/${encodeURIComponent(id)}/${suffix}`;
const locally = {
  get(key) {
    try { return localStorage.getItem(`kiri.${key}`); } catch { return null; }
  },
  set(key, value) {
    try { localStorage.setItem(`kiri.${key}`, value); } catch { /* optional browser preference */ }
  },
};
let lastFocus = null;
let bootInFlight = false;

function appearance(prefs) {
  setLanguage(prefs.language);
  document.documentElement.dataset.theme = prefs.theme === "light" ? "light" : "dark";
  $("skip").textContent = t("skip");
  locally.set("language", language);
  locally.set("theme", document.documentElement.dataset.theme);
}

function quickControls() {
  const theme = document.documentElement.dataset.theme;
  return `<span class="auth-quick" role="group" aria-label="${esc(t("language"))}">
    ${["en", "pl"].map((value) => `<button type="button" class="quiet" data-action="language" data-key="${value}" aria-label="${value === "en" ? "English" : "Polski"}" aria-pressed="${language === value}">${value.toUpperCase()}</button>`).join("")}</span>
    <button class="icon-button" type="button" data-action="theme" title="${esc(t(theme === "dark" ? "light" : "dark"))}"
    aria-label="${esc(t(theme === "dark" ? "light" : "dark"))}">${icon(theme === "dark" ? "moon" : "sun")}</button>`;
}

function notify(message) {
  clearTimeout(state.toast);
  $("toast").textContent = message;
  state.toast = setTimeout(() => { $("toast").textContent = ""; }, 4300);
}

function terminalHelp(adminReady) {
  const option = adminReady ? " --reset" : "";
  return `<details class="auth-help">
    <summary>${esc(t(adminReady ? "resetInTerminal" : "setupInTerminal"))}</summary>
    <p>${esc(t("terminalHelp"))}</p>
    <pre class="compact">Docker
docker exec -it dcc-kiri-manager python -m backend.admin${option}

Kiri
docker --context kiri exec -it dcc-kiri-manager python -m backend.admin${option}

Kiri (Linux)
docker --host unix:///run/kiri/docker.sock exec -it dcc-kiri-manager python -m backend.admin${option}

Python
python -m backend.admin${option}</pre>
    <p>${esc(t("terminalUsername"))} <code>--username operator</code>.</p>
    ${adminReady ? `<p>${esc(t("terminalResetResult"))}</p>` : ""}
    </details>`;
}

function credentialsForm(firstLogin, setup) {
  const passwordHint = setup ? `<small id="password-hint">${esc(t("passwordLength"))}</small>` : "";
  return `<form id="${setup ? "setup-form" : "login-form"}" class="stack">
    <label>${esc(t("account"))}<input name="username" autocomplete="username" maxlength="64"${firstLogin ? ' value="admin"' : ""} required></label>
    <label>${esc(t(setup ? "newPassword" : "password"))}
      <input name="password" type="password" autocomplete="${setup ? "new-password" : "current-password"}"
      maxlength="128" ${setup ? 'minlength="14" aria-describedby="password-hint"' : ""} required>${passwordHint}</label>
    ${setup ? `<label>${esc(t("confirmPassword"))}<input name="confirmation" type="password"
      autocomplete="new-password" minlength="14" maxlength="128" required></label>` : ""}
    <div><button class="primary" type="submit">${esc(t(setup ? "saveAccount" : "signIn"))}${icon("arrow")}</button></div>
    </form>`;
}

function showAuth(error) {
  $("boot").hidden = true;
  $("workspace").hidden = true;
  $("auth").hidden = false;
  const adminReady = state.auth?.admin_ready;
  const firstLogin = state.auth?.setup_available;
  const setup = state.auth?.setup_pending;
  const heading = setup ? "secureAccount" : firstLogin ? "firstLogin" : adminReady ? "signIn" : state.auth ? "firstAdmin" : "offline";
  const hint = setup ? "secureAccountHint" : firstLogin ? "firstLoginHint" : "firstAdminText";
  $("auth").innerHTML = `<main class="auth-layout" id="auth-main" tabindex="-1"><section class="auth-card card pad stack">
    <div class="brand"><img src="/assets/mark.svg" alt="" width="34" height="34"> DCC Kiri Manager</div>
    <div class="actions">${quickControls()}</div>
    <h1>${esc(t(heading))}</h1>
    ${state.auth && !adminReady ? `<p>${esc(t(hint))}</p>` : ""}
    ${adminReady || firstLogin ? credentialsForm(firstLogin, setup) :
      `<div>${elButton(t(state.auth ? "reload" : "retry"), "bootstrap", {symbol: "refresh"})}</div>`}
    <p class="error" id="login-error" role="alert" ${error ? "" : "hidden"}>${error ? esc(problem(error)) : ""}</p>
    ${state.auth ? terminalHelp(adminReady) : ""}
    </section></main>`;
}

function applySession(payload) {
  state.auth = payload;
  if (!payload.authenticated) return;
  state.profiles = payload.profiles;
  state.endpoints = payload.endpoints;
  state.preferences = payload.preferences;
  appearance(state.preferences);
}

async function bootstrap(message) {
  if (bootInFlight) return;
  bootInFlight = true;
  try {
    applySession(await api("/api/session"));
    if (state.auth.authenticated) enter();
    else showAuth(message);
  } catch (error) {
    showAuth(error.code);
  } finally {
    bootInFlight = false;
  }
}

function stopReads() {
  clearTimeout(state.timer);
  state.request?.abort();
  state.request = null;
}

function signInAgain() {
  stopReads();
  if ($("modal").open) $("modal").close();
  state.view = null;
  state.auth = null;
  state.checked.clear();
  showAuth("unauthorized");
  void bootstrap("unauthorized");
}

function enter() {
  $("boot").hidden = $("auth").hidden = true;
  $("workspace").hidden = false;
  const target = route();
  navigate(!state.preferences.onboarded ? "wizard" : target);
}

function route() {
  const target = location.hash.slice(1);
  return routes.has(target) ? target : "overview";
}

function navigate(view, focus = false) {
  stopReads();
  if ($("modal").open) $("modal").close();
  closeMenu();
  const url = `#${view}`;
  if (location.hash !== url) history.replaceState(null, "", url);
  state.view = view;
  state.payload = null;
  state.error = null;
  state.query = filters();
  state.disk = {};
  if (view === "wizard") {
    state.wizard = {
      step: 0, advanced: false, discovery: state.discovery,
      draft: {name: "", host: "linux", runtime: "docker", endpoint: state.endpoints[0] ?? ""}, result: null,
    };
  }
  renderChrome();
  render();
  if (view === "wizard" || view === "connections") void checkDiscovery();
  if (focus) $("main").focus({preventScroll: true});
  if (focus) window.scrollTo(0, 0);
  void refresh();
}

function renderChrome() {
  const view = state.view;
  $("navigation").setAttribute("aria-label", t("nav"));
  $("navigation").innerHTML = Object.entries(navigation).map(([group, items]) => `<section class="nav-group">
    <h2>${esc(t(group))}</h2>${items.map((item) => `<a href="#${item}" ${item === view || (view === "wizard" && item === "connections") ? 'aria-current="page"' : ""}>
    ${icon(item)}${esc(t(item))}</a>`).join("")}</section>`).join("");
  $("version").textContent = `v${state.auth.version}`;
  $("sign-out").innerHTML = `${icon("logout")}${esc(t("signOut"))}`;
  $("breadcrumb").innerHTML = `${icon("overview")}${esc(t("workspace"))}<span aria-hidden="true">/</span><strong>${esc(t(view))}</strong>`;
  const menu = document.querySelector('[data-action="menu"]');
  menu.innerHTML = icon("menu");
  menu.setAttribute("aria-label", t("menu"));
  document.querySelector(".scrim").setAttribute("aria-label", t("closeMenu"));
  $("demo").hidden = !state.auth.demo;
  $("demo").textContent = t("demo");
  const viewTitle = `<div><h1>${esc(t(view))}</h1><p>${esc(t(view === "wizard" ? "wizardHint" : `${view}Hint`))}</p></div>`;
  $("heading").innerHTML = viewTitle + (view !== "wizard" && view !== "settings" ? `<button class="icon-button" type="button" data-action="refresh"
    title="${esc(t("refresh"))}" aria-label="${esc(t("refresh"))}">${icon("refresh")}<span class="refresh-label">${esc(t("refresh"))}</span></button>` : "");
  renderStatus();
}

function renderStatus() {
  $("quick").innerHTML = `<span id="connection-status" aria-live="polite">${badge(t(state.status), state.status === "online" ? "good" : state.status === "offline" ? "bad" : "")}</span>${quickControls()}`;
  $("foot").textContent = state.lastRead ? t("lastRead", {time: fmtTime(state.lastRead)}) : t("noRead");
}

function render() {
  const {view, payload, preferences, monitor} = state;
  const profile = currentProfile();
  let page;
  if (view === "wizard") page = wizard(state.wizard, state.endpoints);
  else if (view === "connections") page = connections(state.profiles, preferences.active, state.checked, state.endpoints, state.status, state.discovery);
  else if (view === "settings") page = settings();
  else if (!profile) page = `<div class="stack">${engineCard(null, null, null, "disconnected")}${empty(t("noProfile"), t("noProfileHint"), navLink("connections"))}</div>`;
  else if (state.error) page = `<div class="stack">${engineCard(null, profile, null, state.status)}${failure(state.error, true)}${navLink("connections", "button")}</div>`;
  else if (!payload) page = opening();
  else if (view === "overview") page = overview(payload, profile, monitor.samples, state.query, monitor.id, monitor.error);
  else if (view === "diagnostics") page = `<div class="stack">${engineCard(payload.engine, profile, payload.counts)}
    <section class="card pad stack-sm"><h2>${esc(t("checks"))}</h2>${capabilityChecks(payload)}</section></div>`;
  else if (view === "monitoring") page = `<div class="stack">${engineCard(payload.engine, profile, null, "online", true)}
    ${metrics(payload.items, monitor.samples, monitor.id, monitor.error, true, state.disk)}</div>`;
  else if (view === "compose") page = `<div class="stack">${engineCard(payload.engine, profile, null, "online", true)}
    ${composeView(payload.items)}</div>`;
  else page = `<div class="stack">${engineCard(payload.engine, profile, null, "online", true)}
    ${inventory(view, payload.items, state.query)}</div>`;
  $("content").setAttribute("aria-busy", String(Boolean(dataViews.has(view) && profile && !payload && !state.error)));
  $("content").innerHTML = `<div class="deck">${page}</div>`;
}

function settings() {
  const {language: locale, theme, interval} = state.preferences;
  return `<form id="settings-form" class="card pad stack">
    <div class="grid2">${select("language", [["en", "English"], ["pl", "Polski"]], locale)}
    ${select("theme", [["dark", t("dark")], ["light", t("light")]], theme)}</div>
    ${select("interval", intervalOptions.map((n) => [n, n ? t("seconds", {count: n}) : t("manual")]), interval, t("autoRefresh"))}
    <p>${esc(t("pollHint"))}</p><small>${esc(t("permission"))} · ${esc(t("adminLocal"))} · ${esc(t("managePermission"))}</small>
    <div><button class="primary" type="submit">${icon("check")}${esc(t("save"))}</button></div></form>`;
}

function monitorRows() {
  return state.view === "overview" ? state.payload?.values.containers : state.payload?.items;
}

function chooseContainer(rows, chosen) {
  const running = (rows ?? []).filter((row) => row.state === "running" && row.id);
  const id = running.find((row) => row.id === chosen)?.id ?? running[0]?.id ?? null;
  if (id !== state.monitor.id) state.monitor = {id, samples: [], error: null};
}

async function readSample(profile, controller) {
  const monitor = state.monitor;
  if (!monitor.id) return;
  try {
    const sample = await api(path(profile.id, `containers/${encodeURIComponent(monitor.id)}/stats`), {signal: controller.signal});
    if (!controller.signal.aborted && monitor === state.monitor) {
      monitor.samples = [...monitor.samples, sample].slice(-24);
      monitor.error = null;
    }
  } catch (error) {
    if (!controller.signal.aborted && monitor === state.monitor) monitor.error = error.code;
  }
}

function schedule() {
  clearTimeout(state.timer);
  if (!state.auth?.authenticated || !currentProfile() || state.view === "wizard" || state.view === "settings") return;
  const interval = state.preferences.interval;
  if (interval && !document.hidden) state.timer = setTimeout(() => {
    const activeControl = document.activeElement?.matches("input,select,summary")
      || document.activeElement?.closest("#content button,#content a");
    if ($("modal").open || activeControl || $("rail").classList.contains("open") || state.request) schedule();
    else void refresh();
  }, interval * 1000);
}

async function refresh(manual = false) {
  const profile = currentProfile();
  const view = state.view;
  if (!profile || view === "wizard" || view === "settings" || document.hidden) {
    if (!profile) state.status = "disconnected";
    renderStatus();
    return;
  }
  if (state.request) {
    if (!manual) return;
    state.request.abort();
  }
  const controller = new AbortController();
  state.request = controller;
  const suffix = ["overview", "diagnostics"].includes(view) ? "snapshot" :
    view === "connections" ? "status" : `inventory/${view === "monitoring" ? "containers" : view}`;
  if (!state.payload && !state.error) {
    state.status = "connecting";
    renderStatus();
  }
  try {
    const result = await api(path(profile.id, suffix), {signal: controller.signal});
    if (controller.signal.aborted) return;
    state.payload = result;
    state.error = null;
    state.status = "online";
    state.lastRead = result.at ?? Math.floor(Date.now() / 1000);
    if (["overview", "monitoring"].includes(view)) {
      chooseContainer(monitorRows(), state.monitor.id);
      if (!manual && !state.monitor.samples.length) render();
      await readSample(profile, controller);
    }
    if (controller.signal.aborted) return;
    if (manual) notify(t("loaded"));
  } catch (error) {
    if (controller.signal.aborted) return;
    state.payload = null;
    state.error = error.code;
    state.status = error.code === "unsupported" ? "online" : "offline";
    state.checked.set(profile.id, {error: error.code});
    state.monitor = {id: null, samples: [], error: null};
  } finally {
    if (state.request === controller) {
      state.request = null;
      renderStatus();
      render();
      schedule();
    }
  }
}

function modal(title, content) {
  const dialog = $("modal");
  if (!dialog.open) lastFocus = document.activeElement;
  dialog.innerHTML = `<div class="pad stack"><header class="modal-top"><h2 id="modal-title">${esc(title)}</h2>
    <button class="icon-button quiet" type="button" aria-label="${esc(t("close"))}" data-action="modal-close">${icon("close")}</button></header>
    <div id="modal-body" class="stack">${content}</div></div>`;
  if (!dialog.open) dialog.showModal();
}

$("modal").addEventListener("close", () => {
  state.modalRef = null;
  $("modal").replaceChildren();
  if (lastFocus?.isConnected) lastFocus.focus();
});

function closeMenu(focus = false) {
  $("rail").classList.remove("open");
  document.querySelector(".scrim").hidden = true;
  const button = document.querySelector('[data-action="menu"]');
  button.setAttribute("aria-expanded", "false");
  if (focus) button.focus();
}

function openMenu() {
  $("rail").classList.add("open");
  document.querySelector(".scrim").hidden = false;
  document.querySelector('[data-action="menu"]').setAttribute("aria-expanded", "true");
  document.querySelector("#navigation [aria-current=page]")?.focus();
}

function updateRows() {
  const mode = state.view === "overview" ? "containers" : state.view;
  const items = state.view === "overview" ? state.payload?.values.containers : state.payload?.items;
  if (!items || !$("rows")) return;
  const results = filtered(items, state.query);
  $("rows").innerHTML = inventoryRows(mode, results);
  $("row-count").textContent = t("rowCount", {count: results.length});
}

async function updatePreferences(changes) {
  state.preferences = await api("/api/preferences", {method: "PUT", data: changes});
  appearance(state.preferences);
}

async function switchAppearance(key, value) {
  if (state.view === "wizard" && $("wizard-form")) wizardForm(state.wizard, $("wizard-form"));
  if (state.auth?.authenticated) await updatePreferences({[key]: value});
  else appearance({language, theme: document.documentElement.dataset.theme, [key]: value});
  if (!state.auth?.authenticated) showAuth();
  else {
    renderChrome();
    render();
  }
}

async function rereadSession() {
  const previous = currentProfile()?.id;
  applySession(await api("/api/session"));
  if (currentProfile()?.id !== previous) {
    state.monitor = {id: null, samples: [], error: null};
    state.lastRead = null;
    state.status = "disconnected";
  }
}

async function checkDiscovery() {
  let result;
  try { result = await api("/api/discovery"); }
  catch (error) { result = {status: "blocked", reason: error.code}; }
  if (!state.auth?.authenticated) return;
  state.discovery = result;
  if (state.wizard) state.wizard.discovery = result;
  if (["wizard", "connections"].includes(state.view)) render();
}

function newProfileBody(form) {
  return Object.fromEntries(new FormData(form));
}

function profileBody(form) {
  const values = newProfileBody(form);
  if (values.transport === "ssh") {
    values.ssh_port = Number(values.ssh_port);
    const {ssh_password, ssh_private_key, ssh_passphrase} = values;
    if (ssh_password || ssh_private_key || ssh_passphrase)
      values.credentials = {password: ssh_password, private_key: ssh_private_key, passphrase: ssh_passphrase};
    delete values.ssh_password;
    delete values.ssh_private_key;
    delete values.ssh_passphrase;
  }
  return values;
}

async function test(values) {
  try { return await api("/api/profiles/test", {method: "POST", data: values}); }
  catch (error) { return {error: error.code}; }
}

async function testWizard() {
  const current = state.wizard;
  current.step = 3;
  current.result = null;
  render();
  $("wizard-result").innerHTML = opening();
  const result = await test(current.draft);
  if (state.view === "wizard" && state.wizard === current) {
    current.result = result;
    render();
    $("wizard-result")?.setAttribute("tabindex", "-1");
    $("wizard-result")?.focus();
  }
}

async function completeWizard(connect) {
  if (connect) {
    if (!state.wizard.result?.engine) return;
    const created = await api("/api/profiles", {method: "POST", data: state.wizard.draft});
    if (created.id !== state.preferences.active) {
      await api(path(created.id, "active"), {method: "PUT", data: {}});
    }
  }
  await updatePreferences({onboarded: true});
  await rereadSession();
  navigate("overview", true);
}

async function openDetail(spec) {
  if (!currentProfile()) return;
  const split = spec.indexOf(":");
  const kind = spec.slice(0, split), key = spec.slice(split + 1);
  const reference = {mode: "detail", kind, key, profile: currentProfile().id, revision: currentProfile().revision, name: null};
  state.modalRef = reference;
  modal(t("details"), opening());
  try {
    const result = await api(path(reference.profile, `inventory/${kind}/${encodeURIComponent(key)}`));
    if (state.modalRef === reference) {
      $("modal-title").textContent = result.item?.name || result.item?.tags?.[0] || t("details");
      reference.name = result.item?.name;
      $("modal-body").innerHTML = detail(kind, result.item, !state.auth?.demo);
    }
  } catch (error) {
    if (state.modalRef === reference) $("modal-body").innerHTML = failure(error.code);
  }
}

async function submit(form) {
  if (form.id === "login-form" || form.id === "setup-form") {
    const preferred = {language, theme: document.documentElement.dataset.theme};
    const endpoint = form.id === "setup-form" ? "/api/setup" : "/api/login";
    applySession(await api(endpoint, {method: "POST", data: newProfileBody(form)}));
    if (!state.auth.authenticated) {
      showAuth(state.auth.setup_pending ? undefined : "setup_complete");
      $("auth-main").focus();
      return;
    }
    if (!state.preferences.onboarded && Object.entries(preferred).some(([key, value]) => state.preferences[key] !== value)) {
      await updatePreferences(preferred);
    }
    enter();
  } else if (form.id === "wizard-form") {
    wizardForm(state.wizard, form);
    if (state.wizard.step === 2) await testWizard();
    else {
      state.wizard.step += 1;
      render();
      $("wizard-form")?.querySelector("input,select,button")?.focus();
    }
  } else if (form.id === "profile-form") {
    const reference = state.modalRef;
    const values = profileBody(form);
    if (reference.profile) {
      await api(`/api/profiles/${reference.profile.id}`, {method: "PUT", data: {...values, revision: reference.profile.revision}});
      state.checked.delete(reference.profile.id);
    } else await api("/api/profiles", {method: "POST", data: values});
    if (state.view === "wizard") await updatePreferences({onboarded: true});
    await rereadSession();
    $("modal").close();
    if (state.view === "wizard") navigate("connections", true);
    else render();
    notify(t("saved"));
    void refresh(true);
  } else if (form.id === "settings-form") {
    const values = newProfileBody(form);
    await updatePreferences({...values, interval: Number(values.interval)});
    renderChrome();
    render();
    notify(t("saved"));
  } else if (form.id === "logs-form") {
    const reference = state.modalRef;
    $("log-output").innerHTML = opening();
    try {
      const {tail} = newProfileBody(form);
      const result = await api(path(reference.profile, `containers/${encodeURIComponent(reference.key)}/logs?tail=${encodeURIComponent(tail)}`));
      if (state.modalRef === reference) $("log-output").innerHTML = result.text ? `<pre class="logs" tabindex="0">${esc(result.text)}</pre>` : `<p>${esc(t("logsEmpty"))}</p>`;
    } catch (error) {
      if (state.modalRef === reference) $("log-output").innerHTML = `<p class="error">${esc(problem(error.code))}</p>`;
    }
  }
}

async function action(name, key, button) {
  const stored = state.profiles.find((entry) => entry.id === key);
  switch (name) {
    case "bootstrap": await bootstrap(); break;
    case "language": await switchAppearance("language", key); break;
    case "theme": await switchAppearance("theme", document.documentElement.dataset.theme === "dark" ? "light" : "dark"); break;
    case "menu": $("rail").classList.contains("open") ? closeMenu(true) : openMenu(); break;
    case "close-menu": closeMenu(true); break;
    case "refresh": await refresh(true); break;
    case "logout":
      applySession(await api("/api/logout", {method: "POST", data: {}}));
      stopReads();
      state.checked.clear();
      state.monitor = {id: null, samples: [], error: null};
      state.status = "disconnected";
      state.lastRead = null;
      showAuth();
      break;
    case "wizard": navigate("wizard", true); break;
    case "wizard-advanced": state.wizard.advanced = true; render(); break;
    case "auto-check": await checkDiscovery(); break;
    case "auto-connect":
      await api("/api/discovery/connect", {method: "POST", data: {}});
      await rereadSession();
      notify(t("autoConnected"));
      navigate("overview", true);
      break;
    case "auto-skip": await completeWizard(false); break;
    case "wizard-back":
      wizardForm(state.wizard, $("wizard-form"));
      state.wizard.step -= 1;
      state.wizard.result = null;
      render();
      $("wizard-form")?.querySelector("input,select,button")?.focus();
      break;
    case "wizard-test": await testWizard(); break;
    case "wizard-finish": await completeWizard(true); break;
    case "wizard-skip": await completeWizard(false); break;
    case "profile-edit":
    case "profile-edit-ssh":
      state.modalRef = {mode: "profile", profile: stored};
      modal(t(stored ? "edit" : name === "profile-edit-ssh" ? "newSSHProfile" : "newProfile"),
        profileForm(stored, state.endpoints, name === "profile-edit-ssh" ? "ssh" : "socket"));
      break;
    case "profile-test": {
      const form = $("profile-form");
      if (!form.reportValidity()) return;
      const destination = $("profile-result");
      destination.innerHTML = opening();
      const reference = state.modalRef;
      let result;
      if (reference.profile) {
        try { result = await api(path(reference.profile.id, "test-draft"), {method: "POST",
          data: {...profileBody(form), revision: reference.profile.revision}}); }
        catch (error) { result = {error: error.code}; }
      } else result = await test(profileBody(form));
      if (destination.isConnected) destination.innerHTML = testReport(result);
      break;
    }
    case "saved-test": {
      let result;
      try { result = await api(path(stored.id, "test"), {method: "POST", data: {}}); }
      catch (error) { result = {error: error.code}; }
      if (!state.auth?.authenticated) return;
      state.checked.set(key, result);
      if (currentProfile()?.id === key) state.status = result.engine ? "online" : "offline";
      renderStatus();
      render();
      modal(t("checks"), testReport(result));
      break;
    }
    case "activate":
      await api(path(key, "active"), {method: "PUT", data: {}});
      await rereadSession();
      render();
      await refresh(true);
      break;
    case "profile-remove":
      modal(t("confirmRemove"), `<p>${esc(stored.name)}</p><p>${esc(t("removeHint"))}</p><div class="actions">
        ${elButton(t("cancel"), "modal-close")}${elButton(t("remove"), "confirm-delete", {key, cls: "danger"})}</div>`);
      break;
    case "confirm-delete":
      await api(`/api/profiles/${key}`, {method: "DELETE", data: {revision: stored.revision}});
      state.checked.delete(key);
      await rereadSession();
      $("modal").close();
      renderStatus();
      render();
      notify(t("removed"));
      break;
    case "modal-close": $("modal").close(); break;
    case "detail": await openDetail(key); break;
    case "container-action": {
      const ref = state.modalRef;
      if (ref?.mode !== "detail" || ref.kind !== "containers" || state.auth?.demo
          || ref.profile !== currentProfile()?.id || ref.revision !== currentProfile()?.revision) return;
      const subject = ref.name || ref.key;
      if (!window.confirm(t("confirmContainerAction", {action: t("action_" + key), name: subject}))) return;
      const confirmation = key === "remove" ? window.prompt(t("confirmContainerRemove", {name: subject})) : ref.key;
      if (key === "remove" && confirmation !== subject) return;
      const buttons = $("modal-body").querySelectorAll("[data-action=container-action]");
      buttons.forEach((control) => control.disabled = true);
      try {
        await api(path(ref.profile, `containers/${encodeURIComponent(ref.key)}/action`), {
          method: "POST", data: {action: key, revision: ref.revision, confirmation},
        });
        notify(t("actionDone"));
        if (state.modalRef === ref) {
          if (key === "remove") $("modal").close();
          else await openDetail("containers:" + ref.key);
        }
        await refresh(true);
      } catch (error) {
        const message = ["timeout", "ssh_connection", "disconnected", "bad_engine", "bad_response", "network"].includes(error.code)
          ? t("actionUncertain") : problem(error.code);
        notify(message);
        if (state.modalRef === ref) $("container-action-status").textContent = message;
        await refresh(true);
      } finally {
        buttons.forEach((control) => control.disabled = false);
      }
      break;
    }
    case "disk": {
      const profile = currentProfile();
      const view = state.view;
      try { state.disk = await api(path(profile.id, "disk")); }
      catch (error) { state.disk = {error: error.code}; }
      if (view === state.view && profile.id === currentProfile()?.id) {
        render();
        document.querySelector('[data-action="disk"]')?.focus();
      }
      break;
    }
    default: button.disabled = false;
  }
}

$("skip").addEventListener("click", (event) => {
  event.preventDefault();
  ($(state.auth?.authenticated ? "main" : "auth-main"))?.focus();
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const name = button.dataset.action;
  button.disabled = true;
  try { await action(name, button.dataset.key, button); }
  catch (error) { notify(problem(error.code)); }
  finally { if (button.isConnected) button.disabled = false; }
});

document.addEventListener("submit", async (event) => {
  const form = event.target;
  event.preventDefault();
  const button = event.submitter;
  if (button) button.disabled = true;
  try { await submit(form); }
  catch (error) {
    if (error.code === "setup_expired" || error.code === "setup_complete") {
      await bootstrap(error.code);
      $("auth-main")?.focus();
    } else if ((form.id === "login-form" || form.id === "setup-form") && $("login-error")) {
      $("login-error").hidden = false;
      $("login-error").textContent = problem(error.code);
    } else notify(problem(error.code));
  } finally { if (button?.isConnected) button.disabled = false; }
});

document.addEventListener("input", (event) => {
  if (event.target.id === "search") {
    state.query.search = event.target.value;
    updateRows();
  }
});

document.addEventListener("change", async (event) => {
  const field = event.target;
  if (["sort", "state"].includes(field.name)) {
    state.query[field.name] = field.value;
    updateRows();
  }
  if (field.name === "selectedContainer" && currentProfile()) {
    chooseContainer(monitorRows(), field.value);
    await refresh(true);
    document.querySelector('[name="selectedContainer"]')?.focus();
  }
});

window.addEventListener("hashchange", () => { if (state.auth?.authenticated) navigate(route(), true); });
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && $("rail").classList.contains("open")) closeMenu(true);
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) stopReads();
  else if (dataViews.has(state.view) && !state.payload) void refresh();
  else schedule();
});

appearance({language: locally.get("language") ?? "en", theme: locally.get("theme") ?? "dark"});
$("boot").textContent = t("boot");
void bootstrap();
