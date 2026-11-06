import{html,t}from'../i18n.js';
import{api}from'../api.js';
import{esc,openDialog,field,notice,notify}from'../ui.js';
import{accountFields}from'./profile_tools.js';

export async function publicMCP(ctx){
 const current=await api('mcp/http');if(!ctx.valid())return;
 return openDialog('Publiczny dostęp AI / MCP',html`<div class="stack">
  ${notice('Domyślnie wyłączony. Włączenie panelu HTTPS lub tunelu nie włącza MCP. Publiczna sesja wymaga tokena dostępu i osobnego zatwierdzenia kodem 2FA w DCC.')}
  <label class="check"><input name="enabled" type="checkbox" ${current.enabled?'checked':''}>Włącz publiczne MCP przez HTTPS</label>
  ${field('Publiczny adres HTTPS panelu','origin',current.origin||current.suggested_origin||'',{placeholder:'https://dcc.example.com'})}
  <p class="fine">Użyj rzeczywistej domeny tego DCC. W eksporcie wybierz później wariant publiczny przy konkretnym dostępie. Nie podawaj adresu zarządzanego urządzenia.</p>
  ${notice('Nowa sesja otwiera ekran DCC. Właściciel dostępu potwierdza hasło i nowy kod z istniejącego wpisu Google Authenticator. Sesja ma limit 15–60 minut i 10 minut bezczynności. Wyłączenie MCP odbierze aktywne sesje i zamknie terminale.','warning')}
  <label class="check"><input name="confirm_public" type="checkbox">Potwierdzam udostępnienie MCP i wymaganie 2FA nowych sesji.</label>
  ${accountFields()}
 </div>`,{submit:'Zapisz ustawienia',onSubmit:async f=>{
  await api('mcp/http',{method:'PUT',data:{enabled:f.has('enabled'),origin:f.get('origin'),confirm_public:f.has('confirm_public'),current_password:f.get('current_password'),otp:f.get('otp')}});
  notify('Ustawienia publicznego MCP zapisane');ctx.refresh();
 }});
}
