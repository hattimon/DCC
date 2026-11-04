import{groupContainers,networksOf}from'../container_data.js';
import{sortContainers,nextSortState}from'../container_sort.js';
import{assistantPanel,wireAssistant}from'./ai.js';
import{html,t,literal,setLanguage}from'../i18n.js';
import{api,state,can,post,pollJob}from'../api.js';
import{copyText,esc,icon,heading,button,status,table,notice,openDialog,field,textarea,mutate,chart,notify,sound,confirmOperation}from'../ui.js';

const number=value=>Number.parseFloat(String(value??0).replace('%',''))||0;
function memory(value){const match=String(value||'').match(/([\d.]+)\s*([KMG])i?B/i);return match?Number(match[1])*({K:1/1024,M:1,G:1024}[match[2].toUpperCase()]||0):0;}

function panelLinks(c,all=false){
 return (c.PanelLinks||[]).filter(v=>all||v.likely_panel).map(v=>html`<span class="panel-endpoint"><a class="panel-link" href="${esc(v.url)}" target="_blank" rel="noopener noreferrer" title="${esc(v.url)}">${esc(v.label)} ↗</a><button type="button" class="quiet icon-button small copy-panel" data-copy-panel="${esc(v.url)}" title="${esc(t('Kopiuj adres panelu'))}: ${esc(v.url)}" aria-label="${esc(t('Kopiuj adres panelu'))} ${esc(v.label)}">${icon('copy')}</button></span>`).join('');
}
function wireCopies(root){root.querySelectorAll('[data-copy-panel],[data-copy-image]').forEach(b=>b.onclick=()=>copyText(b.dataset.copyPanel??b.dataset.copyImage));}

function metric(c){return state.stats.find(v=>v.ID===c.ID||v.ID&&c.ID?.startsWith(v.ID)||v.Container&&c.ID?.startsWith(v.Container))||{};}

