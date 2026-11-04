import{html,t,literal,setLanguage}from'./i18n.js';
import{api,state,post}from'./api.js';
import{esc,icon,heading,notice,notify,applySettings,sound}from'./ui.js';
const navigation=[['overview','Przegląd','home','Overview'],['containers','Kontenery','cube','Containers'],['logs','Logi','logs','Logs'],['monitoring','Monitoring','cpu','Monitoring'],['images','Obrazy','images','Images'],['volumes','Wolumeny','volume','Volumes'],['networks','Sieci','network','Networks'],['compose','Compose','compose','Compose'],['store','Sklep aplikacji','store','App Store'],['profiles','Profile','profiles','Profiles'],['audit','Dziennik operacji','audit','Audit log'],['ai','Asystent AI','spark','AI assistant'],['mcp','AI / MCP','spark','AI / MCP'],['settings','Ustawienia','settings','Settings']];
const loaders={overview:['containers','overview'],containers:['containers','containers'],logs:['containers','logs'],monitoring:['containers','monitoring'],images:['resources','resources'],volumes:['resources','resources'],networks:['resources','resources'],compose:['resources','compose'],audit:['resources','audit'],store:['store','store'],profiles:['profiles','profiles'],ai:['ai','ai'],mcp:['mcp','mcp'],settings:['settings','settings']};
let renderVersion=0,rendering=false,interval;
const root=document.querySelector('#content');

