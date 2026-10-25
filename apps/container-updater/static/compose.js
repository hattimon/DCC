'use strict';

const composeOpen = new Set();
function composeMessage(code) {
  const key = 'compose_code_' + code;
  const stage = 'compose_state_' + String(code).toLowerCase();
  return ui[key] || ui[stage] || code;
}
function composeDate(stamp) {
  return stamp ? new Intl.DateTimeFormat(document.documentElement.lang, {dateStyle:'medium',timeStyle:'medium'}).format(new Date(stamp*1000)) : '—';
}
function composeButton(label, work, enabled = true) {
  const button = element('button', '', t(label)); button.type = 'button';
  button.dataset.composeAction = label; button.dataset.unavailable = String(!enabled); button.disabled = busy || !enabled;
  button.addEventListener('click', () => action(async () => {
    setBusy(true);
    try { await work(); }
    catch (error) { $('compose-progress').textContent = composeMessage(error.message); }
    await loadCompose();
  }));
  return button;
}
function composeSelect(label, values, selected) {
  const field = element('label', 'field', t(label)); const input = element('select');
  for (const value of values) { const option = element('option', '', t('compose_'+value)); option.value = value; input.append(option); }
  input.value = selected; field.append(input); return {field,input};
}
function composeText(label, value, type = 'text') {
  const field = element('label', 'field', t(label)); const input = element('input'); input.type=type; input.value=value || ''; field.append(input); return {field,input};
}
function composeReview(title, content) {
  $('compose-review-title').textContent=title;
  $('compose-review-body').replaceChildren(content);
  if (!$('compose-review').open) $('compose-review').showModal();
}
function composeOperationView(operation) {
  const box = element('div', 'compose-operation');
  box.append(element('p', '', `${operation.id} · ${composeMessage(operation.state)}`));
  for (const code of operation.blockers || []) box.append(element('p', 'status error', composeMessage(code)));
  const diff = operation.diff;
  if (diff) {
    if (diff.two_way) box.append(element('p', 'status error', composeMessage('base_missing')));
    for (const change of diff.changes || []) box.append(element('p', '', `${t('compose_'+change.action)}: ${change.path || 'Compose'}`));
    for (const path of diff.conflicts || []) box.append(element('p', 'status error', `${t('compose_conflict')}: ${path}`));
    for (const path of diff.review_required || []) box.append(element('p', '', `${t('compose_review_required')}: ${path}`));
    if (!(diff.changes?.length || diff.conflicts?.length)) box.append(element('p', '', t('compose_preserved')));
  }
  if (operation.backup) box.append(element('p', '', `${t('compose_backup')}: ${operation.backup.adapter} · ${t('compose_backup_scope')}`));
  const steps=element('ol');
  for (const event of operation.events || []) steps.append(element('li', '', `${composeDate(event.at)} · ${composeMessage(event.state)} · ${composeMessage(event.code)}`));
  box.append(steps); return box;
}
async function composeRun(path) {
  const job = await runJob(path);
  const result = job.results;
  $('compose-progress').textContent = composeMessage(result.state || 'completed');
  if (result.id) composeReview(t('compose_diff'),composeOperationView(result));
  return result;
}
function composeSettings(project) {
  const details=element('details', 'compose-settings'); details.append(element('summary','',t('compose_settings')));
  const form=element('form','compose-form'); const settings=project.settings;
  const mode=composeSelect('compose_mode',['monitor','manual','conditional','migration'],settings.mode);
  const policy=composeSelect('compose_database',['unknown','none','compatible','approved_migration','admin'],settings.database_policy);
  const automation=composeSelect('compose_automation',['off','check','analyze','conditional'],settings.automation);
  form.append(mode.field,policy.field,automation.field,element('p','hint',t('compose_profile_hint')));
  const serviceInputs=new Map();
  for (const service of project.services) {
    const control=composeSelect('compose_service_mode',['monitor','manual','conditional','migration'],settings.services[service.name] || settings.mode);
    control.field.prepend(element('strong','',service.name)); form.append(control.field); serviceInputs.set(service.name,control.input);
  }
  const schedule=settings.schedule || {enabled:false,kind:'daily',time:'03:00',timezone:'Europe/Warsaw',date:'',weekday:0,month_day:1,every:1,unit:'days'};
  const enabled=element('label',''); const check=element('input'); check.type='checkbox'; check.checked=!!schedule.enabled; enabled.append(check,document.createTextNode(t('compose_schedule_enabled'))); form.append(enabled);
  const kind=composeSelect('compose_recurrence',['once','daily','weekly','monthly','interval'],schedule.kind);
  const time=composeText('compose_time',schedule.time,'time'); const timezone=composeText('compose_timezone',schedule.timezone);
  const date=composeText('compose_date',schedule.date,'date'); const weekday=composeText('compose_weekday',schedule.weekday ?? 0,'number'); weekday.input.min='0'; weekday.input.max='6';
  const month=composeText('compose_month_day',schedule.month_day,'number'); month.input.min='1'; month.input.max='31';
  const every=composeText('compose_every',schedule.every,'number'); every.input.min='1'; every.input.max='8760';
  const unit=composeSelect('compose_unit',['hours','days'],schedule.unit);
  const scheduleBox=element('div','compose-grid'); scheduleBox.append(kind.field,time.field,timezone.field,date.field,weekday.field,month.field,every.field,unit.field); form.append(scheduleBox);
  const refreshFields=()=>{date.field.hidden=!['once','interval'].includes(kind.input.value);weekday.field.hidden=kind.input.value!=='weekly';month.field.hidden=kind.input.value!=='monthly';every.field.hidden=unit.field.hidden=kind.input.value!=='interval';};
  kind.input.addEventListener('change',refreshFields); refreshFields();
  const save=element('button','primary',t('save_settings')); save.type='submit'; save.dataset.composeAction='settings'; form.append(save);
  form.addEventListener('submit', event=>{event.preventDefault(); action(async()=>{
    if ((mode.input.value==='conditional' || automation.input.value==='conditional') && !confirm(t('compose_confirm_optin'))) return;
    setBusy(true);
    const payload={mode:mode.input.value,database_policy:policy.input.value,automation:automation.input.value,
      services:Object.fromEntries([...serviceInputs].map(([name,input])=>[name,input.value])),
      schedule:{enabled:check.checked,kind:kind.input.value,time:time.input.value,timezone:timezone.input.value,date:date.input.value,weekday:Number(weekday.input.value),month_day:Number(month.input.value),every:Number(every.input.value),unit:unit.input.value}};
    try {await api(`/api/compose/projects/${encodeURIComponent(project.name)}/settings`,payload);$('compose-progress').textContent=t('compose_saved');await loadCompose();}
    catch(error){$('compose-progress').textContent=composeMessage(error.message);}
  });});
  details.append(form); return details;
}
async function loadCompose() {
  const {projects}=await api('/api/compose/projects'); const box=$('compose-projects'); box.replaceChildren();
  if (!projects.length) box.append(element('p','empty',t('compose_initial')));
  for (const project of projects) {
    const card=element('details','compose-project'); card.open=composeOpen.has(project.name);
    card.addEventListener('toggle',()=>card.open?composeOpen.add(project.name):composeOpen.delete(project.name));
    const summary=element('summary'); summary.append(element('strong','',project.name),element('span','badge',composeMessage(project.status))); card.append(summary);
    const meta=element('dl','compose-meta');
    for(const [key,value] of [['compose_mode',t('compose_'+project.settings.mode)],['compose_location',project.config_files.join(', ') || project.location],['compose_source',project.source],['compose_networks',project.networks.join(', ')],['compose_volumes',project.volumes.join(', ')],['compose_database',`${t('compose_'+project.settings.database_policy)} · ${project.databases.join(', ') || '—'}`],['compose_analyzed',composeDate(project.analyzed_at)],['compose_updated',composeDate(project.updated_at)],['compose_next_run',composeDate(project.schedule_status?.next_run)],['compose_last_run',project.schedule_status?.last_run ? `${composeDate(project.schedule_status.last_run.at)} · ${composeMessage(project.schedule_status.last_run.code || project.schedule_status.last_run.status)}` : '—']]) meta.append(element('dt','',t(key)),element('dd','',value || '—'));
    card.append(meta);
    const services=element('div','compose-services');
    for(const service of project.services){
      const entry=element('div','compose-service');
      entry.append(element('strong','',`${service.name} · ${t('compose_replicas')}: ${service.replicas}`),element('code','',service.images.join(', ')),element('small','',service.image_ids.join(', ')),element('p','',`${t('target_image')}:`),element('code','',project.last_operation?.versions?.[service.name]?.target || service.target_image || '—'),element('p','',`${t('compose_dependencies')}: ${service.dependencies.join(', ') || '—'}`),element('p','',service.update_available===null?t('compose_review_required'):composeMessage(service.update_available?'update_available':'up_to_date')));
      for(const code of service.check_diagnostics || [])entry.append(element('p','status error',composeMessage(code)));
      services.append(entry);
    }
    card.append(services);
    const actions=element('div','actions compose-actions'); const base=`/api/compose/projects/${encodeURIComponent(project.name)}`; const operation=project.last_operation;
    actions.append(composeButton('compose_analyze',()=>composeRun(base+'/analyze')),composeButton('compose_dry_run',()=>composeRun(base+'/dry-run')),composeButton('compose_backup',()=>composeRun(base+'/backup')));
    actions.append(composeButton('compose_diff',async()=>composeReview(t('compose_diff'),composeOperationView(await api('/api/compose/operations/'+operation.id))),!!operation));
    actions.append(composeButton('compose_approve',async()=>{if(confirm(t('compose_confirm_plan')))await api(`/api/compose/operations/${operation.id}/approve`,{});},operation?.state==='READY'&&!operation.approved&&!operation.dry_run));
    actions.append(composeButton('compose_update',async()=>{if(confirm(t('compose_confirm_deploy')))await composeRun(`/api/compose/operations/${operation.id}/execute`);},operation?.state==='READY'&&operation.approved&&!operation.dry_run));
    actions.append(composeButton('compose_cancel',()=>api(`/api/compose/operations/${operation.id}/cancel`,{}),!!operation&&['READY','PLAN_READY','CONFIG_VALIDATED','BACKUP_VERIFIED','MIGRATION_PRECHECK'].includes(operation.state)));
    actions.append(composeButton('compose_history',async()=>{const data=await api(base+'/history');const content=element('div');for(const entry of data.operations)content.append(composeOperationView(entry));composeReview(t('compose_history'),content);}));
    card.append(actions);
    for(const code of operation?.blockers || project.blockers || [])card.append(element('p','status error',composeMessage(code)));
    card.append(composeSettings(project));box.append(card);
  }
  setBusy(busy);
}
$('compose-discover').addEventListener('click',()=>action(async()=>{
  try {await runJob('/api/compose/discover');await loadCompose();$('compose-progress').textContent=t('compose_discovered');}
  catch(error){$('compose-progress').textContent=composeMessage(error.message);}
}));
