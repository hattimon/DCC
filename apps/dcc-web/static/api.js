import{html,t,literal,setLanguage}from'./i18n.js';
export const state={profile:localStorage.getItem('dcc-profile')||'local',settings:null,user:null,profiles:[],view:'overview',target:'',selected:new Set(),containers:[],stats:[],hostAddress:'',containerRevision:null};
export async function api(path,options={}){
 const url=new URL('/api/'+path,location.origin);
 if(!url.searchParams.has('profile'))url.searchParams.set('profile',state.profile);
 const headers={'X-CSRF-Token':document.querySelector('meta[name=csrf-token]').content};
 if(options.data!==undefined){headers['Content-Type']='application/json';options.body=JSON.stringify({profile:state.profile,...options.data});}
 const response=await fetch(url,{credentials:'same-origin',...options,headers:{...headers,...options.headers}});
 const value=await response.json().catch(()=>({error:'Nieprawidłowa odpowiedź serwera'}));
 if(response.status===401){location.assign('/login');throw Error(t('Sesja wygasła'));}
 if(!response.ok)throw Error(t(value.error||'Nie udało się wykonać operacji'));
 return value;
}
export const post=(path,data)=>api(path,{method:'POST',data});
export function can(permission){const p=state.profiles.find(p=>p.id===state.profile);return state.user?.role==='admin'&&p?.permissions.includes(permission)||state.user?.role==='operator'&&['read','containers.write','exec'].includes(permission)&&p?.permissions.includes(permission);}
export async function pollJob(job){if(!job?.id)return job;for(let attempt=0;attempt<400;attempt++){const result=await api('jobs/'+job.id);if(result.status==='success')return result.result;if(result.status==='error')throw Error(t(result.error));await new Promise(resolve=>setTimeout(resolve,1000));}throw Error('Operacja nadal trwa. Sprawdź stan Dockera przed ponowieniem.');}
