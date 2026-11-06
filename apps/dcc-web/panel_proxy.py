"""Scoped panel data gateway. Untrusted HTML never executes in the DCC origin.

The trusted wrapper brokers HTTP and live connections for an opaque-origin
iframe. Every operation keeps ordinary DCC session, MFA, CSRF and profile checks.
No raw target URL, DCC credentials or browser service cookies are forwarded.
"""
import base64
from collections import deque
from email.message import Message
import hashlib
from http.client import HTTPConnection, HTTPSConnection, HTTPException
from http.cookiejar import Cookie, CookieJar
from http.cookies import SimpleCookie, CookieError
from email.utils import parsedate_to_datetime
import ipaddress
import os
import re
import secrets
import socket
import ssl
import threading
import time
import zlib
from types import SimpleNamespace
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import Request

import paramiko
from flask import abort, g, jsonify, render_template, request, session

from engine import EngineError, _connect_ssh
from ports import enrich_containers
from profile_facts import signature
from security import ROLES, trusted_https_request

MAX_RESPONSE = 16 * 1024 * 1024
MAX_BODY = 1_000_000
MAX_DURATION = 600
MAX_QUEUE = 1_000_000
METHODS = {'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'}
REQUEST_HEADERS = {'accept', 'accept-language', 'content-type', 'range',
                   'if-none-match', 'if-modified-since', 'x-csrf-token',
                   'x-csrftoken', 'x-xsrf-token', 'x-requested-with', 'authorization', 'x-api-key'}
RESPONSE_HEADERS = {'content-type', 'content-disposition', 'content-range',
                    'accept-ranges', 'etag', 'last-modified'}


def public_entry(app, domains):
    if g.get('dcc_remote'):
        return True
    host=(urlsplit('//'+request.host).hostname or '').lower()
    saved=domains.saved()
    public=urlsplit(app.config.get('PUBLIC_ORIGIN') or '').hostname
    if host in {str(saved.get('public') or '').lower(), str(public or '').lower()}:
        return True
    if host==str(saved.get('local') or '').lower():
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        # Only explicitly allowed hosts reach here. Recognized local DNS names
        # remain direct, also when TLS is used on a LAN.
        return not (host=='localhost' or '.' not in host or
                    host.endswith(('.local','.localhost','.home.arpa','.lan','.internal')))


def panel_host(profile, domains):
    if profile.get('kind','local') in {'local','wsl'}:
        return profile.get('panel_host') or domains.saved().get('local') or None
    return None


def panel_links(containers, profile, domains, app, host_panels=None):
    values=enrich_containers(containers,profile,panel_host(profile,domains),host_panels)
    enabled=domains.panel_proxy_enabled() and public_entry(app,domains)
    for entry in values:
        for link in entry['PanelLinks']:
            link['via_dcc']=bool(enabled and link['likely_panel'])
            link['open_url']=(f'/panels/view/{profile["id"]}/{entry["ID"]}/{link["panel_id"]}'
                              if link['via_dcc'] else link['url'])
    return values


def safe_path(value):
    if not isinstance(value,str) or len(value)>8192 or not value.startswith('/'):
        raise ValueError('Invalid panel path')
    decoded=value
    for _ in range(3):
        decoded=unquote(decoded)
    if (value.startswith('//') or decoded.startswith('//') or '\\' in decoded or
            any(ord(c)<32 or ord(c)==127 for c in decoded) or
            any(part in {'.','..'} for part in urlsplit(decoded).path.split('/'))):
        raise ValueError('Invalid panel path')
    parsed=urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise ValueError('Invalid panel path')
    return value


def _target(factory, profile, container_id, panel_id, domains, host_panels):
    if not re.fullmatch('[a-f0-9]{64}',container_id) or not re.fullmatch('[a-f0-9]{24}',panel_id):
        abort(404,'Panel not found')
    engine=factory(profile)
    entries=engine._container_list() if hasattr(engine,'_container_list') else engine.containers()
    matched=next((c for c in entries if c.get('ID')==container_id),None)
    if not matched or matched.get('State')!='running':
        abort(404,'Container is not running')
    links=enrich_containers([matched],profile,panel_host(profile,domains),host_panels)[0]['PanelLinks']
    link=next((v for v in links if v['panel_id']==panel_id and v['likely_panel']),None)
    if not link:
        abort(404,'Published web panel not found')
    return link


