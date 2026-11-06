"""Opt-in token-authenticated Streamable HTTP using the official MCP SDK.

The SDK handles framing and protocol negotiation. The Flask boundary validates
TLS/proxy provenance, Host, Origin and a live grant before every request. HTTP
is stateless; PTYs are bounded, grant-scoped resources and never credentials.
"""
import asyncio
from contextvars import ContextVar
import hashlib
import ipaddress
import json
import logging
import os
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

from flask import abort, g, jsonify, request, Response

from mcp_preview import MCPService, READ_SCHEMAS, TOOLS
from security import admin, trusted_https_request

SETTINGS = '__dcc_mcp_http__'
CURRENT = ContextVar('dcc_mcp_service')
MAX_BODY = 262144
OAUTH_PATHS = {'/.well-known/oauth-authorization-server','/authorize','/token','/register','/revoke'}


def origin_url(value):
    if not isinstance(value, str) or len(value) > 250:
        raise ValueError('Provide the public HTTPS origin without a path or credentials')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment
            or not re.fullmatch(r'[A-Za-z0-9.\-:\[\]]+', parsed.netloc)):
        raise ValueError('Provide the public HTTPS origin without a path or credentials')
    # Accessing .port also rejects malformed ports.
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError('Invalid HTTPS port')
    return 'https://' + parsed.netloc.lower()


