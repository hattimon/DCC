const percent=value=>{
 const parsed=Number.parseFloat(String(value??'').replace('%',''));
 return Number.isFinite(parsed)?parsed:null;
};

function mib(value){
 const match=String(value??'').match(/([\d.]+)\s*([KMG])i?B/i);
 if(!match)return null;
 const amount=Number(match[1]);
 return Number.isFinite(amount)?amount*({K:1/1024,M:1,G:1024}[match[2].toUpperCase()]||0):null;
}

function statsFor(container,stats){
 return stats.find(value=>value.ID===container.ID||value.ID&&container.ID?.startsWith(value.ID)||value.Container&&container.ID?.startsWith(value.Container))||{};
}

export function sortContainers(values,stats,key,direction){
 if(!['cpu','ram'].includes(key)||!['asc','desc'].includes(direction))return [...values];
 const sign=direction==='asc'?1:-1;
 return values.map((container,index)=>{
  const data=statsFor(container,stats),value=key==='cpu'?percent(data.CPUPerc):mib(data.MemUsage?.split('/')[0]);
  return {container,index,value};
 }).sort((a,b)=>{
  if(a.value===null)return b.value===null?a.index-b.index:1;
  if(b.value===null)return -1;
  return (a.value-b.value)*sign||a.index-b.index;
 }).map(item=>item.container);
}

export function nextSortState(current,key){
 if(current?.key!==key)return {key,direction:'desc'};
 if(current.direction==='desc')return {key,direction:'asc'};
 return null;
}
