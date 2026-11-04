import{html,t,getLanguage}from'../i18n.js';
import{api,state,post}from'../api.js';
import{esc,heading,button,table,openDialog,field,notice,notify,status,copyText}from'../ui.js';
import{accountFields}from'./profile_tools.js';

async function confirmGrantChange({id,name,action,path,method='POST',description,submit,danger=false},ctx){
 const approval=await openDialog('Potwierdź zmianę dostępu',html`${notice(description,danger?'warning':'')}<p class="mono">${esc(name)}</p><label class="check"><input type="checkbox" required>Potwierdzam świadomie tę zmianę.</label>`,{submit,danger,onSubmit:()=>post('confirmations',{action:'mcp.grant.'+action,target:id})});
 if(!approval)return;
 await api(path,{method,data:approval});
 notify(action==='pause'?'Dostęp wstrzymany':action==='resume'?'Dostęp wznowiony':action==='revoke'?'Dostęp odebrany':'Grant usunięty z historii');
 ctx.refresh();
}

export async function mcp(root,ctx){
 const data=await api('mcp/grants');if(!ctx.valid())return;
 const profileLabel=id=>{const profile=state.profiles.find(p=>p.id===id),address=profile?.host||profile?.endpoint||profile?.distro||profile?.context;return html`<span class="grant-profile">${esc(profile?.name||id)}${address?html`<span class="secondary">${esc(address)}</span>`:''}</span>`;};
 const expired=v=>v.expires!==null&&v.expires<=Date.now()/1000;
 const grants=data.grants.map(v=>html`<tr><td>${esc(v.name)}<span class="secondary">${esc(v.client)} · ${v.mode==='write'?t('Odczyt i modyfikacje'):t('Tylko odczyt')}</span></td><td class="wrap">${v.profiles.map(profileLabel).join('')}<span class="secondary">${v.tools.length} ${t('narzędzi')}</span></td><td>${esc(v.expires===null?t('Bez limitu czasowego'):new Date(v.expires*1000).toLocaleDateString())}</td><td>${!v.revoked&&expired(v)?esc(t('Wygasł')):status(v.revoked?'revoked':v.paused?'paused':'running')}</td><td>${v.revoked?html`<button class="small quiet danger" data-grant-action="delete-history" data-id="${esc(v.id)}" data-name="${esc(v.name)}">Usuń z historii</button>`:html`${v.paused||expired(v)?'':html`<button class="small quiet" data-export="${esc(v.id)}">Eksport</button>`}${v.paused?html`<button class="small quiet" data-grant-action="resume" data-id="${esc(v.id)}" data-name="${esc(v.name)}">Wznów dostęp</button>`:html`<button class="small quiet" data-grant-action="pause" data-id="${esc(v.id)}" data-name="${esc(v.name)}">Pauzuj dostęp</button>`}<button class="small quiet danger" data-grant-action="revoke" data-id="${esc(v.id)}" data-name="${esc(v.name)}">Odbierz dostęp</button>`}</td></tr>`);
 root.innerHTML=heading('AI / MCP','Jawnie ograniczony dostęp MCP do wybranych profili i narzędzi.',button('+ Nowy dostęp','grant-create','primary'))+notice('Działa transport stdio. Dla każdego dostępu wybierz tryb tylko do odczytu albo ograniczone modyfikacje. W Codexie profil wybierzesz po nazwie lub adresie hosta; ID pozostaje dostępne w razie niejednoznaczności. Uprawnienia profilu są sprawdzane przy każdym wywołaniu; dostęp HTTP pozostaje wyłączony.')+html`<div class="two-columns"><section class="panel panel-pad"><h2>Klienci</h2><p>${data.clients.map(esc).join(' · ')}</p><p class="fine">Token jest pokazywany tylko raz. Przechowuj go w menedżerze sekretów klienta; eksport konfiguracji zawiera wyłącznie nazwę zmiennej środowiskowej.</p></section><section class="panel panel-pad"><h2>Granice dostępu</h2><p>Każdy grant ogranicza profile, narzędzia i czas dostępu. Operacje zapisu wymagają ponownego potwierdzenia hasłem i 2FA (jeśli aktywne). Usuwanie kontenerów wymaga oddzielnej zgody.</p></section></div><section class="panel"><div class="panel-header"><h2>Przydzielone dostępy</h2></div>${table(['Nazwa / tryb','Profile i narzędzia','Ważny do','Stan','Akcje'],grants)}</section>`;
 root.querySelector('#grant-create').onclick=()=>{
  const readTools=data.read_tools||Object.fromEntries(Object.entries(data.tools).filter(([key])=>!data.write_tools?.[key]));
  const writeTools=data.write_tools||Object.fromEntries(Object.entries(data.tools).filter(([key])=>!(key in readTools)));
  return openDialog('Nowy dostęp MCP',html`<div class="stack">${field('Nazwa dostępu','name','',{required:true})}<label>Klient<select name="client">${data.clients.map(v=>html`<option>${esc(v)}</option>`.toString()).join('')}</select></label><label>Ważność w dniach<input name="days" type="number" min="1" max="1000000" value="30"></label><label class="check"><input type="checkbox" name="unlimited">Bez limitu czasowego</label><h3>${t('Uprawnienia MCP')}</h3><div class="permission-grid"><label class="check"><input type="radio" name="mode" value="read" checked>${t('Tylko odczyt')}</label><label class="check"><input type="radio" name="mode" value="write">${t('Odczyt i modyfikacje')}</label></div>${notice('Wybierz konkretne narzędzia i profile. Uprawnienia profilu są sprawdzane przy każdym wywołaniu.')}<h3>Profile</h3><div class="permission-grid">${state.profiles.map(p=>{const address=p.host||p.endpoint||p.distro||p.context;return html`<label class="check"><input name="profiles" type="checkbox" value="${esc(p.id)}"><span>${esc(p.name)}${address?html`<span class="secondary">${esc(address)}</span>`:''}</span></label>`;}).join('')}</div><section data-read-tools><h3>Narzędzia tylko do odczytu</h3><div class="permission-grid">${Object.keys(readTools).map(key=>html`<label class="check"><input name="tools" type="checkbox" value="${esc(key)}" checked>${esc(key)}</label>`).join('')}</div></section><section data-write-tools hidden><h3>Narzędzia modyfikujące</h3><div class="permission-grid">${Object.keys(writeTools).map(key=>html`<label class="check"><input name="tools" type="checkbox" value="${esc(key)}">${esc(key)}</label>`).join('')}</div><label class="check"><input type="checkbox" name="allow_destructive">${t('Zezwól na usuwanie kontenerów')}</label>${notice('Utworzenie kontenera używa tylko nazwanych wolumenów, domyślnie publikuje porty na 127.0.0.1 i nie pozwala na privileged ani montowanie ścieżek hosta. Usunięcie kontenera nie usuwa wolumenów.','warning')}<div data-write-auth hidden>${accountFields()}</div></section></div>`,{submit:'Utwórz dostęp',onReady:form=>{const mode=[...form.querySelectorAll('[name=mode]')],write=form.querySelector('[data-write-tools]'),auth=form.querySelector('[data-write-auth]');const sync=()=>{const enabled=form.elements.mode.value==='write';write.hidden=!enabled;auth.hidden=!enabled;auth.querySelectorAll('input').forEach(input=>{input.disabled=!enabled;input.required=enabled&&input.name==='current_password';});};mode.forEach(item=>item.onchange=sync);sync();},onSubmit:async f=>{const result=await post('mcp/grants',{name:f.get('name'),client:f.get('client'),days:Number(f.get('days')),unlimited:f.has('unlimited'),mode:f.get('mode'),allow_destructive:f.has('allow_destructive'),profiles:f.getAll('profiles'),tools:f.getAll('tools'),current_password:f.get('current_password'),otp:f.get('otp')});setTimeout(()=>openDialog('Token — pokazany tylko raz',html`${notice('Zapisz token w menedżerze sekretów klienta. Nie będzie można ponownie go odczytać.','warning')}<pre class="inspect">${esc(result.token)}</pre><p class="fine">Eksport konfiguracji jest dostępny w tabeli i odwołuje się do zmiennej środowiskowej.</p>`),0);ctx.refresh();}});
 };
 root.querySelectorAll('[data-export]').forEach(b=>b.onclick=async()=>{
  try{
   const id=encodeURIComponent(b.dataset.export);
   const path='mcp/config/'+id,instructionsPath='mcp/instructions/'+id;
   const [data,instructions]=await Promise.all([api(path),api(instructionsPath)]);
   if(!ctx.valid())return;
   const config=typeof data.configuration==='string'?data.configuration:JSON.stringify(data.configuration,null,2);
   const codex=data.client==='OpenAI Codex';
   const guide='/docs/mcp?lang='+getLanguage();
   openDialog('Eksport AI / MCP',html`
    <h3>Konfiguracja MCP stdio</h3>
    <p><code>${esc(data.path)}</code></p>
    <pre class="inspect">${esc(config)}</pre>
    <div class="toolbar">
     <a class="button small" data-download-config href="/api/${path}?download=1">Pobierz konfigurację</a>
     ${codex?html`<a class="button small" href="/api/${path}?download=plugin">Pobierz wtyczkę Codex (ZIP)</a>`:''}
    </div>
    <p>Pliki eksportu są generowane bez wartości tokenu. Ustaw DCC_MCP_TOKEN w kliencie MCP lub w środowisku, z którego jest uruchamiany.</p>
    <h3 id="agent-instructions-title">Instrukcje agenta AI</h3>
    <p><code data-instruction-path>${esc(instructions.path)}</code></p>
    ${codex?html`<label>Wariant instrukcji w podglądzie i paczce ZIP
     <select data-variant>
      <option value="standard">Standardowy Codex — domyślnie</option>
      <option value="chatgpt-web">ChatGPT Web — połączenia pośrednie</option>
     </select>
    </label>`:''}
    <pre class="inspect mcp-agent-preview" data-agent-preview tabindex="0" aria-labelledby="agent-instructions-title">${esc(instructions.content)}</pre>
    <div class="toolbar">
     <a class="button small" data-download-agent href="/api/${instructionsPath}?download=1">${codex?t('Pobierz AGENTS.md'):t('Pobierz instrukcję')}</a>
     ${codex?html`<a class="button small" data-download-agent-web href="/api/${instructionsPath}?download=1&amp;variant=chatgpt-web">Pobierz AGENTS.md — ChatGPT Web</a>`:''}
     <button class="small" type="button" data-copy-instructions>Kopiuj instrukcje</button>
    </div>
    <p>${instructions.automatic
     ?t('Scal instrukcję w pokazanej ścieżce projektu. Kroki konfiguracji znajdziesz w README.md w paczce.')
     :t('Skopiuj instrukcję ręcznie do czatu lub instrukcji projektu. Kroki konfiguracji znajdziesz w README.md w paczce.')}</p>
    ${codex?html`<p>W zwykłym ChatGPT Web skopiuj instrukcję ręcznie do czatu lub instrukcji projektu. Czat nie wczytuje lokalnego AGENTS.md.</p>`:''}
    <div class="toolbar"><a class="button small primary" data-download-zip href="/api/mcp/bundle/${id}">Pobierz paczkę projektu (ZIP)</a></div>
    ${codex?html`<p>Instrukcja tokenu według systemu</p>
    <div class="toolbar">
     <a class="button small" href="${guide}#windows" target="_blank" rel="noopener">Windows</a>
     <a class="button small" href="${guide}#macos" target="_blank" rel="noopener">macOS</a>
     <a class="button small" href="${guide}#linux" target="_blank" rel="noopener">Linux</a>
    </div>`:''}
    ${codex?html`<details>
     <summary>Jak połączyć Codex i podać token</summary>
     <p>Aby udostępnić MCP w projekcie, rozpakuj paczkę projektu w jego katalogu głównym i otwórz zaufany projekt w Codex. Jeśli projekt ma już plik .codex/config.toml, dopisz do niego sekcję dcc z pobranego TOML.</p>
     <p>Aby dodać wtyczkę do katalogu Codex, rozpakuj ZIP wtyczki w osobnym folderze i uruchom w nim poniższe polecenie. Następnie zainstaluj DCC Web MCP ze źródła DCC Web.</p>
     <pre class="inspect">codex plugin marketplace add .</pre>
     <p>Jeśli eksport używa Dockera, wybierz kontekst, w którym działa kontener DCC Web. Zdalny host Docker wybierasz przez profil przydzielony tokenowi w DCC Web.</p>
     <p>Przy ręcznym dodawaniu serwera STDIO możesz podać DCC_MCP_TOKEN w polu Klucz i wkleić token w polu Wartość. Codex zapisze go jawnie w swojej konfiguracji. Pole Klucz dostępu zmiennej środowiskowej służy do podania samej nazwy zmiennej.</p>
     <p>Token uprawnia do wybranych profili i narzędzi. Może z niego korzystać każdy czat z dostępem do tego serwera MCP. Kliknij Odbierz dostęp w DCC Web, aby zablokować kolejne wywołania tym tokenem.</p>
     <a href="${guide}" target="_blank" rel="noopener">Instrukcja konfiguracji MCP</a>
    </details>`:''}
   `,{onReady(form){
    const preview=form.querySelector('[data-agent-preview]');
    const picker=form.querySelector('[data-variant]');
    const bundle=form.querySelector('[data-download-zip]');
    let variant='standard';
    form.querySelector('[data-copy-instructions]').onclick=async()=>{
     try{await copyText(preview.textContent);}
     catch(error){notify(error.message,'error');}
    };
    if(picker)picker.onchange=async()=>{
     const selected=picker.value;
     picker.disabled=true;
     try{
      const value=await api(instructionsPath+'?variant='+selected);
      preview.textContent=value.content;
      bundle.href='/api/mcp/bundle/'+id+'?variant='+selected;
      variant=selected;
     }catch(error){
      picker.value=variant;
      notify(error.message,'error');
     }finally{picker.disabled=false;}
    };
   }});
  }catch(e){notify(e.message,'error');}
 });
 root.querySelectorAll('[data-grant-action]').forEach(button=>button.onclick=async()=>{const action=button.dataset.grantAction,id=button.dataset.id,name=button.dataset.name;const config={
  pause:{path:'mcp/grants/'+id+'/pause',description:'Zatrzymanie tego grantu natychmiast odrzuci kolejne wywołania MCP. Później możesz wznowić dostęp.',submit:'Pauzuj dostęp'},
  resume:{path:'mcp/grants/'+id+'/resume',description:'Klient ponownie uzyska dostęp do przydzielonych profili i narzędzi.',submit:'Wznów dostęp'},
  revoke:{path:'mcp/grants/'+id,method:'DELETE',description:'Token zostanie trwale unieważniony. Tego dostępu nie będzie można wznowić.',submit:'Odbierz dostęp',danger:true},
  'delete-history':{path:'mcp/grants/'+id+'/history',method:'DELETE',description:'Grant zniknie z tej listy. Zapis odebrania dostępu pozostanie w dzienniku operacji.',submit:'Usuń z historii',danger:true}
 }[action];if(!config)return;try{await confirmGrantChange({id,name,action,...config},ctx);}catch(error){notify(error.message,'error');}});
}
