"""Explicit, provider-neutral Docker command proposals. No model output is executed."""
import json
import re
import socket
import ipaddress
import threading
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from flask import abort,g,jsonify,request
from security import admin,authorize,redact,ROLES
from catalogs import install_plan
from ports import inventory


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('AI endpoint redirects are disabled')


def validate_connection(data):
    provider=data.get('provider','openai')
    if provider not in {'openai','compatible','ollama'}:raise ValueError('Unknown AI provider')
    endpoint=str(data.get('endpoint') or ('https://api.openai.com/v1' if provider=='openai' else 'http://127.0.0.1:11434' if provider=='ollama' else '')).rstrip('/')
    parsed=urlsplit(endpoint)
    if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('AI endpoint must be an HTTP(S) base URL without credentials or query parameters')
    if provider=='openai' and endpoint!='https://api.openai.com/v1':raise ValueError('Use the compatible provider for a custom endpoint')
    if parsed.scheme=='http' and data.get('allow_local') is not True:raise ValueError('Local HTTP endpoints require explicit local-network consent')
    model=str(data.get('model','')).strip()
    if not model or len(model)>160:raise ValueError('Specify the AI model name')
    return {'provider':provider,'endpoint':endpoint,'model':model,'allow_local':data.get('allow_local') is True,'enabled':data.get('enabled') is True}


def request_json(connection,path,payload=None):
    url=connection['endpoint']+path;parsed=urlsplit(url)
    for value in socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=='https' else 80),type=socket.SOCK_STREAM):
        address=ipaddress.ip_address(value[4][0])
        if address.is_link_local or address.is_multicast or address.is_unspecified:
            raise ValueError('AI endpoint resolves to a prohibited address')
        if not address.is_global and not connection.get('allow_local'):
            raise ValueError('Enable local-network consent for this AI endpoint')
    headers={'Content-Type':'application/json','Accept':'application/json'}
    if connection.get('api_key'):headers['Authorization']='Bearer '+connection['api_key']
    opener=urllib.request.build_opener(NoRedirect(),urllib.request.ProxyHandler({}))
    req=urllib.request.Request(url,data=json.dumps(payload).encode() if payload is not None else None,headers=headers,method='POST' if payload is not None else 'GET')
    try:
        with opener.open(req,timeout=60) as response:
            raw=response.read(1_000_001)
        if len(raw)>1_000_000:raise ValueError('AI response exceeds the limit')
        return json.loads(raw)
    except urllib.error.HTTPError as error:
        raise ValueError(f'AI provider returned HTTP {error.code}. Check the endpoint, model and credentials.') from None
    except (OSError,urllib.error.URLError,json.JSONDecodeError):
        raise ValueError('AI provider is unavailable or returned invalid JSON') from None


def proposal(connection,task,configuration,context,language):
    system='You are a Docker configuration assistant. Return JSON only: {"configuration":{"name":"...","image":"...","host_port":"...","container_port":"...","extra":"...","command":"...","environment":{}},"explanation":"..."}. Preserve supplied settings unless the request changes them. No host shell, command substitution, sudo, scripts, secrets or destructive cleanup. Never use docker run in command (command runs inside the container). Use port mappings in host_port/container_port or -p options in extra, not both for the same mapping. Explain security and persistent storage. Your output is a proposal only. Reply in '+('Polish' if language=='PL' else 'English')+'.'
    prompt=json.dumps({'request':redact(task),'current_configuration':redact(configuration),'host_context':redact(context)},ensure_ascii=False)
    if connection['provider']=='ollama':
        response=request_json(connection,'/api/generate',{'model':connection['model'],'system':system,'prompt':prompt,'stream':False,'format':'json','options':{'num_predict':1800}})
        text=response.get('response','')
    elif connection['provider']=='openai':
        response=request_json(connection,'/responses',{'model':connection['model'],'instructions':system,'input':prompt,'max_output_tokens':1800,'store':False})
        text=''.join(part.get('text','') for output in response.get('output',[]) for part in output.get('content',[]) if part.get('type')=='output_text')
    else:
        response=request_json(connection,'/chat/completions',{'model':connection['model'],'messages':[{'role':'system','content':system},{'role':'user','content':prompt}],'max_tokens':1800,'stream':False})
        text=response.get('choices',[{}])[0].get('message',{}).get('content','')
    text=re.sub(r'^```(?:json)?\s*|\s*```$','',str(text).strip())
    try:value=json.loads(text)
    except (ValueError,TypeError):raise ValueError('AI did not return a valid configuration proposal') from None
    if not isinstance(value,dict) or not isinstance(value.get('configuration'),dict):raise ValueError('AI proposal has no configuration object')
    config=value['configuration']
    allowed={'name','image','host_port','container_port','extra','command','environment'}
    if set(config)-allowed or not all(isinstance(v,str) for k,v in config.items() if k!='environment') or not isinstance(config.get('environment',{}),dict):
        raise ValueError('AI proposal contains unsupported fields')
    if len(json.dumps(config))>20000:raise ValueError('AI configuration is too large')
    return config,str(value.get('explanation',''))[:6000]


