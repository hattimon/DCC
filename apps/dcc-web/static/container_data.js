// Grouping follows the Desktop preference: Compose project, primary network or flat list.
export function labelsOf(entry){
 if(entry.Labels&&typeof entry.Labels==='object')return entry.Labels;
 return Object.fromEntries(String(entry.Labels||'').split(',').filter(v=>v.includes('=')).map(v=>{const at=v.indexOf('=');return[v.slice(0,at).trim(),v.slice(at+1)];}));
}
export function networksOf(entry){
 const values=Array.isArray(entry.Networks)?entry.Networks:String(entry.Networks||'').split(',');
 return [...new Set(values.map(v=>String(v).trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
}
export function projectOf(entry){const labels=labelsOf(entry);return labels['com.docker.compose.project']||labels['com.docker.stack.namespace']||'';}
export function primaryNetwork(entry){
 const networks=networksOf(entry),preferred=projectOf(entry)+'_default';
 return networks.includes(preferred)?preferred:networks.find(v=>!['bridge','host','none'].includes(v))||networks[0]||'';
}
export function groupContainers(values,mode){
 if(mode==='none')return [{key:'',values}];
 const groups=new Map();
 for(const entry of values){const key=mode==='network'?(primaryNetwork(entry)||'__no_network__'):(projectOf(entry)||'__standalone__');if(!groups.has(key))groups.set(key,[]);groups.get(key).push(entry);}
 return [...groups].sort(([a],[b])=>Number(a.startsWith('__'))-Number(b.startsWith('__'))||a.localeCompare(b,undefined,{numeric:true,sensitivity:'base'})).map(([key,values])=>({key,values:[...values].sort((a,b)=>String(a.Names).localeCompare(String(b.Names),undefined,{numeric:true,sensitivity:'base'}))}));
}
