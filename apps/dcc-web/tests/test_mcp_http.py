"""Real SDK HTTP/OAuth routes with DCC shared TOTP and live grant policy."""
import base64
import hashlib
import json
from pathlib import Path
import secrets
import sys
import tempfile
import time
import unittest
import io
import tomllib
from zipfile import ZipFile
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cryptography.fernet import Fernet
from mfa import totp
from security import CAPABILITIES
from web import create_app
from fixtures import FakeBackend
from test_mcp_host import FakePTY


class PublicMCPTests(unittest.TestCase):
    origin='https://dcc.example.test'
    password='MCP-HTTP-QA-password-44779'
    secret='JBSWY3DPEHPK3PXP'

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.app=create_app({'TESTING':True,'DATA_DIR':self.temp.name,'MASTER_KEY':Fernet.generate_key()},backend_factory=FakeBackend,terminal_factory=FakePTY)
        self.state=self.app.extensions['dcc_state']; self.public=self.app.extensions['dcc_mcp_http']
        self.addCleanup(self.public.close)
        self.client=self.app.test_client(); self.client.get('/login')
        with self.client.session_transaction() as s: csrf=s['csrf']
        self.client.post('/setup',data={'username':'public-admin','password':self.password,'csrf':csrf})
        with self.client.session_transaction() as s:
            self.csrf=s['csrf']; s['mfa_verified']=True
            self.browser=dict(s)
        self.owner=self.state.rows("SELECT id FROM users WHERE name='public-admin'")[0]['id']
        self.state.execute('INSERT INTO mfa VALUES(?,?,1,-1,?,0,?)',(self.owner,self.state.vault.encrypt(self.secret.encode()),'[]',''))
        self.state.save_profile('ssh-fixture',{'name':'SSH QA','kind':'ssh','host':'192.0.2.9','username':'qa','permissions':sorted(CAPABILITIES)})
        self.step=int(time.time())//30
        self.grant=self.new_grant()
        self.url=self.origin+'/mcp/'+self.grant['id']
        self.rpc='/mcp/'+self.grant['id']
        # Explicitly enable only the isolated test application's public endpoint.
        enabled=self.admin('/api/mcp/http',{'enabled':True,'confirm_public':True,'origin':self.origin})
        self.assertEqual(enabled.status_code,200,enabled.json)
        with self.client.session_transaction(base_url=self.origin) as s: s.update(self.browser)

    def code(self):
        self.step+=1
        return totp(self.secret,self.step)

    def admin(self,path,data,method='PUT'):
        code=self.code()
        with patch('mfa.time',SimpleNamespace(time=lambda:self.step*30)):
            return self.client.open(path,base_url='https://localhost',method=method,
                headers={'X-CSRF-Token':self.csrf},json={**data,'current_password':self.password,'otp':code})

    def new_grant(self):
        response=self.admin('/api/mcp/grants',{'client':'OpenAI Codex','name':'Public QA','profiles':['ssh-fixture'],
            'tools':['list_containers','host_terminal_open','host_terminal_read','host_terminal_write','host_terminal_close'],
            'mode':'write','allow_host_terminal':True,'terminal_profiles':['ssh-fixture'],'allow_public':True,'public_session_minutes':30},'POST')
        self.assertEqual(response.status_code,201,response.json)
        return response.json

    def http(self,path,method='GET',**kwargs):
        return self.client.open(path,base_url=self.origin,method=method,**kwargs)

    def register(self):
        response=self.http('/register','POST',json={'client_name':'QA client','redirect_uris':['http://127.0.0.1:18652/callback'],
            'token_endpoint_auth_method':'none','grant_types':['authorization_code'],'response_types':['code'],'scope':'dcc'})
        self.assertEqual(response.status_code,201,response.json)
        return response.json

    def pending(self,client=None):
        client=client or self.register(); verifier=secrets.token_urlsafe(48)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        args={'response_type':'code','client_id':client['client_id'],'redirect_uri':client['redirect_uris'][0],
            'code_challenge':challenge,'code_challenge_method':'S256','state':'qa-state','scope':'dcc','resource':self.url}
        response=self.http('/authorize?'+urlencode(args))
        self.assertEqual(response.status_code,302,response.json)
        return client,verifier,urlsplit(response.location).path

    def approve(self,path,code=None,**changes):
        page=self.http(path); self.assertEqual(page.status_code,200,page.json)
        with self.client.session_transaction(base_url=self.origin) as s: csrf=s['csrf']
        code=code or self.code()
        with patch('mfa.time',SimpleNamespace(time=lambda:self.step*30)):
            return self.http(path,'POST',headers={'Origin':self.origin},data={
                'csrf':csrf,'current_password':self.password,'otp':code,'confirm':'yes','duration':'15',**changes})

    def exchange(self,client,verifier,code):
        return self.http('/token','POST',data={'grant_type':'authorization_code','client_id':client['client_id'],
            'redirect_uri':client['redirect_uris'][0],'code_verifier':verifier,'code':code,'resource':self.url})

    def session_token(self):
        client,verifier,path=self.pending()
        approved=self.approve(path); self.assertEqual(approved.status_code,302,approved.json)
        code=parse_qs(urlsplit(approved.location).query)['code'][0]
        result=self.exchange(client,verifier,code); self.assertEqual(result.status_code,200,result.json)
        self.assertNotIn('refresh_token',result.json)
        return result.json['access_token']

    def rpc_call(self,token=None,grant=None,name='list_containers',**arguments):
        headers={'Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-11-25'}
        if token is not None: headers['Authorization']='Bearer '+token
        if grant is not None: headers['X-DCC-MCP-Grant']=grant
        return self.http(self.rpc,'POST',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'tools/call',
            'params':{'name':name,'arguments':{'profile':'ssh-fixture',**arguments}}})

    def test_initialize_includes_grant_scoped_safety_instructions(self):
        token=self.session_token()
        response=self.http(self.rpc,'POST',headers={
            'Authorization':'Bearer '+token,
            'X-DCC-MCP-Grant':self.grant['token'],
            'Accept':'application/json, text/event-stream',
            'MCP-Protocol-Version':'2025-11-25'},json={
            'jsonrpc':'2.0','id':1,'method':'initialize',
            'params':{'protocolVersion':'2025-11-25','capabilities':{},
                      'clientInfo':{'name':'DCC QA client','version':'0.1'}}})
        self.assertEqual(response.status_code,200,response.get_data(as_text=True))
        result=response.json['result']
        self.assertEqual(result['serverInfo']['name'],'dcc-web')
        instructions=result['instructions']
        self.assertIn('ONLY through DCC MCP',instructions)
        self.assertIn('Never bypass',instructions)
        self.assertIn('granted tools and profiles',instructions)
        self.assertNotIn(self.grant['token'],instructions)
        self.assertNotIn(token,instructions)

    def test_stolen_grant_and_complete_config_cannot_start_session(self):
        for token,grant in ((None,None),(None,self.grant['token']),(self.grant['token'],self.grant['token']),('x'*64,self.grant['token'])):
            response=self.rpc_call(token,grant)
            self.assertEqual(response.status_code,401,response.json)
            self.assertNotIn('SSH QA',response.get_data(as_text=True))
            self.assertIn('resource_metadata',response.headers['WWW-Authenticate'])
        # A panel cookie and an arbitrary MCP session id do not authorize MCP.
        response=self.http(self.rpc,'POST',headers={'Mcp-Session-Id':'known-session-id','X-DCC-MCP-Grant':self.grant['token']},json={'jsonrpc':'2.0','id':1,'method':'initialize'})
        self.assertEqual(response.status_code,401)

    def test_sdk_pkce_real_token_routes_tamper_replay_and_success(self):
        client,verifier,path=self.pending()
        self.assertEqual(self.approve(path,code='000000').status_code,403)
        approved=self.approve(path); self.assertEqual(approved.status_code,302,approved.json)
        code=parse_qs(urlsplit(approved.location).query)['code'][0]
        self.assertEqual(self.exchange(client,'wrong-verifier',code).status_code,400)
        other=self.register()
        self.assertEqual(self.exchange(other,verifier,code).status_code,400)
        result=self.exchange(client,verifier,code); self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(self.exchange(client,verifier,code).status_code,400)
        token=result.json['access_token']
        response=self.rpc_call(token,self.grant['token'])
        self.assertEqual(response.status_code,200,response.json)
        self.assertFalse(response.json['result']['isError'],response.json)
        self.assertIn('dcc-container-updater',response.get_data(as_text=True))
        stored=json.dumps([dict(row) for row in self.state.rows('SELECT * FROM mcp_oauth_sessions')])
        self.assertNotIn(token,stored)
        self.assertNotIn(code,json.dumps([dict(row) for row in self.state.rows('SELECT * FROM mcp_oauth_codes')]))

    def test_shared_totp_replay_expiry_and_wrong_browser_binding(self):
        client,verifier,path=self.pending()
        reused=self.code()
        with patch('mfa.time',SimpleNamespace(time=lambda:self.step*30)): self.assertTrue(self.state.mfa.verify(self.owner,reused))
        self.assertEqual(self.approve(path,code=reused).status_code,403)
        old=totp(self.secret,self.step-10)
        self.assertEqual(self.approve(path,code=old).status_code,403)
        stranger=self.app.test_client()
        with stranger.session_transaction(base_url=self.origin) as s: s.update(self.browser)
        self.assertEqual(stranger.post(path,base_url=self.origin,data={'csrf':self.csrf,'current_password':self.password,'otp':self.code(),'confirm':'yes'}).status_code,403)
        self.state.execute('UPDATE mcp_oauth_pending SET expires=0')
        self.assertEqual(self.http(path).status_code,410)

    def test_session_expiry_idle_mfa_change_logout_and_endpoint_disable(self):
        for change in ('expiry','idle','mfa','logout','disable'):
            with self.subTest(change=change):
                token=self.session_token(); hashed=hashlib.sha256(token.encode()).hexdigest()
                self.assertEqual(self.rpc_call(token,self.grant['token']).status_code,200)
                if change=='expiry': self.state.execute('UPDATE mcp_oauth_sessions SET expires=0 WHERE hash=?',(hashed,))
                if change=='idle': self.state.execute('UPDATE mcp_oauth_sessions SET idle_until=0 WHERE hash=?',(hashed,))
                if change=='mfa':
                    self.state.execute('UPDATE mfa SET secret=? WHERE user_id=?',(self.state.vault.encrypt(self.secret.encode()),self.owner))
                if change=='logout': self.public.oauth.revoke_user(self.owner)
                if change=='disable':
                    self.assertEqual(self.admin('/api/mcp/http',{'enabled':False}).status_code,200)
                self.assertIn(self.rpc_call(token,self.grant['token']).status_code,(401,404))

    def test_terminals_are_isolated_and_revoke_closes_idle_session(self):
        one,two=self.session_token(),self.session_token()
        opened=self.rpc_call(one,self.grant['token'],name='host_terminal_open').json['result']
        terminal=json.loads(opened['content'][0]['text'])['terminal']
        denied=self.rpc_call(two,self.grant['token'],name='host_terminal_read',terminal=terminal)
        self.assertTrue(denied.json['result']['isError'])
        entry=self.public.entries[hashlib.sha256(one.encode()).hexdigest()]['service']
        session=entry.terminals.get(terminal,entry.digest,entry.connection_id)
        self.state.execute('UPDATE grants SET revoked=1 WHERE id=?',(self.grant['id'],))
        self.assertEqual(self.rpc_call(one,self.grant['token']).status_code,401)
        for _ in range(120):
            if session.closed: break
            time.sleep(.01)
        self.assertTrue(session.closed)

    def test_strict_https_host_origin_limits_and_metadata(self):
        token=self.session_token()
        headers={'Authorization':'Bearer '+token,'X-DCC-MCP-Grant':self.grant['token']}
        self.assertEqual(self.client.post(self.rpc,base_url=self.origin.replace('https:','http:'),headers=headers,json={}).status_code,403)
        self.assertEqual(self.http(self.rpc,'POST',headers={**headers,'Origin':'https://evil.test'},json={}).status_code,403)
        self.assertEqual(self.client.post(self.rpc,base_url=self.origin.replace('https:','http:'),headers={**headers,'X-Forwarded-Proto':'https'},json={}).status_code,403)
        self.assertEqual(self.http(self.rpc+'?token=redacted','POST',headers=headers,json={}).status_code,400)
        self.assertEqual(self.http(self.rpc,'POST',headers=headers,data=b'x'*262145).status_code,413)
        metadata=self.http('/.well-known/oauth-protected-resource'+self.rpc)
        self.assertEqual(metadata.json['resource'],self.url)
        # Stateless transport: no MCP session identifier is a credential.
        self.assertEqual(self.http(self.rpc,headers=headers).status_code,405)

    def test_public_exports_all_platforms_use_https_oauth_without_local_runtime_or_secrets(self):
        for platform in ('windows','linux','macos'):
            response=self.client.get('/api/mcp/bundle/'+self.grant['id']+'?transport=https&platform='+platform,base_url='https://localhost')
            self.assertEqual(response.status_code,200,response.json)
            with ZipFile(io.BytesIO(response.data)) as archive:
                configuration=tomllib.loads(archive.read('.codex/config.toml').decode())['mcp_servers']['dcc']
                self.assertEqual(configuration['url'],self.url)
                self.assertEqual(configuration['auth'],'oauth')
                self.assertEqual(configuration['env_http_headers'],{'X-DCC-MCP-Grant':'DCC_MCP_TOKEN'})
                self.assertNotIn('command',configuration)
                for name in archive.namelist(): self.assertNotIn(self.grant['token'].encode(),archive.read(name))
                instructions=archive.read('AGENTS.md').decode()
                self.assertIn('Streamable HTTP over HTTPS',instructions)
                self.assertIn('Do not bypass',instructions)
                readme=archive.read('README.md').decode()
                self.assertIn('System klienta: '+platform,readme)
                self.assertIn('codex mcp login dcc',readme)
                self.assertIn('keyring',readme)
        self.assertEqual(self.client.get('/api/mcp/config/'+self.grant['id']+'?transport=https&download=plugin',base_url='https://localhost').status_code,400)

    def test_cross_grant_scope_change_and_public_off_do_not_bypass_session_policy(self):
        token=self.session_token()
        other=self.new_grant()
        self.assertEqual(self.rpc_call(token,other['token']).status_code,401)
        metadata=json.loads(self.state.rows('SELECT data FROM grants WHERE id=?',(self.grant['id'],))[0]['data'])
        metadata['revision']='changed-scope'
        self.state.execute('UPDATE grants SET data=? WHERE id=?',(json.dumps(metadata),self.grant['id']))
        self.assertEqual(self.rpc_call(token,self.grant['token']).status_code,401)
        self.assertEqual(self.admin('/api/mcp/http',{'enabled':False}).status_code,200)
        self.assertEqual(self.rpc_call(token,self.grant['token']).status_code,404)
        response=self.client.get('/api/mcp/bundle/'+self.grant['id']+'?transport=https',base_url='https://localhost')
        self.assertEqual(response.status_code,409)

    def test_rejected_grant_token_does_not_refresh_oauth_idle_deadline(self):
        token=self.session_token()
        token_hash=hashlib.sha256(token.encode()).hexdigest()
        self.state.execute('UPDATE mcp_oauth_sessions SET idle_until=? WHERE hash=?',
                           (time.time()+30,token_hash))
        previous=self.state.rows('SELECT idle_until FROM mcp_oauth_sessions WHERE hash=?',(token_hash,))[0]['idle_until']
        other=self.new_grant()
        self.assertEqual(self.rpc_call(token,other['token']).status_code,401)
        after=self.state.rows('SELECT idle_until FROM mcp_oauth_sessions WHERE hash=?',(token_hash,))[0]['idle_until']
        self.assertEqual(previous,after)
        self.assertEqual(self.rpc_call(token,self.grant['token']).status_code,200)
        renewed=self.state.rows('SELECT idle_until FROM mcp_oauth_sessions WHERE hash=?',(token_hash,))[0]['idle_until']
        self.assertGreater(renewed,after)

    def test_login_preserves_pending_oauth_approval_and_rotates_session(self):
        _,_,path=self.pending()
        visitor=self.app.test_client()
        visitor.get('/login',base_url=self.origin)
        with visitor.session_transaction(base_url=self.origin) as s: old_csrf=s['csrf']
        response=visitor.get(path,base_url=self.origin)
        self.assertEqual(response.status_code,302)
        self.assertEqual(urlsplit(response.location).path,'/login')
        login_code=self.code()
        with patch('mfa.time',SimpleNamespace(time=lambda:self.step*30)):
            logged_in=visitor.post('/login',base_url=self.origin,data={
                'csrf':old_csrf,'username':'public-admin','password':self.password,'otp':login_code})
        self.assertEqual(logged_in.status_code,302)
        self.assertEqual(urlsplit(logged_in.location).path,path)
        with visitor.session_transaction(base_url=self.origin) as s:
            self.assertNotEqual(s['csrf'],old_csrf)
            self.assertNotIn('mcp_approval',s)
        self.assertEqual(visitor.get(path,base_url=self.origin).status_code,200)

    def test_registration_rejects_unsafe_redirects_and_excess_callbacks(self):
        base={'client_name':'QA client','token_endpoint_auth_method':'none',
              'grant_types':['authorization_code'],'response_types':['code'],'scope':'dcc'}
        invalid=[
            'http://example.test/callback', 'https://dcc.example.test:bad/callback',
            'https://dcc.example.test:0/callback', 'https://dcc.example.test:65536/callback',
            'https://user@dcc.example.test/callback', 'https://dcc.example.test/callback#fragment',
            'https://dcc.example.test/'+('x'*2050),
        ]
        for uri in invalid:
            with self.subTest(uri=uri[:90]):
                response=self.http('/register','POST',json={**base,'redirect_uris':[uri]})
                self.assertIn(response.status_code,(400,422),response.get_data(as_text=True))
        excessive=['http://127.0.0.1:18652/callback/'+str(n) for n in range(9)]
        response=self.http('/register','POST',json={**base,'redirect_uris':excessive})
        self.assertIn(response.status_code,(400,422),response.get_data(as_text=True))
        valid=self.http('/register','POST',json={**base,
            'redirect_uris':['https://dcc.example.test/callback','http://127.0.0.1:18652/callback']})
        self.assertEqual(valid.status_code,201,valid.get_data(as_text=True))

    def test_oauth_http_request_size_limits_and_invalid_public_origin(self):
        self.assertEqual(self.http('/authorize?'+'x'*16385).status_code,413)
        self.assertEqual(self.http('/register','POST',data=b'x'*16385).status_code,413)
        chunked=self.http('/register','POST',data=b'x'*16385,
            environ_overrides={'CONTENT_LENGTH':'','wsgi.input_terminated':True})
        self.assertEqual(chunked.status_code,413,chunked.get_data(as_text=True))
        for origin in ('http://dcc.example.test','https://dcc.example.test:bad',
                       'https://dcc.example.test:0','https://dcc.example.test:65536',
                       'https://dcc.example.test/not-origin'):
            with self.subTest(origin=origin):
                response=self.admin('/api/mcp/http',{
                    'enabled':True,'confirm_public':True,'origin':origin})
                self.assertEqual(response.status_code,400,response.get_data(as_text=True))


if __name__=='__main__': unittest.main()
