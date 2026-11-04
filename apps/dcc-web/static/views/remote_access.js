import{html,t}from'../i18n.js';
import{api,post,pollJob}from'../api.js';
import{esc,field,openDialog,notice,notify,copyText}from'../ui.js';
import{accountFields}from'./profile_tools.js';

const statuses={
 'not-installed':'Niezainstalowany',configure:'Wymaga konfiguracji',disabled:'Wyłączony',
 connecting:'Łączenie',active:'Aktywny',reconnecting:'Ponowne łączenie',
 error:'Błąd',blocked:'Zablokowany ze względów bezpieczeństwa'
};
const actions={
 install:'Zainstaluj',configure:'Skonfiguruj',enable:'Włącz dostęp',disable:'Wyłącz dostęp',
 restart:'Uruchom ponownie',uninstall:'Odinstaluj'
};
const consent={
 install:'Zainstaluj izolowany kontener zrok. Dostęp publiczny pozostanie wyłączony.',
 configure:'Zarejestruj środowisko zrok i zarezerwuj nazwę publiczną. Dostęp publiczny pozostanie wyłączony.',
 enable:'Panel administracyjny będzie dostępny przez Internet przez bramę zrok. Logowanie DCC i MFA administratora nadal obowiązują.',
 disable:'Zamknij tunel publiczny. Zarezerwowana nazwa pozostanie dostępna do ponownego użycia.',
 restart:'Uruchom ponownie tunel po ponownym sprawdzeniu wymagań bezpieczeństwa.',
 uninstall:'Zatrzymaj tunel i usuń jego kontener. Wybierz, czy zachować rezerwację i środowisko zrok.'
};

export async function remoteAction(action,status){
 const confirm=await openDialog(actions[action],html`<div class="stack">
  ${notice(consent[action],['enable','restart','uninstall'].includes(action)?'warning':'')}
  ${action==='configure'?html`<a href="https://myzrok.io/" target="_blank" rel="noopener noreferrer">myzrok.io ↗</a>
   <p>Utwórz konto, otwórz konsolę zrok i skopiuj token konta z kreatora.</p>
   ${status.enrolled?'':field('Token konta zrok','account_token','',{type:'password',required:true})}
   ${field('Nazwa publiczna (pusta oznacza nazwę automatyczną)','name',status.name||'')}`:''}
  ${action==='uninstall'?html`<label class="check"><input name="keep_data" type="checkbox" checked>Zachowaj środowisko i rezerwację zrok</label>
   <label class="check"><input name="provider_cleaned" type="checkbox">Środowisko i nazwę usunięto już w konsoli zrok.</label>`:''}
  ${['configure','enable','restart','uninstall'].includes(action)?html`<div class="form-grid">${accountFields()}</div>`:''}
  <label class="check"><input type="checkbox" required>Potwierdzam świadomie tę zmianę.</label>
 </div>`,{submit:actions[action],danger:['enable','uninstall'].includes(action),onSubmit:async form=>{
  const approval=await post('confirmations',{action:'remote-access.'+action,target:'dcc-remote-access'});
  const result=await post('admin/remote-access/'+action,{...Object.fromEntries(form),keep_data:form.has('keep_data'),provider_cleaned:form.has('provider_cleaned'),...approval});
  await pollJob(result);
  return true;
 }});
 return Boolean(confirm);
}

function address(status){
 if(status.state!=='active')return '';
 try{const url=new URL(status.origin);return url.protocol==='https:'&&url.hostname.endsWith('.share.zrok.io')?url.origin:'';}catch{return '';}
}

