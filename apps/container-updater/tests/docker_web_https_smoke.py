"""Disposable real-Docker test: rollback and Web upgrade behind managed Caddy.

Run explicitly, not through unittest discovery. Uses synthetic credentials and
unique QA resources only. No existing containers, keys or volumes are modified.
"""
import base64
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
from updater import UpdateService


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


def main():
    client = docker.from_env()
    suffix = secrets.token_hex(5)
    name = 'dcc-web-update-qa-' + suffix
    proxy_name = 'dcc-web-https-' + suffix
    network_name = proxy_name + '-network'
    labels = {'dcc.qa': 'updater-https', 'io.dcc.web.proxy': name}
    volumes = []
    proxy = network = None
    runner = client.containers.get(os.environ['HOSTNAME']) if os.getenv('DCC_QA_IN_CONTAINER') else None
    old_image = 'ghcr.io/hattimon/dcc-web:0.1.7'
    target = 'ghcr.io/hattimon/dcc-web:0.1.8'
    service = UpdateService(client, wait_seconds=90)
    try:
        for image in (old_image, target, 'caddy:2'):
            client.images.pull(image)
        for ending in ('data', 'certs', 'config'):
            volumes.append(client.volumes.create(name=name+'-'+ending, labels=labels))
        web = client.containers.run(old_image, name=name, detach=True, labels=labels,
            environment={'DCC_WEB_CONTAINER_NAME': name},
            volumes={volumes[0].name: {'bind': '/data', 'mode': 'rw'}},
            ports={'8789/tcp': ('127.0.0.1', None)},
            read_only=True, tmpfs={'/tmp': 'size=64m,mode=1777'},
            cap_drop=['ALL'], cap_add=['SETUID', 'SETGID'])
        service._wait_until_healthy(web)
        old_id = web.id
        credential = re.search(rb'DCC_WEB_INITIAL_CREDENTIALS username=(\S+) password=(\S+)', web.logs())
        assert credential, 'Synthetic bootstrap account was not created'
        code = ('import base64;from state import State;from host_setup import Domains;'
                'd=Domains(State("/data"));d.save({"local":"127.0.0.1","public":""});'
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
        web.reload()
        inventory = client.containers.list(all=True, ignore_removed=True)
        assert service._unsupported_reason(web, inventory) is None
        assert service.automatic_dependency_blocker(web, inventory) is None
        # Inject an unhealthy replacement once and verify the real Docker
        # rollback restores the old container and the HTTPS DNS alias.
        with patch.object(service, '_wait_until_healthy', side_effect=RuntimeError('synthetic health failure')):
            try:
                service.update_one(web, target, _image_already_pulled=True)
            except RuntimeError as error:
                assert 'przywrócono poprzedni kontener' in str(error)
            else:
                raise AssertionError('Rollback was not exercised')
        web = client.containers.get(name)
        assert web.id == old_id
        service._wait_until_healthy(web)
        wait_for(login_page, 'HTTPS did not recover after rollback')
        service.update_one(web, target, _image_already_pulled=True)
        web = client.containers.get(name)
        assert web.id != old_id and web.attrs['Config']['Image'] == target
        assert next(m for m in web.attrs['Mounts'] if m['Destination']=='/data')['Name'] == volumes[0].name
        assert web.attrs['HostConfig']['ReadonlyRootfs'] is True
        assert 'dcc-web-upstream' in web.attrs['NetworkSettings']['Networks'][network_name]['Aliases']
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
        assert status == 200 and bootstrap['user']['role'] == 'admin' and bootstrap['version']=='0.1.8'
        status, _, _ = request('/static/app.css')
        assert status == 200
        proxy.reload()
        assert proxy.attrs['HostConfig']['PortBindings'] == bindings
        assert archive_file(proxy, '/data/caddy/pki/authorities/local/root.crt') == root
        print(json.dumps({'upgrade':'0.1.7 -> 0.1.8','rollback':True,'https_login':True,
            'same_caddy_container':True,'same_ca_and_port':True,'web_volume_preserved':True,
            'managed_alias_preserved':True,'automatic_update_eligible':True}))
    finally:
        if runner and network:
            try: network.disconnect(runner)
            except docker.errors.APIError: pass
        for container in client.containers.list(all=True, filters={'label':'dcc.qa=updater-https'}):
            if (container.attrs.get('Config',{}).get('Labels') or {}).get('io.dcc.web.proxy') == name:
                container.remove(force=True, v=False)
        if network: network.remove()
        for volume in reversed(volumes): volume.remove()
        client.close()


if __name__ == '__main__':
    main()