function rows(values){return values.map(c=>html`<tr><td><input type="checkbox" aria-label="Zaznacz ${esc(c.Names)}" data-select="${esc(c.ID)}" ${state.selected.has(c.ID)?'checked':''}></td><td class="name"><button class="text-button" data-inspect="${esc(c.ID)}" title="${esc(c.Names)}">${esc(c.Names)}</button><span class="secondary mono">${esc(c.ID?.slice(0,12))}</span></td><td>${status(c.State)}<span class="secondary">${esc(c.Status)}</span></td><td class="image-cell mono"><button class="image-copy" data-copy-image="${esc(c.Image)}" title="${esc(c.Image)}&#10;${esc(t('Kliknij, aby skopiować pełną ścieżkę obrazu'))}">${esc(c.Image)}</button></td><td class="ports-cell">${panelLinks(c)}<span class="secondary mono">${esc(c.Ports||(c.HostNetworkPorts||[]).map(port=>t('Sieć hosta')+' · '+port+'/tcp').join(', '))}</span></td><td class="autostart-cell" title="${esc(c.RestartPolicy||t('Brak danych do wyświetlenia'))}">${c.RestartPolicy==null?'—':['always','unless-stopped'].includes(c.RestartPolicy)?'✓':'×'}</td><td class="mono">${esc(metric(c).CPUPerc||'—')}</td><td class="mono">${esc(metric(c).MemUsage?.split('/')[0]||'—')}</td><td><button class="quiet small" data-log="${esc(c.ID)}">Logi</button><button class="quiet icon-button small" data-actions="${esc(c.ID)}" aria-label="Operacje ${esc(c.Names)}">${icon('dots')}</button></td></tr>`);}
function sortHeader(key,label,enabled){
 if(!enabled)return t(label);
 const caption=t(label),aria=t('Sortuj według '+label);
 return `<button type="button" class="sort-button" data-sort="${key}" aria-label="${esc(aria)}" title="${esc(aria)}"><span>${esc(caption)}</span><span class="sort-arrows" aria-hidden="true"><span class="sort-arrow sort-asc">▲</span><span class="sort-arrow sort-desc">▼</span></span></button>`;
}
function containerTable(values,mode='none',sortState=null,sortable=false){
 const content=groupContainers(values,mode).flatMap(group=>{
  const ordered=sortState?sortContainers(group.values,state.stats,sortState.key,sortState.direction):group.values;
  const title=group.key==='__standalone__'?t('Samodzielne kontenery'):group.key==='__no_network__'?t('Bez sieci'):t(mode==='network'?'Sieć':'Projekt')+': '+group.key;
  const header=mode==='none'?[]:[html`<tr class="container-group"><th colspan="9" scope="rowgroup"><label class="group-select"><input type="checkbox" data-select-group="${esc(JSON.stringify(group.values.map(c=>c.ID)))}" aria-label="${esc(t('Zaznacz grupę'))} ${esc(title)}"><strong>${esc(title)}</strong><span class="fine">${group.values.length} ${t('kontenerów')} · ${group.values.filter(v=>v.State==='running').length} ${t('uruchomionych')}</span></label></th></tr>`];
  return [...header,...rows(ordered)];
 });
 return table(['<input type="checkbox" id="select-all" aria-label="Zaznacz wszystkie">','Nazwa','Stan','Obraz','Porty / panele','Autostart',sortHeader('cpu','CPU',sortable),sortHeader('ram','RAM',sortable),'Akcje'],content,'container-table');
}
const selected=()=>state.containers.filter(c=>state.selected.has(c.ID));
function permitted(action){return ['logs','inspect','links','copy-link','copy-details','copy-ports','copy-networks'].includes(action)||can(action==='remove'?'destructive':action==='exec'?'exec':['check','apply'].includes(action)?'update':'containers.write');}
function eligible(c,action){return action==='start'?!['running','paused'].includes(c.State):action==='stop'?['running','paused','restarting'].includes(c.State):action==='pause'?c.State==='running':action==='unpause'?c.State==='paused':action==='restart'?!['removing','dead'].includes(c.State):true;}
function bulkControls(){
 const basic=[['start','▶ Uruchom'],['stop','■ Zatrzymaj'],['restart','↻ Restart']];
 const compact=[['autostart-on','A✓','Włącz autostart'],['autostart-off','A×','Wyłącz autostart'],['pause','Ⅱ','Pauza'],['unpause','▷','Wznów'],['remove','×','Usuń kontenery']];
 return html`<div class="bulk-toolbar"><span class="fine" id="selection-count">${state.selected.size} zaznaczonych</span>${basic.map(([id,label])=>html`<button data-bulk="${id}">${literal(label)}</button>`).join('')}${compact.map(([id,glyph,label])=>html`<button class="icon-button ${id==='remove'?'danger':''}" data-bulk="${id}" aria-label="${esc(t(label))}" title="${esc(t(label))}">${glyph}</button>`).join('')}${[['logs','logs','Logi'],['configure','settings','Edytuj konfigurację startu'],['exec','terminal','Polecenie w kontenerze'],['inspect','search','Szczegóły konfiguracji']].map(([id,glyph,label])=>html`<button class="icon-button" data-selected-action="${id}" aria-label="${esc(t(label))}" title="${esc(t(label))}">${icon(glyph)}</button>`).join('')}<button id="bulk-actions">Więcej operacji</button></div>`;
}
async function enableManagement(ctx){
 if(state.user.role!=='admin')return;
 await openDialog('Włącz zarządzanie kontenerami',html`${notice('Profil zezwala na odczyt, ale zarządzanie kontenerami jest wyłączone. Możesz włączyć start, stop, restart, pauzę i edycję konfiguracji dla tego profilu.','warning')}`,{submit:'Włącz zarządzanie kontenerami',onSubmit:async()=>{
  const p=state.profiles.find(v=>v.id===state.profile);
  await api('profiles/'+p.id,{method:'PUT',data:{permissions:[...new Set([...p.permissions,'containers.write'])]}});
  setTimeout(()=>ctx.reload(),0);
 }});
}

