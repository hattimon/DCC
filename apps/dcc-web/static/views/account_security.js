import{html,t}from'../i18n.js';
import{api,state,post}from'../api.js';
import{esc,field,textarea,button,openDialog,notice,notify,copyText}from'../ui.js';
import{accountFields,download,guarded,workspaceConsent}from'./profile_tools.js';

export async function accountSecurity(root,ctx){
 const [mfa,email]=await Promise.all([api('account/2fa'),api('account/recovery-email')]);if(!ctx.valid())return;
 const appearance=root.querySelector('#settings-form'),account=appearance.nextElementSibling;
 appearance.id='settings-form';appearance.dataset.settingsPanel='appearance';account.dataset.settingsPanel='security';
 const tabs=document.createElement('div');tabs.className='toolbar settings-tabs';tabs.setAttribute('role','tablist');
 tabs.innerHTML=html`<button role="tab" aria-selected="true" data-settings-tab="appearance">Wygląd i dźwięki</button><button role="tab" aria-selected="false" data-settings-tab="security">Administracja i bezpieczeństwo</button>`;
 appearance.before(tabs);account.hidden=true;
 tabs.querySelectorAll('[data-settings-tab]').forEach(b=>b.onclick=()=>{for(const panel of root.querySelectorAll('[data-settings-panel]'))panel.hidden=panel.dataset.settingsPanel!==b.dataset.settingsTab;tabs.querySelectorAll('button').forEach(el=>el.setAttribute('aria-selected',String(el===b)));});
 const extra=document.createElement('div');extra.className='stack';
 extra.innerHTML=html`<hr class="divider"><h3>Uwierzytelnianie 2FA</h3><p>${esc(t(mfa.enabled?'2FA jest włączone':'2FA jest wyłączone'))}</p>${notice('Obsługiwane są aplikacje TOTP, np. Google Authenticator oraz aplikacje uwierzytelniające na iPhone. Kody odzyskiwania są jednorazowe.')}<div>${button(mfa.enabled?'Wyłącz 2FA':'Włącz 2FA','account-2fa')}</div><h3>Odzyskiwanie dostępu</h3><p>${esc(email.email||t('Brak zweryfikowanego adresu email'))}</p>${notice(email.smtp_configured?'Reset 2FA przez email wymaga wcześniej zweryfikowanego adresu i hasła konta.':'Najpierw skonfiguruj SMTP z TLS. Bez emaila możesz użyć jednorazowego kodu odzyskiwania.')}<div>${button('Zweryfikuj adres email','verify-email')}</div>${state.user.role==='admin'?html`<hr class="divider"><h3>Ustawienia administracyjne</h3><div class="toolbar">${button('Poczta odzyskiwania — SMTP','admin-smtp')}${button('Domena lokalna i publiczna','admin-domains')}</div>`:''}`;
 account.append(extra);
 root.querySelector('#account-2fa').onclick=guarded(async()=>{
  if(mfa.enabled){await openDialog('Wyłącz 2FA',html`<div class="stack">${accountFields()}${notice('Pozostałe sesje zostaną wylogowane.','warning')}</div>`,{submit:'Wyłącz 2FA',danger:true,onSubmit:async f=>{await post('account/2fa/disable',Object.fromEntries(f));ctx.reload();}});return;}
  const setup=await openDialog('Włącz 2FA',html`${field('Obecne hasło','current_password','',{type:'password',required:true})}${notice('Przygotuj aplikację uwierzytelniającą. Sekretny klucz zobaczysz tylko podczas konfiguracji.')}`,{submit:'Dalej',onSubmit:async f=>{const password=f.get('current_password');return{password,...await post('account/2fa/setup',{current_password:password})};}});
  if(!setup)return;
  const enabled=await openDialog('Dodaj konto w aplikacji TOTP',html`<div class="stack">${notice('Wybierz ręczne dodanie konta w aplikacji: DCC Web, klucz poniżej, typ czasowy TOTP, 6 cyfr, 30 sekund.')}<code class="selectable">${esc(setup.secret)}</code><button type="button" data-copy-secret>Kopiuj klucz</button><details><summary>Adres otpauth</summary><code class="wrap">${esc(setup.uri)}</code></details>${field('Kod z aplikacji','otp','',{required:true,placeholder:'123456'})}</div>`,{submit:'Włącz 2FA',onReady:form=>form.querySelector('[data-copy-secret]').onclick=()=>copyText(setup.secret),onSubmit:f=>post('account/2fa/enable',{current_password:setup.password,otp:f.get('otp')})});
  if(!enabled)return;
  await openDialog('Zapisz kody odzyskiwania',html`<div class="stack">${notice('Zapisz te kody w bezpiecznym miejscu poza DCC Web. Każdy działa jeden raz. Nie zostaną pokazane ponownie.','warning')}${textarea('Kody odzyskiwania','codes',enabled.recovery_codes.join('\n'))}<div class="toolbar"><button type="button" data-copy-codes>Kopiuj</button><button type="button" data-save-codes>Pobierz</button></div></div>`,{onReady:form=>{form.elements.codes.readOnly=true;form.querySelector('[data-copy-codes]').onclick=()=>copyText(enabled.recovery_codes.join('\n'));form.querySelector('[data-save-codes]').onclick=()=>download(enabled.recovery_codes.join('\n'),'dcc-web-recovery-codes.txt');}});ctx.reload();
 });
 root.querySelector('#verify-email').onclick=guarded(async()=>{
  if(!email.smtp_configured)throw Error(t('Najpierw skonfiguruj SMTP z TLS.'));
  const sent=await openDialog('Zweryfikuj adres email',html`<div class="stack">${field('Email odzyskiwania','email',email.email||'',{type:'email',required:true})}${accountFields()}</div>`,{submit:'Wyślij kod',onSubmit:f=>post('account/recovery-email/request',Object.fromEntries(f))});if(!sent)return;
  await openDialog('Potwierdź adres email',field('Kod z wiadomości email','code','',{required:true}),{submit:'Zweryfikuj',onSubmit:async f=>{await post('account/recovery-email/verify',Object.fromEntries(f));notify('Adres email został zweryfikowany');ctx.reload();}});
 });
 root.querySelector('#admin-smtp')?.addEventListener('click',guarded(async()=>{
  const saved=await api('admin/smtp');await openDialog('Poczta odzyskiwania — SMTP',html`<div class="stack"><div class="form-grid">${field('Serwer SMTP','host',saved.host||'',{required:true})}${field('Port SMTP','port',saved.port||587,{type:'number',required:true})}${field('Adres nadawcy','sender',saved.sender||'',{type:'email',required:true})}${field('Użytkownik SMTP','username',saved.username||'')}${field('Hasło SMTP — puste zachowuje obecne','password','',{type:'password'})}</div><label class="check"><input name="implicit_tls" type="checkbox" ${saved.implicit_tls?'checked':''}>TLS od początku (zwykle port 465)</label>${notice('Bez zaznaczenia: wymagane STARTTLS. Certyfikat jest weryfikowany. Dane SMTP są szyfrowane. Nie jest używana płatna usługa SMS.')}<div class="form-grid">${accountFields()}</div></div>`,{onSubmit:f=>api('admin/smtp',{method:'PUT',data:{...Object.fromEntries(f),implicit_tls:f.has('implicit_tls')}})});
 }));
 root.querySelector('#admin-domains')?.addEventListener('click',guarded(()=>domainDialog()));
}

