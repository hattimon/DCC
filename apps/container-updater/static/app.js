'use strict';

const ui = JSON.parse(document.getElementById('ui-translations').textContent);
const t = (key, values = {}) => Object.entries(values).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), ui[key] || key);
const $ = id => document.getElementById(id);
const csrf = document.querySelector('meta[name="csrf-token"]').content;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let busy = false;
let allItems = [];
let lastSelfCheck = null;
let autoScanOnRefresh = false;
let scheduleState = null;
let scheduleDirty = false;
const scheduleTargets = new Set();
const tabs = ['containers', 'schedule', 'reports', 'settings'];
let reportPage = 1;
let reportSignature = '';
const openReports = new Set();
let preferences = JSON.parse($('panel-preferences').textContent);
let audioContext = null;
const picked = new Set();

async function unlockAudio() {
  if (!preferences.sounds_enabled) return;
  const Audio = window.AudioContext || window.webkitAudioContext;
  if (!Audio) return;
  try {
    audioContext ||= new Audio();
    if (audioContext.state === 'suspended') await audioContext.resume();
  } catch (_) { /* Audio permissions never block container operations. */ }
}
document.addEventListener('pointerdown', unlockAudio, {once:true});
document.addEventListener('keydown', unlockAudio, {once:true});
function playSound(event) {
  if (!preferences.sounds_enabled || audioContext?.state !== 'running') return;
  const notes = {start:[523],success:[523,659,784],error:[330,247],update:[659,880]}[event] || [523];
  const profiles = {soft:{type:'sine',gain:.025,step:.1},chime:{type:'sine',gain:.035,step:.15},digital:{type:'triangle',gain:.018,step:.08}};
  const profile = profiles[preferences.sound_style] || profiles.soft;
  try {
    notes.forEach((frequency,index) => {
      const at = audioContext.currentTime + index*profile.step;
      const oscillator = audioContext.createOscillator(); const gain = audioContext.createGain();
      oscillator.type = profile.type; oscillator.frequency.value = frequency;
      gain.gain.setValueAtTime(0,at); gain.gain.linearRampToValueAtTime(profile.gain,at+.012); gain.gain.exponentialRampToValueAtTime(.0001,at+profile.step+.04);
      oscillator.connect(gain); gain.connect(audioContext.destination); oscillator.start(at); oscillator.stop(at+profile.step+.05);
      oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
    });
  } catch (_) { /* Unsupported audio is optional. */ }
}
async function loadInfrastructure() {
  try {
    const info = await api('/api/infrastructure');
    if (!info.available) throw new Error(info.message);
    $('host-system').textContent = [info.name,info.operating_system || info.os_type,info.architecture].filter(Boolean).join(' · ');
    const resources = [info.docker_version ? `Docker ${info.docker_version}` : '', info.cpus ? `${info.cpus} CPU` : '', info.memory_bytes ? `${new Intl.NumberFormat(document.documentElement.lang,{maximumFractionDigits:1}).format(info.memory_bytes/2**30)} GiB RAM` : ''];
    $('host-engine').textContent = resources.filter(Boolean).join(' · ');
    $('host-system').title = /docker desktop/i.test(info.operating_system) ? t('host_desktop_hint') : info.kernel_version || '';
  } catch (_) { $('host-system').textContent = t('host_unavailable'); }
}

