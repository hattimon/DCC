"""Explicit local-container SSH mounts and separate local/public domain setup."""
import hashlib
import hmac
import ipaddress
import io
import json
import os
from pathlib import Path
import re
import secrets
import socket
import tarfile
import time
from urllib.parse import urlsplit
from flask import send_file
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


def local_host(value):
    """Validate a LAN name or a private/loopback IP used by local HTTPS."""
    value = str(value or '').strip()
    if not value:
        return ''
    try:
        address = ipaddress.ip_address(value.strip('[]'))
    except ValueError:
        return domain(value)
    if address.is_unspecified or address.is_multicast or address.is_link_local or not (address.is_private or address.is_loopback):
        raise ValueError('Use a private LAN or loopback IP address for local HTTPS')
    return address.compressed


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
    # Docker inspect may return the same mounts in a different order between
    # preview and confirmation. Preserve their contents, but canonicalize order.
    mounts = sorted(container.attrs.get('Mounts') or [], key=lambda mount: mount.get('Destination',''))
    return {'source':source,'target_path':SSH_TARGET,'container':container.id,
            'target':digest({'id':container.id,'image':container.attrs.get('Image'),'source':source,'mounts':mounts})}


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
        previous=self.saved()
        merged={**previous,**value}
        merged.setdefault('_tls_proxy_token',secrets.token_urlsafe(32))
        self.state.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(SETTINGS_ID,self.state.encode_profile(merged)))

    def public_settings(self):
        saved=self.saved()
        return {key:saved.get(key,'') for key in ('local','public')}

    def proxy_token(self):
        saved=self.saved()
        token=saved.get('_tls_proxy_token')
        if not token:
            token=secrets.token_urlsafe(32)
            saved['_tls_proxy_token']=token
            self.state.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(SETTINGS_ID,self.state.encode_profile(saved)))
        return token

    def trusts_proxy(self,token):
        expected=self.proxy_token()
        return bool(token and hmac.compare_digest(str(token),expected))

    def proxy_name(self):
        return 'dcc-web-https-'+hashlib.sha256(str(self.state.directory).encode()).hexdigest()[:10]

    def _proxy_port_used(self,client,port,existing_id=None):
        for other in client.containers.list(all=True,ignore_removed=True):
            if str(getattr(other,'id',''))==str(existing_id or ''):
                continue
            attrs=getattr(other,'attrs',{}) or {}
            bindings=(attrs.get('HostConfig') or {}).get('PortBindings') or {}
            runtime=(attrs.get('NetworkSettings') or {}).get('Ports') or {}
            for collection in (bindings,runtime):
                for entries in collection.values():
                    values=entries if isinstance(entries,list) else [entries]
                    for entry in values:
                        if isinstance(entry,dict) and str(entry.get('HostPort') or '')==str(port):
                            return True
        return False

    def _local_https_ports(self,client,existing_id=None):
        preferred=self.saved().get('local_https_port')
        candidates=[]
        if str(preferred or '').isdigit():
            candidates.append(int(preferred))
        candidates.extend(range(9443,9500))
        return [port for port in dict.fromkeys(candidates)
                if 1<=port<=65535 and not self._proxy_port_used(client,port,existing_id)]

    def _local_https_port(self,client,existing_id=None):
        candidates=self._local_https_ports(client,existing_id)
        if candidates:
            return candidates[0]
        raise ValueError('No free HTTPS host port was found in the range 9443–9499')

    @staticmethod
    def _local_bind_ip(hostname):
        try:
            return ipaddress.ip_address(str(hostname).strip('[]')).compressed
        except ValueError:
            try:
                addresses=socket.getaddrinfo(hostname,None,type=socket.SOCK_STREAM)
            except OSError as exc:
                raise ValueError('The local name does not resolve on the Docker host. Use its private IP address or configure local DNS first.') from exc
            for address in addresses:
                try:
                    parsed=ipaddress.ip_address(address[4][0].split('%',1)[0])
                except (ValueError,IndexError):
                    continue
                if (parsed.is_private or parsed.is_loopback) and not (parsed.is_link_local or parsed.is_multicast or parsed.is_unspecified):
                    return parsed.compressed
        raise ValueError('Local HTTPS must bind to a private or loopback host address')

    @staticmethod
    def _is_port_conflict(error,port):
        message=str(error).lower()
        return str(port) in message and any(text in message for text in ('already allocated','address already in use','port is in use','failed to bind'))

    @staticmethod
    def _proxy_config(saved,local_enabled,public_enabled,token):
        lines=['{',' admin off']
        local_name=local_host(saved.get('local')) or '127.0.0.1'
        if local_enabled:
            try:
                address=ipaddress.ip_address(local_name)
            except ValueError:
                pass
            else:
                # IP-address clients omit SNI. Docker's listener address is the
                # container IP, so explicitly select the configured LAN cert.
                lines.append(f' default_sni {address.compressed}')
        if not public_enabled:
            lines.append(' auto_https disable_redirects')
        lines.append('}')
        if local_enabled:
            host=local_name
            host=f'[{host}]' if ':' in host else host
            lines.extend([
                f'https://{host}:9443 {{',
                ' tls {',
                '  issuer internal',
                ' }',
                ' reverse_proxy dcc-web-upstream:8789 {',
                f'  header_up X-DCC-Web-Internal-TLS {token}',
                '  header_up X-Forwarded-Proto https',
                ' }',
                '}',
            ])
        if public_enabled:
            hostname=domain(saved.get('public'))
            lines.extend([
                f'{hostname} {{',
                ' reverse_proxy dcc-web-upstream:8789 {',
                f'  header_up X-DCC-Web-Internal-TLS {token}',
                '  header_up X-Forwarded-Proto https',
                ' }',
                '}',
            ])
        return ('\n'.join(lines)+'\n').encode()

    def provision(self,client,container,hostname,mode='public'):
        import docker
        if mode not in {'local','public'}:
            raise ValueError('Unsupported HTTPS mode')
        hostname = local_host(hostname) if mode=='local' else domain(hostname)
        if mode=='public' and (not hostname or hostname.endswith(('.local','.localhost','.home.arpa','.test','.invalid'))):
            raise ValueError('Public HTTPS requires a public domain you own with DNS pointing to this Docker host')
        if mode=='local' and not hostname:
            hostname='127.0.0.1'
        name = self.proxy_name()
        existing = client.containers.list(all=True,filters={'name':'^/'+name+'$'})
        old_proxy=existing[0] if existing else None
        if len(existing)>1:
            raise ValueError('Multiple HTTPS extensions use the managed name; no changes were made')
        if old_proxy:
            labels=(old_proxy.attrs.get('Config') or {}).get('Labels') or {}
            if labels.get(LABEL)!=container.name:
                raise ValueError('An unrelated container uses the HTTPS extension name')
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
        previous=self.saved()
        old_bindings=((old_proxy.attrs.get('HostConfig') or {}).get('PortBindings') or {}) if old_proxy else {}
        inferred_local='9443/tcp' in old_bindings
        inferred_public='80/tcp' in old_bindings or '443/tcp' in old_bindings
        local_enabled=bool(previous.get('local_https_enabled') or inferred_local) or mode=='local'
        public_enabled=bool(previous.get('public_https_enabled') or inferred_public) or mode=='public'
        token=self.proxy_token()
        proxy_ports=self._local_https_ports(client,getattr(old_proxy,'id',None)) if local_enabled else [None]
        if local_enabled and not proxy_ports:
            raise ValueError('No free HTTPS host port was found in the range 9443–9499')
        local_name=previous.get('local') or (hostname if mode=='local' else '127.0.0.1')
        local_bind_ip=self._local_bind_ip(local_name) if local_enabled else None
        proxy_port=None
        backup_name=name+'-previous-'+secrets.token_hex(3)
        old_renamed=False
        proxy = None
        try:
            if old_proxy:
                try:old_proxy.stop(timeout=10)
                except Exception:pass
                old_proxy.rename(backup_name)
                old_renamed=True
            last_error=None
            for candidate_port in proxy_ports:
                ports={}
                if public_enabled:
                    ports.update({'80/tcp':80,'443/tcp':443})
                if local_enabled:
                    ports['9443/tcp']=(local_bind_ip,candidate_port)
                config=self._proxy_config({**previous,'local':local_name,
                                           'public':hostname if mode=='public' else previous.get('public','')},
                                          local_enabled,public_enabled,token)
                try:
                    proxy = client.containers.create('caddy:2',command=['caddy','run','--config','/config/Caddyfile','--adapter','caddyfile'],name=name,detach=True,network=network_name,
                        ports=ports,restart_policy={'Name':'unless-stopped'},
                        volumes={name+'-certs':{'bind':'/data','mode':'rw'},name+'-config':{'bind':'/config','mode':'rw'}},
                        environment={'XDG_DATA_HOME':'/data','XDG_CONFIG_HOME':'/config'},
                        labels={LABEL:container.name},cap_drop=['ALL'],cap_add=['NET_BIND_SERVICE'],security_opt=['no-new-privileges:true'])
                    archive = io.BytesIO()
                    with tarfile.open(fileobj=archive,mode='w') as tar:
                        info = tarfile.TarInfo('Caddyfile'); info.size=len(config); info.mode=0o644
                        tar.addfile(info,io.BytesIO(config))
                    proxy.put_archive('/config',archive.getvalue())
                    proxy.start()
                    proxy_port=candidate_port
                    break
                except Exception as exc:
                    last_error=exc
                    if proxy is not None:
                        try:proxy.remove(force=True,v=False)
                        except Exception:pass
                        proxy=None
                    if not local_enabled or not self._is_port_conflict(exc,candidate_port) or candidate_port==proxy_ports[-1]:
                        raise
            if proxy is None:
                raise last_error or ValueError('The HTTPS extension could not be started')
            if old_proxy:
                old_proxy.remove(v=False)
            saved={**previous,'local_https_enabled':local_enabled,'public_https_enabled':public_enabled}
            if local_enabled and not saved.get('local'):
                saved['local']=local_name
            if local_enabled:saved['local_https_port']=proxy_port
            if mode=='public':saved['public']=hostname
            if mode=='local':saved['local']=hostname
            saved['_tls_proxy_token']=token
            self.save(saved)
            rendered_host=f'[{hostname}]' if ':' in hostname else hostname
            url=f'https://{rendered_host}:{proxy_port}' if mode=='local' else f'https://{hostname}'
            return {'name':name,'url':url,'status':'starting','local_https_port':proxy_port if local_enabled else None,
                    'local_https_enabled':local_enabled,'public_https_enabled':public_enabled}
        except Exception:
            if proxy is not None:
                proxy.remove(force=True,v=False)
            if old_proxy and old_renamed:
                try:
                    old_proxy.rename(name)
                    old_proxy.start()
                except Exception:
                    pass
            raise


