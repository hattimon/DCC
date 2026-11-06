import{html,t,getLanguage}from'../i18n.js';
import{api}from'../api.js';
import{esc,openDialog,notice,notify,copyText}from'../ui.js';

export async function exportGrant(id,ctx){
 const path='mcp/config/'+encodeURIComponent(id),instructionsPath='mcp/instructions/'+encodeURIComponent(id);
 const [data,instructions]=await Promise.all([api(path),api(instructionsPath)]);if(!ctx.valid())return;
 const codex=data.client==='OpenAI Codex',platform=/Win/i.test(navigator.platform)?'windows':/Mac/i.test(navigator.platform)?'macos':'linux';
 return openDialog('Eksport AI / MCP',html`
  ${notice('ZIP nigdy nie zawiera tokena. Wartość jest widoczna tylko przy utworzeniu dostępu; DCC zapisuje wyłącznie jej skrót. Zmiana zakresu zachowuje aktywny token. Po utracie tokena utwórz nowy dostęp.','warning')}
  <label>System komputera z klientem MCP<select data-platform><option value="windows" ${platform==='windows'?'selected':''}>Windows</option><option value="linux" ${platform==='linux'?'selected':''}>Linux</option><option value="macos" ${platform==='macos'?'selected':''}>macOS</option></select></label>
  <label>Sposób połączenia<select data-transport><option value="stdio">Lokalne MCP — stdio</option><option value="https" ${!codex||!data.public_enabled||!data.grant_public?'disabled':''}>Publiczne HTTPS — token i sesja 2FA</option></select></label>
  ${!data.public_enabled||!data.grant_public?notice('Aby wybrać publiczne HTTPS, administrator musi włączyć Publiczny dostęp AI / MCP i zezwolić na publiczne sesje w tym dostępie.'):!codex?notice('Eksport publicznego HTTPS jest dostępny dla OpenAI Codex. Ten klient korzysta z wariantu stdio.'):''}
  <p class="fine">System klienta jest niezależny od systemu urządzenia. Instrukcja zawiera znane dane profili i osobny zakres terminala.</p>
  <h3>Instalacja krok po kroku</h3>
  <ol><li>Wybierz system klienta i pobierz paczkę projektu ZIP.</li><li>Rozpakuj w głównym katalogu projektu. Jeśli AGENTS.md lub konfiguracja już istnieją, rozpakuj osobno i scal pliki bez zastępowania własnych ustawień.</li><li data-runtime-step>Sprawdź wymagany runtime opisany w README z paczki. Adres publicznego panelu nie jest endpointem HTTP MCP.</li><li>Jeśli DCC_MCP_TOKEN jest już w środowisku, zachowaj ją. Zamknij całkowicie klienta i uruchom go ponownie, aby odziedziczył aktualną zmienną. Nie wklejaj sekretu do czatu.</li><li data-auth-step>Otwórz zaufany projekt i nowy czat. Poproś o listę kontenerów przyznanego profilu przez DCC MCP. Udany odczyt potwierdza połączenie.</li></ol>
  <p>Po zmianie zakresu: połącz MCP ponownie i scal nowy eksport instrukcji. Nie musisz zmieniać tokena.</p>
  <div class="toolbar"><a class="button primary" data-download-zip>Pobierz paczkę projektu (ZIP)</a></div>
  <p class="fine">Paczka zawiera konfigurację, instrukcje agenta i README dla wybranej platformy. Nie instaluje ani nie nadpisuje plików automatycznie.</p>
  <details><summary>Podgląd i osobne pliki</summary>
   <h3>Konfiguracja MCP</h3><p><code>${esc(data.path)}</code></p><pre class="inspect" data-config-preview></pre>
   <a class="button small" data-download-config>Pobierz konfigurację</a>
   ${codex?html`<label>Wariant instrukcji w podglądzie i paczce ZIP<select data-variant><option value="standard">Standardowy Codex — domyślnie</option><option value="chatgpt-web">ChatGPT Web — wymagane DCC MCP</option></select></label>`:''}
   <h3 id="agent-instructions-title">Instrukcje agenta AI</h3><p><code data-instruction-path>${esc(instructions.path)}</code></p>
   <pre class="inspect mcp-agent-preview" data-agent-preview tabindex="0" aria-labelledby="agent-instructions-title">${esc(instructions.content)}</pre>
   <div class="toolbar"><a class="button small" data-download-agent>${codex?t('Pobierz AGENTS.md'):t('Pobierz instrukcję')}</a><button class="small" type="button" data-copy-instructions>Kopiuj instrukcje</button></div>
  </details>
  ${codex?html`<details data-plugin-section><summary>Alternatywa: wtyczka Codex</summary><p>Użyj zamiast konfiguracji projektu. Rozpakuj w osobnym folderze, uruchom codex plugin marketplace add . i zainstaluj DCC Web MCP z tego źródła. Wtyczka także wymaga DCC_MCP_TOKEN i nie zawiera sekretu.</p><a class="button small" data-plugin>Pobierz wtyczkę Codex (ZIP)</a></details>`:''}
  <a href="/docs/mcp?lang=${getLanguage()}" target="_blank" rel="noopener">Instrukcja konfiguracji MCP</a>
 `,{onReady(form){
  const platformPicker=form.querySelector('[data-platform]'),transportPicker=form.querySelector('[data-transport]'),variantPicker=form.querySelector('[data-variant]'),preview=form.querySelector('[data-agent-preview]');
  const update=async()=>{
   const params=new URLSearchParams({platform:platformPicker.value,variant:variantPicker?.value||'standard',transport:transportPicker.value});
   const links=[...form.querySelectorAll('a[data-download-zip],a[data-download-config],a[data-download-agent],a[data-plugin]')];
   links.forEach(a=>a.removeAttribute('href'));platformPicker.disabled=transportPicker.disabled=true;if(variantPicker)variantPicker.disabled=true;
   try{
    const [configuration,instruction]=await Promise.all([api(path+'?'+params),api(instructionsPath+'?'+params)]);
    form.querySelector('[data-config-preview]').textContent=typeof configuration.configuration==='string'?configuration.configuration:JSON.stringify(configuration.configuration,null,2);
    preview.textContent=instruction.content;
    form.querySelector('[data-download-zip]').href='/api/mcp/bundle/'+encodeURIComponent(id)+'?'+params;
    form.querySelector('[data-download-config]').href='/api/'+path+'?'+params+'&download=1';
    form.querySelector('[data-download-agent]').href='/api/'+instructionsPath+'?'+params+'&download=1';
    const publicAccess=transportPicker.value==='https',pluginSection=form.querySelector('[data-plugin-section]');if(pluginSection)pluginSection.hidden=publicAccess;
    const plugin=form.querySelector('[data-plugin]');if(plugin&&!publicAccess)plugin.href='/api/'+path+'?'+params+'&download=plugin';
    form.querySelector('[data-runtime-step]').textContent=t(publicAccess?'Publiczne HTTPS: nie potrzebujesz DCC Desktop, Dockera ani SSH. Paczka wskazuje endpoint konkretnego dostępu na domenie DCC.':'Sprawdź wymagany runtime opisany w README z paczki. Adres publicznego panelu nie jest endpointem HTTP MCP.');
    form.querySelector('[data-auth-step]').textContent=t(publicAccess?'Otwórz zaufany projekt. W MCP wybierz dcc → Authenticate lub uruchom codex mcp login dcc. Na ekranie DCC potwierdź właściwy dostęp hasłem i świeżym kodem z istniejącego Authenticatora. Potem poproś w nowym czacie o listę kontenerów przez MCP.':'Otwórz zaufany projekt i nowy czat. Poproś o listę kontenerów przyznanego profilu przez DCC MCP. Udany odczyt potwierdza połączenie.');
   }catch(error){notify(error.message,'error');}
   finally{platformPicker.disabled=transportPicker.disabled=false;if(variantPicker)variantPicker.disabled=false;}
  };
  form.querySelector('[data-copy-instructions]').onclick=()=>copyText(preview.textContent).catch(e=>notify(e.message,'error'));
  platformPicker.onchange=transportPicker.onchange=update;if(variantPicker)variantPicker.onchange=update;update();
 }});
}