function element(tag, className = '', text = '') {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}
function showStatus(message, kind = '') {
  $('status').textContent = message;
  $('status').className = `status ${kind}`;
}
function showWarning(message = '') {
  $('startup-warning').textContent = message;
  $('startup-warning').hidden = !message;
}
function setBusy(value) {
  busy = value;
  $('progress').classList.toggle('active', value);
  for (const id of ['scan', 'check-self', 'select-updates', 'select-all']) $(id).disabled = value;
  $('update-self').disabled = value || !lastSelfCheck?.supported;
  $('update').disabled = value || picked.size === 0;
  $('schedule-save').disabled = value || !!scheduleState?.pending || !!scheduleState?.storage_error;
  $('notification-save').disabled = value;
  $('preferences-save').disabled = value;
  $('sound-preview').disabled = value || !preferences.sounds_enabled;
  for (const id of ['registry-save','registry-remove','registry-undo','mount-plan']) $(id).disabled = value;
  document.querySelectorAll('.notify-test').forEach(button => { button.disabled = value; });
  $('update-label').textContent = picked.size ? t('selected_count', {count: picked.size}) : t('update_selected');
  document.querySelectorAll('.pick').forEach(check => { check.disabled = value; });
  document.querySelectorAll('.auto-switch').forEach(check => { check.disabled = value; });
  document.querySelectorAll('.language-picker button').forEach(button => { button.disabled = value; });
  const visible = [...document.querySelectorAll('.pick')];
  $('select-all').checked = visible.length > 0 && visible.every(check => check.checked);
  $('select-all').indeterminate = visible.some(check => check.checked) && !$('select-all').checked;
}
function addAdvanced(cell, item) {
  const details = element('details', 'advanced');
  details.append(element('summary', '', t('advanced')));
  details.append(element('p', '', t('tag_scope')));
  details.append(element('p', '', item.persistent_mounts?.length ? t('mounts_kept') : t('no_mounts')));
  if (item.persistent_mounts?.length) {
    details.append(element('strong', '', t('storage')));
    const list = element('ul');
    item.persistent_mounts.forEach(path => { const li = element('li'); li.append(element('code', '', path)); list.append(li); });
    details.append(list);
  }
  if (item.is_compose) {
    details.append(element('p', '', t('compose_alternative')), element('p', '', t('compose_commands')), element('pre', '', 'docker compose pull\ndocker compose up -d'));
  }
  if (item.check_error) details.append(element('p', '', t('registry_alternative')));
  if (item.auto_update_reason) details.append(element('p', '', item.auto_update_reason));
  if (!item.supported && !item.is_panel) details.append(element('p', '', t('runtime_alternative')));
  details.append(element('p', '', t('backup')));
  cell.append(details);
}
function render(items = allItems) {
  allItems = items;
  const eligible = items.filter(item => item.supported && item.update_available && !item.check_error && !item.is_panel);
  const ids = new Set(eligible.map(item => item.id));
  for (const id of picked) if (!ids.has(id)) picked.delete(id);
  $('count').textContent = items.length;
  $('available-count').textContent = eligible.length;
  $('auto-count').textContent = items.filter(item => item.auto_update_on_startup).length;
  const query = $('filter').value.trim().toLocaleLowerCase();
  const filtered = items.filter(item => (preferences.show_unavailable || item.is_panel || (item.supported && !item.check_error)) && `${item.name} ${item.current_image} ${item.target_image || ''}`.toLocaleLowerCase().includes(query));
  const rows = $('rows');
  rows.replaceChildren();
  if (!filtered.length) {
    const row = element('tr'); const cell = element('td', 'empty', t(items.length && !query && !preferences.show_unavailable ? 'hidden_unavailable' : items.length ? 'no_matches' : 'empty')); cell.colSpan = 7; row.append(cell); rows.append(row);
  }
  for (const item of filtered) {
    const row = element('tr', picked.has(item.id) ? 'selected' : '');
    const cells = Array.from({length: 7}, () => element('td'));
    row.append(...cells);
    if (ids.has(item.id)) {
      const check = element('input', 'pick'); check.type = 'checkbox'; check.value = item.id; check.checked = picked.has(item.id); check.setAttribute('aria-label', t('pick', {name: item.name}));
      check.addEventListener('change', () => { check.checked ? picked.add(item.id) : picked.delete(item.id); row.classList.toggle('selected', check.checked); setBusy(busy); });
      cells[0].append(check);
    }
    const stateKey = {restarting: 'restarting_state', error: 'error_state'}[item.status] || item.status || 'unknown';
    cells[1].append(element('div', 'name', item.name), element('div', `state ${item.status === 'running' ? 'running' : ''}`, t(stateKey)));
    if (item.auto_update_supported ?? item.supported) {
      const toggle = element('input', 'auto-switch'); toggle.type = 'checkbox'; toggle.checked = !!item.auto_update_on_startup; toggle.setAttribute('aria-label', t('auto_label', {name: item.name}));
      toggle.addEventListener('change', async () => {
        const enabled = toggle.checked; setBusy(true);
        try { const result = await api('/api/auto-update', {container_id: item.id, name: item.name, enabled}); item.auto_update_on_startup = enabled; showStatus(result.message, 'ok'); render(); }
        catch (error) { toggle.checked = !enabled; showStatus(error.message, 'error'); }
        finally { setBusy(false); }
      }); cells[2].append(toggle);
    } else cells[2].append(element('span', 'manual-label', t(item.is_compose ? 'manual_compose' : 'unavailable')));
    const status = item.is_panel ? 'self' : !item.supported ? 'blocked' : item.update_available ? 'available' : item.check_error ? 'unchecked' : 'current';
    cells[3].append(element('span', `badge ${status}`, t(`${status}_badge`)));
    cells[4].className = cells[5].className = 'image';
    cells[4].textContent = item.current_image || '—'; cells[5].textContent = item.target_image || '—';
    cells[6].append(element('div', 'detail', [item.source, item.message].filter(Boolean).join(' · ')));
    if (item.last_update_result) cells[6].append(element('div', `detail update-result ${item.last_update_ok ? 'ok' : 'error'}`, item.last_update_result));
    if (item.has_update_instructions) cells[6].append(element('div', 'detail', t('instructions')));
    addAdvanced(cells[6], item);
    rows.append(row);
  }
  setBusy(busy);
  renderScheduleTargets();
}
async function api(path, payload) {
  const response = await fetch(path, {method: payload === undefined ? 'GET' : 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body: payload === undefined ? undefined : JSON.stringify(payload)});
  if (response.status === 401) { location.assign('/login'); throw new Error(t('session_expired')); }
  const result = await response.json();
  if (!response.ok) { const error = new Error(result.error || result.progress || t('job_error')); error.status = response.status; error.job = result; throw error; }
  return result;
}
async function waitJob(state) {
  while (state.status === 'queued' || state.status === 'running') {
    showStatus(state.progress || t('loading')); await pause(900); state = await api(`/api/job?id=${encodeURIComponent(state.id)}`);
  }
  if (state.status === 'error') throw new Error(state.progress || t('job_error'));
  return state;
}
async function runJob(path, payload = {}) {
  setBusy(true);
  if (path !== '/api/self-update/check') playSound('start');
  // Join an existing serialized job, then submit the requested action. Its results
  // must never be mistaken for those of a different operation.
  for (;;) {
    try {
      const job = await waitJob(await api(path, payload));
      if (path !== '/api/self-update/check') playSound(job.results?.ok === false || job.results?.updates?.some(item => !item.ok) ? 'error' : 'success');
      return job;
    }
    catch (error) {
      if (error.status !== 409 || !['queued', 'running'].includes(error.job?.status)) throw error;
      const completed = await waitJob(error.job);
      if (completed.results?.started) { await reconnectPanel(completed.instance); return completed; }
    }
  }
}
function presentScan(result) {
  const outcomes = result.updates || [];
  const byName = new Map(outcomes.map(item => [item.name, item]));
  render((Array.isArray(result) ? result : result.containers || []).map(item => {
    const outcome = byName.get(item.name);
    return outcome ? {...item, last_update_result: outcome.result, last_update_ok: outcome.ok} : item;
  }));
  if (outcomes.length) {
    const ok = outcomes.filter(item => item.ok).length;
    showStatus(t('update_done', {ok, failed: outcomes.length - ok}), ok === outcomes.length ? 'ok' : 'error');
    const errors = outcomes.filter(item => !item.ok).map(item => `${item.name || item.id || ''}: ${item.result || item.message || item.error || t('job_error')}`);
    if (errors.length) showWarning(errors.join(' · '));
  } else showStatus(t('scan_done', {count: allItems.length}), 'ok');
}
async function scan(defer = false) {
  const job = await runJob('/api/scan', {defer_panel_update: defer});
  presentScan(job.results);
  await loadLastScan(false);
}
async function loadLastScan(restoreRows = true) {
  const cached = await api('/api/containers');
  autoScanOnRefresh = cached.auto_scan_on_refresh === true;
  $('auto-scan').checked = autoScanOnRefresh;
  if (!cached.scanned_at) return;
  const date = new Date(cached.scanned_at * 1000);
  $('last-scan').dateTime = date.toISOString();
  $('last-scan').textContent = new Intl.DateTimeFormat(document.documentElement.lang === 'pl' ? 'pl-PL' : 'en-GB', {dateStyle: 'medium', timeStyle: 'medium'}).format(date);
  if (restoreRows) render(cached.containers);
}
function askPanelUpdate(result) {
  const dialog = $('self-update-dialog');
  $('self-update-detail').textContent = result.message || '';
  $('dialog-update').disabled = !result.supported;
  dialog.returnValue = '';
  return new Promise(resolve => { dialog.addEventListener('close', () => resolve(dialog.returnValue === 'install'), {once: true}); dialog.showModal(); });
}
async function reconnectPanel(previousInstance) {
  showStatus(t('restarting')); setBusy(true);
  const deadline = Date.now() + 180000;
  while (Date.now() < deadline) {
    await pause(2000);
    try {
      const response = await fetch('/api/job', {cache: 'no-store'});
      if (response.status === 401) { location.assign('/login'); return; }
      if (response.ok && (await response.json()).instance !== previousInstance) { location.reload(); return; }
    } catch (_) { /* The old container has stopped; wait for its replacement. */ }
  }
  throw new Error(t('restart_timeout'));
}
async function checkPanelUpdate() {
  setBusy(true); showWarning(); showStatus(t('loading'));
  let result;
  try {
    result = (await runJob('/api/self-update/check')).results;
    lastSelfCheck = result;
    $('update-self').hidden = !result.update_available;
  } catch (error) { showWarning(`${t('check_failed')} ${error.message}`); }
  if (result?.update_available) {
    playSound('update');
    const install = await askPanelUpdate(result);
    if (install) {
      const job = await runJob('/api/self-update');
      if (job.results.started) { await reconnectPanel(job.instance); return 'restarting'; }
      showWarning(job.results.message || t('check_failed'));
    }
  } else if (result && !result.checked) { showWarning(result.message || t('check_failed')); playSound('error'); }
  showStatus(result?.checked && !result.update_available ? t('panel_current') : t('waiting'), result?.checked && !result.update_available ? 'ok' : '');
}
async function action(work) {
  if (busy) return;
  try { await work(); } catch (error) { showStatus(error.message, 'error'); playSound('error'); }
  finally { setBusy(false); }
}
$('check-self').addEventListener('click', () => action(checkPanelUpdate));
$('update-self').addEventListener('click', () => action(checkPanelUpdate));
$('scan').addEventListener('click', () => action(() => scan(!!lastSelfCheck?.update_available)));
$('auto-scan').addEventListener('change', () => action(async () => {
  const enabled = $('auto-scan').checked;
  setBusy(true);
  try {
    const saved = await api('/api/scan-settings', {auto_scan_on_refresh: enabled});
    autoScanOnRefresh = saved.auto_scan_on_refresh;
    showStatus(saved.message, 'ok');
  } catch (error) { $('auto-scan').checked = autoScanOnRefresh; throw error; }
}));
$('show-all').addEventListener('change', () => action(async () => {
  const enabled=$('show-all').checked; setBusy(true);
  try { await api('/api/preferences',{show_unavailable:enabled}); preferences.show_unavailable=enabled; render(); }
  catch(error) { $('show-all').checked=!!preferences.show_unavailable; throw error; }
}));
$('filter').addEventListener('input', () => render());
$('select-updates').addEventListener('click', () => { document.querySelectorAll('.pick').forEach(check => picked.add(check.value)); render(); });
$('select-all').addEventListener('change', event => { document.querySelectorAll('.pick').forEach(check => event.target.checked ? picked.add(check.value) : picked.delete(check.value)); render(); });
$('update').addEventListener('click', () => action(async () => {
  if (!picked.size || !confirm(t('confirm_updates', {count: picked.size}))) return;
  showWarning(); const job = await runJob('/api/update', {container_ids: [...picked]}); picked.clear(); presentScan(job.results); await loadLastScan(false);
}));
$('password-form').addEventListener('submit', event => { event.preventDefault(); action(async () => {
  const result = await api('/api/password', {old_password: $('old-password').value, new_password: $('new-password').value});
  event.target.reset(); showStatus(result.message, 'ok');
}); });