let infrastructureVersion=0;
function updateContainerIdentity(){
 const inlineAddress=document.querySelector('[data-container-host-address]');
 if(inlineAddress){inlineAddress.textContent=state.hostAddress?'| '+t('Host')+': '+state.hostAddress:'';inlineAddress.hidden=!state.hostAddress;inlineAddress.title=state.hostAddress;}
 const profileId=document.querySelector('[data-container-profile-id]');
 if(profileId){profileId.textContent='| '+t('ID profilu')+': '+state.profile;profileId.title=state.profile;}
}
async function loadInfrastructure(){
 const version=++infrastructureVersion,profile=state.profile,host=document.querySelector('#host-system'),engine=document.querySelector('#host-engine');
 host.textContent=t('Odczytywanie infrastruktury…');engine.textContent='';
 try{
  const info=await api('infrastructure');if(version!==infrastructureVersion||profile!==state.profile)return;
  state.hostAddress=info.address||'';
  host.textContent=[info.name,state.hostAddress?(t('Host')+': '+state.hostAddress):'',info.operating_system||info.os_type,info.architecture].filter(Boolean).join(' · ');
  updateContainerIdentity();
  host.title=info.kernel_version||host.textContent;
  engine.textContent=[info.docker_version?'Docker '+info.docker_version:'',info.cpus?info.cpus+' CPU':'',info.memory_bytes?new Intl.NumberFormat(state.settings.language==='PL'?'pl':'en',{maximumFractionDigits:1}).format(info.memory_bytes/2**30)+' GiB RAM':''].filter(Boolean).join(' · ');
 }catch{if(version===infrastructureVersion){state.hostAddress='';updateContainerIdentity();host.textContent=t('Nie udało się odczytać infrastruktury hosta Docker.');host.title='';engine.textContent='';}}
}
function translateShell(version){
 const labels=[['.host-caption','Infrastruktura hosta Docker'],['.profile-picker>span','Aktywny profil'],['#logout','Wyloguj'],['.workspace-footer>span:first-child','Twoje profile. Twoje dane.']];
 labels.forEach(([selector,text])=>document.querySelector(selector).textContent=t(text));
 document.querySelector('#refresh').textContent='↻ '+t('Odśwież');
 document.querySelector('.sidebar-bottom>a').textContent='DCC Web '+version+' · '+t('Dokumentacja')+' ↗';
 document.querySelector('#profile-select').setAttribute('aria-label',t('Aktywny profil'));
 document.querySelector('#language-switch').setAttribute('aria-label',t('Język'));
}
async function bootstrap(){const data=await api('bootstrap');state.user=data.user;state.features=data.features||{};state.profiles=data.profiles;applySettings(data.settings);if(!state.profiles.some(p=>p.id===state.profile))state.profile=state.profiles[0]?.id||'local';document.querySelector('#profile-select').innerHTML=state.profiles.map(p=>html`<option value="${esc(p.id)}" ${p.id===state.profile?'selected':''}>${esc(p.name)}</option>`).join('');document.querySelector('#user-label').textContent=state.user.name+' · '+state.user.role;document.querySelectorAll('#language-switch [data-language]').forEach(button=>{button.setAttribute('aria-pressed',String(button.dataset.language===state.settings.language));button.disabled=false;});const en=state.settings.language==='EN';document.querySelector('#navigation').innerHTML=navigation.filter(([id])=>state.user.role==='admin'||!['profiles','audit','mcp'].includes(id)).map(([id,label,glyph,english])=>html`<a href="#${id}" data-nav="${id}">${icon(glyph)}<span>${en?english:label}</span></a>`).join('');translateShell(data.version);loadInfrastructure();clearInterval(interval);interval=setInterval(()=>{if(document.hidden||document.querySelector('#modal').open||rendering||document.activeElement.matches('input,textarea,select')||!['overview','containers','monitoring','logs'].includes(state.view)||state.view==='logs'&&state.logLive===false)return;if(state.settings.refresh_changes_only&&['overview','containers'].includes(state.view)){checkContainerChanges();return;}render(false);},Math.max(15,Math.min(900,Number(state.settings.refresh)||15))*1000);}
async function checkContainerChanges(){
 const profile=state.profile,view=state.view,version=renderVersion;
 try{
  const revision=await api('containers/revision');
  if(profile!==state.profile||view!==state.view||version!==renderVersion)return;
  if(state.containerRevision?.profile!==profile){state.containerRevision={profile,value:revision.revision};return;}
  if(revision.revision===state.containerRevision?.value){const label=document.querySelector('#last-refresh');if(label)label.textContent=t('Sprawdzono')+' '+new Date().toLocaleTimeString();return;}
  const snapshot=await api(view==='overview'?'overview':'containers');
  if(profile!==state.profile||view!==state.view||version!==renderVersion||document.querySelector('#modal').open||document.activeElement.matches('input,textarea,select'))return;
  state.containerRevision={profile,value:snapshot.revision||revision.revision};
  await render(false,snapshot);
 }catch(error){if(profile===state.profile&&view===state.view&&version===renderVersion){const label=document.querySelector('#last-refresh');if(label)label.textContent=t('Nie udało się sprawdzić zmian');}}
}
async function render(showLoading=true,containerSnapshot=null){
 const parts=location.hash.replace(/^#/,'').split('/'),view=loaders[parts[0]]?parts[0]:'overview';state.view=view;state.target=decodeURIComponent(parts.slice(1).join('/'));const version=++renderVersion;rendering=true;const valid=()=>version===renderVersion;document.querySelectorAll('[data-nav]').forEach(a=>a.classList.toggle('active',a.dataset.nav===view));document.querySelector('#breadcrumb').textContent=navigation.find(v=>v[0]===view)?.[state.settings.language==='EN'?3:1]||view;document.body.classList.remove('menu-open');if(showLoading)root.innerHTML=literal('<div class="loading">Ładowanie…</div>');
 try{const [module,method]=loaders[view],views=await import('./views/'+module+'.js');await views[method](root,{valid,containerSnapshot,refresh:()=>render(false),reload:async()=>{await bootstrap();await render();},connected:ok=>{const label=document.querySelector('#connection-label');label.textContent=ok?t('Połączono · ')+(state.profiles.find(p=>p.id===state.profile)?.name||'Docker'):t('Brak połączenia Docker');label.previousElementSibling.style.background=ok?'var(--good)':'var(--warn)';}});if(valid())document.querySelector('#last-refresh').textContent=t('Odświeżono ')+new Date().toLocaleTimeString();}
 catch(error){if(valid()){root.innerHTML=heading(navigation.find(v=>v[0]===view)?.[1]||'DCC Web','Sprawdź profil połączenia i uprawnienia.')+notice(error.message,'error')+html`<section class="panel panel-pad"><h2>Jak kontynuować</h2><p>Upewnij się, że Docker działa, a proces DCC Web ma do niego dostęp. Nowe profile mają tylko odczyt; operacje zapisu włącza administrator w profilu.</p><div class="toolbar"><a class="button" href="#profiles">Sprawdź profile</a><button id="retry">Spróbuj ponownie</button></div></section>`;root.querySelector('#retry').onclick=()=>render();document.querySelector('#connection-label').textContent=t('Wymagane sprawdzenie profilu');}}
 finally{if(valid())rendering=false;}
}
document.querySelector('#profile-select').onchange=e=>{state.profile=e.target.value;state.hostAddress='';state.containerRevision=null;localStorage.setItem('dcc-profile',state.profile);state.selected.clear();updateContainerIdentity();loadInfrastructure();render();};document.querySelector('#refresh').onclick=async()=>{const profile=state.profile;loadInfrastructure();if(!['containers','overview'].includes(state.view)){try{const data=await api('containers');if(profile===state.profile){state.containers=data.containers;state.containerRevision={profile,value:data.revision};}}catch(error){notify(error.message,'error');}}await render(false);};document.querySelector('#logout').onclick=async()=>{try{await post('logout',{});location.assign('/login');}catch(e){notify(e.message,'error');}};document.querySelector('#menu-toggle').onclick=()=>document.body.classList.toggle('menu-open');document.querySelector('#backdrop').onclick=()=>document.body.classList.remove('menu-open');window.addEventListener('hashchange',()=>{sound('tab');render();});document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!document.querySelector('#modal').open&&state.view!=='settings')render(false);});
bootstrap().then(()=>render()).catch(error=>{root.innerHTML=notice(error.message,'error');});

document.querySelectorAll('#language-switch [data-language]').forEach(button=>button.onclick=async()=>{if(button.disabled||button.dataset.language===state.settings.language)return;const buttons=[...document.querySelectorAll('#language-switch [data-language]')];buttons.forEach(item=>item.disabled=true);try{applySettings(await api('settings',{method:'PUT',data:{language:button.dataset.language}}));await bootstrap();await render();}catch(error){notify(error.message,'error');}finally{buttons.forEach(item=>item.disabled=false);}});
