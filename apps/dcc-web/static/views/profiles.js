import{profileWizard,vaultSection,bindVault,bindTransfers}from'./profile_tools.js';
import{sshFileKind}from'../ssh_files.js';
import{html,t,literal,setLanguage}from'../i18n.js';
import{api,state,post}from'../api.js';
import{esc,heading,button,table,field,textarea,openDialog,notice,mutate,notify,copyText}from'../ui.js';
const permissions={'host.exec':'Terminal hosta',read:'Odczyt', 'containers.write':'Cykl życia kontenerów',exec:'Polecenia w kontenerach','images.write':'Zarządzanie obrazami','volumes.write':'Tworzenie wolumenów','networks.write':'Tworzenie sieci','compose.write':'Operacje Compose',install:'Instalowanie aplikacji',update:'Aktualizacje',destructive:'Operacje destrukcyjne'};
const guarded=work=>async()=>{try{await work();}catch(e){notify(e.message,'error');}};
const confirmWorkspace=(action,target,description,{extra=''})=>openDialog('Potwierdź operację',html`${notice(description,'warning')}${extra}<label class="check"><input type="checkbox" required>Rozumiem skutki tej operacji i potwierdzam jej wykonanie.</label>`,{submit:'Potwierdzam',danger:true,onSubmit:()=>post('confirmations',{action,target})});
const previewRows=values=>values.map(p=>html`<li><strong>${esc(p.name)}</strong>${p.resolved_path?html` <code>${esc(p.resolved_path)}</code>`:''}</li>`).join('');
export async function profiles(root,ctx){
 const data=await api('profiles'),isAdmin=state.user?.role==='admin';
 const ssh=isAdmin?await api('profile-ssh'):null;
 if(!ctx.valid())return;
 state.profiles=data.profiles;
 const selected=new Set();
 root.innerHTML=heading('Profile połączeń','Lokalny Docker, WSL, SSH, Balena i zdalny Docker przez TLS.',isAdmin?button('Importuj','import-profiles')+button('Eksportuj','export-profiles')+button('+ Nowy profil','new-profile','primary'):'')+
 notice('Nowe profile są domyślnie tylko do odczytu. Konfiguracja i klucze są szyfrowane. Eksport jest chroniony osobnym hasłem.')+
 (isAdmin?vaultSection(ssh)+html`<div class="toolbar"><span id="profile-selection" aria-live="polite"></span>${button('Użyj wspólnego folderu','ssh-apply')}${button('Usuń zaznaczone profile','profiles-delete','danger')}</div>`:'')+
 html`<section class="panel">${table([...(isAdmin?[html`<input id="profiles-all" type="checkbox" aria-label="${esc(t('Zaznacz wszystkie profile'))}">`]:[]),'Profil','Połączenie','Dostęp','Akcje'],data.profiles.map(p=>html`<tr>${isAdmin?html`<td><input type="checkbox" data-select-profile="${esc(p.id)}" aria-label="${esc(p.name)}"></td>`:''}<td class="name">${esc(p.name)}${p.id===state.profile?literal('<span class="secondary">Aktywny</span>'):''}</td><td>${esc(p.kind)}<span class="secondary mono">${esc(p.host||p.endpoint||p.distro||p.context||'Docker CLI context')}</span>${['ssh','balena'].includes(p.kind)?html`<span class="secondary">${esc(t(p.key_scope==='shared'?'Wspólny folder':'Ścieżka indywidualna'))}: ${esc(p.key_path||'—')}</span>`:''}</td><td class="wrap">${esc(p.permissions.join(', '))}</td><td><button class="small quiet" data-test="${esc(p.id)}">Sprawdź</button>${isAdmin?html`<button class="small quiet" data-edit="${esc(p.id)}">Edytuj</button><button class="small quiet danger" data-remove="${esc(p.id)}">Usuń</button>`:''}</td></tr>`))}</section>`;
 root.querySelectorAll('[data-test]').forEach(b=>b.onclick=guarded(async()=>{const value=await api('overview?profile='+encodeURIComponent(b.dataset.test));notify('Połączono z '+(value.info.Name||'Docker Engine'));}));
 if(!isAdmin)return;
 root.querySelector('#new-profile').onclick=()=>profileWizard(null,ctx);
 root.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>profileWizard(data.profiles.find(p=>p.id===b.dataset.edit),ctx));
 root.querySelectorAll('[data-remove]').forEach(b=>b.onclick=guarded(async()=>{const id=b.dataset.remove;const result=await mutate('profiles/'+id,{profile:id},'profile.remove',id,'Usuń zapisany profil połączenia. Zasoby Docker pozostaną zachowane.',{danger:true,method:'DELETE',profile:id});if(result)ctx.reload();}));
 const boxes=[...root.querySelectorAll('[data-select-profile]')],all=root.querySelector('#profiles-all');
 const selection=()=>{all.checked=boxes.length>0&&selected.size===boxes.length;all.indeterminate=selected.size>0&&selected.size<boxes.length;root.querySelector('#profile-selection').textContent=t('Zaznaczone profile:')+' '+selected.size;for(const id of ['ssh-apply','profiles-delete'])root.querySelector('#'+id).disabled=selected.size===0;};
 for(const box of boxes)box.onchange=()=>{box.checked?selected.add(box.dataset.selectProfile):selected.delete(box.dataset.selectProfile);selection();};
 all.onchange=()=>{for(const box of boxes){box.checked=all.checked;box.checked?selected.add(box.dataset.selectProfile):selected.delete(box.dataset.selectProfile);}selection();};selection();
 const bulk=action=>guarded(async()=>{
  const payload={action,ids:[...selected]},plan=await post('profiles/bulk/preview',payload);
  if(!plan.changes.length){notify('Brak wybranych profili SSH lub Balena','error');return;}
  const deleting=action==='profiles.remove.selected';
  const approval=await confirmWorkspace(action,plan.target,deleting?'Usunięte zostaną tylko wybrane profile i ich zapisane hasła. Kontenery, wolumeny oraz pliki SSH pozostaną zachowane. Aktywne terminale tych profili zostaną zamknięte.':'Wybrane profile SSH i Balena będą korzystać ze wspólnego folderu i pliku known_hosts. Nazwy kluczy zostaną zachowane. Pozostałe profile nie zostaną zmienione.',{danger:true,extra:html`<code>${esc(plan.directory)}</code><ul>${previewRows(plan.changes)}</ul>${plan.skipped.length?html`<p>Pominięte profile: ${esc(plan.skipped.map(p=>p.name).join(', '))}</p>`:''}`});
  if(approval){await post('profiles/bulk',{...payload,...approval});notify('Operacja zakończona');ctx.reload();}
 });
 root.querySelector('#ssh-apply').onclick=bulk('profiles.ssh.apply');
 root.querySelector('#profiles-delete').onclick=bulk('profiles.remove.selected');
 root.querySelector('#ssh-copy-path').onclick=()=>copyText(ssh.directory);
 root.querySelector('#ssh-directory').onclick=guarded(async()=>{
  const choice=await openDialog('Wspólne pliki SSH',html`${field('Folder na serwerze DCC Web','directory',ssh.directory,{required:true})}${notice('Folder zarządzany przyjmuje pliki z przeglądarki. Inny folder musi istnieć na serwerze; w kontenerze zamontuj go tylko do odczytu. Zmiana obejmie wyłącznie profile korzystające ze wspólnego folderu.')}`,{onSubmit:async f=>{const directory=f.get('directory');return{directory,plan:await post('profile-ssh/directory/preview',{directory})};}});
  if(!choice)return;
  const approval=await confirmWorkspace('profiles.ssh.directory',choice.plan.target,'Zmiana folderu nie przenosi ani nie usuwa plików. Profile z indywidualnymi ścieżkami pozostaną bez zmian.',{danger:true,extra:html`<code>${esc(choice.plan.directory)}</code><ul>${previewRows(choice.plan.profiles)}</ul>`});
  if(approval){await api('profile-ssh/directory',{method:'PUT',data:{directory:choice.directory,...approval}});ctx.reload();}
 });
 root.querySelector('#ssh-upload')?.addEventListener('click',guarded(async()=>{
  const send=async(path,files,replace,approval={})=>{const form=new FormData();for(const file of files)form.append('files',file,file.name);form.set('replace',String(replace));if(approval.confirmation)form.set('confirmation',approval.confirmation);return api(path,{method:'POST',body:form});};
  let chosen=[];
  const choice=await openDialog('Wgraj pliki SSH',html`<div class="stack">${notice('Wybierz klucze i zaufany plik known_hosts z własnego komputera. Zawartość kluczy nie będzie wyświetlana. Eksport kluczy jest możliwy wyłącznie w szyfrowanej kopii po dodatkowym potwierdzeniu.')}<label>Pliki SSH<input name="files" type="file" multiple></label><label>Wybierz folder SSH<input name="folder" type="file" webkitdirectory multiple></label><div data-ssh-candidates></div><label class="check"><input name="replace" type="checkbox">Zastąp istniejące pliki</label>${notice('Maksymalnie 20 plików, 128 KiB na plik i 1 MiB łącznie. Pliki zachowają swoje nazwy. Nie kopiuj pliku config. Weryfikuj odciski kluczy hostów z zaufanego źródła.','warning')}</div>`,{submit:'Sprawdź i potwierdź',onReady:form=>{
   const scan=async input=>{chosen=[];const found=[];for(const file of input.files){if(file.size>128*1024||found.length>=100)continue;let kind;try{kind=sshFileKind(file.name,await file.text());}catch{continue;}if(kind)found.push({file,kind});}chosen=found.map(v=>v.file);form.querySelector('[data-ssh-candidates]').innerHTML=found.map((v,i)=>html`<label class="check"><input type="checkbox" checked data-key-candidate="${i}">${esc(v.file.name)} · ${esc(t(v.kind==='private key'?'Klucz prywatny':v.kind==='public key'?'Klucz publiczny':'Zaufane hosty'))}</label>`).join('')||notice('Nie znaleziono kluczy SSH');form.querySelectorAll('[data-key-candidate]').forEach(box=>box.onchange=()=>{chosen=[...form.querySelectorAll('[data-key-candidate]:checked')].map(b=>found[Number(b.dataset.keyCandidate)].file);});};
   for(const input of form.querySelectorAll('input[type=file]'))input.onchange=()=>scan(input);
  },onSubmit:async f=>{const files=chosen,replace=f.has('replace');return{files,replace,plan:await send('profile-ssh/files/preview',files,replace)};}});
  if(!choice)return;
  const approval=await confirmWorkspace('profiles.ssh.files',choice.plan.target,'Zezwalam na zapis wybranych plików SSH w prywatnym folderze DCC Web. Klucze prywatne zostaną zaszyfrowane w magazynie. Administrator hosta mający dostęp do klucza głównego może je odszyfrować. Zalecany jest osobny klucz z passphrase. Przesyłaj przez HTTPS lub lokalne połączenie.',{danger:true,extra:html`<code>${esc(choice.plan.directory)}</code><ul>${choice.plan.files.map(f=>html`<li>${esc(f.name)} · ${f.size} B · ${esc(t(f.kind==='private key'?'Klucz prywatny':f.kind==='public key'?'Klucz publiczny':'Zaufane hosty'))}${f.encrypted?html` · Wymaga passphrase`:''}${f.replacing?literal(' · Zastąpienie pliku'):''}${f.fingerprints.map(v=>html`<div class="mono">${esc(v)}</div>`).join('')}</li>`).join('')}</ul>`});
  if(approval){await send('profile-ssh/files',choice.files,choice.replace,approval);notify('Pliki SSH zostały zapisane');ctx.reload();}
 }));
 root.querySelector('#ssh-help').onclick=()=>openDialog('Jak skopiować pliki',html`<div class="stack">${notice('Najprościej użyć Wgraj pliki SSH i wybrać pliki w oknie systemowym. Przeglądarka nie może otworzyć folderu serwera w lokalnym Eksploratorze.')}<p>Przykład dla lokalnego kontenera o nazwie dcc-web. Folder źródłowy wybierasz samodzielnie. Polecenia wykonuj na hoście Dockera.</p>${textarea('PowerShell — kopia wybranego klucza i known_hosts','powershell',ssh.uploads_allowed?'$source = Join-Path $env:USERPROFILE ".ssh"\ndocker exec dcc-web mkdir -p /data/ssh\ndocker cp (Join-Path $source "id_ed25519") dcc-web:/data/ssh/id_ed25519\ndocker cp (Join-Path $source "known_hosts") dcc-web:/data/ssh/known_hosts\ndocker exec dcc-web chmod 700 /data/ssh\ndocker exec dcc-web chmod 600 /data/ssh/id_ed25519 /data/ssh/known_hosts':t('Użyj folderu źródłowego zamontowanego tylko do odczytu.'))}${notice('Polecenia dotyczą domyślnego folderu /data/ssh w obrazie kontenerowym. Nie kopiuj całego folderu SSH. Hasło klucza ustaw osobno w profilu. Zmiana kluczy nie przyznaje uprawnień do operacji Docker.','warning')}</div>`);
 bindVault(root,ctx);bindTransfers(root,ctx,selected);
}