function pageActions(){return button('Terminal','open-host-terminal')+'<a class="button" href="#store">'+t('Sklep')+'</a>'+button('+ Nowy kontener','new-container','primary');}
function wirePageActions(root,ctx){root.querySelector('#new-container').onclick=()=>manualCreate(ctx);root.querySelector('#open-host-terminal').onclick=()=>window.open('/terminal?profile='+encodeURIComponent(state.profile),'_blank','popup,width=1100,height=760,noopener,noreferrer');}
export async function overview(root,ctx){
 const data=await api('overview');if(!ctx.valid())return;state.containers=data.containers;ctx.connected(true);
 const monitor=await api('monitoring').catch(()=>({stats:[],history:[]}));if(!ctx.valid())return;state.stats=monitor.stats;
 const running=data.containers.filter(c=>c.State==='running').length,cpu=monitor.stats.reduce((sum,v)=>sum+number(v.CPUPerc),0),ram=monitor.stats.reduce((sum,v)=>sum+memory(v.MemUsage),0),info=data.info;
 const values=[['Kontenery',data.containers.length,'Wszystkie w tym profilu','cube'],['Uruchomione',running,html`${data.containers.length-running} zatrzymanych`,'play'],['CPU',monitor.stats.length?cpu.toFixed(1)+'%':'—',html`${info.NCPU??'—'} rdzeni hosta`,'cpu'],['Pamięć',monitor.stats.length?(ram/1024).toFixed(2)+' GB':'—','Użycie kontenerów','memory']];
 root.innerHTML=heading('Przegląd','Twoje środowisko Docker w jednym miejscu',pageActions())+html`<div class="summary-strip">${values.map(v=>html`<div class="summary"><span>${t(v[0])}</span>${icon(v[3])}<strong>${esc(v[1])}</strong><small>${esc(t(v[2]))}</small></div>`).join('')}</div><div class="dashboard-grid"><div><section class="panel"><div class="panel-header"><h2>${icon('cube')}Kontenery</h2><a class="button small quiet" href="#containers">Zobacz wszystkie →</a></div>${containerTable(data.containers.slice(0,8))}<div class="table-footer"><span>${data.containers.length} kontenerów w profilu</span><span>Zaznaczone: <b id="selection-count">${state.selected.size}</b></span></div></section><section class="panel"><div class="panel-header"><h2>${icon('audit')}Ostatnie operacje</h2><a class="button small quiet" href="#audit">Dziennik →</a></div><div id="recent-audit"></div></section></div><aside class="dashboard-side"><section class="panel"><div class="panel-header"><h2>Użycie zasobów</h2><span class="fine">Bieżąca historia</span></div><div class="chart-block"><div class="chart-title"><strong>CPU (%)</strong><span class="muted">${monitor.stats.length?cpu.toFixed(1)+'%':'Brak pomiaru'}</span></div>${chart(monitor.history.map(h=>h.stats.reduce((s,v)=>s+number(v.CPUPerc),0)),'Historia użycia CPU')}</div><div class="chart-block"><div class="chart-title"><strong>Pamięć (MiB)</strong><span class="muted">${Math.round(ram)} MiB</span></div>${chart(monitor.history.map(h=>h.stats.reduce((s,v)=>s+memory(v.MemUsage),0)),'Historia użycia pamięci')}</div></section><section class="panel"><div class="panel-header"><h2>Szczegóły hosta</h2></div><div class="host-data">${[['Nazwa',info.Name],['ID profilu',state.profile],['Adres hosta',info.address||'Nie podano w profilu'],['System',info.OperatingSystem],['Architektura',info.Architecture],['Sterownik',info.Driver],['Wersja Engine',info.ServerVersion],['Obrazy',info.Images],['Pamięć hosta',info.MemTotal?(info.MemTotal/1024**3).toFixed(1)+' GB':'—']].map(([k,v])=>html`<div><span>${t(k)}</span><strong>${esc(v??'—')}</strong></div>`).join('')}</div></section></aside></div>`;
 wire(root,ctx);wirePageActions(root,ctx);
 const audit=await api('audit').catch(()=>({events:[]}));if(!ctx.valid())return;
 root.querySelector('#recent-audit').innerHTML=table(['Czas','Operacja','Wynik'],audit.events.slice(0,5).map(v=>html`<tr><td>${new Date(v.at*1000).toLocaleTimeString()}</td><td class="wrap">${esc(v.action)}</td><td>${status(v.result<400?'success':'error')}</td></tr>`));
}


