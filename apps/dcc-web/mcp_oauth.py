"""MCP SDK OAuth provider backed by DCC grants and the existing account TOTP.

The SDK implements registration, authorization-code/PKCE validation and token
responses. This provider stores only hashes of codes/access tokens, never issues
refresh tokens, and requires fresh, shared replay-protected TOTP at approval.
"""
import hashlib
import ipaddress
import json
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit

from flask import abort, g, redirect, render_template, request, session
from mcp.server.auth.provider import AccessToken, AuthorizationCode, AuthorizeError, RegistrationError, TokenError
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


def digest(value): return hashlib.sha256(value.encode()).hexdigest()


class BoundCode(AuthorizationCode):
    grant_id: str
    owner: str
    revision: str
    mfa_binding: str
    duration: int


class DCCOAuth:
    def __init__(self, public):
        self.public, self.state = public, public.state
        with self.state.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS mcp_oauth_clients(id TEXT PRIMARY KEY,data TEXT,expires REAL);
                CREATE TABLE IF NOT EXISTS mcp_oauth_pending(id TEXT PRIMARY KEY,data TEXT,expires REAL);
                CREATE TABLE IF NOT EXISTS mcp_oauth_codes(hash TEXT PRIMARY KEY,data TEXT,expires REAL);
                CREATE TABLE IF NOT EXISTS mcp_oauth_sessions(hash TEXT PRIMARY KEY,data TEXT,expires REAL,idle_until REAL,revoked INTEGER DEFAULT 0);
            ''')

    def cleanup(self):
        with self.state.connect() as db:
            for table in ('mcp_oauth_clients','mcp_oauth_pending','mcp_oauth_codes','mcp_oauth_sessions'):
                db.execute('DELETE FROM '+table+' WHERE expires<?', (time.time(),))

    def grant(self, ident):
        rows = self.state.rows('SELECT * FROM grants WHERE id=? AND revoked=0 AND paused=0',(ident,))
        if not rows or not self.public.enabled(): raise PermissionError('Public MCP is unavailable')
        value = json.loads(rows[0]['data'])
        owner = value.get('public_owner')
        if (value.get('allow_public') is not True or not owner or not self.state.mfa.enabled(owner)
                or value.get('expires') is not None and value['expires'] <= time.time()
                or not self.state.rows("SELECT 1 FROM users WHERE id=? AND role='admin'",(owner,))):
            raise PermissionError('Public MCP grant is unavailable')
        return value

    def mfa_binding(self, owner):
        rows = self.state.rows('SELECT secret FROM mfa WHERE user_id=? AND enabled=1',(owner,))
        return hashlib.sha256(bytes(rows[0]['secret'])).hexdigest() if rows else None

    async def get_client(self, client_id):
        rows = self.state.rows('SELECT data FROM mcp_oauth_clients WHERE id=? AND expires>?',(client_id,time.time()))
        return OAuthClientInformationFull.model_validate_json(rows[0]['data']) if rows else None

    async def register_client(self, client_info):
        self.cleanup()
        if (client_info.token_endpoint_auth_method != 'none' or len(client_info.model_dump_json()) > 10000
                or not 1 <= len(client_info.redirect_uris) <= 8):
            raise RegistrationError('invalid_client_metadata','Public PKCE clients are required')
        for uri in client_info.redirect_uris:
            value = str(uri)
            try:
                parsed = urlsplit(value)
                port = parsed.port
                try: loopback = ipaddress.ip_address(parsed.hostname).is_loopback
                except ValueError: loopback = parsed.hostname == 'localhost'
                valid = (len(value) <= 2048 and not any(ord(char) < 33 or ord(char) == 127 for char in value)
                         and not parsed.fragment and not parsed.username and not parsed.password
                         and bool(parsed.hostname) and (port is None or 1 <= port <= 65535)
                         and (parsed.scheme == 'https' or parsed.scheme == 'http' and loopback))
            except (ValueError, TypeError):
                valid = False
            if not valid:
                raise RegistrationError('invalid_redirect_uri','Use HTTPS or a loopback callback')
        with self.state.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM mcp_oauth_clients').fetchone()[0] >= 128:
                raise RegistrationError('invalid_client_metadata','Client registration limit reached')
            db.execute('INSERT INTO mcp_oauth_clients VALUES(?,?,?)',(client_info.client_id,client_info.model_dump_json(),time.time()+604800))

    async def authorize(self, client, params):
        origin = self.public.saved()['origin']
        resource = params.resource or ''
        match = re.fullmatch(re.escape(origin)+r'/mcp/([a-f0-9]{24})',resource)
        if not match or not params.code_challenge or len(params.model_dump_json()) > 12000:
            raise AuthorizeError('invalid_target','Use the exported grant-specific MCP URL and PKCE')
        try: grant = self.grant(match[1])
        except PermissionError: raise AuthorizeError('access_denied','This grant is unavailable') from None
        self.cleanup()
        ident = secrets.token_urlsafe(32)
        value = {'client':client.client_id,'client_name':str(client.client_name or 'MCP client')[:100],
                 'params':params.model_dump(mode='json'),'grant':match[1],
                 'owner':grant['public_owner']}
        with self.state.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM mcp_oauth_pending').fetchone()[0] >= 128:
                raise AuthorizeError('temporarily_unavailable','Authorization request limit reached')
            db.execute('INSERT INTO mcp_oauth_pending VALUES(?,?,?)',(ident,json.dumps(value),time.time()+300))
        return origin+'/mcp-approve/'+ident

    async def load_authorization_code(self, client, authorization_code):
        rows = self.state.rows('SELECT data FROM mcp_oauth_codes WHERE hash=? AND expires>?',(digest(authorization_code),time.time()))
        if not rows: return None
        value = json.loads(rows[0]['data'])
        if value['client_id'] != client.client_id: return None
        return BoundCode(code=authorization_code,**value)

    async def exchange_authorization_code(self, client, authorization_code):
        code = authorization_code
        try:
            grant = self.grant(code.grant_id)
            if grant.get('revision') != code.revision or self.mfa_binding(code.owner) != code.mfa_binding:
                raise PermissionError()
        except PermissionError: raise TokenError('invalid_grant','Grant or second factor changed') from None
        token = secrets.token_urlsafe(48)
        now = time.time(); expires = min(now+60*code.duration,grant.get('expires') or float('inf'))
        value = {'client':client.client_id,'grant':code.grant_id,'owner':code.owner,'revision':code.revision,
                 'mfa_binding':code.mfa_binding,'resource':code.resource,'created':now}
        with self.state.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('DELETE FROM mcp_oauth_codes WHERE hash=? AND expires>?',(digest(code.code),now)).rowcount != 1:
                raise TokenError('invalid_grant','Authorization code already used or expired')
            if db.execute('SELECT COUNT(*) FROM mcp_oauth_sessions WHERE revoked=0 AND expires>? AND idle_until>?',(now,now)).fetchone()[0] >= 64:
                raise TokenError('invalid_grant','Session limit reached')
            db.execute('INSERT INTO mcp_oauth_sessions VALUES(?,?,?,?,0)',(digest(token),json.dumps(value),expires,min(expires,now+600)))
            self.state.write_audit(db,code.owner,'mcp.oauth.session',code.grant_id,201)
        return OAuthToken(access_token=token,token_type='Bearer',expires_in=max(1,int(expires-now)),scope='dcc')

    def active(self, token_hash, touch=False):
        now = time.time()
        rows = self.state.rows('SELECT * FROM mcp_oauth_sessions WHERE hash=? AND revoked=0 AND expires>? AND idle_until>?',(token_hash,now,now))
        if not rows: return None
        value = json.loads(rows[0]['data'])
        try: grant = self.grant(value['grant'])
        except PermissionError: return None
        if (grant.get('revision') != value['revision'] or grant.get('public_owner') != value['owner']
                or not secrets.compare_digest(value['mfa_binding'],self.mfa_binding(value['owner']) or '')):
            return None
        if touch:
            if self.state.execute('UPDATE mcp_oauth_sessions SET idle_until=? WHERE hash=? AND revoked=0 AND expires>? AND idle_until>?',
                    (min(rows[0]['expires'],now+600),token_hash,now,now)) != 1: return None
        return value

    async def load_access_token(self, token):
        value = self.active(digest(token))
        if not value: return None
        row = self.state.rows('SELECT expires FROM mcp_oauth_sessions WHERE hash=?',(digest(token),))[0]
        return AccessToken(token=token,client_id=value['client'],scopes=['dcc'],expires_at=int(row['expires']),resource=value['resource'],subject=value['owner'])

    async def verify_token(self, token): return await self.load_access_token(token)
    async def load_refresh_token(self, client, refresh_token): return None
    async def exchange_refresh_token(self, client, refresh_token, scopes): raise TokenError('invalid_grant','Fresh human authorization is required')
    async def revoke_token(self, token):
        self.state.execute('UPDATE mcp_oauth_sessions SET revoked=1 WHERE hash=?',(digest(token.token),))
        self.public.close_inactive()

    def revoke_user(self, owner):
        # Revoke the entire authorization chain. Pending approvals created by
        # older versions lack an owner field; resolve those via their grant.
        with self.state.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE mcp_oauth_sessions SET revoked=1 WHERE json_extract(data,'$.owner')=?",(owner,))
            db.execute("DELETE FROM mcp_oauth_codes WHERE json_extract(data,'$.owner')=?",(owner,))
            db.execute('''DELETE FROM mcp_oauth_pending WHERE json_extract(data,'$.owner')=?
                OR (json_extract(data,'$.owner') IS NULL AND json_extract(data,'$.grant') IN
                    (SELECT id FROM grants WHERE json_extract(data,'$.public_owner')=?))''',(owner,owner))
        self.public.close_inactive()


def register_approval(app, public, reauthenticate):
    oauth = public.oauth

    @app.route('/mcp-approve/<pending_id>',methods=['GET','POST'])
    def mcp_approve(pending_id):
        if not public.enabled() or not public.tls() or request.host != urlsplit(public.saved()['origin']).netloc:
            abort(403)
        if not g.user:
            session['mcp_login_next'] = pending_id
            return redirect('/login')
        rows = oauth.state.rows('SELECT * FROM mcp_oauth_pending WHERE id=? AND expires>?',(pending_id,time.time()))
        if not rows: abort(410,'This authorization request expired or was already approved')
        pending = json.loads(rows[0]['data'])
        try: grant = oauth.grant(pending['grant'])
        except PermissionError: abort(403)
        if pending.get('owner', grant['public_owner']) != grant['public_owner']: abort(403)
        if g.user['id'] != grant['public_owner']: abort(403,'Only this grant owner can authorize the session')
        # Bind conscious approval to the browser that reviewed this challenge.
        binding = hashlib.sha256(session['sid'].encode()).hexdigest()
        if request.method=='GET':
            session['mcp_approval'] = {'id':pending_id,'binding':binding}
        else:
            approval = session.get('mcp_approval',{})
            if approval != {'id':pending_id,'binding':binding} or request.form.get('confirm') != 'yes':
                abort(403,'Review and explicitly confirm this client request')
            code = request.form.get('otp','')
            if not re.fullmatch(r'[0-9]{6}',code): abort(403,'A fresh six-digit authenticator code is required')
            reauthenticate({'current_password':request.form.get('current_password'),'otp':code})
            try: duration = int(request.form.get('duration','15'))
            except ValueError: abort(400)
            if duration not in (15,30,60) or duration > grant.get('public_session_minutes',30): abort(400)
            params = pending['params']; raw = secrets.token_urlsafe(32)
            authcode = BoundCode(code=raw,scopes=['dcc'],expires_at=time.time()+60,client_id=pending['client'],
                code_challenge=params['code_challenge'],redirect_uri=params['redirect_uri'],
                redirect_uri_provided_explicitly=params['redirect_uri_provided_explicitly'],resource=params['resource'],
                subject=g.user['id'],grant_id=pending['grant'],owner=g.user['id'],revision=grant['revision'],
                mfa_binding=oauth.mfa_binding(g.user['id']),duration=duration)
            data = authcode.model_dump(mode='json'); data.pop('code')
            with oauth.state.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute('DELETE FROM mcp_oauth_pending WHERE id=? AND expires>?',(pending_id,time.time())).rowcount != 1: abort(409)
                db.execute('INSERT INTO mcp_oauth_codes VALUES(?,?,?)',(digest(raw),json.dumps(data),authcode.expires_at))
                oauth.state.write_audit(db,g.user['id'],'mcp.oauth.approve',pending['grant'],200)
            session.pop('mcp_approval',None)
            destination = str(authcode.redirect_uri)
            query = {'code':raw,'iss':public.saved()['origin']}
            if params.get('state') is not None: query['state'] = params['state']
            return redirect(destination+('&' if '?' in destination else '?')+urlencode(query))
        profiles = [oauth.state.profile(ident) for ident in grant['profiles']]
        return render_template('mcp_approve.html',pending=pending,grant=grant,profiles=profiles,
                               challenge=hashlib.sha256(pending['params']['code_challenge'].encode()).hexdigest()[:12])
