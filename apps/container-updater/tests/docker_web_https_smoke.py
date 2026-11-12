"""Disposable real-Docker test: rollback and Web upgrade behind managed Caddy.

Run explicitly, not through unittest discovery. Uses synthetic credentials and
unique QA resources only. No existing containers, keys or volumes are modified.
"""
import argparse
import base64
from contextlib import closing
import http.client
import io
import json
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import sys
import tarfile
import time
from unittest.mock import patch
from urllib.parse import urlencode

import docker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from updater import UpdateService, load_catalog


# The real controller, socket, database and sidecar run in Docker. Substitute
# zrok's account and hosted HTTPS calls so the fixture needs no public domain.
SYNTHETIC_PROVIDER = """
from contextlib import closing
import io
import json
import tarfile
import time
import remote_maintenance
import web
import remote_access
from host_setup import local_container

start_control = remote_maintenance.start_control
def start_fixture(remote):
    token, identity, account = 'FixtureShare123', 'fixture-env', 'FixtureAccount123'
    occupied = True
    data = json.dumps({'ziti_identity': identity, 'zrok_token': account}).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        member = tarfile.TarInfo('.zrok2/environment.json')
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    def restore(sidecar, config):
        remote.stop(sidecar)
        sidecar.start()
        return buffer.getvalue()
    remote.restore = restore
    def reservation(sidecar, name):
        assert name == 'qa-fixture'
        value = {'reserved': True, 'namespaceToken': 'public', 'namespaceName': 'shares.zrok.io'}
        if occupied:
            value['shareToken'] = token
        return value
    remote.reservation = reservation
    def command(sidecar, args, **kwargs):
        if args[:3] == ['zrok2', 'list', 'shares']:
            return json.dumps({'shares': [{'shareToken': token, 'envZId': identity,
                'shareMode': 'public', 'backendMode': 'proxy', 'target': 'http://dcc-remote-panel:8791'}]}).encode()
        assert args[:2] == ['/bin/sh', '-c'] and kwargs['data'].startswith(b'qa-fixture ')
        assert not occupied
        return b''
    remote.command = command
    def unshare(env, api_token, share):
        nonlocal occupied
        assert (env, api_token, share) == (identity, account, token) and occupied
        occupied = False
        return 200
    remote_access.unshare = unshare
    remote_access.public_health = lambda origin: (502, '')
    def verify(route):
        assert not occupied
        route['verified'] = True
        remote.tunnel = 'active'
    remote.monitor = verify
    handle = remote.maintenance
    def maintenance(args):
        nonlocal occupied
        if args == ['fixture-ready']:
            return bool(remote.route and remote.route['verified'] and not occupied)
        if args == ['fixture-stop']:
            with remote.lock, closing(remote.client_factory()) as client:
                remote.recovery_next = time.monotonic() + 3600
                remote.stop(remote.container(client))
            return True
        if args not in (['seed'], ['seed-stopped']):
            return handle(args)
        owner = 'fixture-tunnel-owner'
        remote.state.execute('INSERT INTO users VALUES(?,?,?,?)', (owner, owner, 'unused', 'admin'))
        remote.state.execute('INSERT INTO mfa VALUES(?,?,?,?,?,?,?)', (owner, b'fixture', 1, -1, '[]', 0, ''))
        remote.save({'name': 'qa-fixture', 'origin': 'https://qa-fixture.shares.zrok.io', 'identity': 'fixture'})
        with closing(remote.client_factory()) as client:
            if args == ['seed']:
                occupied = False
                remote.enable(remote.container(client), owner, remote.epoch, resume_after_update=True)
            else:
                remote.recovery_next = time.monotonic() + 3600
            remote.remember_recovery(owner, remote.epoch, local_container(client).attrs['Image'],
                                     resume_after_restart=True, resume_after_update=True)
        return True
    remote.maintenance = maintenance
    start_control(remote)
remote_maintenance.start_control = start_fixture
web.main()
"""

PROJECT_PANEL = """
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket

class Panel(BaseHTTPRequestHandler):
    def do_GET(self):
        body = Path('/data/marker').read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

# Deliberately not on container localhost: Docker publishes the interface IP.
ThreadingHTTPServer((socket.gethostbyname(socket.gethostname()), 3000), Panel).serve_forever()
"""