export async function containers(root,ctx){
 const [data,metrics]=await Promise.all([api('containers'),api('monitoring').catch(()=>({stats:[]}))]);if(!ctx.valid())return;
 state.containers=data.containers;state.stats=metrics.stats;ctx.connected(true);
 const groupStorage='dcc-container-grouping-'+state.user.id+'-'+state.profile;
 const sortStorage='dcc-container-sort-'+state.user.id+'-'+state.profile;
 let query=state.containerQuery||'',filter=state.containerStatus||'',group=localStorage.getItem(groupStorage)||'project';
 let sort=null;try{sort=JSON.parse(localStorage.getItem(sortStorage)||'null');}catch{}
 if(!sort||!['cpu','ram'].includes(sort.key)||!['asc','desc'].includes(sort.direction))sort=null;
 if(!['project','network','none'].includes(group))group='project';
 const permission=can('containers.write')?'':html`<div class="notice warning container-permission"><span>Profil zezwala na odczyt, ale zarządzanie kontenerami jest wyłączone.</span>${state.user.role==='admin'?literal('<button id="enable-container-management">Włącz zarządzanie kontenerami</button>'):literal('<span>Poproś administratora o uprawnienie containers.write.</span>')}</div>`;
 root.innerHTML=heading('Kontenery','Pełna kontrola cyklu życia — z zachowaniem danych.',pageActions())+permission+html`<div class="toolbar container-toolbar"><div class="container-filters"><input id="container-search" aria-label="Szukaj kontenera" placeholder="Szukaj nazwy lub obrazu…" value="${esc(query)}"><select id="status-filter" aria-label="Filtr stanu"><option value="">Wszystkie stany</option><option value="running">Uruchomione</option><option value="exited">Zatrzymane</option><option value="paused">Wstrzymane</option><option value="created">Utworzony</option></select><select id="container-grouping" aria-label="Grupuj"><option value="project">Projekty</option><option value="network">Sieci</option><option value="none">Lista płaska</option></select></div>${bulkControls()}</div><section class="panel" id="containers-table"></section>`;
 const redraw=()=>{const values=data.containers.filter(v=>(v.Names+' '+v.Image).toLowerCase().includes(query.toLowerCase())&&(!filter||v.State===filter));root.querySelector('#containers-table').innerHTML=containerTable(values,group,sort,true);root.querySelectorAll('[data-sort]').forEach(control=>{const key=control.dataset.sort,active=sort?.key===key,header=control.closest('th');header?.setAttribute('aria-sort',active?(sort.direction==='asc'?'ascending':'descending'):'none');control.setAttribute('aria-pressed',String(active));if(active)control.dataset.direction=sort.direction;control.onclick=()=>{sort=nextSortState(sort,key);if(sort)localStorage.setItem(sortStorage,JSON.stringify(sort));else localStorage.removeItem(sortStorage);redraw();};});wire(root,ctx,values);};
 root.querySelector('#status-filter').value=filter;root.querySelector('#container-grouping').value=group;
 root.querySelector('#container-search').oninput=e=>{state.containerQuery=query=e.target.value;redraw();};
 root.querySelector('#status-filter').onchange=e=>{state.containerStatus=filter=e.target.value;redraw();};
 root.querySelector('#container-grouping').onchange=e=>{group=e.target.value;localStorage.setItem(groupStorage,group);redraw();};
 root.querySelector('#bulk-actions').onclick=()=>bulkMenu(ctx);
 root.querySelectorAll('[data-bulk]').forEach(b=>b.onclick=()=>bulkAction(b.dataset.bulk,ctx));
 root.querySelectorAll('[data-selected-action]').forEach(b=>b.onclick=()=>selectionAction(b.dataset.selectedAction,ctx));
 wirePageActions(root,ctx);
 const enable=root.querySelector('#enable-container-management');if(enable)enable.onclick=()=>enableManagement(ctx);
 redraw();
}
async function bulkMenu(ctx){
 if(!selected().length)return notify('Zaznacz kontenery');
 const groups={'Cykl życia':[['start','Uruchom'],['stop','Zatrzymaj'],['restart','Restart'],['pause','Pauza'],['unpause','Wznów'],['remove','Usuń kontenery']],'Konfiguracja':[['autostart-on','Włącz autostart'],['autostart-off','Wyłącz autostart'],['configure','Edytuj konfigurację startu']],'Diagnostyka':[['logs','Logi'],['exec','Polecenie w kontenerze'],['inspect','Szczegóły konfiguracji']],'Odnośniki i dane':[['copy-details','Kopiuj szczegóły'],['copy-link','Kopiuj adres panelu'],['copy-ports','Kopiuj porty'],['copy-networks','Kopiuj sieci']]};
 await openDialog('Operacja na zaznaczonych kontenerach',html`<p>${selected().length} kontenerów. Dane w wolumenach pozostaną zachowane.</p><label>Operacja<select name="action">${Object.entries(groups).map(([label,items])=>html`<optgroup label="${esc(t(label))}">${items.map(([id,label])=>html`<option value="${id}" ${permitted(id)&&(!['configure','exec','inspect'].includes(id)||selected().length===1)?'':'disabled'}>${esc(t(label))}</option>`).join('')}</optgroup>`).join('')}</select></label>`,{submit:'Dalej',onReady:form=>{const first=form.querySelector('option:not(:disabled)');if(first)form.querySelector('select').value=first.value;},onSubmit:f=>{const action=f.get('action');setTimeout(()=>['logs','configure','exec','inspect'].includes(action)||action.startsWith('copy-')?selectionAction(action,ctx):bulkAction(action,ctx),0);}});
}
async function selectionAction(action,ctx){
 const values=selected();if(!values.length)return notify('Zaznacz kontenery');
 try{
  if(action==='copy-details')return copyText(JSON.stringify(values,null,2));
  if(action==='copy-link')return copyText([...new Set(values.flatMap(c=>(c.PanelLinks||[]).filter(v=>v.likely_panel).map(v=>v.url)))].join('\n'));
  if(action==='copy-ports')return copyText(values.map(c=>c.Names+': '+(c.Ports||'—')).join('\n'));
  if(action==='copy-networks')return copyText(values.map(c=>c.Names+': '+networksOf(c).join(', ')).join('\n'));
  if(action==='logs'){
   if(values.length===1){location.hash='logs/'+encodeURIComponent(values[0].ID);return;}
   return openDialog('Logi',html`<div class="stack">${values.map(c=>html`<a class="button" data-close href="#logs/${encodeURIComponent(c.ID)}">${esc(c.Names)}</a>`).join('')}</div>`);
  }
  if(values.length!==1)return notify('Zaznacz jeden kontener');
  if(action==='configure')return configure(values[0].ID,ctx);
  if(action==='inspect')return inspect(values[0].ID,ctx);
  if(action==='exec')return exec(values[0].ID);
 }catch(error){notify(error.message,'error');}
}


