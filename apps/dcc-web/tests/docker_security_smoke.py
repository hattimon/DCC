"""Explicit disposable Docker migration/mount smoke; never uses user profiles or keys."""
import base64
import http.cookiejar
import io
import json
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request


def main():
    import argparse
    import paramiko
    parser=argparse.ArgumentParser()
    parser.add_argument('--image',default='dcc-web:qa-0.1.5')
    parser.add_argument('--old-image',default='ghcr.io/hattimon/dcc-web:0.1.2')
    parser.add_argument('--mount-fixture',help='Explicit readable host directory containing only synthetic marker files')
    args=parser.parse_args()
    name='dcc-web-security-qa-'+secrets.token_hex(4);volume=name+'-data'
    created=False;running=False
    def docker(*parts):
        result=subprocess.run(['docker',*parts],capture_output=True,text=True)
        if result.returncode:raise RuntimeError(result.stderr[:1500])
        return result.stdout.strip()
    def start(image):
        nonlocal running
        docker('run','-d','--name',name,'--label','dcc.qa=security-smoke','-p','127.0.0.1::8789',
            '-v',volume+':/data','-v','/var/run/docker.sock:/var/run/docker.sock','-e','DCC_WEB_CONTAINER_NAME='+name,
            '--cap-drop=ALL','--cap-add=SETUID','--cap-add=SETGID','--read-only','--tmpfs','/tmp:size=64m,mode=1777',image)
        running=True
        base='http://127.0.0.1:'+docker('port',name,'8789/tcp').rsplit(':',1)[1]
        for _ in range(60):
            try:
                with urllib.request.urlopen(base+'/api/health',timeout=2):return base
            except Exception:time.sleep(.5)
        raise RuntimeError('QA image failed health check')
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    try:
        docker('volume','create','--label','dcc.qa=security-smoke',volume);created=True
        base=start(args.old_image)
        credential=re.search(r'DCC_WEB_INITIAL_CREDENTIALS username=(\S+) password=(\S+)',docker('logs',name))
        assert credential,'No synthetic bootstrap account'
        with opener.open(base+'/login') as response:page=response.read().decode()
        csrf=re.search(r'name="csrf" value="([^"]+)"',page)[1]
        data=urllib.parse.urlencode({'username':credential[1],'password':credential[2],'csrf':csrf}).encode()
        with opener.open(base+'/login',data) as response:page=response.read().decode()
        csrf=re.search(r'name="csrf-token" content="([^"]+)"',page)[1]
        def api(path,value=None,method=None):
            req=urllib.request.Request(base+'/api/'+path,data=json.dumps(value).encode() if value is not None else None,
                method=method,headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
            with opener.open(req,timeout=50) as response:return json.load(response)
        key=paramiko.RSAKey.generate(1024);text=io.StringIO();key.write_private_key(text,password='fixture-key-pass')
        private=text.getvalue();known='fixture.invalid '+key.get_name()+' '+key.get_base64()+'\n'
        payload=base64.b64encode(json.dumps({'key':private,'known':known}).encode()).decode()
        code='import base64,json;from pathlib import Path;d=json.loads(base64.b64decode('+repr(payload)+'));p=Path("/data/ssh");p.mkdir(exist_ok=True);p.chmod(0o700);(p/"fixture.key").write_text(d["key"]);(p/"known_hosts").write_text(d["known"]);(p/"fixture.key").chmod(0o600)'
        docker('exec','--user','10001:10001',name,'python','-c',code)
        ident=api('profiles',{'name':'Upgrade SSH fixture','kind':'ssh','host':'fixture.invalid','username':'fixture','port':22,
            'key_scope':'shared','key_path':'fixture.key','permissions':['read'],'credentials':{'passphrase':'fixture-key-pass'}})['id']
        api('settings',{'theme':'violet','language':'PL'},'PUT')
        before=api('profiles')['profiles'];user=api('bootstrap')['user']['id']
        docker('stop','--time','5',name);docker('rm',name);running=False
        base=start(args.image)
        after=api('bootstrap')
        assert after['version']=='0.1.5',after['version']
        assert after['user']['id']==user and after['settings']['theme']=='violet' and after['settings']['language']=='PL'
        assert api('profiles')['profiles']==before
        docker('exec','--user','10001:10001',name,'python','-c',
            'from state import State;from pathlib import Path;from profile_ssh import connection_options;s=State("/data");p=s.profile('+repr(ident)+',private=True);assert p["credentials"]["passphrase"]=="fixture-key-pass";assert connection_options(p)["pkey"];assert not Path("/data/ssh/fixture.key").exists();assert all(r["public"].startswith("fernet:") for r in s.rows("SELECT public FROM profiles"));print("Encrypted migration and in-memory SSH key OK")')
        for category in ('all','DCC','Administracja','WWW'):
            values=api('catalog?q=DCC%20Web&category='+category)['apps']
            assert len(values)==1,'Duplicate catalog entry'
        mount_verified=False
        if args.mount_fixture:
            source=str(Path(args.mount_fixture).resolve())
            payload={'source':source}
            plan=api('profile-ssh/mount/preview',payload)
            payload.update(current_password=credential[2],confirmation=api('confirmations',{'action':'profiles.ssh.mount','target':plan['target']})['confirmation'])
            old_id=docker('inspect','--format','{{.Id}}',name)
            api('profile-ssh/mount',payload)
            for _ in range(120):
                try:
                    inspected=json.loads(docker('inspect',name))[0]
                    helper=docker('ps','-q','--filter','label=io.dcc.web.mount-helper='+old_id)
                    if inspected['Id']!=old_id and inspected['State'].get('Health',{}).get('Status')=='healthy' and not helper:break
                except Exception:pass
                time.sleep(.5)
            else:raise RuntimeError('Read-only mount helper did not recreate a healthy QA container')
            mounts=inspected['Mounts'];mount=next(m for m in mounts if m['Destination']=='/mnt/dcc-ssh')
            assert mount['RW'] is False
            docker('exec','--user','10001:10001',name,'python','-c','from pathlib import Path;assert (Path("/mnt/dcc-ssh")/"qa-marker.txt").read_text()=="synthetic mount fixture"')
            assert inspected['HostConfig']['PortBindings']['8789/tcp']
            assert next(m for m in mounts if m['Destination']=='/data')['Name']==volume
            mount_verified=True
        inspected=json.loads(docker('inspect',name))[0]
        assert inspected['RestartCount']==0
        print(json.dumps({'old_image':args.old_image,'new_image':args.image,'profile_configuration_preserved':True,
            'credentials_and_keys_encrypted':True,'settings_preserved':True,'catalog_unique':True,
            'read_only_host_mount_verified':mount_verified,'restart_count':inspected['RestartCount']},indent=2))
    finally:
        if running:
            docker('stop','--time','5',name);docker('rm',name)
        if created:docker('volume','rm',volume)


if __name__=='__main__':main()