async function domainDialog(){
 const saved=await api('admin/domains');
 const choice=await openDialog('Domena lokalna i publiczna',html`<div class="stack"><h3>Domena lokalna</h3>${field('Nazwa w sieci lokalnej','local',saved.local||'',{placeholder:'dcc.home.arpa'})}${notice('Dodaj w DNS routera lub pliku hosts wpis: adres IP hosta Docker → nazwa lokalna. To ustawienie dopuszcza nazwę w panelu; nie zmienia konfiguracji routera. Port panelu pozostaje bez zmian.')}<h3>Domena publiczna</h3>${field('Twoja domena publiczna','public',saved.public||'',{placeholder:'dcc.example.com'})}${notice('Publiczny DNS musi wskazywać hosta. Rozszerzenie Caddy może automatycznie uzyskać certyfikat HTTPS na portach 80/443. Wymaga publicznej osiągalności hosta. Przy CGNAT użyj własnego tunelu lub VPN i reverse proxy. Włącz silne hasło i 2FA przed publikacją.','warning')}<div class="form-grid">${accountFields()}</div></div>`,{submit:'Zapisz domeny',onSubmit:f=>api('admin/domains',{method:'PUT',data:Object.fromEntries(f)})});
 if(!choice?.public)return;
 await openDialog('Publiczny dostęp HTTPS',html`<div class="stack"><a href="https://${esc(choice.public)}" target="_blank" rel="noopener">https://${esc(choice.public)}</a>${notice('Rozszerzenie działa na tym samym hoście Docker co DCC Web. Instalacja pobiera oficjalny obraz Caddy i publikuje porty 80 oraz 443. Certyfikaty są przechowywane w osobnym wolumenie.')}<div class="toolbar">${['install','start','stop','remove'].map((action,i)=>html`<button type="button" data-proxy="${action}">${t(['Zainstaluj HTTPS','Włącz dostęp','Wyłącz dostęp','Usuń rozszerzenie'][i])}</button>`).join('')}<button type="button" data-verify-https>Sprawdź HTTPS</button></div><p data-https-status aria-live="polite"></p><a href="/docs/security" target="_blank" rel="noopener">Dokumentacja</a></div>`,{onReady:form=>{
  form.querySelector('[data-verify-https]').onclick=async()=>{const el=form.querySelector('[data-https-status]');el.textContent=t('Sprawdzanie połączenia…');try{await post('admin/domains/verify',{});el.textContent=t('HTTPS działa poprawnie');}catch(e){el.textContent=e.message;}};
  form.querySelectorAll('[data-proxy]').forEach(b=>b.onclick=async()=>{const action=b.dataset.proxy;await proxyOperation(action);});
 }});
}
async function proxyOperation(action){
 const credentials=await openDialog('Potwierdź operację HTTPS',html`<div class="stack">${accountFields()}${notice('Instalacja zajmie porty 80/443. Wyłączenie zatrzyma publiczny dostęp przez rozszerzenie. Usunięcie zachowuje wolumeny certyfikatów.','warning')}</div>`,{onSubmit:async f=>{const data=Object.fromEntries(f);return{data,plan:await post('admin/domains/proxy/'+action,{...data,preview:true})};}});
 if(!credentials)return;
 const approval=await workspaceConsent('panel.proxy',credentials.plan.target,'Potwierdzam zmianę publicznego dostępu HTTPS.',html`<p>${esc(credentials.plan.domain)} · ${esc(action)}</p>`);
 if(approval){try{await post('admin/domains/proxy/'+action,{...credentials.data,...approval});notify('Operacja zakończona');}catch(e){notify(e.message,'error');}}
}
