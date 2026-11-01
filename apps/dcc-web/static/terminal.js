import{api,state}from'./api.js';
import{applySettings,copyText,notice,openDialog,esc}from'./ui.js';
import{t,html}from'./i18n.js';
const initialProfile=document.querySelector('meta[name=terminal-profile]').content;
const surface=document.querySelector('#terminal-surface'),status=document.querySelector('#terminal-status');
const tabs=[],infrastructure=new Map();let active=null,nextTab=0,resizing;
const bar=document.createElement('div');bar.id='terminal-tabs';bar.setAttribute('role','tablist');surface.before(bar);
const newTabButton=document.createElement('button');newTabButton.id='terminal-new-tab';document.querySelector('#terminal-new-window').before(newTabButton);
function send(tab,path,data){return api(path+'?profile='+encodeURIComponent(tab.profile.id),{method:'POST',data:{profile:tab.profile.id,...data}});}
function banner(message){document.querySelector('#terminal-notice').textContent=t(message||'');}
function encode(text){const bytes=new TextEncoder().encode(text);let result='';for(const byte of bytes)result+=String.fromCharCode(byte);return btoa(result);}
function drawTabs(){
 bar.innerHTML=tabs.map(tab=>html`<span class="terminal-tab"><button role="tab" aria-selected="${tab===active}" aria-controls="terminal-pane-${tab.key}" data-terminal-tab="${tab.key}">${esc(tab.profile.name)}${tab.serial>1?' · '+tab.serial:''}</button><button class="quiet small" aria-label="${esc(t('Zamknij zakładkę'))}" data-terminal-close="${tab.key}">×</button></span>`).join('');
 bar.querySelectorAll('[data-terminal-tab]').forEach(b=>b.onclick=()=>activate(tabs.find(tab=>tab.key===b.dataset.terminalTab)));
 bar.querySelectorAll('[data-terminal-close]').forEach(b=>b.onclick=()=>closeTab(tabs.find(tab=>tab.key===b.dataset.terminalClose)));
}
function drawHeader(){
 const tab=active;document.querySelector('#terminal-profile-name').textContent=tab?.profile.name||t('Terminal');
 document.title='DCC Web — '+t('Terminal')+(tab?' · '+tab.profile.name:'');
 status.textContent=tab?t(tab.status):'';
 document.querySelector('#terminal-connect').disabled=!tab||Boolean(tab.id)||tab.connecting;
 document.querySelector('#terminal-disconnect').disabled=!tab?.id;
 document.querySelector('#terminal-copy').disabled=!tab;
 banner(tab?.error||'');
 const info=tab&&infrastructure.get(tab.profile.id);
 document.querySelector('#terminal-host').textContent=info?[info.name,info.operating_system||info.os_type,info.architecture].filter(Boolean).join(' · '):'';
 document.querySelector('#terminal-engine').textContent=info?[info.docker_version?'Docker '+info.docker_version:'',info.cpus?info.cpus+' CPU':'',info.memory_bytes?(info.memory_bytes/2**30).toFixed(1)+' GiB RAM':''].filter(Boolean).join(' · '):'';
}
function fitTab(tab){if(tab!==active)return;tab.fit.fit();if(tab.id)send(tab,'host-terminal/'+encodeURIComponent(tab.id)+'/resize',{cols:Math.min(300,Math.max(20,tab.term.cols)),rows:Math.min(120,Math.max(5,tab.term.rows))}).catch(error=>{tab.error=error.message;if(tab===active)drawHeader();});}
function activate(tab){
 active=tab;state.profile=tab?.profile.id||initialProfile;
 tabs.forEach(value=>value.pane.hidden=value!==tab);
 drawTabs();drawHeader();
 if(tab){requestAnimationFrame(()=>{fitTab(tab);tab.term.focus();});poll(tab);}
}
async function connect(tab){
 if(!tab||tab.id||tab.connecting)return;
 try{
  if(!tab.profile.permissions.includes('host.exec')){
   if(state.user.role!=='admin')throw Error(t('Terminal wymaga osobnego uprawnienia host.exec.'));
   const allowed=await openDialog('Włącz terminal dla tego profilu',html`${notice('Wpisywane polecenia działają na wybranym hoście.','warning')}<p class="mono">${esc(tab.profile.name)}</p><label class="check"><input type="checkbox" required>${t('Terminal wymaga osobnego uprawnienia host.exec.')}</label>`,{submit:'Włącz terminal dla tego profilu',onSubmit:async()=>{await api('profiles/'+tab.profile.id+'?profile='+encodeURIComponent(tab.profile.id),{method:'PUT',data:{permissions:[...new Set([...tab.profile.permissions,'host.exec'])]}});tab.profile.permissions.push('host.exec');return true;}});
   if(!allowed)return;
  }
  tab.connecting=true;tab.status='Połączenie z hostem…';tab.error='';if(tab===active)drawHeader();
  fitTab(tab);
  const approval=await send(tab,'confirmations',{action:'host.terminal',target:tab.profile.id});
  const value=await send(tab,'host-terminal',{...approval,cols:Math.min(300,Math.max(20,tab.term.cols)),rows:Math.min(120,Math.max(5,tab.term.rows))});
  if(!tabs.includes(tab)){await send(tab,'host-terminal/'+value.id+'/close',{});return;}
  tab.id=value.id;tab.offset=0;tab.closed=false;tab.term.options.disableStdin=false;tab.status='Połączono';poll(tab);
 }catch(error){tab.error=error.message;tab.status='Błąd';}
 finally{tab.connecting=false;if(tab===active)drawHeader();}
}
async function poll(tab){
 if(!tab||tab.polling||!tab.id||tab!==active)return;
 tab.polling=true;const id=tab.id;
 try{
  while(tab.id===id&&active===tab&&!tab.closed){
   const value=await api('host-terminal/'+encodeURIComponent(id)+'?profile='+encodeURIComponent(tab.profile.id)+'&offset='+tab.offset);
   if(tab.id!==id)return;
   if(value.truncated)tab.term.writeln('\r\n[Earlier terminal output was discarded]\r\n');
   if(value.data)tab.term.write(Uint8Array.from(atob(value.data),c=>c.charCodeAt(0)));
   tab.offset=value.offset;
   if(value.closed){tab.closed=true;tab.id='';tab.term.options.disableStdin=true;tab.status='Sesja terminala zakończona.';break;}
  }
 }catch(error){if(tab.id===id){tab.error=error.message;tab.status='Błąd';tab.id='';tab.term.options.disableStdin=true;}}
 finally{tab.polling=false;if(tab===active)drawHeader();}
}
async function disconnect(tab){
 if(!tab)return;
 const id=tab.id;tab.id='';tab.closed=true;tab.term.options.disableStdin=true;tab.status='Sesja terminala zakończona.';
 if(tab===active)drawHeader();
 if(id)await send(tab,'host-terminal/'+encodeURIComponent(id)+'/close',{});
}
async function closeTab(tab){
 if(!tab)return;
 await disconnect(tab).catch(()=>{});
 const at=tabs.indexOf(tab);if(at>=0)tabs.splice(at,1);tab.term.dispose();tab.pane.remove();
 if(active===tab)activate(tabs[Math.min(at,tabs.length-1)]||null);else drawTabs();
}
function addTab(profileId){
 const profile=state.profiles.find(p=>p.id===profileId);if(!profile)return;
 const key=String(++nextTab),pane=document.createElement('div');pane.id='terminal-pane-'+key;pane.className='terminal-pane';pane.setAttribute('role','tabpanel');surface.append(pane);
 const style=getComputedStyle(document.documentElement);
 const term=new window.Terminal({fontFamily:'"Cascadia Code",Consolas,monospace',fontSize:13,scrollback:3000,disableStdin:true,cursorBlink:state.settings.animations!==false,theme:{background:style.getPropertyValue('--bg').trim(),foreground:style.getPropertyValue('--text').trim(),cursor:style.getPropertyValue('--accent').trim(),selectionBackground:style.getPropertyValue('--surface3').trim()}});
 const fit=new window.FitAddon.FitAddon();term.loadAddon(fit);term.open(pane);
 const tab={key,profile,pane,term,fit,id:'',offset:0,closed:false,connecting:false,polling:false,status:'Połącz',error:'',write:Promise.resolve(),serial:tabs.filter(v=>v.profile.id===profileId).length+1};
 term.onData(data=>{if(!tab.id)return;const id=tab.id;tab.write=tab.write.then(()=>send(tab,'host-terminal/'+encodeURIComponent(id)+'/input',{data:encode(data)})).catch(error=>{tab.error=error.message;if(tab===active)drawHeader();});});
 tabs.push(tab);activate(tab);
 api('infrastructure?profile='+encodeURIComponent(profile.id)).then(info=>{infrastructure.set(profile.id,info);if(tab===active)drawHeader();}).catch(error=>{tab.error=error.message;if(tab===active)drawHeader();});
 connect(tab);
}
async function main(){
 if(document.readyState!=='complete')await new Promise(resolve=>window.addEventListener('load',resolve,{once:true}));
 const bootstrap=await api('bootstrap');state.user=bootstrap.user;state.profiles=bootstrap.profiles;applySettings(bootstrap.settings);
 if(!state.profiles.some(p=>p.id===initialProfile))throw Error('Profile access denied');
 for(const [id,label]of [['terminal-connect','Połącz'],['terminal-copy','Kopiuj'],['terminal-disconnect','Rozłącz'],['terminal-new-tab','Nowa zakładka'],['terminal-new-window','Otwórz kolejne okno'],['terminal-scope','Wpisywane polecenia działają na wybranym hoście.']])document.getElementById(id).textContent=t(label);
 document.querySelector('#terminal-new-profile').innerHTML=state.profiles.map(p=>html`<option value="${esc(p.id)}" ${p.id===initialProfile?'selected':''}>${esc(p.name)}</option>`).join('');
 newTabButton.onclick=()=>addTab(document.querySelector('#terminal-new-profile').value);
 document.querySelector('#terminal-new-window').onclick=()=>window.open('/terminal?profile='+encodeURIComponent(document.querySelector('#terminal-new-profile').value),'_blank','popup,width=1100,height=760,noopener,noreferrer');
 document.querySelector('#terminal-connect').onclick=()=>connect(active);
 document.querySelector('#terminal-disconnect').onclick=()=>disconnect(active).catch(error=>banner(error.message));
 document.querySelector('#terminal-copy').onclick=()=>{if(!active)return;let text=active.term.getSelection();if(!text){const buffer=active.term.buffer.active,lines=[];for(let i=0;i<buffer.length;i++)lines.push(buffer.getLine(i)?.translateToString(true)||'');text=lines.join('\n');}copyText(text);};
 new ResizeObserver(()=>{clearTimeout(resizing);resizing=setTimeout(()=>{if(active)fitTab(active);},100);}).observe(surface);
 addTab(initialProfile);
}
window.addEventListener('pagehide',()=>{const data=new URLSearchParams({csrf:document.querySelector('meta[name=csrf-token]').content});for(const tab of tabs)if(tab.id)navigator.sendBeacon('/api/host-terminal/'+encodeURIComponent(tab.id)+'/close?profile='+encodeURIComponent(tab.profile.id),data);});
main().catch(error=>banner(error.message));
