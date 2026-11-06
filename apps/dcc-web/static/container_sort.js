const percent=value=>{
 const parsed=Number.parseFloat(String(value??'').replace('%',''));
 return Number.isFinite(parsed)?parsed:null;
};

function bytes(value){
 const match=String(value??'').trim().match(/^([\d.]+)\s*([KMGTPE]?)(i?B)$/i);
 if(!match)return null;
 const amount=Number(match[1]);
 const power=match[2]?'KMGTPE'.indexOf(match[2].toUpperCase())+1:0;
 return Number.isFinite(amount)?amount*(match[3].length===2?1024:1000)**power:null;
}

const totalIO=value=>{
 const parts=String(value??'').split('/').map(bytes);
 return parts.length===2&&parts.every(v=>v!==null)?parts[0]+parts[1]:null;
};

const metrics={cpu:v=>percent(v.CPUPerc),ram:v=>bytes(v.MemUsage?.split('/')[0]),
 'ram-percent':v=>percent(v.MemPerc),network:v=>totalIO(v.NetIO),disk:v=>totalIO(v.BlockIO),
 processes:v=>/^\d+$/.test(String(v.PIDs??''))?Number(v.PIDs):null};

function byValue(values,metric,direction){
 const sign=direction==='asc'?1:-1;
 return values.map((item,index)=>({item,index,value:metric(item)})).sort((a,b)=>{
  if(a.value===null)return b.value===null?a.index-b.index:1;
  if(b.value===null)return -1;
  return (a.value-b.value)*sign||a.index-b.index;
 }).map(v=>v.item);
}

export function sortMetrics(values,key,direction){
 if(!Object.hasOwn(metrics,key)||!['asc','desc'].includes(direction))return [...values];
 return byValue(values,metrics[key],direction);
}

function statsFor(container,stats){
 return stats.find(value=>value.ID===container.ID||value.ID&&container.ID?.startsWith(value.ID)||value.Container&&container.ID?.startsWith(value.Container))||{};
}

export function sortContainers(values,stats,key,direction){
 if(!['cpu','ram'].includes(key)||!['asc','desc'].includes(direction))return [...values];
 return byValue(values,container=>metrics[key](statsFor(container,stats)),direction);
}

export function nextSortState(current,key){
 if(current?.key!==key)return {key,direction:'desc'};
 if(current.direction==='desc')return {key,direction:'asc'};
 return null;
}