def _socket(profile, link):
    url=urlsplit(link['url'])
    host=url.hostname
    client=None
    try:
        if profile.get('kind') in {'ssh','balena'}:
            client=paramiko.SSHClient()
            _connect_ssh(client,profile)
            destination='127.0.0.1' if link['bind_ip'] in {'0.0.0.0','::','*'} else link['bind_ip']
            channel=client.get_transport().open_channel('direct-tcpip',(destination,url.port),('127.0.0.1',0),timeout=8)
            channel.settimeout(8)
        else:
            if link['loopback_only'] and (profile.get('kind') in {'tcp','tunnel'} or os.environ.get('DCC_WEB_CONTAINER_NAME')):
                raise EngineError('A loopback-only panel needs an SSH profile for its Docker host')
            if profile.get('kind') in {'tunnel','wsl'} and not profile.get('panel_host'):
                raise EngineError('Configure a reachable panel host address for this profile')
            channel=socket.create_connection((host,url.port),timeout=8)
        if url.scheme=='https':
            channel=ssl.create_default_context().wrap_socket(channel,server_hostname=host)
        return channel,client
    except Exception:
        if client:client.close()
        raise


def _close(connection,client=None):
    try:
        if connection.sock:connection.sock.shutdown(socket.SHUT_RDWR)
    except (OSError,AttributeError):pass
    connection.close()
    if client:client.close()


class BoundedSocket:
    """Limit an incoming WS message before the library allocates its payload."""
    def __init__(self,sock):self.sock,self.received=sock,0
    def __getattr__(self,name):return getattr(self.sock,name)
    def recv(self,size):
        value=self.sock.recv(min(size,65536))
        self.received+=len(value)
        if self.received>MAX_QUEUE+16384:
            self.sock.close();raise OSError('Panel WebSocket message exceeds gateway limit')
        return value


def _headers(data, origin):
    values=data.get('headers',{})
    if not isinstance(values,dict) or len(values)>32:
        raise ValueError('Invalid panel headers')
    result={}
    for name,value in values.items():
        if not isinstance(name,str) or not isinstance(value,str) or len(value)>8192 or '\r' in value or '\n' in value:
            raise ValueError('Invalid panel headers')
        if name.lower() in REQUEST_HEADERS:
            result[name.lower()]=value
    result.update({'Host':urlsplit(origin).netloc,'Origin':origin,'Referer':origin+'/',
                   'Accept-Encoding':'identity','Connection':'close'})
    return result


class PanelContext:
    def __init__(self, state, domains, profile, owner, login, verified, remote):
        self.state,self.domains=state,domains
        self.profile,self.fingerprint=profile['id'],self.signature(profile)
        self.owner,self.login,self.verified,self.remote=owner,login,verified,remote
        self.jar=CookieJar()
        self.lock=threading.RLock()
        self.touched=time.monotonic()

    def signature(self,profile):
        return (signature(profile),profile.get('panel_host'),self.domains.saved().get('local'))

    def active(self):
        # A missing/unreadable database or settings file must close live access.
        try:return self._active()
        except Exception:return False

    def _active(self):
        if not self.domains.panel_proxy_enabled():return False
        rows=self.state.rows('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?',
                             (self.login,time.time()))
        if not rows or rows[0]['id']!=self.owner:return False
        user=rows[0]
        enabled=self.state.mfa.enabled(self.owner)
        if enabled and not self.verified or self.remote and user['role']=='admin' and not enabled:return False
        try:p=self.state.profile(self.profile)
        except ValueError:return False
        return bool(self.signature(p)==self.fingerprint and 'read' in ROLES.get(user['role'],set()) and
                    'read' in p.get('permissions',['read']) and
                    (not p.get('users') or self.owner in p['users'] or user['role']=='admin'))

    def cookies(self,url):
        with self.lock:
            req=Request(url);self.jar.add_cookie_header(req)
            return req.get_header('Cookie')

    def accept_cookies(self,url,headers):
        msg=Message()
        for name,value in headers:
            if name.lower()=='set-cookie':msg.add_header('Set-Cookie',value)
        with self.lock:
            self.jar.extract_cookies(SimpleNamespace(info=lambda:msg),Request(url))
            if len(self.jar)>100:self.jar.clear()

    def visible_cookies(self,url):
        # Only service cookies which its own JS could read, never HttpOnly.
        with self.lock:
            visible=CookieJar()
            for cookie in self.jar:
                if not any(k.lower()=='httponly' for k in cookie._rest):visible.set_cookie(cookie)
            req=Request(url);visible.add_cookie_header(req)
            return req.get_header('Cookie','')

    def set_script_cookie(self,url,value):
        if not isinstance(value,str) or len(value)>4096 or '\r' in value or '\n' in value:
            raise ValueError('Invalid panel cookie')
        parsed=SimpleCookie()
        try:parsed.load(value)
        except CookieError:raise ValueError('Invalid panel cookie') from None
        host=urlsplit(url).hostname
        with self.lock:
            for item in parsed.values():
                if item['domain'] and item['domain'].lstrip('.').lower()!=host.lower():
                    raise ValueError('Panel cookie domain rejected')
                if item['httponly']:raise ValueError('Scripts cannot set HttpOnly cookies')
                path=item['path'] or '/'
                if not path.startswith('/') or len(path)>2000:raise ValueError('Invalid panel cookie path')
                expires=None
                if item['max-age']:
                    try:expires=int(time.time())+int(item['max-age'])
                    except ValueError:raise ValueError('Invalid panel cookie expiry') from None
                elif item['expires']:
                    try:expires=int(parsedate_to_datetime(item['expires']).timestamp())
                    except Exception:raise ValueError('Invalid panel cookie expiry') from None
                # A script must not overwrite an existing HttpOnly service cookie.
                if any(c.name==item.key and c.path==path and any(k.lower()=='httponly' for k in c._rest) for c in self.jar):
                    raise ValueError('Scripts cannot overwrite HttpOnly cookies')
                self.jar.set_cookie(Cookie(0,item.key,item.value,None,False,host,False,False,path,True,
                                           bool(item['secure']),expires,expires is None,None,None,{},False))
            if len(self.jar)>100:self.jar.clear()