class PublicMCP:
    def __init__(self, app, state, backend_factory=None, terminal_factory=None, command_factory=None):
        self.app, self.state = app, state
        self.factories = dict(backend_factory=backend_factory, terminal_factory=terminal_factory)
        if command_factory is not None: self.factories['command_factory'] = command_factory
        self.entries, self.rates = {}, {}
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(4)
        self.adapter = self.manager = self.lifetime = None
        self.closed = threading.Event()
        from mcp_oauth import DCCOAuth
        self.oauth = DCCOAuth(self)

    def saved(self):
        rows = self.state.rows('SELECT data FROM settings WHERE user_id=?', (SETTINGS,))
        return json.loads(rows[0]['data']) if rows else {}

    def enabled(self):
        config = self.saved()
        owner = config.get('owner')
        return bool(config.get('enabled') and owner and self.state.mfa.enabled(owner)
                    and self.state.rows("SELECT 1 FROM users WHERE id=? AND role='admin'", (owner,)))

    def tls(self):
        return trusted_https_request(self.app)

    def rate(self, key, limit):
        now = time.monotonic()
        with self.lock:
            self.rates = {k: value for k, value in self.rates.items() if now-value[0] < 60}
            if len(self.rates) >= 512 and key not in self.rates: abort(429, 'MCP rate limit reached')
            start, count = self.rates.get(key, (now, 0))
            if count >= limit: abort(429, 'MCP rate limit reached')
            self.rates[key] = start, count+1

    def boundary(self):
        if not self.enabled(): abort(404)
        config = self.saved()
        expected = config['origin']
        if not self.tls(): abort(403, 'MCP requires verified HTTPS')
        if request.host.lower() != urlsplit(expected).netloc: abort(403, 'MCP Host rejected')
        if request.headers.get('Origin') is not None and request.headers['Origin'] != expected:
            abort(403, 'MCP Origin rejected')
        peer = hashlib.sha256(str(request.remote_addr).encode()).hexdigest()
        # Count all arrivals before expensive authorization; bounded per-peer
        # and globally even behind a tunnel that reports a common peer.
        self.rate('all', 1200)
        self.rate('peer:'+peer, 600)
        return peer

    def guard(self):
        peer = self.boundary()
        if request.query_string: abort(400, 'MCP credentials and options must not be sent in a URL')
        if request.method not in {'POST', 'GET', 'DELETE'}: abort(405)
        header = request.headers.get('X-DCC-MCP-Grant', '')
        match = re.fullmatch(r'([A-Za-z0-9_-]{40,160})', header)
        token = match[1] if match else ''
        digest = hashlib.sha256(token.encode()).hexdigest()
        rows = self.state.rows('SELECT token,data,revoked,paused,id FROM grants WHERE token=?', (digest,))
        valid = bool(rows and secrets.compare_digest(rows[0]['token'], digest))
        grant = json.loads(rows[0]['data']) if valid else {}
        valid = valid and not rows[0]['revoked'] and not rows[0]['paused'] and grant.get('allow_public') is True
        valid = valid and (grant.get('expires') is None or grant['expires'] > time.time())
        authorization = re.fullmatch(r'Bearer ([A-Za-z0-9_-]{40,160})',request.headers.get('Authorization',''))
        session_hash = hashlib.sha256(authorization[1].encode()).hexdigest() if authorization else ''
        # Invalid grant credentials must never extend an OAuth session's idle TTL.
        authorized = self.oauth.active(session_hash) if authorization else None
        grant_id = (request.view_args or {}).get('grant_id','')
        valid = valid and rows[0]['id']==grant_id and authorized and authorized['grant']==grant_id
        valid = valid and authorized['resource']==self.saved()['origin']+'/mcp/'+grant_id
        if not valid:
            self.rate('invalid:'+peer, 30)
            self.state.audit('anonymous', 'mcp.http.denied', 'mcp', 401)
            metadata=self.saved()['origin']+'/.well-known/oauth-protected-resource/mcp/'+grant_id
            return jsonify(error='MCP requires the grant token and a current session approved with 2FA'), 401, {'WWW-Authenticate':'Bearer resource_metadata="'+metadata+'", scope="dcc"'}
        self.rate('grant:'+digest, 180)
        if request.content_length is not None and request.content_length > MAX_BODY: abort(413)
        # Renew the idle deadline only after all credentials and request limits pass.
        if not self.oauth.active(session_hash,touch=True):
            abort(401,'MCP session has expired')
        g.dcc_mcp_digest, g.dcc_mcp_token, g.dcc_mcp_session = digest, token, session_hash
        return None

    def entry(self, token, session_hash):
        digest = session_hash
        with self.lock:
            now = time.monotonic()
            for key, entry in list(self.entries.items()):
                if now-entry['touched'] > 600 or now-entry['created'] > 3600 or not self.oauth.active(key):
                    entry['service'].close(); self.entries.pop(key)
            if digest not in self.entries:
                if len(self.entries) >= 32: raise ValueError('MCP active grant limit reached')
                service = MCPService(self.state, token, **self.factories)
                service.public_check = lambda: bool(self.oauth.active(session_hash))
                service.initialized = service.negotiated = True
                self.entries[digest] = {'service':service, 'created':now, 'touched':now, 'busy':threading.Lock()}
            self.entries[digest]['touched'] = now
            return self.entries[digest]

    def start(self):
        with self.lock:
            if self.adapter: return
            from a2wsgi import ASGIMiddleware
            from mcp.server.lowlevel import Server
            from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
            from mcp.server.transport_security import TransportSecuritySettings
            import mcp.types as types
            import anyio
            from mcp.server.auth.routes import create_auth_routes
            from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
            from pydantic import AnyHttpUrl
            from starlette.applications import Starlette
            # SDK diagnostics must not serialize model-provided commands/input.
            logger = logging.getLogger('mcp'); logger.handlers = [logging.NullHandler()]; logger.propagate = False

            async def tools(ctx, params):
                service = CURRENT.get()
                result = await anyio.to_thread.run_sync(lambda: service.handle({'id':1,'method':'tools/list'}))
                return types.ListToolsResult.model_validate(result['result'])

            async def call(ctx, params):
                try:
                    result = await anyio.to_thread.run_sync(lambda: CURRENT.get().call(params.name, params.arguments or {}))
                    return types.CallToolResult.model_validate(result)
                except PermissionError:
                    return types.CallToolResult(content=[types.TextContent(type='text',text='MCP operation denied by the current grant or device permissions')],isError=True)
                except Exception:
                    return types.CallToolResult(content=[types.TextContent(type='text',text='Invalid request or unavailable DCC resource; check this profile in DCC Web')],isError=True)

            server = Server('dcc-web', version=__import__('web').VERSION,
                instructions='Manage granted devices ONLY through DCC MCP. Never bypass it via SSH, another app or browser terminal. Use only granted tools and profiles. Token authorization is required for every HTTP request; terminal IDs are not credentials.',
                on_list_tools=tools, on_call_tool=call,
                get_tool_input_schema=lambda name: {'type':'object','properties':{'profile':{'type':'string'},**READ_SCHEMAS[name].get('properties',{})},'required':READ_SCHEMAS[name]['required'],'additionalProperties':False} if name in TOOLS else None)
            self.manager = StreamableHTTPSessionManager(server, stateless=True, json_response=True, max_request_body_size=MAX_BODY,
                security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False))
            # Flask guard already validates exact Host and Origin against the
            # configured origin after verifying TLS/proxy provenance.
            async def asgi(scope, receive, send):
                if scope['path'] in OAUTH_PATHS:
                    oauth_app = Starlette(routes=create_auth_routes(self.oauth, issuer_url=AnyHttpUrl(self.saved()['origin']),
                        client_registration_options=ClientRegistrationOptions(enabled=True,valid_scopes=['dcc'],default_scopes=['dcc']),
                        revocation_options=RevocationOptions(enabled=True)))
                    return await oauth_app(scope,receive,send)
                binding = CURRENT.set(scope['wsgi_environ']['dcc.mcp_service'])
                try: await self.manager.handle_request(scope, receive, send)
                finally: CURRENT.reset(binding)
            self.adapter = ASGIMiddleware(asgi, wait_time=2)
            ready = threading.Event()
            async def lifetime():
                async with self.manager.run():
                    ready.set()
                    while not self.closed.is_set(): await asyncio.sleep(.1)
            self.lifetime = asyncio.run_coroutine_threadsafe(lifetime(), self.adapter.loop)
            if not ready.wait(5): raise RuntimeError('MCP SDK did not start')

    def handle(self):
        # GET/SSE is optional in Streamable HTTP. JSON responses and explicit
        # terminal reads avoid idle streams occupying panel worker threads.
        if request.method in {'GET', 'DELETE'}:
            return '', 405, {'Allow':'POST'}
        body = request.get_data(cache=True)
        if len(body) > MAX_BODY: abort(413)
        if not self.slots.acquire(blocking=False): abort(429, 'MCP concurrency limit reached')
        try:
            entry = self.entry(g.dcc_mcp_token, g.dcc_mcp_session)
            if not entry['busy'].acquire(blocking=False): abort(429, 'Another MCP request is running for this grant')
            try:
                entry['service'].grant()
                self.start()
                request.environ['dcc.mcp_service'] = entry['service']
                # The body was bounded/read above; give the adapter a fresh stream.
                import io
                environ = dict(request.environ, **{'wsgi.input':io.BytesIO(body), 'CONTENT_LENGTH':str(len(body))})
                return Response.from_app(self.adapter, environ, buffered=True)
            finally: entry['busy'].release()
        finally: self.slots.release()

    def close(self):
        self.closed.set()
        with self.lock:
            for entry in self.entries.values(): entry['service'].close()
            self.entries.clear()

    def close_inactive(self):
        with self.lock:
            for key,entry in list(self.entries.items()):
                if not self.oauth.active(key):
                    entry['service'].close(); self.entries.pop(key,None)

    def handle_oauth(self):
        self.boundary()
        if len(request.query_string) > 16384 or request.content_length is not None and request.content_length > 16384:
            abort(413)
        self.rate('oauth:'+str(request.remote_addr),60)
        self.start()
        if request.method != 'POST':
            return Response.from_app(self.adapter, request.environ, buffered=True)
        # Bound chunked/unknown-length bodies before passing them to the SDK.
        import io
        body = request.stream.read(16385)
        if len(body) > 16384: abort(413)
        environ = dict(request.environ, **{'wsgi.input':io.BytesIO(body), 'CONTENT_LENGTH':str(len(body))})
        return Response.from_app(self.adapter, environ, buffered=True)


