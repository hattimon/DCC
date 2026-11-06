import{html,t}from'../i18n.js';
import{api,state,post}from'../api.js';
import{esc,heading,button,table,openDialog,notice,notify,status}from'../ui.js';
import{grantForm}from'./mcp_grant_form.js';
import{exportGrant}from'./mcp_export.js';
import{publicMCP}from'./mcp_public.js';

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
 const grants=data.grants.map(v=>html`<tr><td>${esc(v.name)}<span class="secondary">${esc(v.client)} · ${v.mode==='write'?t('Odczyt i modyfikacje'):t('Tylko odczyt')}</span></td><td class="wrap">${v.profiles.map(profileLabel).join('')}<span class="secondary">${v.tools.length} ${t('narzędzi')}</span></td><td>${esc(v.expires===null?t('Bez limitu czasowego'):new Date(v.expires*1000).toLocaleDateString())}</td><td>${!v.revoked&&expired(v)?esc(t('Wygasł')):status(v.revoked?'revoked':v.paused?'paused':'running')}</td><td>${v.revoked?html`<button class="small quiet danger" data-grant-action="delete-history" data-id="${esc(v.id)}" data-name="${esc(v.name)}">Usuń z historii</button>`:html`<button class="small quiet" data-grant-edit="${esc(v.id)}">Edytuj</button>${v.paused||expired(v)?'':html`<button class="small quiet" data-export="${esc(v.id)}">Eksport</button>`}${v.paused?html`<button class="small quiet" data-grant-action="resume" data-id="${esc(v.id)}" data-name="${esc(v.name)}">Wznów dostęp</button>`:html`<button class="small quiet" data-grant-action="pause" data-id="${esc(v.id)}" data-name="${esc(v.name)}">Pauzuj dostęp</button>`}<button class="small quiet danger" data-grant-action="revoke" data-id="${esc(v.id)}" data-name="${esc(v.name)}">Odbierz dostęp</button>`}</td></tr>`);
 root.innerHTML=heading('AI / MCP','Jawnie ograniczony dostęp MCP do wybranych profili i narzędzi.',button('Publiczny dostęp AI / MCP','mcp-public')+button('+ Nowy dostęp','grant-create','primary'))+notice('Działa transport stdio. Dla każdego dostępu wybierz tryb tylko do odczytu albo ograniczone modyfikacje. W Codexie profil wybierzesz po nazwie lub adresie hosta; ID pozostaje dostępne w razie niejednoznaczności. Uprawnienia profilu są sprawdzane przy każdym wywołaniu. Publiczne MCP jest osobną, opcjonalną funkcją z potwierdzaniem nowych sesji przez 2FA.')+html`<div class="two-columns"><section class="panel panel-pad"><h2>Klienci</h2><p>${data.clients.map(esc).join(' · ')}</p><p class="fine">Token jest pokazywany tylko raz. Przechowuj go w menedżerze sekretów klienta; eksport konfiguracji zawiera wyłącznie nazwę zmiennej środowiskowej.</p></section><section class="panel panel-pad"><h2>Granice dostępu</h2><p>Każdy grant ogranicza profile, narzędzia i czas dostępu. Operacje zapisu wymagają ponownego potwierdzenia hasłem i 2FA (jeśli aktywne). Usuwanie kontenerów wymaga oddzielnej zgody.</p></section></div><section class="panel"><div class="panel-header"><h2>Przydzielone dostępy</h2></div>${table(['Nazwa / tryb','Profile i narzędzia','Ważny do','Stan','Akcje'],grants)}</section>`;
 root.querySelector('#mcp-public').onclick=()=>publicMCP(ctx).catch(e=>notify(e.message,'error'));
 root.querySelector('#grant-create').onclick=()=>grantForm(data,ctx);
 root.querySelectorAll('[data-grant-edit]').forEach(b=>b.onclick=()=>grantForm(data,ctx,data.grants.find(v=>v.id===b.dataset.grantEdit)));
 root.querySelectorAll('[data-export]').forEach(b=>b.onclick=()=>exportGrant(b.dataset.export,ctx).catch(e=>notify(e.message,'error')));
 root.querySelectorAll('[data-grant-action]').forEach(button=>button.onclick=async()=>{const action=button.dataset.grantAction,id=button.dataset.id,name=button.dataset.name;const config={
  pause:{path:'mcp/grants/'+id+'/pause',description:'Zatrzymanie tego grantu natychmiast odrzuci kolejne wywołania MCP. Później możesz wznowić dostęp.',submit:'Pauzuj dostęp'},
  resume:{path:'mcp/grants/'+id+'/resume',description:'Klient ponownie uzyska dostęp do przydzielonych profili i narzędzi.',submit:'Wznów dostęp'},
  revoke:{path:'mcp/grants/'+id,method:'DELETE',description:'Token zostanie trwale unieważniony. Tego dostępu nie będzie można wznowić.',submit:'Odbierz dostęp',danger:true},
  'delete-history':{path:'mcp/grants/'+id+'/history',method:'DELETE',description:'Grant zniknie z tej listy. Zapis odebrania dostępu pozostanie w dzienniku operacji.',submit:'Usuń z historii',danger:true}
 }[action];if(!config)return;try{await confirmGrantChange({id,name,action,...config},ctx);}catch(error){notify(error.message,'error');}});
}
