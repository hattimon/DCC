"""Explicit local-container SSH mounts and separate local/public domain setup."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tarfile
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

from flask import abort, jsonify, request
from security import admin
from profile_ssh import digest

SETTINGS_ID = '__dcc_domains__'
SSH_TARGET = '/mnt/dcc-ssh'
LABEL = 'io.dcc.web.proxy'


def domain(value):
    value = str(value or '').strip().lower().rstrip('.')
    if not value:
        return ''
    if len(value)>253 or '.' not in value or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',p) for p in value.split('.')) or re.fullmatch(r'[0-9.]+',value):
        raise ValueError('Enter a hostname without a scheme, port or path')
    return value


def mount_source(value):
    value = str(value or '').strip().replace('\\','/')
    if len(value)>500 or '\0' in value or '..' in value.split('/'):
        raise ValueError('Invalid host directory')
    if re.match(r'^[A-Za-z]:/',value):
        if not value[3:].strip('/'):
            raise ValueError('Select a dedicated SSH directory, not an entire drive')
        return '/run/desktop/mnt/host/'+value[0].lower()+value[2:]
    if not value.startswith('/') or value.startswith('//') or value=='/':
        raise ValueError('Provide an absolute directory on the Docker host')
    return value


def local_container(client):
    # Never act on the currently selected remote profile or guess a production path.
    if not Path('/.dockerenv').is_file():
        raise ValueError('Automatic mounting is available only inside the local DCC Web container. Native installations can select an existing server directory.')
    hostname = os.environ.get('HOSTNAME','')
    candidates = [hostname,os.environ.get('DCC_WEB_CONTAINER_NAME','dcc-web')]
    for name in filter(None,candidates):
        try:
            container = client.containers.get(name)
        except Exception:
            continue
        attrs = container.attrs
        if hostname and attrs.get('Config',{}).get('Hostname') == hostname and any(m.get('Destination')=='/data' for m in attrs.get('Mounts',[])):
            return container
    raise ValueError('Cannot safely identify this DCC Web container')


def mount_plan(container, source):
    source = mount_source(source)
    labels = container.attrs.get('Config',{}).get('Labels') or {}
    if labels.get('com.docker.compose.project'):
        raise ValueError('This installation is managed by Compose. Add a read-only bind mount in its Compose file, then recreate that service. See SSH folder setup in the documentation.')
    return {'source':source,'target_path':SSH_TARGET,'container':container.id,
            'target':digest({'id':container.id,'image':container.attrs.get('Image'),'source':source,'mounts':container.attrs.get('Mounts')})}


def test_directory(client, image, source):
    import docker
    # --mount fails if the source is missing; it never creates a host directory.
    probe = client.containers.create(image, ['-c','import os; assert os.path.isdir("/check"); os.listdir("/check")'],
        entrypoint=['python'],user='10001:10001',network_mode='none',read_only=True,cap_drop=['ALL'],
        security_opt=['no-new-privileges:true'],mounts=[docker.types.Mount('/check',source,type='bind',read_only=True)],
        mem_limit='128m',pids_limit=32)
    try:
        probe.start()
        if probe.wait(timeout=15)['StatusCode'] != 0:
            raise ValueError('The host directory is missing or not readable by the Web account')
    finally:
        probe.remove(force=True,v=False)


def schedule_mount(client, container, plan):
    import docker
    image = container.attrs['Image']  # Exact existing immutable image, no registry pull.
    test_directory(client,image,plan['source'])
    socket = '/var/run/docker.sock'
    helper = client.containers.run(image,['host_setup.py','--mount-helper',container.id,plan['source']],
        entrypoint=['python'],working_dir='/opt/dcc/apps/dcc-web',user='0:0',detach=True,
        network_mode='none',read_only=True,cap_drop=['ALL'],security_opt=['no-new-privileges:true'],
        mounts=[docker.types.Mount(socket,socket,type='bind')],mem_limit='256m',pids_limit=64,
        labels={'io.dcc.web.mount-helper':container.id},auto_remove=True)
    return helper.id


def run_mount_helper(identifier, source):
    import docker
    import importlib.util
    source = mount_source(source)
    client = docker.from_env(timeout=45)
    try:
        container = client.containers.get(identifier)
        if not re.fullmatch(r'[a-f0-9]{64}',identifier) or container.id != identifier:
            raise ValueError('Invalid target container')
        time.sleep(3)
        spec = importlib.util.spec_from_file_location('dcc_mount_updater',Path(__file__).resolve().parents[1]/'container-updater/updater.py')
        module = importlib.util.module_from_spec(spec)
        import sys
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        service = module.UpdateService(client)
        image = container.attrs['Image']
        config = service._create_config(container,image)
        host = config.get('HostConfig',{})
        mounts = [m for m in (host.get('Mounts') or []) if m.get('Target') != SSH_TARGET]
        mounts.append({'Type':'bind','Source':source,'Target':SSH_TARGET,'ReadOnly':True})
        binds = [v for v in (host.get('Binds') or []) if v.rsplit(':',2)[-2] != SSH_TARGET]
        print(service.update_one(container,image,{'host_config':{'Mounts':mounts,'Binds':binds}},
              _allow_self=True,_image_already_pulled=True,_expected_image_id=image),flush=True)
    finally:
        client.close()


class Domains:
    def __init__(self,state):
        self.state = state

    def saved(self):
        rows = self.state.rows('SELECT data FROM settings WHERE user_id=?',(SETTINGS_ID,))
        return self.state.decode_profile(rows[0]['data']) if rows else {'local':'','public':''}

    def save(self,value):
        self.state.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(SETTINGS_ID,self.state.encode_profile(value)))

    def proxy_name(self):
        return 'dcc-web-https-'+hashlib.sha256(str(self.state.directory).encode()).hexdigest()[:10]

    def provision(self,client,container,hostname):
        import docker
        hostname = domain(hostname)
        if not hostname or hostname.endswith(('.local','.localhost','.home.arpa','.test','.invalid')):
            raise ValueError('Public HTTPS requires a public domain you own with DNS pointing to this Docker host')
        name = self.proxy_name()
        existing = client.containers.list(all=True,filters={'name':'^/'+name+'$'})
        if existing:
            raise ValueError('The HTTPS extension already exists. Stop or remove it before changing its domain.')
        client.images.pull('caddy:2')
        network_name = name+'-network'
        networks = client.networks.list(names=[network_name])
        network = next((n for n in networks if n.name==network_name),None)
        if network is None:
            network = client.networks.create(network_name,driver='bridge',labels={LABEL:container.name})
        elif network.attrs.get('Labels',{}).get(LABEL) != container.name:
            raise ValueError('An unrelated Docker network uses the extension name')
        if container.id not in (network.attrs.get('Containers') or {}):
            network.connect(container,aliases=['dcc-web-upstream'])
        proxy = None
        try:
            proxy = client.containers.create('caddy:2',command=['caddy','run','--config','/config/Caddyfile','--adapter','caddyfile'],name=name,detach=True,network=network_name,
                ports={'80/tcp':80,'443/tcp':443},restart_policy={'Name':'unless-stopped'},
                volumes={name+'-certs':{'bind':'/data','mode':'rw'},name+'-config':{'bind':'/config','mode':'rw'}},
                labels={LABEL:container.name},cap_drop=['ALL'],cap_add=['NET_BIND_SERVICE'],security_opt=['no-new-privileges:true'])
            data = (hostname+' {\n reverse_proxy dcc-web-upstream:8789\n}\n').encode()
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive,mode='w') as tar:
                info = tarfile.TarInfo('Caddyfile'); info.size=len(data); info.mode=0o644
                tar.addfile(info,io.BytesIO(data))
            proxy.put_archive('/config',archive.getvalue())
            proxy.start()
            return {'name':name,'url':'https://'+hostname,'status':'starting'}
        except Exception:
            if proxy is not None:
                proxy.remove(force=True,v=False)
            raise


def register_host_setup(app,state,reauthenticate,confirmed):
    domains = Domains(state)
    app.config['ALLOWED_HOSTS'] = list(app.config['ALLOWED_HOSTS'])
    app.config['ALLOWED_HOSTS'].extend(v for k,v in domains.saved().items() if k in {'local','public'} and v)
    app.config['TRUSTED_HTTPS_HOSTS'] = [domains.saved().get('public')]
    from flask.sessions import SecureCookieSessionInterface
    class DomainSessionInterface(SecureCookieSessionInterface):
        def get_cookie_secure(self,application):
            return bool(application.config.get('SESSION_COOKIE_SECURE') or (urlsplit('//'+request.host).hostname in application.config.get('TRUSTED_HTTPS_HOSTS',[])))
    app.session_interface = DomainSessionInterface()

    @app.post('/api/profile-ssh/mount/preview')
    @app.post('/api/profile-ssh/mount')
    def ssh_mount():
        import docker
        admin()
        data = request.get_json() or {}
        client = docker.from_env(timeout=30)
        try:
            container = local_container(client)
            plan = mount_plan(container,data.get('source'))
            if request.path.endswith('/preview'):
                return jsonify(plan)
            reauthenticate(data)
            confirmed(data,'profiles.ssh.mount','workspace',plan['target'])
            return jsonify(helper=schedule_mount(client,container,plan),restarting=True)
        finally:
            client.close()

    @app.route('/api/admin/domains',methods=['GET','PUT'])
    def domain_settings():
        admin()
        if request.method=='PUT':
            data = request.get_json() or {}
            reauthenticate(data)
            value = {k:domain(data.get(k)) for k in ('local','public')}
            domains.save(value)
            app.config['TRUSTED_HTTPS_HOSTS'] = [value.get('public')]
            # Host checking stays restrictive; never wildcard the panel.
            app.config['ALLOWED_HOSTS'] = list(set(app.config['ALLOWED_HOSTS']) | {v for v in value.values() if v})
        return jsonify(domains.saved())

    @app.post('/api/admin/domains/verify')
    def verify_domain():
        admin()
        hostname = domains.saved().get('public')
        if not hostname:
            raise ValueError('Set a public domain first')
        # Only the administrator-selected domain, verified TLS and no redirects to a different host.
        with urlopen('https://'+hostname+'/api/health',timeout=8) as response:
            if urlsplit(response.url).hostname != hostname:
                raise ValueError('The domain redirected to a different host')
            value = json.loads(response.read(4096))
            if value.get('status') != 'ok' or 'version' not in value:
                raise ValueError('The public domain does not reach DCC Web')
        return jsonify(ok=True,url='https://'+hostname)

    @app.post('/api/admin/domains/proxy/<action>')
    def proxy_action(action):
        import docker
        admin()
        if action not in {'install','start','stop','remove'}:
            abort(404)
        data = request.get_json() or {}
        reauthenticate(data,second_factor=data.get('preview') is not True)
        hostname = domains.saved().get('public')
        target = digest({'domain':hostname,'action':action,'name':domains.proxy_name()})
        if data.get('preview') is True:
            return jsonify(target=target,domain=hostname,action=action)
        confirmed(data,'panel.proxy','workspace',target)
        client = docker.from_env(timeout=60)
        try:
            container = local_container(client)
            if action=='install':
                return jsonify(domains.provision(client,container,hostname))
            proxy = client.containers.get(domains.proxy_name())
            if proxy.attrs.get('Config',{}).get('Labels',{}).get(LABEL) != container.name:
                abort(409,'The extension does not belong to this Web container')
            if action in {'stop','remove'}:
                proxy.stop(timeout=10)
            if action=='remove':
                proxy.remove(v=False)  # Certificate volumes are deliberately preserved.
            elif action=='start':
                proxy.start()
            return jsonify(ok=True)
        finally:
            client.close()


if __name__=='__main__':
    import sys
    if len(sys.argv)==4 and sys.argv[1]=='--mount-helper':
        run_mount_helper(sys.argv[2],sys.argv[3])
    else:
        raise SystemExit('Unsupported helper invocation')