export function mountRemoteAccess(root,ctx){
 const section=root.querySelector('#remote-access');
 if(!section)return;
 const update=async()=>{
  if(!ctx.valid()||!section.isConnected)return;
  try{
   const value=await api('admin/remote-access');
   if(!ctx.valid()||!section.isConnected)return;
   const url=address(value),installed=value.container!=='missing',running=['active','connecting','reconnecting'].includes(value.state);
   const authenticatedAction=value.can_reauthenticate&&value.security!=='blocked';
   const buttons=value.available&&value.can_manage?(installed?[
    ...(!running&&authenticatedAction?['configure']:[]),
    ...(!running&&authenticatedAction&&value.name&&value.mfa_ready?['enable']:[]),
    ...(running||value.container==='running'?['disable']:[]),
    ...(value.state==='active'&&value.mfa_ready&&authenticatedAction?['restart']:[]),
    ...(!running&&value.can_reauthenticate?['uninstall']:[])
   ]:['install']):[];
   const time=value.last_connection?new Date(value.last_connection*1000).toLocaleString():'—';
   section.innerHTML=html`<h3>Zdalny dostęp przez Internet</h3>
   <p class="fine">Udostępnij panel przez HTTPS za pośrednictwem zrok.</p>
   <div class="detail-meta">
   <div><span>Stan</span><strong data-remote-state>${esc(t(statuses[value.state]||value.state))}</strong></div>
   <div><span>Dostawca</span>zrok ${esc(value.provider_version)}</div>
   <div><span>Kontener</span>${esc(value.container)}</div>
   <div><span>Stan tunelu</span>${esc(t(statuses[value.tunnel]||value.tunnel))}</div>
   <div><span>Zarezerwowana nazwa</span>${esc(value.name||'—')}</div>
   <div><span>Ostatnie połączenie</span>${esc(time)}</div>
   <div><span>Polityka bezpieczeństwa</span>${esc(t(value.security==='blocked'?statuses.blocked:'Przypięty obraz zrok'))}</div>
   <div><span>Aktualizacja</span>${esc(value.update?(value.update.available?value.update.latest:t('Brak nowszej wersji')):'—')}</div>
   </div>
   ${value.error?notice(value.error,'warning'):''}
   ${!value.available?notice('Instalacja jest dostępna w kontenerowym DCC Web na lokalnym silniku Docker.'):''}
   ${value.available&&!value.can_manage?notice('Zarządzaj zdalnym dostępem z lokalnego panelu.'):''}
   ${value.available&&value.can_manage&&!value.can_reauthenticate?notice('Open the local panel over HTTPS for this operation.') : ''}
   ${value.available&&!value.mfa_ready?notice('Włącz 2FA na swoim koncie administratora, aby uruchomić tunel.','warning'):''}
   ${url?html`<p><a data-remote-address href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(url)}</a></p>`:''}
   <div class="toolbar">${buttons.map(action=>html`<button type="button" data-remote-action="${action}">${esc(t(actions[action]))}</button>`).join('')}
   ${url?html`<button type="button" data-copy-remote>Kopiuj adres</button><a class="button" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Otwórz panel</a>`:''}
   <button type="button" data-remote-diagnostics>Diagnostyka</button>
   ${value.available&&value.can_manage?html`<button type="button" data-remote-update>Sprawdź aktualizacje</button>`:''}</div>`;
   for(const button of section.querySelectorAll('[data-remote-action]')){
    button.onclick=async()=>{try{if(await remoteAction(button.dataset.remoteAction,value))await update();}catch(error){notify(error.message,'error');}};
   }
   const copy=section.querySelector('[data-copy-remote]');
   if(copy)copy.onclick=()=>copyText(url);
   section.querySelector('[data-remote-diagnostics]').onclick=()=>openDialog('Diagnostyka',html`<pre class="inspect">${esc(JSON.stringify(value,null,2))}</pre>`);
   const check=section.querySelector('[data-remote-update]');
   if(check)check.onclick=async()=>{try{await post('admin/remote-access/check-update',{});await update();}catch(error){notify(error.message,'error');}};
   if(running)setTimeout(update,6000);
  }catch(error){
   if(ctx.valid())section.innerHTML=notice(error.message,'error');
  }
 };
 update();
}