class LivePanel:
    def __init__(self,ctx,resource,closer,kind,protocol=''):
        self.id=secrets.token_urlsafe(24)
        self.context,self.resource,self.closer,self.kind=ctx,resource,closer,kind
        self.protocol=protocol
        self.events=deque();self.size=0;self.closed=False
        self.lock=threading.RLock()
        self.created=self.touched=time.monotonic()
        self.thread=threading.Thread(target=self._read,daemon=True,name='dcc-panel-live');self.thread.start()

    def close(self):
        self.closed=True
        try:self.closer()
        except Exception:pass

    def _read(self):
        try:
            while not self.closed and self.context.active():
                if self.kind=='ws':
                    import websocket
                    opcode,value=self.resource.recv_data()
                    self.resource.sock.received=0
                    binary=opcode==websocket.ABNF.OPCODE_BINARY
                    if isinstance(value,str):value=value.encode('utf-8')
                else:
                    value=self.resource.read1(32768);binary=False
                if not value:break
                if not self.context.active():break
                with self.lock:
                    self.size+=len(value)
                    if self.size>MAX_QUEUE:break
                    self.events.append({'data':base64.b64encode(value).decode(),'binary':binary})
        except Exception:
            pass
        finally:self.close()

    def poll(self):
        self.touched=time.monotonic()
        with self.lock:
            values=list(self.events);self.events.clear();self.size=0
        return {'events':values,'closed':self.closed,'protocol':self.protocol}


class Panels:
    def __init__(self,state,domains):
        self.state,self.domains=state,domains
        self.contexts={};self.streams={};self.lock=threading.RLock();self.reaper=None
        self.stopping=threading.Event()

    def close(self):
        with self.lock:
            values=list(self.streams.values())
            self.stopping.set()
            for value in values:value.close()
            self.streams.clear();self.contexts.clear()
        for value in values:
            if value.thread is not threading.current_thread():value.thread.join(timeout=2)
        if self.reaper and self.reaper is not threading.current_thread():self.reaper.join(timeout=2)

    def context(self,profile,container_id,panel_id):
        login=hashlib.sha256(session['sid'].encode()).hexdigest()
        key=(login,profile['id'],container_id,panel_id)
        with self.lock:
            ctx=self.contexts.get(key)
            if not ctx:
                if len(self.contexts)>=256:abort(429,'Too many open panels')
                ctx=PanelContext(self.state,self.domains,profile,g.user['id'],login,bool(session.get('mfa_verified')),bool(g.get('dcc_remote')))
                self.contexts[key]=ctx
            ctx.touched=time.monotonic()
            if not self.reaper or not self.reaper.is_alive():
                self.reaper=threading.Thread(target=self._reap,daemon=True,name='dcc-panel-expiry');self.reaper.start()
        return ctx

    def existing(self,profile,container_id,panel_id):
        login=hashlib.sha256(session['sid'].encode()).hexdigest()
        with self.lock:ctx=self.contexts.get((login,profile['id'],container_id,panel_id))
        if not ctx or not ctx.active():abort(404,'Panel connection not found')
        ctx.touched=time.monotonic()
        return ctx

    def _reap(self):
        while not self.stopping.wait(1):
            with self.lock:
                now=time.monotonic()
                for key,value in list(self.streams.items()):
                    if now-value.created>MAX_DURATION or now-value.touched>30 or not value.context.active():
                        value.close()
                    if value.closed and now-value.touched>30:self.streams.pop(key,None)
                for key,ctx in list(self.contexts.items()):
                    if now-ctx.touched>900 or not ctx.active():self.contexts.pop(key,None)
                if not self.contexts and not self.streams:return

    def add_stream(self,ctx,resource,closer,kind,protocol=''):
        with self.lock:
            active=[v for v in self.streams.values() if not v.closed]
            if len(active)>=32 or sum(v.context.owner==ctx.owner for v in active)>=4:
                closer();abort(429,'Panel live connection limit reached')
            stream=LivePanel(ctx,resource,closer,kind,protocol)
            self.streams[stream.id]=stream
            return {'stream':stream.id,'protocol':protocol}

    def stream(self,ctx,stream_id):
        with self.lock:
            value=self.streams.get(stream_id)
            if not value or value.context is not ctx or not ctx.active():abort(404,'Panel connection not found')
            return value