def register_host_setup(app,state,reauthenticate,confirmed):
    domains = Domains(state)
    base_allowed=set(app.config['ALLOWED_HOSTS'])
    app.extensions['dcc_domains']=domains
    app.config['ALLOWED_HOSTS'] = list(base_allowed | {v for k,v in domains.saved().items() if k in {'local','public'} and v})
    app.config['TRUSTED_HTTPS_HOSTS'] = [domains.saved().get('public')]
    from flask.sessions import SecureCookieSessionInterface
    from security import trusted_https_request
    class DomainSessionInterface(SecureCookieSessionInterface):
        def get_cookie_secure(self,application):
            return bool(application.config.get('SESSION_COOKIE_SECURE') or trusted_https_request(application))
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
            value = {'local':local_host(data.get('local')),'public':domain(data.get('public'))}
            domains.save(value)
            app.config['TRUSTED_HTTPS_HOSTS'] = [value.get('public')]
            # Rebuild the allowlist so removing a saved name revokes it immediately.
            app.config['ALLOWED_HOSTS'] = list(base_allowed | {v for v in value.values() if v})
        return jsonify(domains.public_settings())

    @app.get('/api/admin/https/status')
    def local_https_status():
        admin()
        saved=domains.saved()
        port=saved.get('local_https_port') or 9443
        return jsonify(local_enabled=bool(saved.get('local_https_enabled')),public_enabled=bool(saved.get('public_https_enabled')),
                       local_port=int(port),local_host=saved.get('local') or '127.0.0.1')

    @app.get('/api/admin/https/ca')
    def download_local_ca():
        import docker
        admin()
        client=docker.from_env(timeout=30)
        try:
            container=local_container(client)
            proxy=client.containers.get(domains.proxy_name())
            labels=(proxy.attrs.get('Config') or {}).get('Labels') or {}
            if labels.get(LABEL)!=container.name or not domains.saved().get('local_https_enabled'):
                abort(404,'Install local HTTPS before downloading its CA certificate')
            try:
                archive, _stat=proxy.get_archive('/data/caddy/pki/authorities/local/root.crt')
            except Exception as exc:
                raise ValueError('Local CA is not ready yet. Open the local HTTPS address once, then retry the download.') from exc
            with tarfile.open(fileobj=io.BytesIO(b''.join(archive)),mode='r:*') as tar:
                member=next((item for item in tar.getmembers() if item.isfile() and item.name.rsplit('/',1)[-1]=='root.crt'),None)
                if not member or member.size>128_000:
                    abort(404,'The local CA certificate is not ready yet; open the local HTTPS address once, then retry')
                stream=tar.extractfile(member)
                if stream is None:abort(404,'The local CA certificate is unavailable')
                data=stream.read()
                if b'-----BEGIN CERTIFICATE-----' not in data or b'-----END CERTIFICATE-----' not in data:
                    abort(404,'The local CA certificate is not valid PEM data')
                certificate=io.BytesIO(data)
            certificate.seek(0)
            return send_file(certificate,mimetype='application/x-x509-ca-cert',as_attachment=True,download_name='DCC-Web-local-root-CA.crt')
        finally:
            client.close()

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
        if action not in {'install','install-local','install-public','start','stop','remove'}:
            abort(404)
        data = request.get_json() or {}
        reauthenticate(data,second_factor=data.get('preview') is not True)
        hostname = domains.saved().get('public')
        mode='local' if action=='install-local' else 'public'
        target = digest({'domain':domains.saved().get(mode,''),'action':action,'name':domains.proxy_name()})
        if data.get('preview') is True:
            return jsonify(target=target,domain=domains.saved().get(mode,''),action=action,mode=mode)
        confirmed(data,'panel.proxy','workspace',target)
        client = docker.from_env(timeout=60)
        try:
            container = local_container(client)
            if action=='install':
                return jsonify(domains.provision(client,container,hostname,'public'))
            if action in {'install-local','install-public'}:
                hostname=domains.saved().get(mode,'')
                if mode=='local' and not hostname:hostname='127.0.0.1'
                return jsonify(domains.provision(client,container,hostname,mode))
            proxy = client.containers.get(domains.proxy_name())
            if proxy.attrs.get('Config',{}).get('Labels',{}).get(LABEL) != container.name:
                abort(409,'The extension does not belong to this Web container')
            if action in {'stop','remove'}:
                proxy.stop(timeout=10)
            if action=='remove':
                proxy.remove(v=False)  # Certificate volumes are deliberately preserved.
                domains.save({**domains.saved(),'local_https_enabled':False,'public_https_enabled':False})
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
