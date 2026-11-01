import{api,state,post}from'./api.js';
import{copyText,esc,openDialog,notice,notify,sound}from'./ui.js';
import{html,t}from'./i18n.js';
export const lastInstallKey=()=> 'dcc-installation-'+state.user.id+'-'+state.profile;
export async function showInstallProgress(initial,ctx){
 const id=typeof initial==='string'?initial:initial.id,profile=state.profile;
 localStorage.setItem(lastInstallKey(),id);
 const phases=['checking','pulling','creating','starting','access','completed'];
 const names={checking:'Sprawdzanie konfiguracji',pulling:'Pobieranie obrazu',creating:'Tworzenie kontenera',starting:'Uruchamianie i kontrola stanu',access:'Odczyt logów i danych dostępowych',completed:'Instalacja zakończona',failed:'Instalacja nie powiodła się'};
 let current;
 await openDialog('Postęp instalacji',html`<div class="stack"><h3 data-install-status>Instalacja trwa…</h3><progress class="install-progress" aria-label="Postęp instalacji"></progress><ol class="install-phases">${phases.slice(0,-1).map(phase=>html`<li data-install-phase="${phase}">${t(names[phase])}</li>`).join('')}</ol><div class="notice" data-install-message hidden></div><div class="toolbar"><button type="button" data-install-copy>Kopiuj logi</button><button type="button" data-install-download>Pobierz logi</button><button type="button" data-install-access hidden>Pokaż dane dostępowe</button></div><pre class="install-log log-view" tabindex="0"></pre><div class="stack" data-install-details></div><div class="stack" data-install-result></div><p class="fine">Zamknięcie okna nie przerywa instalacji. Postęp można ponownie otworzyć w sklepie.</p></div>`,{onReady:form=>{
  const logs=form.querySelector('.install-log'),status=form.querySelector('[data-install-status]'),progress=form.querySelector('progress'),message=form.querySelector('[data-install-message]');
  form.querySelector('[data-install-copy]').onclick=()=>copyText(logs.textContent);
  form.querySelector('[data-install-download]').onclick=()=>{const blob=new Blob([logs.textContent],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='dcc-installation-'+id+'.log';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  form.querySelector('[data-install-access]').onclick=async()=>{
   try{
    const value=await api('jobs/'+encodeURIComponent(id)+'/access?profile='+encodeURIComponent(profile),{method:'POST',data:{profile}});
    const target=form.querySelector('[data-install-details]');
    target.innerHTML=value.details.length?html`<h3>Dane dostępowe wykryte w logach</h3>${value.details.map((v,i)=>html`<label>${esc(v.label)}<span class="access-value"><input readonly data-access-value="${i}" value="${esc(v.value)}" autocomplete="off" spellcheck="false"><button type="button" data-access-copy="${i}">Kopiuj</button></span></label>`).join('')}`:notice('Nie wykryto gotowych danych logowania. Utwórz konto w aplikacji przy pierwszym uruchomieniu.');
    target.querySelectorAll('[data-access-copy]').forEach(b=>b.onclick=()=>copyText(target.querySelector('[data-access-value="'+b.dataset.accessCopy+'"]').value));
   }catch(error){notify(error.message,'error');}
  };
  const poll=async()=>{
   try{
    while(form.isConnected){
     current=await api('jobs/'+encodeURIComponent(id)+'?profile='+encodeURIComponent(profile));
     if(!form.isConnected)return;
     const done=current.status!=='running',phase=current.phase||(done?(current.status==='success'?'completed':'failed'):'creating'),index=phases.indexOf(phase);
     status.textContent=t(done?(current.status==='success'?'Instalacja zakończona':'Instalacja nie powiodła się'):'Instalacja trwa…')+' · '+t(names[phase]||'Instalacja trwa…');
     progress.classList.toggle('failed',current.status==='error');if(done){progress.max=1;progress.value=current.status==='success'?1:0;}else progress.removeAttribute('value');
     form.querySelectorAll('[data-install-phase]').forEach(li=>{const position=phases.indexOf(li.dataset.installPhase);li.classList.toggle('done',done&&current.status==='success'||position<index);li.classList.toggle('active',li.dataset.installPhase===phase);});
     const text=current.logs||(typeof current.result==='string'?current.result:'');
     if(logs.textContent!==text){const follow=logs.scrollHeight-logs.scrollTop-logs.clientHeight<30;logs.textContent=text;if(follow)logs.scrollTop=logs.scrollHeight;}
     form.querySelector('[data-install-access]').hidden=!(current.access_count>0);
     if(done){
      message.hidden=false;message.className='notice '+(current.status==='error'?'error':'');
      message.textContent=current.status==='error'?t(current.error||'Błąd'):t('Kontener został utworzony. Sprawdź jego panel i stan uruchomienia.');
      const result=form.querySelector('[data-install-result]'),info=current.result;
      if(current.status==='success'){
       result.innerHTML=(info?.links||[]).map(v=>html`<div class="panel-endpoint"><a href="${esc(v.url)}" target="_blank" rel="noopener noreferrer">${esc(v.label)} ↗</a><button type="button" data-result-copy="${esc(v.url)}">Kopiuj</button></div>`).join('')+(info?.hints||[]).map(v=>html`<p class="fine">${esc(v)}</p>`).join('')+(current.access_count===0?notice('Nie wykryto gotowych danych logowania. Utwórz konto w aplikacji przy pierwszym uruchomieniu.'):'');
       result.querySelectorAll('[data-result-copy]').forEach(b=>b.onclick=()=>copyText(b.dataset.resultCopy));
       sound('install');
      }
      ctx?.refresh?.();return;
     }
     await new Promise(resolve=>setTimeout(resolve,800));
    }
   }catch(error){message.hidden=false;message.className='notice error';message.textContent=t(error.message);}
  };
  poll();
 }});
}