def register_ai(app,state,profile_lookup,factory,body):
    state.execute('CREATE TABLE IF NOT EXISTS ai_connections(id TEXT PRIMARY KEY, public TEXT, private BLOB)')
    active=threading.BoundedSemaphore(2)
    def connection(private=False):
        rows=state.rows("SELECT * FROM ai_connections WHERE id='default'")
        if not rows:return {'provider':'openai','endpoint':'https://api.openai.com/v1','model':'','enabled':False,'allow_local':False,'has_key':False}
        row=rows[0];value=json.loads(row['public'])
        secrets=json.loads(state.vault.decrypt(row['private']))
        value['has_key']=bool(secrets.get('api_key'))
        if private:value.update(secrets)
        return value

    @app.route('/api/ai/connection',methods=['GET','PUT'])
    def configure():
        if request.method=='GET':return jsonify(connection())
        admin();data=body();value=validate_connection(data)
        old=connection(private=True)
        same_endpoint=(old.get('endpoint'),old.get('provider'))==(value['endpoint'],value['provider'])
        key='' if data.get('clear_key') is True else str(data.get('api_key') or (old.get('api_key','') if same_endpoint else ''))
        if len(key)>4096 or any(c in key for c in '\r\n\0'):abort(400,'Invalid AI credential')
        state.execute("INSERT OR REPLACE INTO ai_connections VALUES('default',?,?)",(json.dumps(value),state.vault.encrypt(json.dumps({'api_key':key}).encode())))
        return jsonify(connection())

    @app.get('/api/ai/models')
    def models():
        admin();value=connection(private=True)
        response=request_json(value,'/api/tags' if value['provider']=='ollama' else '/models')
        entries=response.get('models',[]) if value['provider']=='ollama' else response.get('data',[])
        return jsonify(models=[entry.get('name') or entry.get('id') for entry in entries if isinstance(entry,dict)][:500])

    @app.post('/api/ai/propose')
    def generate():
        data=body();p=profile_lookup(data.get('profile'))
        if not (set(p.get('permissions',[])) & ROLES.get(g.user['role'],set()) & {'install','containers.write','exec'}):
            abort(403,'Enable installation or container management for this profile to use the AI assistant')
        value=connection(private=True)
        if not value.get('enabled'):abort(409,'Configure and enable the AI connection first')
        task=data.get('prompt','');config=data.get('configuration',{})
        if not isinstance(task,str) or not 1<=len(task)<=8000 or not isinstance(config,dict):abort(400,'A request and configuration object are required')
        if not active.acquire(blocking=False):abort(429,'AI is busy; try again shortly')
        try:
            engine=factory(p);context={};planning=engine
            if data.get('target'):
                target=str(data['target'])
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,200}',target):abort(400,'Invalid container identifier')
                current=engine.inspect(target)
                class EditPlan:
                    info=engine.info
                    json=engine.json
                    profile=p
                    def containers(self):
                        return [entry for entry in engine.containers() if entry.get('ID')!=current.get('Id') and entry.get('Names')!=str(current.get('Name','')).lstrip('/')]
                planning=EditPlan()
            if data.get('send_context') is True:
                info=engine.info()
                context={'architecture':info.get('Architecture'),'cpus':info.get('NCPU'),'ram_bytes':info.get('MemTotal'),'ports':inventory(planning)['occupied']}
            suggested,explanation=proposal(value,task,config,context,data.get('language','EN'))
            if data.get('target') and suggested.get('image',config.get('image'))!=current.get('Config',{}).get('Image'):
                raise ValueError('Use the image update action to change the existing container image')
            suggested=dict(config,**suggested,auto_port=data.get('auto_port') is True)
            plan=install_plan({'name':'AI proposal','image':suggested.get('image','')},suggested,planning)
            result=plan['resolved_configuration']
            state.audit(g.user['id'],'ai.propose',p['id'],200)
            return jsonify(configuration=result,explanation=explanation,preview=redact(plan),executed=False)
        finally:active.release()