def register_public_mcp(app, state, reauthenticate, backend_factory, terminal_factory=None):
    service = PublicMCP(app, state, backend_factory, terminal_factory)
    app.extensions['dcc_mcp_http'] = service
    configured_peers = app.config.get('MCP_TRUSTED_PROXY_IPS', os.environ.get('DCC_MCP_TRUSTED_PROXY_IPS','').split(','))
    app.config['MCP_TRUSTED_PROXY_IPS'] = {str(ipaddress.ip_address(value.strip())) for value in configured_peers if value.strip()}
    saved_origin = service.saved().get('origin')
    if saved_origin: app.config['ALLOWED_HOSTS'] = set(app.config['ALLOWED_HOSTS']) | {urlsplit(saved_origin).hostname}

    from mcp_oauth import register_approval
    register_approval(app,service,reauthenticate)

    @app.route('/mcp/<grant_id>', methods=['POST','GET','DELETE','OPTIONS'])
    def mcp_http(grant_id): return service.handle()

    @app.get('/.well-known/oauth-protected-resource/mcp/<grant_id>')
    def mcp_resource_metadata(grant_id):
        service.boundary()
        if not re.fullmatch(r'[a-f0-9]{24}',grant_id): abort(404)
        origin=service.saved()['origin']
        return jsonify(resource=origin+'/mcp/'+grant_id,authorization_servers=[origin],scopes_supported=['dcc'],bearer_methods_supported=['header'])

    def oauth_endpoint(): return service.handle_oauth()
    for index,path in enumerate(OAUTH_PATHS):
        app.add_url_rule(path,'dcc_oauth_'+str(index),oauth_endpoint,methods=['GET','POST','OPTIONS'])

    @app.route('/api/mcp/http', methods=['GET','PUT'])
    def mcp_http_settings():
        admin()
        if request.method == 'PUT':
            data = request.get_json() or {}
            reauthenticate(data)
            enabled = data.get('enabled') is True
            if enabled and (data.get('confirm_public') is not True or not state.mfa.enabled(g.user['id'])):
                abort(400, 'Enable administrator 2FA and explicitly authorize public MCP access')
            if enabled and not service.tls(): abort(403, 'Use verified HTTPS to enable public MCP')
            try:
                origin = origin_url(data.get('origin','')) if enabled else service.saved().get('origin','')
            except ValueError as error:
                abort(400, str(error))
            value = {'enabled':enabled,'origin':origin, 'owner':g.user['id']}
            state.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(SETTINGS,json.dumps(value)))
            if value['origin']: app.config['ALLOWED_HOSTS'] = set(app.config['ALLOWED_HOSTS']) | {urlsplit(value['origin']).hostname}
            if not enabled:
                state.execute('UPDATE mcp_oauth_sessions SET revoked=1')
                with service.lock:
                    for entry in service.entries.values(): entry['service'].close()
                    service.entries.clear()
            state.audit(g.user['id'],'mcp.http.enable' if enabled else 'mcp.http.disable','mcp',200)
        config = service.saved()
        remote = app.extensions.get('dcc_remote_access')
        suggested = remote.saved().get('origin','') if remote else ''
        return jsonify(enabled=service.enabled(), origin=config.get('origin',''), suggested_origin=suggested or app.config.get('PUBLIC_ORIGIN',''),
                       endpoint=config.get('origin','')+'/mcp/<grant-id>' if service.enabled() else None)