function wire(root,ctx,visible=state.containers){
 wireCopies(root);
 root.querySelectorAll('[data-inspect]').forEach(b=>b.onclick=()=>inspect(b.dataset.inspect,ctx));
 root.querySelectorAll('[data-log]').forEach(b=>b.onclick=()=>location.hash='logs/'+encodeURIComponent(b.dataset.log));
 root.querySelectorAll('[data-actions]').forEach(b=>b.onclick=()=>actions(b.dataset.actions,ctx));
 const count=()=>{
  const values=selected(),el=root.querySelector('#selection-count');if(el)el.textContent=el.tagName==='B'?values.length:values.length+' '+t('zaznaczonych');
  root.querySelectorAll('[data-bulk]').forEach(b=>{const action=b.dataset.bulk;b.disabled=!permitted(action)||!values.some(c=>eligible(c,action));b.title=!permitted(action)?t('Brak uprawnienia profilu')+': '+(action==='remove'?'destructive':'containers.write'):!values.length?t('Zaznacz kontenery'):t({'start':'Uruchom','stop':'Zatrzymaj','restart':'Restart','pause':'Pauza','unpause':'Wznów','remove':'Usuń kontenery','autostart-on':'Włącz autostart','autostart-off':'Wyłącz autostart'}[action]);});
  root.querySelectorAll('[data-selected-action]').forEach(b=>{b.disabled=!values.length||!permitted(b.dataset.selectedAction)||(b.dataset.selectedAction!=='logs'&&values.length!==1);});
  const more=root.querySelector('#bulk-actions');if(more)more.disabled=!values.length;
  root.querySelectorAll('[data-select-group]').forEach(box=>{const ids=JSON.parse(box.dataset.selectGroup),count=ids.filter(id=>state.selected.has(id)).length;box.checked=count===ids.length;box.indeterminate=count>0&&count<ids.length;});
  const all=root.querySelector('#select-all');if(all){all.checked=visible.length>0&&visible.every(c=>state.selected.has(c.ID));all.indeterminate=visible.some(c=>state.selected.has(c.ID))&&!all.checked;}

 };
 root.querySelectorAll('[data-select-group]').forEach(box=>box.onchange=()=>{JSON.parse(box.dataset.selectGroup).forEach(id=>box.checked?state.selected.add(id):state.selected.delete(id));root.querySelectorAll('[data-select]').forEach(b=>b.checked=state.selected.has(b.dataset.select));count();});
 count();
 root.querySelectorAll('[data-select]').forEach(box=>box.onchange=()=>{box.checked?state.selected.add(box.dataset.select):state.selected.delete(box.dataset.select);count();});
 const all=root.querySelector('#select-all');if(all){all.checked=visible.length>0&&visible.every(c=>state.selected.has(c.ID));all.indeterminate=visible.some(c=>state.selected.has(c.ID))&&!all.checked;all.onchange=()=>{visible.forEach(v=>all.checked?state.selected.add(v.ID):state.selected.delete(v.ID));root.querySelectorAll('[data-select]').forEach(b=>b.checked=all.checked);count();};}
}

async function inspect(target,ctx){try{const data=await api('containers/'+encodeURIComponent(target));await openDialog('Szczegóły i konfiguracja',html`<p class="fine">Sekrety środowiska są maskowane. Porty, montowania, healthcheck i konfiguracja pochodzą z Docker inspect.</p><pre class="inspect">${esc(JSON.stringify(data,null,2))}</pre>`);}catch(e){notify(e.message,'error');}}