def register_panels(app,factory,profile,domains,host_panels,state):
    panels=Panels(state,domains)
    app.extensions['dcc_panels']=panels

    def details(profile_id,container_id,panel_id):
        if not domains.panel_proxy_enabled():abort(404,'Panel forwarding is disabled')
        selected=profile(profile_id,'read')
        link=_target(factory,selected,container_id,panel_id,domains,host_panels())
        ctx=panels.context(selected,container_id,panel_id)
        if not ctx.active():abort(401,'Login required')
        return selected,link,ctx

    def body():
        value=request.get_json(silent=True)
        if not isinstance(value,dict):raise ValueError('A JSON object is required')
        return value

    @app.get('/panels/view/<profile_id>/<container_id>/<panel_id>')
    def panel_view(profile_id,container_id,panel_id):
        selected,link,ctx=details(profile_id,container_id,panel_id)
        return render_template('panel.html',profile_id=profile_id,container_id=container_id,
                               panel_id=panel_id,panel=link)

    base='/api/panels/<profile_id>/<container_id>/<panel_id>'

    @app.get(base+'/status')
    def panel_status(profile_id,container_id,panel_id):
        selected=profile(profile_id,'read')
        panels.existing(selected,container_id,panel_id)
        return jsonify(ok=True)

    @app.post(base+'/request')
    def panel_request(profile_id,container_id,panel_id):
        selected,link,ctx=details(profile_id,container_id,panel_id)
        data=body();path=safe_path(data.get('path','/'));method=data.get('method','GET')
        if method not in METHODS:raise ValueError('Invalid panel method')
        try:payload=base64.b64decode(data.get('body',''),validate=True)
        except Exception:raise ValueError('Invalid panel body') from None
        if len(payload)>MAX_BODY:abort(413,'Panel upload exceeds gateway limit')
        headers=_headers(data,link['url'])
        connection=ssh=None
        try:
            for attempt in range(6):
                if not ctx.active():abort(401,'Login required')
                url=link['url']+path
                channel,ssh=_socket(selected,link)
                connection=HTTPConnection(urlsplit(link['url']).hostname,timeout=8)
                connection.sock=channel
                cookie=ctx.cookies(url)
                outgoing=dict(headers)
                if cookie:outgoing['Cookie']=cookie
                connection.request(method,path,body=payload or None,headers=outgoing)
                result=connection.getresponse();received=result.getheaders()
                ctx.accept_cookies(url,received)
                if result.status in {301,302,303,307,308} and result.getheader('Location'):
                    location=urlsplit(urljoin(url,result.getheader('Location')))
                    origin=urlsplit(link['url'])
                    if (location.scheme,location.hostname,location.port)!=(origin.scheme,origin.hostname,origin.port) or location.username or location.password:
                        abort(502,'Panel redirect outside the selected service was blocked')
                    path=safe_path(location.path+('?' + location.query if location.query else ''))
                    if result.status==303 or result.status in {301,302} and method=='POST':
                        method='GET';payload=b''
                    connection.close()
                    if ssh:ssh.close()
                    continue
                content_type=result.getheader('Content-Type','application/octet-stream')
                if 'text/event-stream' in content_type:
                    channel.settimeout(None)
                    def close(conn=connection,client=ssh,stream=result,raw=channel):
                        try:raw.shutdown(socket.SHUT_RDWR)
                        except OSError:pass
                        stream.close()
                        _close(conn,client)
                    value=panels.add_stream(ctx,result,close,'sse')
                    return jsonify(**value,status=result.status,headers={'content-type':content_type},path=path)
                chunks=[];size=0;started=time.monotonic()
                while True:
                    chunk=result.read1(32768)
                    if not chunk:break
                    if not ctx.active():abort(401,'Login required')
                    if time.monotonic()-started>30:abort(504,'Panel response timed out')
                    size+=len(chunk)
                    if size>MAX_RESPONSE:abort(413,'Panel response exceeds gateway limit')
                    chunks.append(chunk)
                raw=b''.join(chunks)
                encoding=result.getheader('Content-Encoding','identity').lower()
                if encoding in {'gzip','deflate'}:
                    decoder=zlib.decompressobj(31 if encoding=='gzip' else zlib.MAX_WBITS)
                    raw=decoder.decompress(raw,MAX_RESPONSE+1)
                    if len(raw)>MAX_RESPONSE or not decoder.eof:abort(413,'Panel response exceeds gateway limit')
                elif encoding!='identity':abort(502,'Unsupported panel content encoding')
                if not ctx.active():abort(401,'Login required')
                return jsonify(status=result.status,headers={k.lower():v for k,v in received if k.lower() in RESPONSE_HEADERS},
                               body=base64.b64encode(raw).decode(),path=path,cookies=ctx.visible_cookies(url))
            abort(502,'Too many panel redirects')
        except (OSError,HTTPException,paramiko.SSHException,zlib.error) as error:
            raise EngineError('Panel is unreachable from DCC Web. Check the panel host, published port and SSH forwarding.') from error
        finally:
            # Streams transfer ownership of the socket to the bounded manager.
            if connection and not ('value' in locals() and 'stream' in value):
                if 'result' in locals():result.close()
                connection.close()
                if ssh:ssh.close()

    @app.post(base+'/ws')
    def panel_ws(profile_id,container_id,panel_id):
        import websocket
        selected,link,ctx=details(profile_id,container_id,panel_id)
        data=body();path=safe_path(data.get('path','/'))
        protocols=data.get('protocols',[])
        if not isinstance(protocols,list) or len(protocols)>10 or any(not isinstance(p,str) or not re.fullmatch(r'[A-Za-z0-9!#$%&*+.^_`|~-]{1,128}',p) for p in protocols):
            raise ValueError('Invalid WebSocket protocols')
        channel=ssh=None
        try:
            channel,ssh=_socket(selected,link)
            cookie=ctx.cookies(link['url']+path)
            wsurl=link['url'].replace('https://','wss://',1).replace('http://','ws://',1)+path
            resource=websocket.create_connection(wsurl,socket=BoundedSocket(channel),timeout=8,
                         origin=link['url'],cookie=cookie,subprotocols=protocols or None,redirect_limit=0)
            resource.settimeout(None)
            def close():
                resource.abort()
                if ssh:ssh.close()
            return jsonify(panels.add_stream(ctx,resource,close,'ws',resource.getsubprotocol() or ''))
        except Exception as error:
            if channel:channel.close()
            if ssh:ssh.close()
            if getattr(error,'code',None):raise
            raise EngineError('Panel WebSocket is unreachable or rejected the connection') from error

    @app.post(base+'/cookie')
    def panel_cookie(profile_id,container_id,panel_id):
        selected,link,ctx=details(profile_id,container_id,panel_id)
        data=body();path=safe_path(data.get('path','/'))
        ctx.set_script_cookie(link['url']+path,data.get('value'))
        return jsonify(cookies=ctx.visible_cookies(link['url']+path))

    @app.post(base+'/live/<stream_id>/<action>')
    def panel_live(profile_id,container_id,panel_id,stream_id,action):
        selected=profile(profile_id,'read')
        ctx=panels.existing(selected,container_id,panel_id)
        value=panels.stream(ctx,stream_id)
        if action=='read':return jsonify(value.poll())
        if action=='close':value.close();return jsonify(ok=True)
        if action!='send' or value.kind!='ws' or value.closed:abort(400,'Invalid panel connection operation')
        data=body()
        try:raw=base64.b64decode(data.get('data',''),validate=True)
        except Exception:raise ValueError('Invalid panel message') from None
        if len(raw)>MAX_BODY:abort(413,'Panel message exceeds gateway limit')
        import websocket
        value.resource.send(raw,opcode=websocket.ABNF.OPCODE_BINARY if data.get('binary') else websocket.ABNF.OPCODE_TEXT)
        value.touched=time.monotonic()
        return jsonify(ok=True)
