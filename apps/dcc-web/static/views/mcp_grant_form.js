import{html,t}from'../i18n.js';
import{api,state,post}from'../api.js';
import{esc,openDialog,field,notice,notify}from'../ui.js';
import{accountFields}from'./profile_tools.js';

export function grantForm(data,ctx,grant=null){
 const editing=!!grant,selected=new Set(grant?.profiles||[]),tools=new Set(grant?.tools||Object.keys(data.read_tools));
 const hostProfiles=state.profiles.filter(p=>['ssh','balena'].includes(p.kind)&&p.permissions?.includes('read')&&p.permissions?.includes('host.exec'));
 const checkbox=(name,value,label,checked=false,extra='')=>html`<label class="check"><input type="checkbox" name="${name}" value="${esc(value)}" ${checked?'checked':''} ${extra}>${label}</label>`;
 const profileLabel=p=>html`<span class="grant-profile">${esc(p.name)}<span class="secondary">${esc(p.host||p.endpoint||p.distro||p.context||'')}</span>${p.kind==='local'?html`<span class="secondary">MCP · Docker</span>`:''}</span>`;
 return openDialog(editing?'Edytuj dostęp MCP':'Nowy dostęp MCP',html`<div class="stack">
  ${editing?notice('Zapis zachowa obecny token. Wszystkie czaty używające tego tokena otrzymają nowy zakres. Otwarte terminale zostaną zamknięte.'):''}
  ${field('Nazwa dostępu','name',grant?.name||'',{required:true})}
  <label>Klient<select name="client">${data.clients.map(v=>html`<option ${v===(grant?.client||'OpenAI Codex')?'selected':''}>${esc(v)}</option>`).join('')}</select></label>
  ${editing?checkbox('renew_expiry','yes',t('Zmień termin ważności'),false):''}
  <div data-expiry><label>Ważność w dniach<input name="days" type="number" min="1" max="1000000" value="30"></label>${checkbox('unlimited','yes',t('Bez limitu czasowego'),grant?.expires===null)}</div>
  <h3>Uprawnienia MCP</h3><div class="permission-grid"><label class="check"><input type="radio" name="mode" value="read" ${grant?.mode!=='write'?'checked':''}>Tylko odczyt</label><label class="check"><input type="radio" name="mode" value="write" ${grant?.mode==='write'?'checked':''}>Odczyt i modyfikacje</label></div>
  ${checkbox('allow_public','yes',t('Zezwól na publiczne sesje MCP z 2FA'),grant?.allow_public===true)}
  <div data-public-scope><p>Publiczne MCP musi być osobno włączone w panelu. Dostęp zostaje powiązany z kontem właściciela i jego istniejącym 2FA. Kod podajesz wyłącznie na ekranie DCC.</p><label>Maksymalny czas publicznej sesji<select name="public_session_minutes">${[15,30,60].map(v=>html`<option value="${v}" ${v===(grant?.public_session_minutes||30)?'selected':''}>${v} min</option>`).join('')}</select></label><p class="fine">Wygaśnięcie lub 10 minut bezczynności wymaga nowego zatwierdzenia. Brak automatycznego odnawiania.</p></div>
  ${notice('Wybierz konkretne narzędzia i profile. Uprawnienia profilu są sprawdzane przy każdym wywołaniu.')}
  <h3>Profile</h3><div class="permission-grid">${state.profiles.map(p=>checkbox('profiles',p.id,profileLabel(p),selected.has(p.id))).join('')}</div>
  <section><h3>Narzędzia tylko do odczytu</h3><div class="permission-grid">${Object.keys(data.read_tools).map(key=>checkbox('tools',key,esc(key),tools.has(key))).join('')}</div></section>
  <section data-write-tools><h3>Narzędzia modyfikujące</h3><div class="permission-grid">${Object.keys(data.write_tools).filter(key=>key!=='container_remove').map(key=>checkbox('tools',key,esc(key),tools.has(key))).join('')}</div>
   ${checkbox('allow_destructive','yes',html`${t('Zezwól na usuwanie kontenerów')} <code>container_remove</code>`,tools.has('container_remove')&&grant?.allow_destructive)}
   ${notice('Ta zgoda włącza container_remove i potwierdza usuwanie. Wolumeny pozostają. Nie ogranicza poleceń wykonywanych przez terminal.','warning')}
   ${checkbox('allow_host_terminal','yes',t('Zezwól na dostęp terminalowy'),grant?.allow_host_terminal===true)}
   <section data-terminal-scope><h3>Urządzenia z dostępem terminalowym</h3>
    ${notice('Polecenia działają jako użytkownik SSH profilu i mogą zmieniać lub usuwać dane hosta. Uprawnienia root lub sudo zależą od tego konta. Wybierz urządzenia osobno.','warning')}
    <p class="fine">Aby używać poleceń systemu Windows przez MCP, dodaj osobny profil SSH z uprawnieniem host.exec i wybierz go w sekcji Profile.</p>
    <p class="fine" data-no-host-profiles>Wybierz w sekcji Profile urządzenie SSH lub Balena z uprawnieniem host.exec.</p>
    <div class="permission-grid">${hostProfiles.map(p=>checkbox('terminal_profiles',p.id,profileLabel(p),grant?.terminal_profiles?.includes(p.id))).join('')}</div>
    <h4>Narzędzia terminala MCP</h4><div class="permission-grid">${Object.keys(data.terminal_tools).map(key=>checkbox('tools',key,esc(key),tools.has(key))).join('')}</div>
   </section>
   ${notice('Utworzenie kontenera używa tylko nazwanych wolumenów, domyślnie publikuje porty na 127.0.0.1 i nie pozwala na privileged ani montowanie ścieżek hosta. Usunięcie kontenera nie usuwa wolumenów.','warning')}
  </section>
  <div data-write-auth>${accountFields()}</div>
 </div>`,{submit:editing?'Zapisz dostęp':'Utwórz dostęp',onReady:form=>{
  const sync=()=>{
   const write=form.elements.mode.value==='write',terminal=write&&form.elements.allow_host_terminal.checked;
   form.querySelector('[data-write-tools]').hidden=!write;
   form.querySelectorAll('[data-write-tools] input').forEach(input=>input.disabled=!write);
   form.querySelector('[data-terminal-scope]').hidden=!terminal;
   const selectedProfiles=new Set([...form.querySelectorAll('[name=profiles]:checked')].map(input=>input.value));
   const devices=[...form.querySelectorAll('[name=terminal_profiles]')];
   devices.forEach(input=>{
    const eligible=selectedProfiles.has(input.value);
    input.disabled=!terminal||!eligible;
    if(!eligible)input.checked=false;
   });
   form.querySelector('[data-no-host-profiles]').hidden=devices.some(input=>!input.disabled);
   form.querySelectorAll('[data-terminal-scope] [name=tools]').forEach(input=>input.disabled=!terminal);
   const publicEnabled=form.elements.allow_public.checked;form.querySelector('[data-public-scope]').hidden=!publicEnabled;
   const authenticate=editing||write||publicEnabled,auth=form.querySelector('[data-write-auth]');auth.hidden=!authenticate;
   auth.querySelectorAll('input').forEach(input=>{input.disabled=!authenticate;input.required=authenticate&&input.name==='current_password';});
   const expiry=!editing||form.elements.renew_expiry.checked;form.querySelector('[data-expiry]').hidden=!expiry;
  };
  form.querySelectorAll('[name=mode],[name=profiles],[name=renew_expiry],[name=allow_public]').forEach(input=>input.onchange=sync);
  form.elements.allow_host_terminal.onchange=sync;
  sync();
 },onSubmit:async f=>{
  const selectedTools=f.getAll('tools');if(f.has('allow_destructive'))selectedTools.push('container_remove');
  if(f.has('allow_host_terminal')&&(!f.getAll('terminal_profiles').length||!selectedTools.some(key=>Object.hasOwn(data.terminal_tools,key)))){
   throw Error(t('Wybierz co najmniej jedno urządzenie i narzędzie terminala MCP.'));
  }
  const payload={name:f.get('name'),client:f.get('client'),days:Number(f.get('days')),unlimited:f.has('unlimited'),renew_expiry:f.has('renew_expiry'),mode:f.get('mode'),allow_destructive:f.has('allow_destructive'),allow_host_terminal:f.has('allow_host_terminal'),terminal_profiles:f.getAll('terminal_profiles'),profiles:f.getAll('profiles'),tools:selectedTools,allow_public:f.has('allow_public'),public_session_minutes:Number(f.get('public_session_minutes')),current_password:f.get('current_password'),otp:f.get('otp')};
  if(editing)payload.expected_revision=grant.revision??null;
  const result=editing?await api('mcp/grants/'+encodeURIComponent(grant.id),{method:'PUT',data:payload}):await post('mcp/grants',payload);
  if(editing)notify('Dostęp zapisany. Token pozostał ten sam. Połącz MCP ponownie i pobierz aktualne instrukcje.');
  else setTimeout(()=>openDialog('Token — pokazany tylko raz',html`${notice('Zapisz token w menedżerze sekretów klienta. Nie będzie można ponownie go odczytać.','warning')}<pre class="inspect">${esc(result.token)}</pre>`),0);
  ctx.refresh();
 }});
}