async function bulkAction(action,ctx){
 const values=selected().filter(c=>eligible(c,action));if(!values.length)return notify('Zaznacz kontenery');
 try{
  const targets=values.map(c=>c.ID),bytes=new TextEncoder().encode(JSON.stringify(targets)),digest=await crypto.subtle.digest('SHA-256',bytes),target=[...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');
  const result=await mutate('bulk',{targets,action},'bulk.'+action,target,html`${action}: ${targets.length} kontenerów`,{danger:['stop','restart','remove','autostart-on','autostart-off'].includes(action)});
  if(result){
   state.selected.clear();ctx.refresh();
   const failed=result.filter(v=>!v.ok);if(failed.length)await openDialog('Wynik operacji zbiorczej',html`${notice('Niektóre operacje nie powiodły się.','warning')}${table(['Kontener','Wynik'],result.map(v=>html`<tr><td class="wrap">${esc(values.find(c=>c.ID===v.container)?.Names||v.container)}</td><td class="wrap">${v.ok?t('Sukces'):esc(v.error||t('Błąd'))}</td></tr>`))}`);
  }
 }catch(e){notify(e.message,'error');}
}

async function actions(target,ctx){
 const c=state.containers.find(v=>v.ID===target),running=c?.State==='running';
 const groups={'Cykl życia':[['start','Uruchom',!running&&c?.State!=='paused'],['stop','Zatrzymaj',running||c?.State==='paused'],['restart','Restart',true],['pause','Pauza',running],['unpause','Wznów',c?.State==='paused']],'Konfiguracja':[['configure','Edytuj konfigurację startu',true],['autostart-on','Włącz autostart',true],['autostart-off','Wyłącz autostart',true]],'Diagnostyka':[['logs','Logi',true],['exec','Polecenie w kontenerze',running],['inspect','Szczegóły konfiguracji',true]],'Odnośniki i dane':[['links','Adresy paneli / porty',true],['copy-link','Kopiuj adres panelu',Boolean(c?.PanelLinks?.length)],['copy-details','Kopiuj szczegóły',true],['copy-ports','Kopiuj porty',Boolean(c?.Ports)],['copy-networks','Kopiuj sieci',true]],'Aktualizacje i usuwanie':[['check','Sprawdź aktualizację obrazu',true],['apply','Aktualizuj bezpiecznie obraz',true],['remove','Usuń kontener — zachowaj wolumeny',true]]};
 await openDialog(c?.Names||'Operacje kontenera',html`<div class="stack"><label>Operacja<select name="action">${Object.entries(groups).map(([label,items])=>html`<optgroup label="${esc(t(label))}">${items.map(([id,text,enabled])=>html`<option value="${id}" ${enabled&&permitted(id)?'':'disabled'}>${esc(t(text))}</option>`).join('')}</optgroup>`).join('')}</select></label><div class="quick-actions">${[['start','▶ Uruchom'],['stop','■ Zatrzymaj'],['restart','↻ Restart'],['pause','Ⅱ Pauza'],['configure','Edytuj']].map(([id,text])=>html`<button type="button" data-quick="${id}">${literal(text)}</button>`).join('')}</div><div class="panel-links">${panelLinks(c||{},true)}</div>${notice('Operacje wymagają odpowiednich uprawnień profilu. Wolumeny nie są automatycznie usuwane.')}</div>`,{submit:'Dalej',rawTitle:true,onSubmit:f=>{const action=f.get('action');setTimeout(async()=>{try{
 if(action==='logs'){location.hash='logs/'+encodeURIComponent(target);return;}
 if(action==='inspect')return inspect(target,ctx);
 if(action==='exec')return exec(target);
 if(action==='configure')return configure(target,ctx);
 if(action==='links')return openDialog('Adresy paneli / porty',html`<div class="stack">${panelLinks(c,true)}<pre class="inspect">${esc(c?.Ports||'—')}</pre>${notice('Adresy HTTP/HTTPS są wyznaczane z opublikowanych portów TCP. Usługi inne niż WWW mogą nie obsługiwać przeglądarki.')}</div>`,{onReady:wireCopies});
 if(action==='copy-link')return copyText((c.PanelLinks.find(v=>v.likely_panel)||c.PanelLinks[0]).url);
 if(action==='copy-ports')return copyText(c.Ports||'');
 if(action==='copy-details'||action==='copy-networks'){const value=await api('containers/'+target);return copyText(action==='copy-details'?JSON.stringify(value,null,2):Object.keys(value.NetworkSettings?.Networks||{}).join('\n'));}
 const updating=['check','apply'].includes(action),result=await mutate(updating?html`updates/${target}/${action}`:html`containers/${target}/${action}`,{},updating?'update.'+action:'container.'+action,target,html`${c?.Names}: ${action}`,{danger:['stop','restart','remove','apply'].includes(action)});
 if(result){sound(action==='start'?'start':action==='stop'?'stop':'success');if(updating)await openDialog('Wynik aktualizacji',html`<pre class="inspect">${esc(JSON.stringify(result,null,2))}</pre>`);ctx.refresh();}
 }catch(e){notify(e.message,'error');}},0);},onReady:form=>{wireCopies(form);form.querySelectorAll('[data-quick]').forEach(b=>{const option=form.querySelector(html`option[value="${b.dataset.quick}"]`);b.disabled=option?.disabled||false;b.onclick=()=>{form.querySelector('[name=action]').value=b.dataset.quick;form.requestSubmit();};});}});
}
async function exec(target){await openDialog('Polecenie wewnątrz kontenera',html`${notice('Polecenie działa wewnątrz wybranego kontenera. Docker socket lub uprzywilejowany kontener może zapewniać dostęp do hosta.','warning')}${field('Komenda','command','',{placeholder:'np. uname -a',required:true})}`,{submit:'Dalej',onSubmit:f=>{const command=f.get('command');setTimeout(async()=>{try{const result=await mutate('exec/'+target,{command},'container.exec',target,'Uruchom polecenie: '+command,{danger:true});if(result)openDialog('Wynik polecenia',html`<pre class="inspect">${esc(result.output)}</pre>`);}catch(e){notify(e.message,'error');}},0);}});}

export async function manualCreate(ctx){const {installForm}=await import('./store.js');return installForm(null,ctx);}

export async function logs(root,ctx){
 const values=(await api('containers')).containers;if(!ctx.valid())return;const target=state.target||values[0]?.ID;
 if(!target){root.innerHTML=heading('Logi i diagnostyka','Bieżący strumień zdarzeń z wybranego kontenera.')+notice('Brak kontenerów w tym profilu.');return;}
 root.innerHTML=heading('Logi i diagnostyka','Automatyczne odświeżanie, wyszukiwanie i pobieranie logów.')+html`<div class="toolbar"><select id="logs-container" aria-label="Kontener">${values.map(v=>html`<option value="${esc(v.ID)}" ${v.ID===target?'selected':''}>${esc(v.Names)}</option>`).join('')}</select><input id="logs-search" aria-label="Szukaj w logach" placeholder="Szukaj w logach…" value="${esc(state.logQuery||'')}"><select id="logs-tail" aria-label="Liczba linii">${[100,200,500,2000].map(v=>html`<option ${v===(state.logTail||200)?'selected':''}>${v}</option>`).join('')}</select><label class="check"><input type="checkbox" id="logs-live" ${state.logLive!==false?'checked':''}>Na żywo</label><button id="logs-copy">Kopiuj logi</button><button id="logs-download">Pobierz .log</button>${state.features?.access_details?literal('<button id="logs-access">Wykryj dane dostępowe</button>'):''}</div><section class="panel"><div class="panel-header"><h2>Wyjście kontenera</h2><span class="fine" id="log-count"></span></div><pre class="log-view" id="logs-output">Ładowanie logów…</pre></section>`;
 const access=root.querySelector('#logs-access');if(access)access.onclick=async()=>{try{const data=await post('logs/'+encodeURIComponent(target)+'/access',{});await openDialog('Dane dostępowe wykryte w logach',data.details.length?html`<div class="stack">${data.details.map((v,i)=>html`<label>${esc(v.label)}<span class="access-value"><input readonly name="access-${i}" value="${esc(v.value)}"><button type="button" data-copy-access="${i}">Kopiuj</button></span></label>`).join('')}</div>`:notice('Nie wykryto gotowych danych logowania. Utwórz konto w aplikacji przy pierwszym uruchomieniu.'),{onReady:form=>form.querySelectorAll('[data-copy-access]').forEach(b=>b.onclick=()=>copyText(form.elements['access-'+b.dataset.copyAccess].value))});}catch(e){notify(e.message,'error');}};root.querySelector('#logs-copy').onclick=()=>copyText(root.querySelector('#logs-output').innerText);
 let timer;const load=async()=>{try{const data=await api(html`logs/${encodeURIComponent(target)}?tail=${state.logTail||200}&q=${encodeURIComponent(state.logQuery||'')}`);if(!ctx.valid())return;root.querySelector('#logs-output').innerHTML=data.logs.split('\n').map(line=>html`<span class="${/error|fatal|exception|traceback/i.test(line)?'log-error':/warn/i.test(line)?'log-warning':''}">${esc(line)}</span>`).join('\n');root.querySelector('#log-count').textContent=data.lines+t(' linii');}catch(e){notify(e.message,'error');}};
 root.querySelector('#logs-container').onchange=e=>location.hash='logs/'+encodeURIComponent(e.target.value);root.querySelector('#logs-search').oninput=e=>{state.logQuery=e.target.value;clearTimeout(timer);timer=setTimeout(load,300);};root.querySelector('#logs-tail').onchange=e=>{state.logTail=Number(e.target.value);load();};root.querySelector('#logs-live').onchange=e=>state.logLive=e.target.checked;root.querySelector('#logs-download').onclick=()=>window.open(html`/api/logs/${encodeURIComponent(target)}?profile=${encodeURIComponent(state.profile)}&tail=${state.logTail||200}&download=1`,'_blank','noopener');await load();
}

export async function monitoring(root,ctx){const data=await api('monitoring');if(!ctx.valid())return;ctx.connected(true);root.innerHTML=heading('Monitoring','CPU, pamięć, sieć i I/O. Historia obejmuje zebrane pomiary tego profilu.')+html`<div class="two-columns"><section class="panel"><div class="panel-header"><h2>CPU kontenerów (%)</h2></div><div class="chart-block">${chart(data.history.map(h=>h.stats.reduce((s,v)=>s+number(v.CPUPerc),0)),'CPU')}</div></section><section class="panel"><div class="panel-header"><h2>Pamięć (MiB)</h2></div><div class="chart-block">${chart(data.history.map(h=>h.stats.reduce((s,v)=>s+memory(v.MemUsage),0)),'Pamięć')}</div></section></div><section class="panel"><div class="panel-header"><h2>Aktualne zasoby</h2><span class="fine">${data.history.length} pomiarów</span></div>${table(['Kontener','CPU','RAM','RAM %','Sieć','Dysk I/O','Procesy'],data.stats.map(v=>html`<tr>${['Name','CPUPerc','MemUsage','MemPerc','NetIO','BlockIO','PIDs'].map(k=>html`<td>${esc(v[k]||'—')}</td>`).join('')}</tr>`))}</section>`;}

async function configure(target,ctx){
 try{
 const current=await api('containers/'+target),config=current.Config||{},host=current.HostConfig||{};
 const originalCommand=Array.isArray(config.Cmd)?config.Cmd.map(value=>JSON.stringify(value)).join(' '):config.Cmd||'';
 const originalPorts=Object.entries(host.PortBindings||{}).flatMap(([port,entries])=>(entries||[]).map(binding=>{let ip=binding.HostIp||'0.0.0.0';if(ip.includes(':'))ip='['+ip+']';return ip+':'+binding.HostPort+':'+port;})).join('\n');
 const original={command:originalCommand,user:config.User||'',working_dir:config.WorkingDir||'',ports:originalPorts,restart:host.RestartPolicy?.Name||'no'};
 await openDialog('Konfiguracja startu kontenera',html`<div class="stack">${notice('Kontener zostanie odtworzony z zachowaniem konfiguracji i montowań przez istniejący bezpieczny updater DCC. Usługi Compose i sam Updater wymagają ich własnej ścieżki aktualizacji.','warning')}<p class="mono">${esc(config.Image||'')}</p>${field('Nowa komenda (opcjonalnie)','command',original.command)}${field('Użytkownik kontenera (opcjonalnie)','user',original.user)}${field('Katalog roboczy (opcjonalnie)','working_dir',original.working_dir)}${textarea('Porty — [IP:]HOST:CONTAINER/tcp lub /udp, po jednym na linię','ports',original.ports)}<label>${t('Polityka restartu')}<select name="restart">${['no','always','unless-stopped','on-failure'].map(value=>html`<option value="${value}" ${value===original.restart?'selected':''}>${value}</option>`).join('')}</select></label>${textarea('Zmienne do zmiany — pozostałe zostaną zachowane','environment','','KEY=value')}${assistantPanel()}${notice('Montowania i pozostałe ustawienia są zachowywane. Zmiana obrazu jest osobną operacją aktualizacji.')}</div>`,{submit:'Dalej',onReady:form=>{
 const environment=()=>{const result={};for(const line of form.elements.environment.value.split('\n').filter(Boolean)){const at=line.indexOf('=');if(at<1)throw Error(t('Wymagana postać KEY=value'));result[line.slice(0,at)]=line.slice(at+1);}return result;};
 wireAssistant(form,()=>{const line=form.elements.ports.value.split('\n').find(Boolean)||'',parts=line.split(':');return{name:current.Name?.replace(/^\//,'')||target,image:config.Image,command:form.elements.command.value,extra:'--restart '+form.elements.restart.value,environment:environment(),host_port:parts.at(-2)||'',container_port:parts.at(-1)||''};},values=>{
 if(values.command!==undefined)form.elements.command.value=values.command;
 if(values.environment)form.elements.environment.value=Object.entries(values.environment).map(([k,v])=>k+'='+v).join('\n');
 if(values.host_port&&values.container_port){const lines=form.elements.ports.value.split('\n').filter(Boolean);const old=lines[0]?.split(':')||[];lines[0]=(old.length>2?old.slice(0,-2).join(':')+':':'')+values.host_port+':'+values.container_port;form.elements.ports.value=lines.join('\n');}
 const policy=String(values.extra||'').match(/--restart(?:=|\s+)([a-z-]+)/)?.[1];if(policy)form.elements.restart.value=policy;
 },{target});
 },onSubmit:f=>{const changes={};for(const key of ['command','user','working_dir','ports','restart'])if(String(f.get(key))!==original[key])changes[key]=String(f.get(key));if(f.get('environment')){changes.environment={};for(const line of String(f.get('environment')).split('\n').filter(Boolean)){const i=line.indexOf('=');if(i<1)throw Error(t('Wymagana postać KEY=value'));changes.environment[line.slice(0,i)]=line.slice(i+1);}}
 if(!Object.keys(changes).length)throw Error(t('Brak zmian konfiguracji'));
 setTimeout(async()=>{try{if(await mutate('configuration/'+target,{changes},'container.configure',target,'Odtwórz kontener z nową konfiguracją. Montowania i pozostałe ustawienia zostaną zachowane.',{danger:true}))ctx.refresh();}catch(e){notify(e.message,'error');}},0);}});
 }catch(e){notify(e.message,'error');}
}
