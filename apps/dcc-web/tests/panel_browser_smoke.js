// Pass this function to Playwright CLI run-code with panel_browser_fixture.py
// running. It uses only synthetic credentials and the loopback fixture ports.
async page=>{
 const origin='http://127.0.0.1:18879',results={};
 const ensure=(test,message)=>{if(!test)throw Error(message);};
 await page.goto(origin+'/login');
 await page.getByRole('textbox',{name:'Username'}).fill('fixture-admin');
 await page.getByRole('textbox',{name:'Password',exact:true}).fill('Fixture-pass-4433');
 await page.getByRole('button',{name:'Open DCC Web →'}).click();
 const entries=await page.evaluate(async()=> (await (await fetch('/api/containers')).json()).containers);
 const address=c=>origin+'/panels/view/local/'+c.ID+'/'+c.PanelLinks[0].panel_id;
 await page.goto(address(entries[0]));
 const child=()=>page.frames().find(f=>f!==page.mainFrame());
 await page.frameLocator('#panel-frame').locator('#ws').getByText('live-echo',{exact:true}).waitFor();
 await child().waitForFunction(()=>document.querySelector('#sse')?.textContent.startsWith('tick-'));
 results.live=await child().evaluate(()=>({api:document.querySelector('#api').textContent,ws:document.querySelector('#ws').textContent,sse:document.querySelector('#sse').textContent,isolation:document.querySelector('#isolation').textContent,image:document.querySelector('img').naturalWidth,background:getComputedStyle(document.body).backgroundColor,lang:document.documentElement.lang,theme:document.documentElement.dataset.theme,bodyAttribute:document.body.dataset.fixtureBody}));
 ensure(results.live.api==='/echo'&&results.live.ws==='live-echo'&&results.live.isolation==='isolated'&&results.live.image===24&&results.live.lang==='pl'&&results.live.theme==='fixture-theme'&&results.live.bodyAttribute==='preserved','Live panel, document attributes or isolation failed');
 results.live.cspHead=await child().evaluate(()=>document.querySelector('meta[http-equiv="Content-Security-Policy"]')?.parentElement===document.head);
 ensure(results.live.cspHead,'The live panel CSP is outside <head>');
 results.upload=await child().evaluate(async()=>{
  document.cookie='xsrf=browser-fixture; Path=/';
  const received=await (await fetch('/echo')).json();
  const data=new FormData();data.append('file',new Blob(['fixture-file-content']),'fixture.txt');
  const uploaded=await (await fetch('/upload',{method:'POST',body:data})).json();
  return {serviceCookie:received.cookie.includes('xsrf=browser-fixture'),dccCookieLeaked:received.cookie.includes('dcc_web_session'),multipart:uploaded.type.startsWith('multipart/form-data; boundary='),file:atob(uploaded.body).includes('fixture-file-content')};
 });
 ensure(results.upload.serviceCookie&&!results.upload.dccCookieLeaked&&results.upload.multipart&&results.upload.file,'Cookie or multipart upload failed');
 await page.screenshot({path:'output/playwright/panels-live.png',fullPage:true});
 await page.frameLocator('#panel-frame').getByRole('button',{name:'Submit panel'}).click();
 await page.frameLocator('#panel-frame').locator('#form-result').waitFor();results.form=true;
 await child().evaluate(()=>{const a=document.createElement('a');a.href='/modules';document.body.append(a);a.click();});
 await page.frameLocator('#panel-frame').getByRole('heading',{name:'ESM 42 dynamic',exact:true}).waitFor();
 await child().waitForFunction(()=>document.querySelector('#module-image')?.naturalWidth===24);
 results.modules={static:true,circular:true,dynamic:true,importMeta:true,dynamicImage:true,cspHead:await child().evaluate(()=>document.querySelector('meta[http-equiv="Content-Security-Policy"]')?.parentElement===document.head)};
 ensure(results.modules.cspHead,'The module panel CSP is outside <head>');
 await page.screenshot({path:'output/playwright/panels-modules.png',fullPage:true});
 await page.goto(address(entries[1]));
 const updaterFrame=()=>page.frames().find(f=>f!==page.mainFrame());
 await page.frameLocator('#panel-frame').getByRole('textbox',{name:/^(Panel password|Hasło panelu)$/}).fill('Fixture-updater-4433');
 await page.frameLocator('#panel-frame').getByRole('button',{name:/^(Sign in|Zaloguj)$/}).click();
 await page.frameLocator('#panel-frame').getByRole('heading',{name:/^(Container updates|Aktualizacje kontenerów)$/}).waitFor();
 await page.frameLocator('#panel-frame').locator('#rows tr .name').getByText('fixture-container',{exact:true}).waitFor();
 results.updater=await updaterFrame().evaluate(()=>({lang:document.documentElement.lang,theme:document.documentElement.dataset.theme,container:document.querySelector('#rows .name')?.textContent,numberFormat:new Intl.NumberFormat(document.documentElement.lang).format(1234.5)}));
 ensure(results.updater.lang==='pl'&&results.updater.theme==='red'&&results.updater.container==='fixture-container','Updater did not retain document language/theme or render the scanned container');
 results.updater.cspHead=await updaterFrame().evaluate(()=>document.querySelector('meta[http-equiv="Content-Security-Policy"]')?.parentElement===document.head);
 ensure(results.updater.cspHead,'The updater panel CSP is outside <head>');
 await page.frameLocator('#panel-frame').getByRole('tab',{name:/^(Reports|Raporty)$/}).click();
 results.updater.reports=(await page.frameLocator('#panel-frame').getByRole('tab',{name:/^(Reports|Raporty)$/}).getAttribute('aria-selected'))==='true';
 ensure(results.updater.reports,'Updater report navigation failed');
 await page.screenshot({path:'output/playwright/panels-updater.png',fullPage:true});
 await page.goto(address(entries[0]));
 await page.frameLocator('#panel-frame').locator('#ws').getByText('live-echo',{exact:true}).waitFor();
 await page.evaluate(async()=>{const csrf=document.querySelector('meta[name=csrf-token]').content;const result=await fetch('/api/logout',{method:'POST',headers:{'X-CSRF-Token':csrf,'Content-Type':'application/json'},body:'{}'});if(!result.ok)throw Error('Logout failed');});
 await page.locator('body.failed').waitFor();
 results.revoked=await page.locator('#panel-frame').getAttribute('srcdoc')==='';
 ensure(results.revoked,'The open panel was not cleared after logout');
 await page.screenshot({path:'output/playwright/panels-session-revoked.png',fullPage:true});
 return results;
}
