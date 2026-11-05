"""Code passed to the disposable DCC Web Docker smoke container."""
INSIDE = r"""
from contextlib import closing
import docker
import ipaddress
import os
import sys
import time
import requests

sys.path.insert(0, "/opt/dcc")
from remote_access import IMAGE, LABEL, RemoteAccess
from state import State
from werkzeug.security import generate_password_hash
from flask import Flask

base = 'http://127.0.0.1:8789'
for _ in range(60):
    try:
        if requests.get(base+'/api/health', timeout=1).ok:
            break
    except requests.RequestException:
        pass
    time.sleep(1)
else:
    raise AssertionError('QA panel not ready')
state = State('/data')
account = state.rows('SELECT id,name FROM users WHERE role=?', ('admin',))[0]
password = 'fixture-dcc-remote-access-4488'
state.execute('UPDATE users SET password=? WHERE id=?', (generate_password_hash(password), account['id']))
profile_id = 'fixture-local-docker'
state.save_profile(profile_id, {'name':'Fixture Docker','kind':'local','permissions':['read','install']})
state.execute('DELETE FROM profiles WHERE id=?', ('local',))
session = requests.Session()
login = session.get(base+'/login').text
import re
csrf = re.search(r'name="csrf" value="([^"]+)"', login)[1]
assert session.post(base+'/login', data={'csrf':csrf,'username':account['name'],'password':password},allow_redirects=False).status_code == 302
index = session.get(base+'/').text
csrf = re.search(r'name="csrf-token" content="([^"]+)"',index)[1]
headers = {'X-CSRF-Token':csrf}

def api(path, data=None):
    if data is None:
        response = session.get(base+'/api/'+path, params={'profile': profile_id}, timeout=60)
    else:
        response = session.post(base+'/api/'+path, json={'profile': profile_id, **data}, headers=headers, timeout=60)
    assert response.ok, (path, response.status_code, response.json().get('error'))
    return response.json()

def action(name, *, expected_error=None, **options):
    token = api('confirmations', {'action':'remote-access.'+name,'target':'dcc-remote-access'})['confirmation']
    result = api('admin/remote-access/'+name, {'confirmation':token, 'current_password':password, **options})
    if 'id' not in result:
        return
    for _ in range(180):
        job = api('jobs/'+result['id'])
        if job['status'] != 'running':
            if expected_error:
                assert job['status'] == 'error' and job['error'] == expected_error, (name, job)
            else:
                assert job['status'] == 'success', (name, job.get('error'))
            return
        time.sleep(0.5)
    raise AssertionError('QA job did not finish')

initial = api('admin/remote-access')
assert initial['available'] and initial['state']=='not-installed', initial
catalog = api('catalog?category=DCC&q=DCC%20Remote%20Access')['apps']
assert [app['name'] for app in catalog] == ['DCC Remote Access']
action('install')
# Input validation returns the real job error before contacting zrok.
action('configure', account_token='invalid/token', expected_error='Enter a valid zrok account token.')
remote = RemoteAccess(Flask(__name__), state)
with closing(docker.DockerClient(base_url='unix:///var/run/docker.sock',timeout=20)) as client:
    sidecar = client.containers.get(remote.name)
    first_id = sidecar.id
    assert sidecar.attrs['Config']['Labels'][LABEL] == remote.owner
    remote.validate_container(sidecar)
    assert sidecar.attrs['State']['Status'] == 'created'
    assert client.networks.get(remote.ingress).attrs['Internal']
    assert not client.networks.get(remote.egress).attrs['Internal']
    action('install')
    assert client.containers.get(remote.name).id == first_id
    # Exercise a real Docker network migration using only a synthetic RFC2544
    # address; never route a user's actual LAN or saved profile through the test.
    old_network = client.networks.get(remote.ingress)
    old_subnet = ipaddress.ip_network(old_network.attrs['IPAM']['Config'][0]['Subnet'])
    fixture_host = str(old_subnet.network_address + 2)
    state.save_profile('fixture-remote-lan', {
        'name':'Synthetic Remote LAN', 'kind':'ssh', 'host':fixture_host,
        'username':'fixture', 'port':22, 'permissions':['read'],
    })
    assert remote.repair_panel_network(client, panel=client.containers.get(os.environ['DCC_WEB_CONTAINER_NAME']))
    new_network = client.networks.get(remote.ingress)
    new_subnet = ipaddress.ip_network(new_network.attrs['IPAM']['Config'][0]['Subnet'])
    assert new_subnet != old_subnet and ipaddress.ip_address(fixture_host) not in new_subnet
    sidecar = client.containers.get(remote.name)
    assert sidecar.id == first_id
    assert set(sidecar.attrs['NetworkSettings']['Networks']) == {remote.ingress, remote.egress}
    remote.validate_container(sidecar)
    sidecar.start()
    result = sidecar.exec_run(['sh','-c','id -u; test ! -e /var/run/docker.sock; test ! -e /data; test ! -e /mnt/dcc-ssh'])
    assert result.exit_code == 0 and result.output.strip() == b'2171'
    rejected = sidecar.exec_run(['curl','--max-time','8','-sS','-o','/dev/null','-w','%{http_code}',
                                 '-H','Host: localhost','http://dcc-remote-panel:8791/api/health'])
    assert rejected.exit_code == 0 and rejected.output.strip() == b'400', rejected
    action('disable')
    sidecar.reload()
    assert not sidecar.attrs['State']['Running']
action('uninstall',keep_data=True)
assert api('admin/remote-access')['state'] == 'not-installed'
assert api('health')['status'] == 'ok'
print('Remote Access Docker QA passed: custom profile installation, workspace job polling, idempotency, private ingress, UID/mounts, stop and uninstall.')
"""