def wait_for(check, description):
    for _ in range(120):
        try:
            return check()
        except Exception:
            time.sleep(.5)
    raise RuntimeError(description)


def archive_file(container, path):
    stream, _ = container.get_archive(path)
    with tarfile.open(fileobj=io.BytesIO(b''.join(stream))) as archive:
        return archive.extractfile(archive.getmembers()[0]).read()


def assert_tunnel_ready(service, panel):
    assert service._remote_update_control(panel, 'fixture-ready')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-image', default='ghcr.io/hattimon/dcc-web:0.1.7')
    parser.add_argument('--target-image', default='ghcr.io/hattimon/dcc-web:0.1.8')
    parser.add_argument('--expected-version', default='0.1.8')
    parser.add_argument('--local-target', action='store_true', help='Use an already-built release candidate')
    parser.add_argument('--expect-remote-access', action='store_true')
    parser.add_argument('--with-remote-access', action='store_true', help='Attach a stopped managed zrok sidecar')
    parser.add_argument('--with-tunnel-resume', action='store_true', help='Exercise active tunnel handoff with a synthetic provider and local target image')
    parser.add_argument('--with-legacy-stopped-tunnel', action='store_true',
                        help='Upgrade a released Web image with saved consent and a stopped tunnel')
    parser.add_argument('--verify-catalog', action='store_true', help='Require the official catalog to offer the target')
    parser.add_argument('--verify-release-candidate', action='store_true',
                        help='Use the checked-out catalog and exercise a running loopback-only project panel')
    args = parser.parse_args()
    if args.with_tunnel_resume and not args.local_target:
        parser.error('--with-tunnel-resume requires a local target')
    if args.with_legacy_stopped_tunnel and (not args.local_target or args.with_tunnel_resume):
        parser.error('--with-legacy-stopped-tunnel needs a local target and its own run')
    if args.verify_release_candidate and not (args.local_target and args.expect_remote_access):
        parser.error('--verify-release-candidate needs --local-target and --expect-remote-access')
    synthetic_tunnel = args.with_tunnel_resume or args.with_legacy_stopped_tunnel
    args.with_remote_access = args.with_remote_access or synthetic_tunnel
    args.expect_remote_access = args.expect_remote_access or args.with_remote_access
    client = docker.from_env()
    suffix = secrets.token_hex(5)
    name = 'dcc-web-update-qa-' + suffix
    proxy_name = 'dcc-web-https-' + suffix
    network_name = proxy_name + '-network'
    labels = {'dcc.qa': 'updater-https', 'io.dcc.web.proxy': name}
    volumes = []
    proxy = network = project = project_network = project_data = None
    remote_name = None
    runner = client.containers.get(os.environ['HOSTNAME']) if os.getenv('DCC_QA_IN_CONTAINER') else None
    old_image, target = args.old_image, args.target_image
    qa_images = []
    service = UpdateService(client, wait_seconds=90)
    try:
        for image in ('caddy:2',) if args.with_tunnel_resume else (old_image, 'caddy:2'):
            client.images.pull(image)
        if args.local_target:
            client.images.get(target)
        else:
            client.images.pull(target)
        command = None
        if args.with_tunnel_resume:
            old_image = 'ghcr.io/hattimon/dcc-web:qa-old-' + suffix
            dockerfile = io.BytesIO(f'FROM {target}\nLABEL dcc.qa.variant=old\n'.encode())
            client.images.build(fileobj=dockerfile, tag=old_image, rm=True)
            qa_images.append(old_image)
            new_image = 'ghcr.io/hattimon/dcc-web:qa-new-' + suffix
            client.images.get(target).tag(new_image)
            qa_images.append(new_image)
            target = new_image
        if synthetic_tunnel:
            command = ['python', '-c', SYNTHETIC_PROVIDER, '--host', '0.0.0.0', '--allow-lan', '--data', '/data']
        for ending in ('data', 'certs', 'config'):
            volumes.append(client.volumes.create(name=name+'-'+ending, labels=labels))
        web_mounts = {volumes[0].name: {'bind': '/data', 'mode': 'rw'}}
        if args.expect_remote_access:
            web_mounts['/var/run/docker.sock'] = {'bind': '/var/run/docker.sock', 'mode': 'rw'}
        with socket.socket() as port_probe:
            port_probe.bind(('127.0.0.1', 0))
            web_port = port_probe.getsockname()[1]
        web = client.containers.run(old_image, name=name, detach=True, labels=labels,
            command=command,
            environment={'DCC_WEB_CONTAINER_NAME': name},
            volumes=web_mounts, ports={'8789/tcp': ('127.0.0.1', web_port)},
            read_only=True, tmpfs={'/tmp': 'size=64m,mode=1777'},
            cap_drop=['ALL'], cap_add=['SETUID', 'SETGID'])
        try:
            service._wait_until_healthy(web)
        except RuntimeError as error:
            failures = re.findall(rb'(?m)^([A-Za-z]+(?:Error|Exception)):', web.logs(tail=30))
            kind = failures[-1].decode() if failures else 'unknown'
            raise RuntimeError(f'Fixture Web failed at startup ({kind})') from error
        old_id = web.id
        credential = re.search(rb'DCC_WEB_INITIAL_CREDENTIALS username=(\S+) password=(\S+)', web.logs())
        assert credential, 'Synthetic bootstrap account was not created'
        code = ('import base64;from state import State;from host_setup import Domains;'
                'd=Domains(State("/data"));d.save({"local":"127.0.0.1","public":"",'
                '"panel_proxy_enabled":True});'
                'print(base64.b64encode(d._proxy_config(d.saved(),True,False,d.proxy_token())).decode())')
        result = web.exec_run(['python', '-c', code], user='10001:10001')
        assert result.exit_code == 0, 'Cannot prepare synthetic HTTPS settings'
        config = base64.b64decode(result.output.strip())
        # The old image lacks default_sni for IP clients; keep that known fix in
        # the proxy fixture so the test isolates the Updater replacement path.
        if b'default_sni' not in config:
            config = config.replace(b'{\n', b'{\n default_sni 127.0.0.1\n', 1)
        network = client.networks.create(network_name, driver='bridge', labels=labels)
        network.connect(web, aliases=['dcc-web-upstream'])
        proxy = client.containers.create('caddy:2', name=proxy_name, labels=labels,
            network=network_name, ports={'9443/tcp': ('127.0.0.1', None)},
            volumes={volumes[1].name: {'bind':'/data','mode':'rw'},
                     volumes[2].name: {'bind':'/config','mode':'rw'}},
            environment={'XDG_DATA_HOME':'/data','XDG_CONFIG_HOME':'/config'},
            cap_drop=['ALL'], cap_add=['NET_BIND_SERVICE'],
            security_opt=['no-new-privileges:true'],
            command=['caddy','run','--config','/config/Caddyfile','--adapter','caddyfile'])
        with io.BytesIO() as data:
            with tarfile.open(fileobj=data, mode='w') as archive:
                member = tarfile.TarInfo('Caddyfile'); member.size = len(config)
                archive.addfile(member, io.BytesIO(config))
            proxy.put_archive('/config', data.getvalue())
        proxy.start(); proxy.reload(); web.reload()
        bindings = proxy.attrs['HostConfig']['PortBindings']
        published = proxy.attrs['NetworkSettings']['Ports']['9443/tcp'][0]['HostPort']
        root = wait_for(lambda: archive_file(proxy, '/data/caddy/pki/authorities/local/root.crt'), 'Missing QA CA')
        context = ssl.create_default_context(cadata=root.decode())
        origin = 'https://127.0.0.1:' + published

        def request(path, method='GET', body=None, headers=None):
            if runner:
                network.connect(runner)
            try:
                connection = http.client.HTTPSConnection('127.0.0.1', int(published), context=context, timeout=8)
                if runner:
                    proxy.reload()
                    address = proxy.attrs['NetworkSettings']['Networks'][network_name]['IPAddress']
                    connection.connect = lambda: setattr(connection, 'sock', context.wrap_socket(
                        socket.create_connection((address, 9443), timeout=8), server_hostname='127.0.0.1'))
                connection.request(method, path, body, {'Host':'127.0.0.1:'+published, **(headers or {})})
                response = connection.getresponse()
                status, values, content = response.status, dict(response.getheaders()), response.read()
                connection.close()
                return status, values, content
            finally:
                if runner:
                    network.disconnect(runner)

        def login_page():
            status, headers, body = request('/login')
            assert status == 200
            return headers, body

        wait_for(login_page, 'Old Web HTTPS does not respond')
        if args.verify_release_candidate:
            project_network = client.networks.create(name+'-project', driver='bridge')
            project_data = client.volumes.create(name=name+'-project-data')
            project = client.containers.run(target, name=name+'-project-panel', detach=True,
                entrypoint=['python'], command=['-u','-c',
                    "from pathlib import Path; Path('/data/marker').write_text('preserved-project-data')\n"
                    + PROJECT_PANEL],
                network=project_network.name, ports={'3000/tcp':('127.0.0.1',None)},
                volumes={project_data.name:{'bind':'/data','mode':'rw'}},
                healthcheck={'test':['NONE']})
            project.reload()
            project_started = project.attrs['State']['StartedAt']
            project_port = project.attrs['NetworkSettings']['Ports']['3000/tcp'][0]['HostPort']

            def project_ready():
                with closing(http.client.HTTPConnection('127.0.0.1',int(project_port),timeout=3)) as conn:
                    conn.request('GET','/')
                    assert conn.getresponse().read()==b'preserved-project-data'
                return True

            wait_for(project_ready, 'Original project panel did not respond on host loopback')
        if args.with_remote_access:
            code = """import sys
sys.path.insert(0, "/opt/dcc")
from contextlib import closing
from flask import Flask
from state import State
from remote_access import RemoteAccess, local_container
remote = RemoteAccess(Flask(__name__), State("/data"))
"""
            command = ['/usr/local/bin/dcc-web-entrypoint', 'python', '-c']
            result = web.exec_run([*command, code + 'print(remote.name)'])
            match = re.search(rb'(?m)^dcc-remote-access-[a-f0-9]{16}$', result.output)
            assert result.exit_code == 0 and match, result.output.decode(errors='replace')[-1200:]
            remote_name = match[0].decode()
            remote_panel = remote_name + '-panel'
            result = web.exec_run([*command, code + """
with closing(remote.client_factory()) as client:
    remote.install(client, local_container(client))
"""])
            assert result.exit_code == 0, result.output.decode(errors='replace')[-1200:]
            remote_id = client.containers.get(remote_name).id
            if args.with_tunnel_resume:
                assert service._remote_update_control(web, 'seed')
                wait_for(lambda: assert_tunnel_ready(service, web), 'Synthetic tunnel was not authorized')
            elif args.with_legacy_stopped_tunnel:
                assert service._remote_update_control(web, 'seed-stopped')
                assert not service._remote_update_control(web, 'status')
        web.reload()
        inventory = client.containers.list(all=True, ignore_removed=True)
        assert service.update_blocker(web, inventory) is None
        assert service.automatic_dependency_blocker(web, inventory) is None
        if args.verify_catalog:
            apps = load_catalog()
            candidate = service.inspect_container(web, apps, all_containers=inventory)
            assert candidate['update_available'] and candidate['supported'], candidate
            assert candidate['target_image'] == target, candidate
            if args.expect_remote_access:
                entries = [app for app in apps if app['name'] == 'DCC Remote Access']
                assert len(entries) == 1 and entries[0]['category'] == 'DCC', entries
        if args.verify_release_candidate:
            catalog_file = Path(__file__).resolve().parents[3] / 'dcc-catalog.json'
            apps = json.loads(catalog_file.read_text(encoding='utf-8'))['apps']
            candidate = service.inspect_container(web, apps, all_containers=inventory)
            assert candidate['update_available'] and candidate['supported'], candidate
            assert candidate['target_image'] == target, candidate
        # Inject an unhealthy replacement once and verify the real Docker
        # rollback restores the old container and the HTTPS DNS alias.
        wait_for_health = service._wait_until_healthy

        def reject_replacement(item):
            if item.id == old_id:
                return wait_for_health(item)
            raise RuntimeError('synthetic health failure')

        with patch.object(service, '_wait_until_healthy', side_effect=reject_replacement):
            try:
                service.update_one(web, target, _image_already_pulled=True)
            except RuntimeError as error:
                assert 'przywrócono poprzedni kontener' in str(error)
            else:
                raise AssertionError('Rollback was not exercised')
        web = client.containers.get(name)
        assert web.id == old_id
        if remote_name:
            assert 'dcc-remote-panel' in web.attrs['NetworkSettings']['Networks'][remote_panel]['Aliases']
        service._wait_until_healthy(web)
        wait_for(login_page, 'HTTPS did not recover after rollback')
        if args.with_tunnel_resume:
            wait_for(lambda: assert_tunnel_ready(service, web), 'Tunnel did not resume after rollback')
        if synthetic_tunnel:
            assert service._remote_update_control(web, 'fixture-stop')
            assert client.containers.get(remote_name).attrs['State']['Status'] in {'exited', 'created'}
        service.update_one(web, target, _image_already_pulled=True)
        web = client.containers.get(name)
        assert web.id != old_id and web.attrs['Config']['Image'] == target
        assert next(m for m in web.attrs['Mounts'] if m['Destination']=='/data')['Name'] == volumes[0].name
        assert web.attrs['NetworkSettings']['Ports']['8789/tcp'][0]['HostPort'] == str(web_port)
        assert web.attrs['HostConfig']['ReadonlyRootfs'] is True
        assert 'dcc-web-upstream' in web.attrs['NetworkSettings']['Networks'][network_name]['Aliases']
        if remote_name:
            assert 'dcc-remote-panel' in web.attrs['NetworkSettings']['Networks'][remote_panel]['Aliases']
            sidecar = client.containers.get(remote_name)
            assert sidecar.id == remote_id
            if synthetic_tunnel:
                wait_for(lambda: assert_tunnel_ready(service, web), 'Tunnel did not resume after successful replacement')
                web.restart(timeout=12)
                service._wait_until_healthy(web)
                wait_for(lambda: assert_tunnel_ready(service, web), 'Tunnel did not recover after restarting Web')
            else:
                assert sidecar.attrs['State']['Status'] == 'created'
        headers, page = wait_for(login_page, 'New Web HTTPS does not respond')
        assert 'Secure' in headers['Set-Cookie']
        csrf = re.search(rb'name="csrf" value="([^"]+)"', page)[1].decode()
        cookie = headers['Set-Cookie'].split(';',1)[0]
        form = urlencode({'csrf':csrf,'username':credential[1].decode(),'password':credential[2].decode()})
        status, headers, _ = request('/login', 'POST', form,
            {'Content-Type':'application/x-www-form-urlencoded','Origin':origin,'Cookie':cookie})
        assert status in (302,303), 'HTTPS login rejected after update: '+str(status)
        cookie = headers['Set-Cookie'].split(';',1)[0]
        status, _, body = request('/api/bootstrap', headers={'Cookie':cookie})
        bootstrap = json.loads(body)
        assert status == 200 and bootstrap['user']['role'] == 'admin' and bootstrap['version'] == args.expected_version
        if args.verify_release_candidate:
            status, _, page = request('/', headers={'Cookie':cookie})
            assert status == 200
            csrf = re.search(rb'name="csrf-token" content="([^"]+)"', page)[1].decode()
            status, _, body = request('/api/containers', headers={'Cookie':cookie})
            assert status == 200
            entry = next(row for row in json.loads(body)['containers'] if row['ID']==project.id)
            link = next(link for link in entry['PanelLinks'] if link['container_port']==3000)
            assert link['url']==f'http://127.0.0.1:{project_port}' and link['loopback_only']
            endpoint = f'/api/panels/local/{project.id}/{link["panel_id"]}/request'
            status, _, body = request(endpoint, 'POST', '{"path":"/"}',
                {'Content-Type':'application/json','Origin':origin,'Cookie':cookie,'X-CSRF-Token':csrf})
            assert status==200, (status,body)
            assert base64.b64decode(json.loads(body)['body'])==b'preserved-project-data'
            assert client.containers.get(project.name).id==project.id
            project.reload()
            assert project.attrs['State']['Running'] and project.attrs['State']['StartedAt']==project_started
            assert project_network.name not in web.attrs['NetworkSettings']['Networks']
            assert proxy.attrs['State']['Running']
            print('Catalog offered the release and the preserved project panel opened over the isolated relay.')
        if args.expect_remote_access:
            status, _, body = request('/api/admin/remote-access', headers={'Cookie':cookie})
            remote = json.loads(body)
            expected_state = 'active' if synthetic_tunnel else 'configure' if remote_name else 'not-installed'
            assert status == 200 and remote['available'] and remote['state'] == expected_state, remote
            if synthetic_tunnel:
                assert remote['restart_resume_allowed'], remote
            status, _, body = request('/static/views/remote_access.js')
            assert status == 200 and 'Zdalny dostęp przez Internet'.encode() in body
            if args.verify_catalog:
                status, _, page = request('/', headers={'Cookie':cookie})
                assert status == 200
                csrf = re.search(rb'name="csrf-token" content="([^"]+)"', page)[1].decode()
                status, _, body = request('/api/catalog/refresh', 'POST', '{}',
                    {'Content-Type':'application/json','Origin':origin,'Cookie':cookie,'X-CSRF-Token':csrf})
                assert status == 202, status
                job = json.loads(body)['id']

                def refreshed_catalog():
                    status, _, result = request('/api/jobs/'+job, headers={'Cookie':cookie})
                    assert status == 200 and json.loads(result)['status'] == 'success'
                    return json.loads(result)

                refresh = wait_for(refreshed_catalog, 'Catalog refresh did not complete')
                official = next(source for source in refresh['result'] if source['id'] == 'official')
                assert official['checked'] > 0 and not official['error'], official
            status, _, body = request('/api/catalog?category=DCC', headers={'Cookie':cookie})
            catalog = json.loads(body)
            assert status == 200 and catalog['categories'][:4] == ['all', 'installed', 'DCC', 'AI']
            cards = [app for app in catalog['apps'] if app['name'] == 'DCC Remote Access']
            assert len(cards) == 1 and cards[0]['engines'] == ['dcc-web-managed'], cards
        status, _, _ = request('/static/app.css')
        assert status == 200
        proxy.reload()
        assert proxy.attrs['HostConfig']['PortBindings'] == bindings
        assert archive_file(proxy, '/data/caddy/pki/authorities/local/root.crt') == root
        print(json.dumps({'old_image':old_image,'new_image':target,'rollback':True,'https_login':True,
            'same_caddy_container':True,'same_ca_and_port':True,'web_volume_preserved':True,
            'same_http_port':True,'managed_alias_preserved':True,'automatic_update_eligible':True,
            'remote_access_verified':args.expect_remote_access,'remote_network_preserved':bool(remote_name),
            'synthetic_tunnel_resumed':synthetic_tunnel,
            'legacy_stopped_tunnel_recovered':args.with_legacy_stopped_tunnel,
            'official_catalog_verified':args.verify_catalog}))
    finally:
        if project:
            project.remove(force=True, v=False)
        if project_network:
            project_network.remove()
        if project_data:
            project_data.remove()
        if runner and network:
            try: network.disconnect(runner)
            except docker.errors.APIError: pass
        for container in client.containers.list(all=True, filters={'label':'dcc.qa=updater-https'}):
            if (container.attrs.get('Config',{}).get('Labels') or {}).get('io.dcc.web.proxy') == name:
                container.remove(force=True, v=False)
        if remote_name:
            try:
                client.containers.get(remote_name).remove(force=True, v=False)
            except docker.errors.NotFound:
                pass
            for suffix in ('-panel', '-egress'):
                try:
                    client.networks.get(remote_name + suffix).remove()
                except docker.errors.NotFound:
                    pass
        if network: network.remove()
        for volume in reversed(volumes): volume.remove()
        for image in reversed(qa_images): client.images.remove(image, force=True)
        client.close()


if __name__ == '__main__':
    main()
