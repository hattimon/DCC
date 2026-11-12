// Trusted DCC document. Only this side knows the DCC CSRF token and session.
import{parse}from'./vendor/es-module-lexer.js';
const frame=document.querySelector('#panel-frame'),status=document.querySelector('#panel-status');
const endpoint=document.body.dataset.panelApi,service=document.body.dataset.serviceOrigin;
const csrf=document.querySelector('meta[name=csrf-token]').content;
const pl=document.documentElement.lang==='pl';
let currentPath='/',generation=0,port=null,stopped=false;
const streams=new Set();
const b64=bytes=>{let text='';for(let i=0;i<bytes.length;i+=32768)text+=String.fromCharCode(...bytes.subarray(i,i+32768));return btoa(text);};
const bytes=text=>Uint8Array.from(atob(text||''),c=>c.charCodeAt(0));
const text=value=>new TextDecoder().decode(bytes(value));
const dataURL=(value,type)=>'data:'+type+';base64,'+value;
async function api(action,data){
 const response=await fetch(endpoint+'/'+action,{method:data===undefined?'GET':'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:data===undefined?undefined:JSON.stringify(data)});
 const value=await response.json();
 if(!response.ok){if([401,403,404].includes(response.status))stop(value.error);throw Error(value.error||'Panel request failed');}
 return value;
}
function pathOf(input,base=currentPath){
 const value=new URL(input,new URL(base,service));
 if(!['http:','https:','ws:','wss:'].includes(value.protocol)||value.username||value.password||value.host!==new URL(service).host)throw Error(pl?'Zablokowano adres poza wybranym panelem':'Address outside this panel was blocked');
 return value.pathname+value.search;
}
async function request(path,options={}){return api('request',{path:pathOf(path),method:options.method||'GET',headers:options.headers||{},body:options.body||''});}
function stop(message){
 if(stopped)return;stopped=true;generation++;port?.close();frame.srcdoc='';document.body.classList.add('failed');
 status.textContent=message||(pl?'Sesja lub uprawnienia wygasły. Otwórz DCC Web i zaloguj się ponownie.':'Session or permissions expired. Open DCC Web and sign in again.');
 for(const stream of streams)api('live/'+stream+'/close',{}).catch(()=>{});streams.clear();
}
async function asset(url,base){const response=await request(pathOf(url,base));if(response.status>=400)throw Error('Panel resource: '+response.status);return response;}
function openingTag(source,name){
 const lower=source.toLowerCase(),needle='<'+name;let cursor=0,start;
 while((start=lower.indexOf(needle,cursor))>=0){
  const next=source[start+needle.length];cursor=start+needle.length;
  if(next!=='>'&&next!=='/'&&next!==undefined&&next.trim()!=='')continue;
  if(source.lastIndexOf('<!--',start)>source.lastIndexOf('-->',start))continue;
  let quote='';
  for(let i=start;i<source.length;i++){
   const char=source[i];
   if(quote){if(char===quote)quote='';continue;}
   if(char==='"'||char==="'"){quote=char;continue;}
   if(char==='>')return{start,end:i+1,value:source.slice(start,i+1)};
  }
 }
 return null;
}
function safeRootTag(source){
 const found=openingTag(source,'html');
 if(!found)return `<html lang="${document.documentElement.lang||'en'}">`;
 const holder=document.createElement('template');
 holder.innerHTML=found.value.replace(/^<html/i,'<span')+'</span>';
 const parsed=holder.content.firstElementChild;
 if(!parsed)return `<html lang="${document.documentElement.lang||'en'}">`;
 const lang=parsed.getAttribute('lang')||'';let valid=false;
 try{valid=!!lang&&Intl.getCanonicalLocales(lang).length===1;}catch{}
 if(!valid)parsed.setAttribute('lang',document.documentElement.lang||'en');
 const attributes=[...parsed.attributes].filter(attribute=>!attribute.name.toLowerCase().startsWith('on'))
  .map(attribute=>`${attribute.name}="${attribute.value.replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;')}"`);
 return `<html${attributes.length?' '+attributes.join(' '):''}>`;
}
async function css(source,base,depth=0){
 if(depth>4)throw Error('CSS import depth exceeded');
 const pattern=/url\(\s*(['"]?)([^)'"\s]+)\1\s*\)|@import\s+(['"])([^'"]+)\3\s*;/gi;
 let output='',end=0;
 for(const match of source.matchAll(pattern)){
  output+=source.slice(end,match.index);end=match.index+match[0].length;
  const url=match[2]||match[4];
  if(url.startsWith('data:')||url.startsWith('#')){output+=match[0];continue;}
  try{const result=await asset(url,base);output+=match[4]||result.headers['content-type']?.includes('text/css')?await css(text(result.body),pathOf(url,base),depth+1):'url("'+dataURL(result.body,result.headers['content-type']||'application/octet-stream')+'")';}
  catch{output+='url("data:,")';}
 }
 return output+source.slice(end);
}
const bridgeSource=await (await fetch('/static/panel_bridge.js',{credentials:'same-origin'})).text();
async function prepare(response){
 // Template parsing is inert, including images/frames. Never parse upstream
 // markup into a document that could initiate requests with DCC credentials.
 const source=text(response.body),rootTag=safeRootTag(source),bodyTag=openingTag(source,'body');
 const boundary='dcc-panel-body-'+crypto.randomUUID(),marker=`<!--${boundary}-->`;
 const marked=bodyTag?source.slice(0,bodyTag.end)+marker+source.slice(bodyTag.end):source;
 const template=document.createElement('template');template.innerHTML=marked;const doc=template.content;
 const base=response.path;
 doc.querySelectorAll('base,meta[http-equiv],iframe,object,embed').forEach(el=>el.remove());
 doc.querySelectorAll('[autofocus]').forEach(el=>el.removeAttribute('autofocus'));
 const modules={},importMap={};let moduleBytes=0,inlineIndex=0;
 for(const element of doc.querySelectorAll('script[type="importmap"]')){
  const map=JSON.parse(element.textContent);
  if(map.scopes&&Object.keys(map.scopes).length)throw Error('Scoped import maps require a dedicated panel origin');
  Object.assign(importMap,map.imports||{});element.remove();
 }
 function resolveModule(specifier,parent){
  if(!/^(\.\.?\/|\/|https?:\/\/)/.test(specifier)){
   const key=Object.keys(importMap).filter(k=>k===specifier||k.endsWith('/')&&specifier.startsWith(k)).sort((a,b)=>b.length-a.length)[0];
   if(!key)throw Error('Unmapped panel module: '+specifier);
   specifier=importMap[key]+(key.endsWith('/')?specifier.slice(key.length):'');parent=base;
  }
  return new URL(pathOf(specifier,parent),service).href;
 }
 async function compileModule(source,id){
  moduleBytes+=new TextEncoder().encode(source).length;
  if(Object.keys(modules).length>128||moduleBytes>4_000_000)throw Error('Panel module graph exceeds gateway limit');
  const [imports]=parse(source);let output=source;
  const replacements=[];
  for(const item of imports){
   if(item.d===-2){replacements.push([item.s,item.e,'({url:'+JSON.stringify(id)+'})']);continue;}
   if(!item.n)throw Error('Computed dynamic imports require a dedicated panel origin');
   const url=resolveModule(item.n,id);
   if(!Object.hasOwn(modules,url)){
    modules[url]='';const resource=await asset(url,base);modules[url]=await compileModule(text(resource.body),url);
   }
   replacements.push([item.s,item.e,item.d>=0?JSON.stringify(url):url]);
  }
  for(const [start,end,value] of replacements.sort((a,b)=>b[0]-a[0]))output=output.slice(0,start)+value+output.slice(end);
  return output;
 }
 for(const element of doc.querySelectorAll('script[type="module"]')){
  const source=element.getAttribute('src');
  const id=source?resolveModule(source,base):new URL('/__dcc_inline_'+(++inlineIndex)+'.mjs',service).href;
  if(!Object.hasOwn(modules,id)){
   modules[id]='';modules[id]=await compileModule(source?text((await asset(source,base)).body):element.textContent,id);
  }
  element.removeAttribute('src');element.removeAttribute('integrity');element.removeAttribute('crossorigin');
  element.textContent='import '+JSON.stringify(id)+';';
 }
 let count=0;
 for(const element of doc.querySelectorAll('script[src],link[href],img[src],source[src],video[poster],audio[src]')){
  if(++count>160)throw Error('Panel resource limit exceeded');
  const attr=element.hasAttribute('src')?'src':element.hasAttribute('poster')?'poster':'href';
  const url=element.getAttribute(attr);if(!url||url.startsWith('data:'))continue;
  element.removeAttribute('integrity');element.removeAttribute('crossorigin');element.removeAttribute('srcset');
  if(element.tagName==='LINK'&&!['stylesheet','icon','shortcut icon'].includes(element.rel)){element.remove();continue;}
  try{
   const resource=await asset(url,base);
   if(element.tagName==='LINK'&&element.rel==='stylesheet'){
    const style=document.createElement('style');style.textContent=await css(text(resource.body),pathOf(url,base));element.replaceWith(style);
   }else element.setAttribute(attr,dataURL(resource.body,element.tagName==='SCRIPT'?'text/javascript':resource.headers['content-type']||'application/octet-stream'));
  }catch(error){if(element.tagName==='SCRIPT')throw error;element.removeAttribute(attr);status.textContent=error.message;}
 }
 for(const style of doc.querySelectorAll('style'))style.textContent=await css(style.textContent,base);
 for(const element of doc.querySelectorAll('[style]'))element.setAttribute('style',await css(element.getAttribute('style'),base));
 doc.querySelectorAll('[srcset]').forEach(el=>el.removeAttribute('srcset'));
 const config=document.createElement('script');config.id='dcc-panel-config';config.type='application/json';
 config.textContent=JSON.stringify({origin:service,path:base,modules,cookies:response.cookies||''}).replaceAll('<','\\u003c');
 const bootstrap=document.createElement('script');bootstrap.src=dataURL(b64(new TextEncoder().encode(bridgeSource)),'text/javascript');
 const policy=document.createElement('meta');policy.httpEquiv='Content-Security-Policy';
 policy.content="default-src 'none'; script-src data: blob: 'unsafe-inline'; style-src 'unsafe-inline' data: blob:; img-src data: blob:; font-src data: blob:; media-src data: blob:; connect-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'";
 doc.prepend(policy,config,bootstrap);
 const serialized=template.innerHTML,index=serialized.indexOf(marker);
 if(index<0){
  // A fragment without an explicit <body> has no boundary marker. Keep the
  // security policy in <head>; placing it in <body> causes browsers to ignore it.
  policy.remove();config.remove();bootstrap.remove();
  return '<!doctype html>'+rootTag+'<head>'+policy.outerHTML+config.outerHTML+bootstrap.outerHTML+'</head><body>'+template.innerHTML+'</body></html>';
 }
 const head=serialized.slice(0,index),body=serialized.slice(index+marker.length);
 const safeBodyTag=bodyTag?.value||'<body>';
 return '<!doctype html>'+rootTag+'<head>'+head+'</head>'+safeBodyTag+body+'</body></html>';
}
async function navigate(path='/',options={}){
 const mine=++generation;
 for(const stream of streams)api('live/'+stream+'/close',{}).catch(()=>{});streams.clear();
 const response=await request(path,options);
 if(response.stream)throw Error('Cannot navigate to a live data stream');
 if(!response.headers['content-type']?.includes('text/html')){
  if(response.headers['content-disposition']?.includes('attachment')){
   const a=document.createElement('a');a.href=dataURL(response.body,response.headers['content-type']||'application/octet-stream');a.download=response.headers['content-disposition'].match(/filename="?([^";]+)/)?.[1]||'download';a.click();return;
  }
  response.body=b64(new TextEncoder().encode('<pre>'+text(response.body).replaceAll('&','&amp;').replaceAll('<','&lt;')+'</pre>'));
 }
 currentPath=response.path;
 const html=await prepare(response);if(stopped||mine!==generation)return;
 port?.close();const channel=new MessageChannel();port=channel.port1;
 port.onmessage=async({data})=>{
  if(stopped||mine!==generation||!data||!Number.isSafeInteger(data.id))return;
  try{
   let result;
   if(data.type==='request')result=await request(pathOf(data.path,currentPath),data);
   else if(data.type==='asset'){
    result=await asset(data.path,currentPath);
    if(result.headers['content-type']?.includes('text/css'))result.body=b64(new TextEncoder().encode(await css(text(result.body),pathOf(data.path,currentPath))));
   }
   else if(data.type==='navigate'){await navigate(pathOf(data.path,currentPath),data);return;}
   else if(data.type==='ws')result=await api('ws',{path:pathOf(data.path,currentPath),protocols:data.protocols||[]});
   else if(data.type==='cookie')result=await api('cookie',{path:currentPath,value:String(data.value)});
   else if(data.type==='read'||data.type==='send'||data.type==='close'){
    if(!streams.has(data.stream))throw Error('Unknown panel connection');
    result=await api('live/'+encodeURIComponent(data.stream)+'/'+data.type,data.type==='send'?{data:data.data,binary:!!data.binary}:{});
    if(data.type==='close')streams.delete(data.stream);
   }else if(data.type==='download'){
    const response=await request(pathOf(data.path,currentPath));const a=document.createElement('a');a.href=dataURL(response.body,response.headers['content-type']||'application/octet-stream');a.download=String(data.name||'download').replace(/[\\/]/g,'_');a.click();result={};
   }else throw Error('Unknown panel operation');
   if(result.stream)streams.add(result.stream);
   port?.postMessage({id:data.id,result});
  }catch(error){port?.postMessage({id:data.id,error:error.message});}
 };
 frame.onload=()=>{if(mine===generation&&!stopped)frame.contentWindow.postMessage({type:'dcc-panel-init'},'*',[channel.port2]);};
 frame.srcdoc=html;status.textContent=pl?'Połączono przez DCC Web':'Connected through DCC Web';
}
document.querySelector('#panel-reload').onclick=()=>location.reload();
const timer=setInterval(async()=>{try{await api('status');}catch(error){stop(error.message);clearInterval(timer);}},1000);
window.addEventListener('pagehide',()=>{for(const stream of streams)fetch(endpoint+'/live/'+stream+'/close',{method:'POST',keepalive:true,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:'{}'}).catch(()=>{});});
try{await navigate();}catch(error){stop(error.message);}
