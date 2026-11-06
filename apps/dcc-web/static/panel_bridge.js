// This code executes only inside the opaque-origin sandbox. It has no DCC
// token, cookie, storage or API access. The parent fixes the destination panel.
(()=>{
 'use strict';
 const config=JSON.parse(document.getElementById('dcc-panel-config').textContent);
 const imports={};
 for(const [id,source] of Object.entries(config.modules||{}))imports[id]=URL.createObjectURL(new Blob([source],{type:'text/javascript'}));
 if(Object.keys(imports).length){const map=document.createElement('script');map.type='importmap';map.textContent=JSON.stringify({imports});document.head.append(map);}
 let port,next=0;const pending=new Map();
 let cookies=config.cookies||'',cookieWrite=Promise.resolve();
 let activate;const ready=new Promise(resolve=>activate=resolve);
 window.addEventListener('message',function init(event){
  if(event.source!==parent||event.data?.type!=='dcc-panel-init'||!event.ports[0])return;
  window.removeEventListener('message',init);port=event.ports[0];
  port.onmessage=({data})=>{const item=pending.get(data.id);if(!item)return;pending.delete(data.id);data.error?item.reject(Error(data.error)):item.resolve(data.result);};
  activate();
 });
 async function rpc(type,values={}){await ready;return new Promise((resolve,reject)=>{const id=++next;pending.set(id,{resolve,reject});port.postMessage({type,id,...values});});}
 function encode(value){const bytes=new Uint8Array(value);let out='';for(let i=0;i<bytes.length;i+=32768)out+=String.fromCharCode(...bytes.subarray(i,i+32768));return btoa(out);}
 const decode=value=>Uint8Array.from(atob(value||''),c=>c.charCodeAt(0));
 function path(input){const url=new URL(input,new URL(config.path,config.origin));if(url.host!==new URL(config.origin).host||!['http:','https:','ws:','wss:'].includes(url.protocol))throw Error('Address outside this panel was blocked');return url.pathname+url.search;}
 async function options(init={}){
  const result={method:(init.method||'GET').toUpperCase(),headers:Object.fromEntries(new Headers(init.headers||{}))};
  if(init.body!=null){const request=new Request(config.origin,{method:result.method,headers:result.headers,body:init.body});result.headers=Object.fromEntries(request.headers);result.body=encode(await request.arrayBuffer());}
  return result;
 }
 window.fetch=async(input,init={})=>{
  await cookieWrite;
  const source=input instanceof Request?input.url:input;
  if(input instanceof Request){init={method:input.method,headers:input.headers,...init};if(!['GET','HEAD'].includes(input.method)&&init.body===undefined)init.body=await input.clone().arrayBuffer();}
  if(init.signal?.aborted)throw new DOMException('Aborted','AbortError');
  const value=await rpc('request',{path:path(String(source)),...await options(init)});
  if(typeof value.cookies==='string')cookies=value.cookies;
  if(value.stream)throw Error('Use EventSource for panel event streams');
  const response=new Response([101,204,205,304].includes(value.status)?null:decode(value.body),{status:value.status,headers:value.headers});
  Object.defineProperty(response,'url',{value:config.origin+value.path});return response;
 };
 class PanelXHR extends EventTarget{
  constructor(){super();this.readyState=0;this.status=0;this.responseType='';this.responseText='';this.response=null;this.headers={};this.upload=new EventTarget();}
  emit(name){const event=new Event(name);this.dispatchEvent(event);this['on'+name]?.(event);}
  open(method,url,async=true){if(!async)throw Error('Synchronous XHR is unsupported in the panel sandbox');this.method=method;this.url=url;this.readyState=1;this.emit('readystatechange');}
  setRequestHeader(k,v){this.headers[k]=v;}
  getResponseHeader(k){return this.received?.get(k)||null;}
  getAllResponseHeaders(){return [...(this.received||[])].map(([k,v])=>k+': '+v).join('\r\n');}
  overrideMimeType(){}
  abort(){this.cancelled=true;this.emit('abort');}
  async send(body){try{this.emit('loadstart');const value=await fetch(this.url,{method:this.method,headers:this.headers,body});if(this.cancelled)return;this.status=value.status;this.statusText=value.statusText;this.responseURL=value.url;this.received=value.headers;this.readyState=2;this.emit('readystatechange');const bytes=await value.arrayBuffer();this.responseText=new TextDecoder().decode(bytes);this.response=this.responseType==='arraybuffer'?bytes:this.responseType==='blob'?new Blob([bytes],{type:value.headers.get('content-type')}):this.responseType==='json'?JSON.parse(this.responseText):this.responseText;this.readyState=4;this.emit('readystatechange');this.emit('load');}catch{this.emit('error');}finally{this.emit('loadend');}}
 }
 window.XMLHttpRequest=PanelXHR;
 class PanelSocket extends EventTarget{
  static CONNECTING=0;static OPEN=1;static CLOSING=2;static CLOSED=3;
  constructor(url,protocols=[]){super();this.url=String(url);this.readyState=0;this.binaryType='blob';this.bufferedAmount=0;this.protocol='';this.extensions='';this.chain=Promise.resolve();this.start(url,typeof protocols==='string'?[protocols]:protocols);}
  emit(name,event=new Event(name)){this.dispatchEvent(event);this['on'+name]?.(event);}
  async start(url,protocols){try{const result=await rpc('ws',{path:path(String(url)),protocols});this.stream=result.stream;this.protocol=result.protocol;if(this.readyState===2){await rpc('close',{stream:this.stream});return this.finish(1000);}this.readyState=1;this.emit('open');while(this.readyState===1){const value=await rpc('read',{stream:this.stream});for(const item of value.events){const bytes=decode(item.data),data=item.binary?(this.binaryType==='arraybuffer'?bytes.buffer:new Blob([bytes])):new TextDecoder().decode(bytes);this.emit('message',new MessageEvent('message',{data}));}if(value.closed){this.finish(1006);break;}await new Promise(r=>setTimeout(r,150));}}catch{this.emit('error');this.finish(1006);}}
  send(value){if(this.readyState!==1)throw new DOMException('WebSocket is not open','InvalidStateError');this.chain=this.chain.then(async()=>{const binary=typeof value!=='string';const buffer=value instanceof Blob?await value.arrayBuffer():binary?value:new TextEncoder().encode(value);const raw=encode(buffer);this.bufferedAmount+=raw.length;try{await rpc('send',{stream:this.stream,data:raw,binary});}finally{this.bufferedAmount-=raw.length;}}).catch(()=>{this.emit('error');this.close();});}
  finish(code){if(this.readyState===3)return;this.readyState=3;this.emit('close',new CloseEvent('close',{code,wasClean:code===1000}));}
  close(){if(this.readyState>=2)return;this.readyState=2;if(this.stream)rpc('close',{stream:this.stream}).finally(()=>this.finish(1000));}
 }
 for(const name of ['CONNECTING','OPEN','CLOSING','CLOSED'])PanelSocket.prototype[name]=PanelSocket[name];
 window.WebSocket=PanelSocket;
 class PanelEvents extends EventTarget{
  static CONNECTING=0;static OPEN=1;static CLOSED=2;
  constructor(url,opts={}){super();this.url=String(url);this.withCredentials=!!opts.withCredentials;this.readyState=0;this.start();}
  emit(name,event=new Event(name)){this.dispatchEvent(event);this['on'+name]?.(event);}
  async start(){try{const response=await rpc('request',{path:path(this.url),headers:{accept:'text/event-stream'}});if(!response.stream)throw Error('Not an event stream');this.stream=response.stream;if(this.readyState===2){rpc('close',{stream:this.stream});return;}this.readyState=1;this.emit('open');const decoder=new TextDecoder();let buffer='',id='';while(this.readyState===1){const value=await rpc('read',{stream:this.stream});for(const item of value.events){buffer+=decoder.decode(decode(item.data),{stream:true}).replaceAll('\r\n','\n');let index;while((index=buffer.indexOf('\n\n'))>=0){const event=buffer.slice(0,index);buffer=buffer.slice(index+2);let type='message',data=[];for(const line of event.split('\n')){if(line.startsWith('event:'))type=line.slice(6).trim();if(line.startsWith('data:'))data.push(line.slice(5).replace(/^ /,''));if(line.startsWith('id:'))id=line.slice(3).trim();}if(data.length)this.emit(type,new MessageEvent(type,{data:data.join('\n'),lastEventId:id,origin:config.origin}));}}if(value.closed){this.close();this.emit('error');break;}await new Promise(r=>setTimeout(r,150));}}catch{this.close();this.emit('error');}}
  close(){this.readyState=2;if(this.stream)rpc('close',{stream:this.stream}).catch(()=>{});}
 }
 for(const name of ['CONNECTING','OPEN','CLOSED'])PanelEvents.prototype[name]=PanelEvents[name];
 window.EventSource=PanelEvents;
 Object.defineProperty(document,'cookie',{get:()=>cookies,set:value=>{
  cookieWrite=cookieWrite.then(()=>rpc('cookie',{value:String(value)})).then(result=>{cookies=result.cookies;}).catch(console.error);
 }});
 async function submit(form,submitter){
  const data=new FormData(form);if(submitter?.name)data.append(submitter.name,submitter.value);
  const method=(form.getAttribute('method')||'GET').toUpperCase(),target=path(form.getAttribute('action')||config.path);
  if(method==='GET'){const url=new URL(target,config.origin);for(const [k,v] of data)if(typeof v==='string')url.searchParams.append(k,v);return rpc('navigate',{path:url.pathname+url.search});}
  return rpc('navigate',{path:target,...await options({method,body:form.enctype==='multipart/form-data'?data:new URLSearchParams([...data].filter(([,v])=>typeof v==='string'))})});
 }
 document.addEventListener('submit',event=>{if(event.defaultPrevented)return;event.preventDefault();submit(event.target,event.submitter).catch(console.error);});
 HTMLFormElement.prototype.submit=function(){submit(this).catch(console.error);};
 document.addEventListener('click',event=>{const anchor=event.target.closest?.('a[href]');if(!anchor||event.defaultPrevented)return;const href=anchor.getAttribute('href');if(href.startsWith('#'))return;if(/^(blob:|data:)/.test(href)){if(!anchor.hasAttribute('download'))event.preventDefault();return;}event.preventDefault();rpc(anchor.hasAttribute('download')?'download':'navigate',{path:path(href),name:anchor.getAttribute('download')}).catch(console.error);});
 // Storage is deliberately local to this iframe; DCC storage is never exposed.
 for(const name of ['localStorage','sessionStorage']){const store=new Map();try{Object.defineProperty(window,name,{value:{getItem:k=>store.get(String(k))??null,setItem:(k,v)=>store.set(String(k),String(v)),removeItem:k=>store.delete(String(k)),clear:()=>store.clear(),key:i=>[...store.keys()][i]??null,get length(){return store.size;}}});}catch{}}
 // Dynamically created resources also pass through the scoped broker. CSP
 // blocks any unhandled network loads rather than giving them DCC cookies.
 for(const [Constructor,property] of [[HTMLScriptElement,'src'],[HTMLImageElement,'src'],[HTMLLinkElement,'href']]){
  const original=Object.getOwnPropertyDescriptor(Constructor.prototype,property);if(!original?.set)continue;
  Object.defineProperty(Constructor.prototype,property,{get:original.get,set(value){if(String(value).startsWith('data:')||String(value).startsWith('blob:'))return original.set.call(this,value);rpc('asset',{path:path(String(value))}).then(resource=>original.set.call(this,'data:'+(this instanceof HTMLScriptElement?'text/javascript':resource.headers['content-type']||'application/octet-stream')+';base64,'+resource.body)).catch(console.error);}});
 }
})();
