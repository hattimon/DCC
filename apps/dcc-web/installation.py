"""Installation phases, redacted logs, and explicitly revealed encrypted access details."""
import json
import re
import time
from dcc_catalog import parse_access_details,image_repository
from engine import EngineError
from ports import enrich_containers
from security import redact


def execute_install(engine,plan,entry,report,vault,trusted=None,language='EN'):
    patterns=(trusted or {}).get('credential_patterns',[])
    def save_logs(raw):
        found=parse_access_details(raw,patterns,language)
        if found:
            values=[{'label':label,'value':value} for label,value in found]
            report(access_blob=vault.encrypt(json.dumps(values).encode()).decode(),access_count=len(values))
            for _,value in found:raw=raw.replace(value,'••••')
        report(log=redact(raw)+'\n')
        return found
    report(phase='checking',log='Configuration and host requirements validated.\n',container=plan['name'])
    try:
        image=engine.json(['image','inspect',plan['image']])
        exists=bool(image)
    except EngineError:exists=False
    if exists:
        report(phase='pulling',log='The requested image is already available locally.\n')
    else:
        report(phase='pulling',log='Pulling image '+plan['image']+'\n')
        engine.stream(['pull',plan['image']],lambda chunk:report(log=redact(chunk)),timeout=900)
    report(phase='creating',log='Creating container '+plan['name']+'\n')
    output=engine.run(plan['args'],timeout=900)
    report(log=redact(str(output))+'\n',phase='starting')
    details={}
    for attempt in range(12):
        details=engine.inspect(plan['name'])
        state=details.get('State',{})
        if state.get('Status') in {'exited','dead'} or (state.get('Running') is False and state.get('ExitCode',0)):
            raw=engine.logs(plan['name'],300)
            save_logs(raw)
            raise EngineError('The container stopped during startup. Review its log; existing volumes were retained.')
        health=state.get('Health',{}).get('Status')
        if health=='unhealthy':
            save_logs(engine.logs(plan['name'],300))
            raise EngineError('Container health check failed. Review the startup log; volumes were retained.')
        if health!='starting':break
        time.sleep(1)
    report(phase='access',log='Reading startup logs and access information.\n')
    raw=''
    detected=[]
    for attempt in range(8):
        try:raw=engine.logs(plan['name'],300)
        except EngineError:raw=''
        detected=parse_access_details(raw,patterns,language)
        if detected or attempt==7:break
        time.sleep(.25)
    if not detected:report(access_count=0)
    save_logs(raw)
    containers=[c for c in engine.containers() if c.get('Names')==plan['name']]
    port=str(entry.get('container_port','')).split('/')[0]
    defaults={image_repository(entry['image']):int(port)} if port.isdigit() else {}
    links=enrich_containers(containers,engine.profile,host_panels=defaults)[0].get('PanelLinks',[]) if containers else []
    hints=(entry.get('post_install_hints_en') if language=='EN' else entry.get('post_install_hints')) or []
    report(log='Installation completed; persistent volumes were retained.\n')
    return {'name':plan['name'],'output':redact(output),'links':links,'hints':hints,'startup':details.get('State',{}).get('Health',{}).get('Status') or 'running'}
