"""Real loopback HTTP, SSE and WebSocket fixtures; no user Docker/SSH data."""
import base64
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import paramiko
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cryptography.fernet import Fernet
from panel_proxy import _socket, safe_path
from web import create_app
from fixtures import FakeBackend

CONTAINER='a'*64


class PanelFixture(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def respond(self,data,status=200,content_type='application/json',headers=None):
        raw=data if isinstance(data,bytes) else json.dumps(data).encode()
        self.send_response(status);self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(raw)))
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path=='/chunked':
            self.send_response(200)
            self.send_header('Transfer-Encoding','chunked')
            self.send_header('Content-Type','text/plain')
            self.end_headers()
            self.wfile.write(b'5\r\nhello\r\n0\r\n\r\n')
            return
        if self.path=='/ws':
            import websocket
            accept=base64.b64encode(hashlib.sha1((self.headers['Sec-WebSocket-Key']+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            self.send_response(101);self.send_header('Upgrade','websocket');self.send_header('Connection','Upgrade');self.send_header('Sec-WebSocket-Accept',accept);self.end_headers()
            ws=websocket.WebSocket();ws.sock=self.connection;ws.connected=True
            try:
                while True:
                    opcode,data=ws.recv_data()
                    if opcode==websocket.ABNF.OPCODE_CLOSE:break
                    frame=websocket.ABNF.create_frame(data,opcode);frame.mask_value=0;ws.send_frame(frame)
            except Exception:pass
            return
        if self.path=='/events':
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Connection','close');self.end_headers()
            try:
                for i in range(100):
                    self.wfile.write(f'data: tick-{i}\n\n'.encode());self.wfile.flush();time.sleep(.1)
            except (OSError,ConnectionError):pass
            self.close_connection=True;return
        if self.path=='/redirect':return self.respond(b'',302,headers={'Location':'/echo'})
        if self.path=='/external':return self.respond(b'',302,headers={'Location':'http://169.254.169.254/latest/meta-data/'})
        if self.path=='/cookie':return self.respond({'ok':True},headers={'Set-Cookie':'service_login=fixture-cookie; Path=/; HttpOnly'})
        if self.path=='/large':return self.respond(b'x'*1024,content_type='application/octet-stream')
        if self.path=='/style.css':return self.respond(b'body { background: rgb(242, 247, 250); }',content_type='text/css')
        if self.path=='/modules':return self.respond(b'<h1 id="module">Loading module</h1><script type="module" src="/entry.js"></script>',content_type='text/html')
        if self.path=='/entry.js':return self.respond(b"import {answer} from './dep.js';const value=await import('./dynamic.js');document.querySelector('#module').textContent='ESM '+answer+' '+value.value;const img=new Image();img.id='module-image';img.src=new URL('./image.svg',import.meta.url);document.body.append(img);",content_type='text/javascript')
        if self.path=='/dep.js':return self.respond(b"import {extra} from './cycle.js';export const answer=40+extra();",content_type='text/javascript')
        if self.path=='/cycle.js':return self.respond(b"import {answer} from './dep.js';export function extra(){return 2;}",content_type='text/javascript')
        if self.path=='/dynamic.js':return self.respond(b"export const value='dynamic';",content_type='text/javascript')
        if self.path=='/image.svg':return self.respond(b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><rect width="24" height="24" fill="teal"/></svg>',content_type='image/svg+xml')
        if self.path=='/app.js':return self.respond(b"document.querySelector('#api').textContent='loading';fetch('/echo').then(r=>r.json()).then(v=>document.querySelector('#api').textContent=v.path);const s=new WebSocket('ws://'+JSON.parse(document.getElementById('dcc-panel-config').textContent).origin.split('://')[1]+'/ws');s.onopen=()=>s.send('live-echo');s.onmessage=e=>document.querySelector('#ws').textContent=e.data;const events=new EventSource('/events');events.onmessage=e=>document.querySelector('#sse').textContent=e.data;document.querySelector('#isolation').textContent=(()=>{try{return parent.document.title}catch{return 'isolated'}})();",content_type='text/javascript')
        if self.path=='/':
            return self.respond(b'<!doctype html><html lang="pl" data-theme="fixture-theme"><head><title>Isolated live panel</title><link rel="stylesheet" href="/style.css"></head><body data-fixture-body="preserved"><h1>Panel fixture</h1><img src="/image.svg"><div id="api"></div><div id="ws"></div><div id="sse"></div><div id="isolation"></div><form method="post" action="/form"><input name="value" value="sample"><button>Submit panel</button></form><script src="/app.js" defer></script></body></html>',content_type='text/html; charset=utf-8')
        return self.respond({'path':self.path,'cookie':self.headers.get('Cookie',''),'authorization':self.headers.get('Authorization',''),'origin':self.headers.get('Origin',''),'dcc_marker':self.headers.get('X-DCC-Web-Internal-TLS','')})
    def do_POST(self):
        raw=self.rfile.read(int(self.headers.get('Content-Length','0')))
        if self.path=='/form':return self.respond(b'<h1 id="form-result">Form saved</h1><a href="/">Back</a>',content_type='text/html')
        return self.respond({'method':'POST','body':base64.b64encode(raw).decode(),'type':self.headers.get('Content-Type')})
    do_PUT=do_POST
    do_PATCH=do_POST
    do_DELETE=do_POST


class SimulatedSSHChannel:
    """In-memory SSH transport with Paramiko's read1-less ChannelFile."""
    def __init__(self, response):
        self.response=response
        self.position=0
        self.closed=False

    def makefile(self, mode='r', bufsize=-1):
        return paramiko.ChannelFile(self,mode,bufsize)

    def sendall(self, value):pass
    def recv(self, size):
        value=self.response[self.position:self.position+size]
        self.position+=len(value)
        return value
    def settimeout(self, value):pass
    def shutdown(self, value):self.closed=True
    def close(self):self.closed=True


class InMemoryPanelSocket:
    """HTTP/SSE/WebSocket fixture for Windows runners that forbid loopback TCP.

    The real socket integration is still exercised whenever the OS permits it.
    This fixture models the upstream byte protocol, leaving the gateway's
    http.client, header, cookie, redirect and websocket code under test.
    """

    def __init__(self):
        self.cv = threading.Condition()
        self.incoming = bytearray()
        self.outgoing = bytearray()
        self.timeout = 8
        self.closed = False
        self.websocket = False

    def settimeout(self, value):
        self.timeout = value

    def gettimeout(self):
        return self.timeout

    def send(self, data):
        self.sendall(data)
        return len(data)

    def sendall(self, data):
        with self.cv:
            self.incoming.extend(data)
            if self.websocket:
                self._ws_frames()
            elif b'\r\n\r\n' in self.incoming:
                header, remainder = self.incoming.split(b'\r\n\r\n', 1)
                lines = header.decode('iso-8859-1').split('\r\n')
                method, path, _ = lines[0].split(' ', 2)
                headers = dict(line.split(': ', 1) for line in lines[1:] if ': ' in line)
                length = int(headers.get('Content-Length', '0'))
                if len(remainder) >= length:
                    self.incoming = bytearray(remainder[length:])
                    self._handle(method, path, headers, remainder[:length])
            self.cv.notify_all()

    def _reply(self, body=b'', status=200, content_type='application/json', headers=None):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        reason = {200: 'OK', 302: 'Found', 101: 'Switching Protocols'}[status]
        fields = {'Content-Type': content_type, 'Content-Length': str(len(body))}
        fields.update(headers or {})
        payload = f'HTTP/1.1 {status} {reason}\r\n'.encode()
        payload += b''.join(f'{key}: {value}\r\n'.encode() for key, value in fields.items())
        self.outgoing.extend(payload + b'\r\n' + body)

    def _handle(self, method, path, headers, data):
        if path == '/ws':
            import hashlib
            key = headers['Sec-WebSocket-Key']
            accept = base64.b64encode(hashlib.sha1(
                (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            self.outgoing.extend(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n'
                                  'Connection: Upgrade\r\nSec-WebSocket-Accept: ' + accept +
                                  '\r\n\r\n').encode())
            self.websocket = True
            self._ws_frames()
        elif path == '/events':
            self.outgoing.extend(b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                                 b'Connection: close\r\n\r\ndata: tick-0\n\n')
        elif path == '/chunked':
            self.outgoing.extend(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n'
                                 b'Content-Type: text/plain\r\n\r\n5\r\nhello\r\n0\r\n\r\n')
        elif path == '/redirect':
            self._reply(b'', 302, headers={'Location': '/echo'})
        elif path == '/external':
            self._reply(b'', 302, headers={'Location': 'http://169.254.169.254/latest/meta-data/'})
        elif path == '/cookie':
            self._reply({'ok': True}, headers={'Set-Cookie': 'service_login=fixture-cookie; Path=/; HttpOnly'})
        elif path == '/large':
            self._reply(b'x' * 1024, content_type='application/octet-stream')
        elif path == '/':
            self._reply(b'<html lang="pl"><body>Fixture</body></html>', content_type='text/html')
        elif path == '/form':
            self._reply(b'<h1>Form saved</h1>', content_type='text/html')
        elif method != 'GET':
            self._reply({'method': method, 'body': base64.b64encode(data).decode(),
                         'type': headers.get('content-type', headers.get('Content-Type'))})
        else:
            self._reply({'path': path, 'cookie': headers.get('Cookie', ''),
                         'authorization': headers.get('authorization', headers.get('Authorization', '')),
                         'origin': headers.get('Origin', ''),
                         'dcc_marker': headers.get('X-DCC-Web-Internal-TLS', '')})

    def _ws_frames(self):
        while len(self.incoming) >= 2:
            kind = self.incoming[0] & 15
            length = self.incoming[1] & 127
            at = 2
            if length == 126:
                if len(self.incoming) < 4:
                    return
                length = int.from_bytes(self.incoming[2:4], 'big')
                at = 4
            elif length == 127:
                if len(self.incoming) < 10:
                    return
                length = int.from_bytes(self.incoming[2:10], 'big')
                at = 10
            masked = bool(self.incoming[1] & 128)
            if len(self.incoming) < at + (4 if masked else 0) + length:
                return
            mask = self.incoming[at:at + 4] if masked else b''
            at += 4 if masked else 0
            payload = bytes(self.incoming[at + i] ^ mask[i % 4] if masked else self.incoming[at + i]
                            for i in range(length))
            del self.incoming[:at + length]
            if kind == 8:
                self.closed = True
                return
            size = (bytes([length]) if length < 126 else
                    b'\x7e' + length.to_bytes(2, 'big') if length < 65536 else
                    b'\x7f' + length.to_bytes(8, 'big'))
            self.outgoing.extend(bytes([0x80 | kind]) + size + payload)

    def recv(self, size):
        with self.cv:
            if not self.outgoing and not self.closed:
                notified = self.cv.wait(timeout=self.timeout)
                if not notified and not self.closed and not self.outgoing:
                    raise socket.timeout('In-memory panel timed out')
            if not self.outgoing:
                return b''
            data = bytes(self.outgoing[:size])
            del self.outgoing[:size]
            return data

    def shutdown(self, _how):
        self.close()

    def close(self):
        with self.cv:
            self.closed = True
            self.cv.notify_all()


class PanelBackend(FakeBackend):
    panel_entries=[]
    def containers(self):return copy.deepcopy(self.panel_entries)


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = None
        cls.port = 33789
        try:
            server = ThreadingHTTPServer(('127.0.0.1', 0), PanelFixture)
            cls.port = server.server_port
            with socket.create_connection(('127.0.0.1', cls.port), timeout=1):
                pass
            cls.server = server
            threading.Thread(target=server.serve_forever, daemon=True).start()
        except OSError:
            if 'server' in locals():
                server.server_close()
    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.shutdown()
            cls.server.server_close()
    def setUp(self):
        if not self.server:
            virtual = patch('panel_proxy._socket', side_effect=lambda profile, link: (InMemoryPanelSocket(), None))
            virtual.start()
            self.addCleanup(virtual.stop)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.config={'TESTING':True,'DATA_DIR':self.temp.name,'MASTER_KEY':Fernet.generate_key(),
                     'ALLOWED_HOSTS':{'localhost','dcc.example.com','8.8.4.4','192.168.1.3'}}
        self.app=create_app(self.config,backend_factory=PanelBackend)
        self.state=self.app.extensions['dcc_state'];self.domains=self.app.extensions['dcc_domains']
        self.domains.save({'panel_proxy_enabled':True})
        self.state.save_profile('local',{'name':'Synthetic Docker','kind':'local','panel_host':'127.0.0.1','permissions':['read']})
        PanelBackend.panel_entries=[{'ID':CONTAINER,'State':'running','Names':'fixture','Image':'fixture/web:1','Ports':f'0.0.0.0:{self.port}->80/tcp','Networks':'bridge'}]
        self.client=self.app.test_client();self.client.get('/login')
        with self.client.session_transaction() as s:csrf=s['csrf']
        self.client.post('/setup',data={'username':'fixture-admin','password':'Fixture-pass-4433','csrf':csrf})
        self.login=self.state.rows('SELECT * FROM sessions')[0]
        self.user=self.state.rows('SELECT * FROM users')[0]
        with self.client.session_transaction() as s:self.csrf=s['csrf']
        link=self.client.get('/api/containers').json['containers'][0]['PanelLinks'][0]
        self.link=link;self.base=f'/api/panels/local/{CONTAINER}/{link["panel_id"]}'
        self.view=f'/panels/view/local/{CONTAINER}/{link["panel_id"]}'
        def cleanup():
            self.app.extensions['dcc_panels'].close()
            self.domains.save({'panel_proxy_enabled':False})
        self.addCleanup(cleanup)
    def call(self,path='/',**data):
        return self.client.post(self.base+'/request',json={'path':path,**data},headers={'X-CSRF-Token':self.csrf})
    def live(self,stream,action,data=None):return self.client.post(self.base+'/live/'+stream+'/'+action,json=data or {},headers={'X-CSRF-Token':self.csrf})
    def decoded(self,response):return json.loads(base64.b64decode(response.json['body']))
    def wait_for(self,predicate):
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            if predicate():return
            time.sleep(.05)
        self.fail('Expected condition did not become true')
    def test_original_addresses_and_public_clicks_are_separate(self):
        for origin,proxied in [('http://localhost',False),('https://localhost',False),('https://192.168.1.3',False),('https://dcc.example.com:9443',True),('https://8.8.4.4:9443',True)]:
            client=self.app.test_client()
            with self.client.session_transaction() as source:
                with client.session_transaction(base_url=origin) as dest:dest.update(source)
            response=client.get('/api/containers',base_url=origin)
            link=response.json['containers'][0]['PanelLinks'][0]
            self.assertEqual(link['url'],f'http://127.0.0.1:{self.port}')
            self.assertEqual(link['via_dcc'],proxied)
            self.assertEqual(link['open_url'].startswith('/panels/'),proxied)
        response=self.client.get('/api/containers',headers={'X-Forwarded-Host':'evil.example','X-Forwarded-Proto':'https'})
        self.assertFalse(response.json['containers'][0]['PanelLinks'][0]['via_dcc'])
    def test_missing_host_is_explicit_and_never_public_domain(self):
        self.state.save_profile('local',{'name':'No panel address','kind':'local','permissions':['read']})
        value=self.client.get('/api/containers').json['containers'][0]
        self.assertTrue(value['PanelAddressRequired']);self.assertEqual(value['PanelLinks'],[])
    def test_setting_defaults_migration_and_explicit_false_survive_restart(self):
        from host_setup import SETTINGS_ID
        self.state.execute('DELETE FROM settings WHERE user_id=?',(SETTINGS_ID,))
        self.assertFalse(self.domains.panel_proxy_enabled())
        self.domains.save({'local_https_enabled':True});self.assertTrue(self.domains.panel_proxy_enabled())
        response=self.client.put('/api/admin/panels',json={'enabled':False,'profile':'local'},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(response.status_code,200)
        self.domains.save({'public':'dcc.example.com','public_https_enabled':True})
        other=create_app(self.config,backend_factory=PanelBackend)
        self.assertFalse(other.extensions['dcc_domains'].panel_proxy_enabled())
    def test_authentication_csrf_and_origin_are_not_exempted(self):
        self.assertEqual(self.app.test_client().get(self.view).status_code,401)
        for origin in ('null','https://evil.example'):
            value=self.client.post(self.base+'/request',json={'path':'/'},headers={'Origin':origin,'X-CSRF-Token':self.csrf})
            self.assertEqual(value.status_code,403)
        self.assertEqual(self.client.post(self.base+'/request',json={'path':'/'}).status_code,403)
        self.assertEqual(self.client.post('/panels/content/any',data={}).status_code,403)
        self.assertEqual(self.client.get(self.view,headers={'Host':'evil.example'}).status_code,400)
    def test_profile_permissions_container_port_and_scope_are_rechecked(self):
        self.assertEqual(self.call('/echo').status_code,200)
        PanelBackend.panel_entries[0]['Ports']=f'0.0.0.0:{self.port}->6379/tcp'
        self.assertEqual(self.call('/echo').status_code,404)
        self.state.save_profile('local',{'name':'Denied','kind':'local','panel_host':'127.0.0.1','permissions':[]})
        self.assertEqual(self.call().status_code,403)
    def test_path_and_header_manipulation_cannot_change_destination(self):
        for path in ('http://evil.example','//evil.example/','/%2f/evil','/a/../api','/%252e%252e/api','/x%0d%0aHost:x','/x\\evil'):
            self.assertEqual(self.call(path).status_code,400,path)
        value=self.call('/echo',headers={'Cookie':'dcc_web_session=forged','Host':'evil.example','X-DCC-Web-Internal-TLS':'forged','Authorization':'Bearer service-fixture'})
        decoded=self.decoded(value)
        self.assertEqual(decoded['cookie'],'');self.assertEqual(decoded['dcc_marker'],'')
        self.assertEqual(decoded['authorization'],'Bearer service-fixture')
        self.assertEqual(decoded['origin'],f'http://127.0.0.1:{self.port}')
    def test_service_cookies_are_server_side_and_isolated_by_login(self):
        self.call('/cookie')
        value=self.call('/echo')
        self.assertIn('service_login=fixture-cookie',self.decoded(value)['cookie'])
        self.assertNotIn('dcc_web_session',self.decoded(value)['cookie'])
        self.assertFalse(any('service_login' in v for v in value.headers.getlist('Set-Cookie')))
        other=self.app.test_client();other.get('/login')
        with other.session_transaction() as s:csrf=s['csrf']
        other.post('/login',data={'username':'fixture-admin','password':'Fixture-pass-4433','csrf':csrf})
        with other.session_transaction() as s:csrf=s['csrf']
        value=other.post(self.base+'/request',json={'path':'/echo'},headers={'X-CSRF-Token':csrf})
        self.assertEqual(self.decoded(value)['cookie'],'')
    def test_redirects_are_followed_only_inside_the_selected_service(self):
        self.assertEqual(self.decoded(self.call('/redirect'))['path'],'/echo')
        self.assertEqual(self.call('/external').status_code,502)
    def test_uploads_binary_downloads_and_limits(self):
        data=b'file-content\x00\xff'
        value=self.call('/upload',method='POST',body=base64.b64encode(data).decode(),headers={'content-type':'application/octet-stream'})
        self.assertEqual(base64.b64decode(self.decoded(value)['body']),data)
        with patch('panel_proxy.MAX_RESPONSE',128):self.assertEqual(self.call('/large').status_code,413)
        self.assertEqual(self.call('/',method='CONNECT').status_code,400)
    def test_wrapper_is_sandboxed_and_upstream_html_is_only_json(self):
        view=self.client.get(self.view)
        self.assertIn(b'sandbox="allow-scripts allow-forms allow-downloads"',view.data)
        self.assertNotIn(b'allow-same-origin',view.data)
        raw=self.call('/')
        self.assertTrue(raw.content_type.startswith('application/json'))
        self.assertNotIn('Access-Control-Allow-Origin',raw.headers)
        ordinary=self.client.get('/')
        self.assertNotIn('unsafe-inline',ordinary.headers['Content-Security-Policy'])
    def test_verified_ssh_forwarding_uses_remote_loopback(self):
        profile={'kind':'ssh','host':'fixture.invalid'}
        link={'url':'http://fixture.invalid:8788','bind_ip':'0.0.0.0','loopback_only':False}
        with patch('panel_proxy.paramiko.SSHClient') as client,patch('panel_proxy._connect_ssh') as connect:
            channel,owner=_socket(profile,link)
            connect.assert_called_once_with(client.return_value,profile)
            client.return_value.get_transport.return_value.open_channel.assert_called_once_with('direct-tcpip',('127.0.0.1',8788),('127.0.0.1',0),timeout=8)
        local_link={'url':'http://127.0.0.1:8788','bind_ip':'127.0.0.1',
                    'loopback_only':True,'container_port':80,'container_id':CONTAINER}
        with patch.dict('panel_proxy.os.environ',{'DCC_WEB_CONTAINER_NAME':'fixture'}), \
                patch('panel_proxy.open_local_panel') as bridge:
            bridge.return_value=(MagicMock(),MagicMock())
            channel,owner=_socket({'kind':'local'},local_link)
            bridge.assert_called_once_with({'kind':'local'},CONTAINER,80)
            self.assertIs(channel,bridge.return_value[0])
        with patch('panel_proxy.open_local_panel') as bridge:
            with patch.dict('panel_proxy.os.environ',{'DCC_WEB_CONTAINER_NAME':'fixture'}):
                with self.assertRaisesRegex(Exception,'verified'):_socket({'kind':'local'},
                    {**local_link,'container_id':None})
            # Invalid targets must be rejected before any helper is started.
            bridge.assert_not_called()
    def test_http_timeout_is_safe_and_reports_route_failure(self):
        with patch('panel_proxy._socket',side_effect=TimeoutError('fixture-private-detail')):
            response=self.call('/')
        self.assertEqual(response.status_code,503);self.assertNotIn('fixture-private-detail',response.get_data(as_text=True))
    def test_paramiko_channel_without_read1_handles_regular_chunked_and_sse(self):
        regular=json.dumps({'path':'/echo'}).encode()
        responses=[
            b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+str(len(regular)).encode()+b'\r\n\r\n'+regular,
            b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nContent-Type: text/plain\r\n\r\n5\r\nhello\r\n0\r\n\r\n',
            b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n\r\ndata: tick-1\n\n',
        ]
        self.assertFalse(hasattr(SimulatedSSHChannel(responses[0]).makefile('rb'),'read1'))
        def transport(_profile,_link):
            return SimulatedSSHChannel(responses.pop(0)),MagicMock()
        with patch('panel_proxy._socket',side_effect=transport):
            self.assertEqual(self.decoded(self.call('/echo'))['path'],'/echo')
            chunked=self.call('/chunked')
            self.assertEqual(chunked.status_code,200,chunked.json)
            self.assertEqual(base64.b64decode(chunked.json['body']),b'hello')
            stream=self.call('/events')
            self.assertEqual(stream.status_code,200,stream.json)
            event=self.app.extensions['dcc_panels'].streams[stream.json['stream']]
            self.wait_for(lambda:bool(event.events))
            self.assertIn(b'tick-',base64.b64decode(self.live(stream.json['stream'],'read').json['events'][0]['data']))
            self.live(stream.json['stream'],'close')
    def test_sse_closes_after_logout(self):
        response=self.call('/events');self.assertEqual(response.status_code,200,response.json)
        key=response.json['stream'];value=self.app.extensions['dcc_panels'].streams[key]
        self.wait_for(lambda:bool(value.events))
        data=self.live(key,'read').json
        self.assertIn(b'data: tick-',base64.b64decode(data['events'][0]['data']))
        self.state.execute('DELETE FROM sessions')
        self.wait_for(lambda:value.closed)
        self.assertEqual(self.live(key,'read').status_code,401)
    def test_websocket_text_binary_and_permission_revocation(self):
        response=self.client.post(self.base+'/ws',json={'path':'/ws'},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(response.status_code,200,response.json)
        key=response.json['stream'];value=self.app.extensions['dcc_panels'].streams[key]
        for binary,data in ((False,b'live-echo'),(True,b'\x00\xff\x02')):
            self.assertEqual(self.live(key,'send',{'data':base64.b64encode(data).decode(),'binary':binary}).status_code,200)
            self.wait_for(lambda:bool(value.events));received=self.live(key,'read').json['events'][0]
            self.assertEqual(base64.b64decode(received['data']),data);self.assertEqual(received['binary'],binary)
        self.state.save_profile('local',{'name':'Denied','kind':'local','panel_host':'127.0.0.1','permissions':[]})
        self.wait_for(lambda:value.closed)

    def test_service_script_cookies_do_not_expose_or_replace_httponly(self):
        self.call('/cookie')
        self.assertEqual(self.call('/echo').json['cookies'],'')
        endpoint=self.base+'/cookie'
        headers={'X-CSRF-Token':self.csrf}
        response=self.client.post(endpoint,json={'value':'xsrf=readable; Path=/','path':'/'},headers=headers)
        self.assertEqual(response.status_code,200,response.json)
        self.assertIn('xsrf=readable',response.json['cookies'])
        self.assertNotIn('service_login',response.json['cookies'])
        self.assertIn('xsrf=readable',self.decoded(self.call('/echo'))['cookie'])
        for value in ('service_login=overwrite; Path=/','xsrf=bad; Domain=evil.example','x=y; HttpOnly'):
            self.assertEqual(self.client.post(endpoint,json={'value':value},headers=headers).status_code,400)

    def test_stream_session_expiry_mfa_and_disabled_setting_close_idle_sockets(self):
        for reason in ('expiry','mfa','disabled'):
            response=self.call('/events');self.assertEqual(response.status_code,200,response.json)
            value=self.app.extensions['dcc_panels'].streams[response.json['stream']]
            if reason=='expiry':self.state.execute('UPDATE sessions SET expires=?',(time.time()-1,))
            elif reason=='mfa':self.state.execute('INSERT OR REPLACE INTO mfa VALUES(?,?,1,-1,?,0,?)',(self.user['id'],self.state.vault.encrypt(b'JBSWY3DPEHPK3PXP'),'[]',''))
            else:self.domains.save({'panel_proxy_enabled':False})
            self.wait_for(lambda:value.closed)
            self.state.execute('UPDATE sessions SET expires=?',(time.time()+3600,))
            self.state.execute('DELETE FROM mfa');self.domains.save({'panel_proxy_enabled':True})

    def test_other_logins_and_profiles_cannot_read_live_connections(self):
        response=self.call('/events');key=response.json['stream']
        other=self.app.test_client();other.get('/login')
        with other.session_transaction() as s:csrf=s['csrf']
        other.post('/login',data={'username':'fixture-admin','password':'Fixture-pass-4433','csrf':csrf})
        with other.session_transaction() as s:csrf=s['csrf']
        self.assertEqual(other.post(self.base+'/live/'+key+'/read',json={},headers={'X-CSRF-Token':csrf}).status_code,404)
        self.state.save_profile('other',{'name':'Other Docker','kind':'local','panel_host':'127.0.0.1','permissions':['read']})
        endpoint=self.base.replace('/local/','/other/')+'/live/'+key+'/read'
        self.assertEqual(self.client.post(endpoint,json={},headers={'X-CSRF-Token':self.csrf}).status_code,404)

    def test_port_order_does_not_retarget_links_and_unrecognized_ports_are_denied(self):
        PanelBackend.panel_entries[0]['Ports']=f'0.0.0.0:33333->6379/tcp, 0.0.0.0:{self.port}->80/tcp'
        self.assertEqual(self.call('/echo').status_code,200)
        value=self.client.get('/api/containers').json['containers'][0]
        unknown=next(v for v in value['PanelLinks'] if v['host_port']==33333)
        endpoint=self.base.rsplit('/',1)[0]+'/'+unknown['panel_id']+'/request'
        self.assertEqual(self.client.post(endpoint,json={'path':'/'},headers={'X-CSRF-Token':self.csrf}).status_code,404)

    def test_nonadmin_profile_users_and_mfa_boundaries(self):
        self.state.execute('UPDATE users SET role=? WHERE id=?',('viewer',self.user['id']))
        self.assertEqual(self.call('/echo').status_code,200)
        self.state.save_profile('local',{'name':'Restricted','kind':'local','panel_host':'127.0.0.1','permissions':['read'],'users':['someone-else']})
        self.assertEqual(self.call('/echo').status_code,403)
        self.state.execute('UPDATE users SET role=? WHERE id=?',('admin',self.user['id']))
        self.state.execute('INSERT OR REPLACE INTO mfa VALUES(?,?,1,-1,?,0,?)',(self.user['id'],self.state.vault.encrypt(b'JBSWY3DPEHPK3PXP'),'[]',''))
        self.assertEqual(self.client.get(self.view).status_code,401)

    def test_unreadable_authorization_state_fails_closed_and_live_limits_are_bounded(self):
        self.call('/echo');ctx=next(iter(self.app.extensions['dcc_panels'].contexts.values()))
        with patch.object(self.state,'rows',side_effect=OSError('fixture')):self.assertFalse(ctx.active())
        keys=[]
        for _ in range(4):keys.append(self.call('/events').json['stream'])
        self.assertEqual(self.call('/events').status_code,429)
        for key in keys:self.live(key,'close')


if __name__=='__main__':unittest.main()
