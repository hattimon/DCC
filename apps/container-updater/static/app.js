'use strict';

const ui = JSON.parse(document.getElementById('ui-translations').textContent);
const t = (key, values = {}) => Object.entries(values).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), ui[key] || key);
const $ = id => document.getElementById(id);
const csrf = document.querySelector('meta[name="csrf-token"]').content;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let busy = false;
let allItems = [];
let lastSelfCheck = null;
const picked = new Set();

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
  if (!item.supported && !item.is_panel) details.append(element('p', '', t('runtime_alternative')));
  details.append(element('p', '', t('backup')));
  cell.append(details);
}
function render(items = allItems) {
  allItems = items;
  const eligible = items.filter(item => item.supported && item.update_available && !item.is_panel);
  const ids = new Set(eligible.map(item => item.id));
  for (const id of picked) if (!ids.has(id)) picked.delete(id);
  $('count').textContent = items.length;
  $('available-count').textContent = eligible.length;
  $('auto-count').textContent = items.filter(item => item.auto_update_on_startup).length;
  const query = $('filter').value.trim().toLocaleLowerCase();
  const filtered = items.filter(item => `${item.name} ${item.current_image} ${item.target_image || ''}`.toLocaleLowerCase().includes(query));
  const rows = $('rows');
  rows.replaceChildren();
  if (!filtered.length) {
    const row = element('tr'); const cell = element('td', 'empty', t(items.length ? 'no_matches' : 'empty')); cell.colSpan = 7; row.append(cell); rows.append(row);
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
  // Join an existing serialized job, then submit the requested action. Its results
  // must never be mistaken for those of a different operation.
  for (;;) {
    try { return await waitJob(await api(path, payload)); }
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
async function checkPanelThenScan() {
  setBusy(true); showWarning(); showStatus(t('loading'));
  let result;
  try {
    result = (await runJob('/api/self-update/check')).results;
    lastSelfCheck = result;
    $('update-self').hidden = !result.update_available;
  } catch (error) { showWarning(`${t('check_failed')} ${error.message}`); }
  if (result?.update_available) {
    const install = await askPanelUpdate(result);
    if (install) {
      const job = await runJob('/api/self-update');
      if (job.results.started) { await reconnectPanel(job.instance); return; }
      showWarning(job.results.message || t('check_failed'));
    }
    await scan(true);
  } else {
    if (result && !result.checked) showWarning(result.message || t('check_failed'));
    await scan();
  }
}
async function action(work) {
  if (busy) return;
  try { await work(); } catch (error) { showStatus(error.message, 'error'); }
  finally { setBusy(false); }
}
$('check-self').addEventListener('click', () => action(checkPanelThenScan));
$('update-self').addEventListener('click', () => action(checkPanelThenScan));
$('scan').addEventListener('click', () => action(() => scan(!!lastSelfCheck?.update_available)));
$('filter').addEventListener('input', () => render());
$('select-updates').addEventListener('click', () => { document.querySelectorAll('.pick').forEach(check => picked.add(check.value)); render(); });
$('select-all').addEventListener('change', event => { document.querySelectorAll('.pick').forEach(check => event.target.checked ? picked.add(check.value) : picked.delete(check.value)); render(); });
$('update').addEventListener('click', () => action(async () => {
  if (!picked.size || !confirm(t('confirm_updates', {count: picked.size}))) return;
  showWarning(); const job = await runJob('/api/update', {container_ids: [...picked]}); picked.clear(); presentScan(job.results);
}));
$('password-form').addEventListener('submit', event => { event.preventDefault(); action(async () => {
  const result = await api('/api/password', {old_password: $('old-password').value, new_password: $('new-password').value});
  event.target.reset(); showStatus(result.message, 'ok');
}); });
action(checkPanelThenScan);