function selectTab(name) {
  for (const tab of tabs) {
    $(`tab-${tab}`).setAttribute('aria-selected', String(tab === name));
    $(`tab-${tab}`).tabIndex = tab === name ? 0 : -1;
    $(`${tab}-panel`).hidden = tab !== name;
  }
  if (name === 'reports') loadReports().catch(error => { $('report-storage-error').hidden = false; $('report-storage-error').textContent = error.message; });
}
for (const name of tabs) {
  $(`tab-${name}`).addEventListener('click', () => selectTab(name));
  $(`tab-${name}`).addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? tabs[0] : event.key === 'End' ? tabs.at(-1) : tabs[(tabs.indexOf(name) + (event.key === 'ArrowLeft' ? tabs.length - 1 : 1)) % tabs.length];
    selectTab(next); $(`tab-${next}`).focus();
  });
}
function scheduleFields() {
  const kind = $('schedule-kind').value;
  $('schedule-date-field').hidden = !['once', 'interval'].includes(kind);
  $('schedule-date').required = !$('schedule-date-field').hidden;
  $('schedule-weekday-field').hidden = kind !== 'weekly';
  $('schedule-monthday-field').hidden = kind !== 'monthly';
  $('schedule-interval-field').hidden = kind !== 'interval';
  $('schedule-targets-field').hidden = $('schedule-action').value !== 'update';
  $('schedule-all-hint').hidden = $('schedule-action').value !== 'update_all';
}
function renderScheduleTargets() {
  const box = $('schedule-targets');
  box.replaceChildren();
  const available = new Map(allItems.filter(item => !item.is_panel && !item.is_compose && (item.auto_update_supported ?? item.supported)).map(item => [item.name, item]));
  for (const name of scheduleTargets) if (!available.has(name)) available.set(name, {name});
  if (!available.size) { box.append(element('p', 'hint', t('schedule_no_targets'))); return; }
  for (const [name] of available) {
    const label = element('label'); const check = element('input'); check.type = 'checkbox'; check.checked = scheduleTargets.has(name);
    check.addEventListener('change', () => check.checked ? scheduleTargets.add(name) : scheduleTargets.delete(name));
    label.append(check, element('span', '', name)); box.append(label);
  }
}
function scheduleDate(timestamp, zone) {
  return new Intl.DateTimeFormat(document.documentElement.lang === 'pl' ? 'pl-PL' : 'en-GB', {dateStyle: 'medium', timeStyle: 'short', timeZone: zone}).format(new Date(timestamp * 1000));
}
function displaySchedule(state) {
  scheduleState = state;
  scheduleDirty = false;
  const config = state.config;
  $('schedule-enabled').checked = config.enabled;
  $('schedule-panel-first').checked = config.panel_first;
  for (const key of ['action', 'kind', 'time', 'timezone', 'weekday', 'every', 'unit']) $(`schedule-${key}`).value = config[key];
  $('schedule-monthday').value = config.month_day;
  const today = new Date();
  $('schedule-date').value = config.date || `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
  if (!state.configured) $('schedule-timezone').value = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  scheduleTargets.clear(); config.targets.forEach(target => scheduleTargets.add(target.name));
  displayScheduleStatus(state);
  renderScheduleTargets(); scheduleFields(); setBusy(busy);
}
function displayScheduleStatus(state) {
  const zone = state.config.timezone;
  $('schedule-next').textContent = state.pending ? t('schedule_running') : state.next_run ? `${scheduleDate(state.next_run, zone)} · ${zone}` : t('schedule_off');
  $('schedule-last-time').textContent = state.last_run ? `${scheduleDate(state.last_run.finished_at, zone)} · ${zone}` : '—';
  $('schedule-last-result').textContent = state.last_run?.message || t('no_runs');
  $('schedule-last-result').className = `detail ${state.last_run?.status === 'error' ? 'error' : 'ok'}`;
  if (state.storage_error) { $('schedule-status').textContent = t('schedule_storage_error'); $('schedule-status').className = 'status error'; }
}
async function loadSchedule() { displaySchedule(await api('/api/schedule')); }
$('schedule-form').addEventListener('input', () => { scheduleDirty = true; });
$('schedule-kind').addEventListener('change', scheduleFields);
$('schedule-action').addEventListener('change', scheduleFields);
$('schedule-form').addEventListener('submit', event => { event.preventDefault(); action(async () => {
  setBusy(true);
  const targets = [...scheduleTargets].map(name => ({name, repository: scheduleState?.config.targets.find(item => item.name === name)?.repository || allItems.find(item => item.name === name)?.current_image || ''}));
  const payload = {enabled: $('schedule-enabled').checked, panel_first: $('schedule-panel-first').checked,
    action: $('schedule-action').value, kind: $('schedule-kind').value, time: $('schedule-time').value,
    timezone: $('schedule-timezone').value.trim(), date: $('schedule-date').value,
    weekday: Number($('schedule-weekday').value), month_day: Number($('schedule-monthday').value),
    every: Number($('schedule-every').value), unit: $('schedule-unit').value, targets};
  try {
    const result = await api('/api/schedule', payload); displaySchedule(result);
    $('schedule-status').textContent = result.message; $('schedule-status').className = 'status ok';
  } catch (error) { $('schedule-status').textContent = error.message; $('schedule-status').className = 'status error'; }
}); });
setInterval(async () => {
  if ($('schedule-panel').hidden || document.hidden) return;
  try {
    const state = await api('/api/schedule');
    const completed = state.last_run?.finished_at !== scheduleState?.last_run?.finished_at;
    if (!scheduleDirty && !busy) displaySchedule(state);
    else { scheduleState = state; displayScheduleStatus(state); }
    if (completed && !busy) { await loadLastScan(); playSound(state.last_run?.status === 'error' ? 'error' : 'success'); }
  } catch (_) { /* A disconnected panel keeps the last visible schedule state. */ }
}, 10000);

async function loadReports(page = reportPage) {
  const data = await api(`/api/reports?page=${page}&issues_only=${$('reports-issues').checked ? '1' : '0'}`);
  reportPage = data.page;
  $('reports-page').textContent = t('report_page', {page: data.page, pages: data.pages});
  $('reports-prev').disabled = data.page <= 1; $('reports-next').disabled = data.page >= data.pages;
  $('report-storage-error').hidden = !data.storage_error;
  const signature = JSON.stringify(data);
  if (signature === reportSignature) return;
  reportSignature = signature;
  const list = $('report-list'); list.replaceChildren();
  if (!data.entries.length) list.append(element('p', 'empty', t('no_reports')));
  for (const entry of data.entries) {
    const row = element('article', 'report-row'); const header = element('div', 'report-row-header');
    const date = element('time', 'report-time', scheduleDate(entry.occurred_at, Intl.DateTimeFormat().resolvedOptions().timeZone)); date.dateTime = new Date(entry.occurred_at*1000).toISOString();
    let summary = entry.message || t('report_success_badge');
    if (entry.status === 'error' || entry.status === 'warning') summary = t('report_issues', {count: entry.issues || entry.details.length || 1});
    else if (entry.updated) summary = t('report_success', {count: entry.updated});
    else if (['scan', 'schedule_scan'].includes(entry.kind)) summary = t('report_scan', {count: entry.scanned});
    header.append(date, element('span', '', t(`kind_${entry.kind}`)), element('span', `badge ${entry.status}`, t(`report_${entry.status}_badge`)), element('span', '', summary));
    row.append(header);
    if (entry.status === 'error' || entry.status === 'warning') {
      const details = element('details'); details.open = openReports.has(entry.id);
      details.addEventListener('toggle', () => { details.open ? openReports.add(entry.id) : openReports.delete(entry.id); });
      details.append(element('summary', '', t('details')));
      if (entry.message) details.append(element('p', '', entry.message));
      const diagnostics = element('div', 'report-diagnostics');
      for (const item of entry.details) {
        const line = element('div', 'report-diagnostic');
        if (item.name) line.append(element('strong', 'report-container', item.name));
        line.append(element('span', '', item.result)); diagnostics.append(line);
      }
      details.append(diagnostics);
      if (entry.help_codes?.length) {
        const guidance = element('section', 'report-guidance'); guidance.append(element('h4', '', t('suggested_steps')));
        const steps = element('ul'); entry.help_codes.forEach(code => steps.append(element('li', '', t(`help_${code}`))));
        guidance.append(steps); details.append(guidance);
        const advanced = element('button','quiet',t('advanced_updates')); advanced.type='button';
        advanced.addEventListener('click',()=>{ selectTab('settings'); $('advanced-settings').open=true; $('advanced-settings').scrollIntoView({behavior:'smooth',block:'start'}); });
        details.append(advanced);
      }
      for (const [channel, delivery] of Object.entries(entry.delivery || {})) details.append(element('p', '', `${channel}: ${t(`delivery_${delivery.status}`)}${delivery.message ? ' · '+delivery.message : ''}`));
      row.append(details);
    }
    list.append(row);
  }
}
for (const [id, offset] of [['reports-prev', -1], ['reports-next', 1]]) $(id).addEventListener('click', () => loadReports(reportPage+offset).catch(error => showStatus(error.message,'error')));
$('refresh-reports').addEventListener('click', () => loadReports().catch(error => showStatus(error.message,'error')));
$('reports-issues').addEventListener('change', () => loadReports(1).catch(error => showStatus(error.message,'error')));
setInterval(() => { if (!$('reports-panel').hidden && !document.hidden) loadReports().catch(() => {}); }, 10000);

const notificationFields = {
  telegram: ['bot_token','chat_id'], signal: ['url','number','recipients','bearer_token'],
  whatsapp: ['access_token','phone_id','recipients','template','template_language','api_version'],
  email: ['host','port','security','username','password','sender','recipients'],
};
const notificationSecrets = {telegram:'bot_token',signal:'bearer_token',whatsapp:'access_token',email:'password'};
function displayNotifications(config) {
  $('notify-enabled').checked = config.enabled; $('notify-scan-errors').checked = config.scan_errors; $('notify-language').value = config.language;
  for (const [channel, fields] of Object.entries(notificationFields)) {
    $('notify-'+channel+'-enabled').checked = config[channel].enabled;
    $('notify-'+channel+'-clear').checked = false;
    $('notify-'+channel+'-configured').textContent = t(config[channel].enabled ? 'configured' : 'not_configured');
    for (const field of fields) {
      const input = $(`notify-${channel}-${field}`);
      input.value = config[channel][field] || '';
      if (field === notificationSecrets[channel]) input.placeholder = config[channel].secret_saved ? t('secret_saved') : '';
    }
  }
  if (config.storage_error) { $('notification-status').textContent = t('reports_storage_error'); $('notification-status').className = 'status error'; }
}
async function loadNotifications() { displayNotifications(await api('/api/notifications')); }
$('notification-form').addEventListener('submit', event => { event.preventDefault(); action(async () => {
  setBusy(true);
  const payload = {enabled:$('notify-enabled').checked,scan_errors:$('notify-scan-errors').checked,language:$('notify-language').value};
  for (const [channel, fields] of Object.entries(notificationFields)) {
    payload[channel] = {enabled:$('notify-'+channel+'-enabled').checked,clear_secret:$('notify-'+channel+'-clear').checked};
    for (const field of fields) payload[channel][field] = $(`notify-${channel}-${field}`).value;
  }
  try { const result = await api('/api/notifications',payload); displayNotifications(result); $('notification-status').textContent=result.message; $('notification-status').className='status ok'; }
  catch (error) { $('notification-status').textContent=error.message; $('notification-status').className='status error'; }
}); });
document.querySelectorAll('.notify-test').forEach(button => button.addEventListener('click', () => action(async () => {
  setBusy(true);
  try { const result=await api('/api/notifications/test',{channel:button.dataset.channel}); $('notification-status').textContent=result.message; $('notification-status').className='status ok'; }
  catch (error) { $('notification-status').textContent=error.message; $('notification-status').className='status error'; }
})));
$('preferences-form').addEventListener('change', () => {
  preferences = {...preferences,theme:document.querySelector('input[name=theme]:checked').value,sounds_enabled:$('sounds-enabled').checked,sound_style:$('sound-style').value};
  document.documentElement.dataset.theme = preferences.theme;
  $('sound-preview').disabled = busy || !preferences.sounds_enabled;
  if (!preferences.sounds_enabled && audioContext?.state === 'running') audioContext.suspend().catch(() => {});
  else unlockAudio();
});
$('sound-preview').addEventListener('click', async () => { await unlockAudio(); playSound('success'); });
$('preferences-form').addEventListener('submit', event => { event.preventDefault(); action(async () => {
  setBusy(true);
  try {
    const result = await api('/api/preferences',preferences);
    $('preferences-status').textContent = result.message; $('preferences-status').className = 'status ok'; playSound('success');
  } catch (error) { $('preferences-status').textContent=error.message; $('preferences-status').className='status error'; playSound('error'); }
}); });
async function loadRegistryAccess() {
  const state = await api('/api/registry-access'); const list=$('registry-list'); list.replaceChildren();
  for (const item of state.registries) {
    const button=element('button','quiet',`${item.registry} · ${item.username || '—'}`); button.type='button';
    button.addEventListener('click',()=>{ $('registry-host').value=item.registry; $('registry-username').value=item.username; $('registry-password').value=''; });
    list.append(button);
  }
  if(state.storage_error) { $('registry-status').textContent=t('registry_credentials_hint'); $('registry-status').className='status error'; }
}
async function changeRegistry(operation) {
  setBusy(true);
  try {
    const result=await api('/api/registry-access',{action:operation,registry:$('registry-host').value,username:$('registry-username').value,password:$('registry-password').value});
    $('registry-password').value=''; $('registry-status').textContent=result.message; $('registry-status').className='status ok'; await loadRegistryAccess(); playSound('success');
  } catch(error) { $('registry-status').textContent=error.message; $('registry-status').className='status error'; playSound('error'); }
}
$('registry-form').addEventListener('submit',event=>{ event.preventDefault(); action(()=>changeRegistry('save')); });
for (const operation of ['remove','undo']) $(`registry-${operation}`).addEventListener('click',()=>action(()=>changeRegistry(operation)));
$('mount-plan-form').addEventListener('submit',event=>{ event.preventDefault(); action(async()=>{
  setBusy(true);
  try {
    const plan=await api('/api/advanced/mount-plan',{path:$('mount-path').value,read_capability:$('mount-capability').checked});
    const box=$('mount-plan-output'); box.replaceChildren(); box.hidden=false;
    const block=(title,text)=>{ box.append(element('h4','',title)); if(text)box.append(element('pre','',text)); };
    block(t('plan_inspect'),plan.inspect); box.append(element('p','hint',t('plan_backup_note')));
    block(t('plan_parameter'),plan.parameter); block(t('plan_prepare'),plan.prepare);
    box.append(element('p','hint',t(plan.compose?'plan_compose':'plan_recreate')));
    if(plan.compose) { block('Compose',plan.compose_snippet); block('Docker Compose',plan.apply); }
    block(t('plan_undo'),plan.undo); $('mount-plan-status').textContent='';
  } catch(error) { $('mount-plan-status').textContent=error.message; $('mount-plan-status').className='status error'; $('mount-plan-output').hidden=true; }
}); });
loadRegistryAccess().catch(error=>{ $('registry-status').textContent=error.message; });
loadInfrastructure();

action(async () => {
  await Promise.all([loadLastScan(), loadSchedule(), loadNotifications()]);
  const state = await checkPanelUpdate();
  if (autoScanOnRefresh && state !== 'restarting') await scan(!!lastSelfCheck?.update_available);
});
