"""Migration, encrypted transfers and recovery are tested with synthetic material only."""
import base64
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cryptography.fernet import Fernet
import paramiko
from web import create_app
from fixtures import FakeBackend
from state import State
from mfa import MFA, totp
from profile_transfer import ProfileTransfer, seal, unseal
from profile_ssh import connection_options
from host_setup import domain,mount_source,mount_plan,local_container,Domains,test_directory


class AccountSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key=paramiko.RSAKey.generate(1024)
        text=io.StringIO();key.write_private_key(text,password='fixture-passphrase')
        cls.private=text.getvalue().encode()
        cls.known=('fixture.invalid '+key.get_name()+' '+key.get_base64()+'\n').encode()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.master=Fernet.generate_key()
        self.app=create_app({'TESTING':True,'DATA_DIR':self.temp.name,'MASTER_KEY':self.master},backend_factory=FakeBackend)
        self.state=self.app.extensions['dcc_state'];self.client=self.app.test_client()
        self.client.get('/login')
        with self.client.session_transaction() as s:self.csrf=s['csrf']
        self.password='Fixture-account-pass-4477'
        self.client.post('/setup',data={'csrf':self.csrf,'username':'fixture-admin','password':self.password})
        with self.client.session_transaction() as s:self.csrf=s['csrf'];self.sid=s['sid']
        self.user=self.state.rows('SELECT id FROM users')[0]['id']

    def request(self,path,data=None,method='POST'):
        return self.client.open('/api/'+path,method=method,json=data or {},headers={'X-CSRF-Token':self.csrf})

    def token(self,action,target):
        value=self.request('confirmations',{'action':action,'target':target})
        self.assertEqual(value.status_code,200,value.json)
        return value.json['confirmation']

    def upload(self):
        self.state.ssh.write_files([('fixture.pem',self.private),('known_hosts',self.known)])
        self.state.save_profile('ssh',{'name':'Fixture SSH','kind':'ssh','host':'fixture.invalid','username':'fixture','port':22,'key_scope':'shared','key_path':'fixture.pem','permissions':['read','host.exec']},{'passphrase':'fixture-passphrase'})

    def enable_mfa(self):
        setup=self.state.mfa.begin(self.user,'fixture-admin',self.sid)
        codes=self.state.mfa.enable(self.user,totp(setup['secret'],int(time.time())//30),self.sid)
        with self.client.session_transaction() as s:s['mfa_verified']=True
        return setup,codes

    def test_vault_encrypts_and_resolves_only_in_memory_and_selected_deletion(self):
        self.upload()
        self.assertFalse((Path(self.temp.name)/'ssh/fixture.pem').exists())
        self.assertNotIn(b'BEGIN RSA PRIVATE',self.state.path.read_bytes())
        public=self.client.get('/api/profiles').get_data(as_text=True)
        self.assertNotIn('private_key',public);self.assertNotIn('fixture-passphrase',public)
        profile=self.state.profile('ssh',private=True)
        self.assertEqual(profile['credentials']['private_key'].encode(),self.private)
        self.assertIsNotNone(connection_options(profile)['pkey'])
        plan=self.request('profile-ssh/files/delete/preview',{'names':['fixture.pem']}).json
        self.assertEqual(plan['profiles'][0]['id'],'ssh')
        payload={'names':['fixture.pem']}
        self.assertEqual(self.request('profile-ssh/files/delete',payload).status_code,409)
        payload['confirmation']=self.token('profiles.ssh.remove',plan['target'])
        self.assertEqual(self.request('profile-ssh/files/delete',payload).status_code,200)
        self.assertIsNone(self.state.ssh.vault_file('fixture.pem'))
        self.assertTrue((Path(self.temp.name)/'ssh/known_hosts').is_file())
        self.assertEqual(len(self.state.profiles()),2)

    def test_existing_plaintext_profiles_and_managed_keys_are_migrated(self):
        value={'name':'Secret-config-marker','kind':'local','permissions':['read']}
        self.state.execute("UPDATE profiles SET public=? WHERE id='local'",(json.dumps(value),))
        path=Path(self.temp.name)/'ssh';path.mkdir();(path/'fixture.pem').write_bytes(self.private)
        migrated=State(self.temp.name,self.master)
        self.assertEqual(migrated.profile('local')['name'],value['name'])
        self.assertTrue(migrated.rows('SELECT public FROM profiles')[0]['public'].startswith('fernet:'))
        self.assertFalse((path/'fixture.pem').exists())
        self.assertEqual(migrated.vault.decrypt(migrated.ssh.vault_file('fixture.pem')['private']),self.private)
        self.assertNotIn(value['name'].encode(),migrated.path.read_bytes())

    def test_encrypted_export_roundtrip_and_no_plaintext_secret_injection(self):
        self.upload()
        response=self.request('profiles/export',{'current_password':self.password,'backup_password':'fixture-backup-password','include_secrets':True,'ids':['ssh']})
        self.assertEqual(response.status_code,200,response.json)
        raw=json.dumps(response.json)
        for marker in ('fixture-passphrase','fixture.invalid','BEGIN RSA PRIVATE'):
            self.assertNotIn(marker,raw)
        decoded=unseal(response.json,'fixture-backup-password')
        self.assertEqual(decoded['profiles'][0]['credentials']['passphrase'],'fixture-passphrase')
        self.assertEqual(len(decoded['ssh_files']),2)
        with self.assertRaises(ValueError):unseal(response.json,'a-wrong-backup-password')
        altered=dict(response.json,payload=response.json['payload'][:-5]+'xxxxx')
        with self.assertRaises(ValueError):unseal(altered,'fixture-backup-password')
        legacy={'profiles':[{'name':'Legacy','kind':'local','credentials':{'password':'must-not-import'}}],'ssh_files':[{'name':'bad','data':'x'}]}
        values,files=ProfileTransfer(self.state).decode(legacy)
        self.assertEqual(values[0][1],{});self.assertEqual(files,[])
        self.assertEqual(self.client.get('/api/profiles/export').status_code,400)

    def test_export_requires_password_csrf_and_second_factor(self):
        data={'backup_password':'fixture-backup-password','current_password':'wrong'}
        self.assertEqual(self.request('profiles/export',data).status_code,403)
        self.assertEqual(self.client.post('/api/profiles/export',json=data).status_code,403)
        _,codes=self.enable_mfa()
        data['current_password']=self.password
        self.assertEqual(self.request('profiles/export',data).status_code,403)
        data['otp']=codes[0]
        self.assertEqual(self.request('profiles/export',data).status_code,200)
        self.assertEqual(self.request('profiles/export',data).status_code,403)

    def test_import_preview_is_nonmutating_confirmation_is_exact_and_duplicates_skipped(self):
        self.upload()
        incoming={'profiles':[{'name':'Windows profile','mode':'ssh','ssh_target':'fixture@fixture.invalid','ssh_key_path':r'C:\Users\fixture\.ssh\fixture.pem'}]}
        data={'contents':incoming,'shared_keys':True}
        plan=self.request('profiles/transfer/preview',data).json
        self.assertEqual(plan['profiles'][0]['matched_key'],'fixture.pem')
        self.assertEqual(len(self.state.profiles()),2)
        self.assertEqual(self.request('profiles/transfer',data).status_code,409)
        data['confirmation']=self.token('profiles.transfer',plan['target'])
        response=self.request('profiles/transfer',data)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.state.profile(response.json['added'][0])['permissions'],['read'])
        plan=self.request('profiles/transfer/preview',data).json
        self.assertTrue(plan['profiles'][0]['duplicate'])
        data['confirmation']=self.token('profiles.transfer',plan['target'])
        self.assertEqual(self.request('profiles/transfer',data).json['added'],[])

    def test_rfc6238_vectors_replay_enrollment_expiry_and_session_binding(self):
        secret=base64.b32encode(b'12345678901234567890').decode().rstrip('=')
        for timestamp,expected in [(59,'94287082'),(1111111109,'07081804'),(1111111111,'14050471'),(2000000000,'69279037')]:
            self.assertEqual(totp(secret,timestamp//30,digits=8),expected)
        setup=self.state.mfa.begin(self.user,'fixture',self.sid)
        code=totp(setup['secret'],int(time.time())//30)
        with self.assertRaises(ValueError):self.state.mfa.enable(self.user,code,'another-session')
        self.state.execute('UPDATE mfa SET pending_until=0 WHERE user_id=?',(self.user,))
        with self.assertRaises(ValueError):self.state.mfa.enable(self.user,code,self.sid)
        setup,codes=self.enable_mfa()
        self.assertFalse(self.state.mfa.verify(self.user,totp(setup['secret'],int(time.time())//30)))
        self.assertTrue(self.state.mfa.verify(self.user,codes[0]))
        self.assertFalse(self.state.mfa.verify(self.user,codes[0]))
        row=self.state.rows('SELECT * FROM mfa')[0]
        self.assertNotIn(setup['secret'],str(row));self.assertNotIn(codes[1],row['recovery'])

    def test_login_requires_otp_and_enabling_revokes_other_sessions(self):
        other=self.app.test_client();other.get('/login')
        with other.session_transaction() as s:csrf=s['csrf']
        other.post('/login',data={'csrf':csrf,'username':'fixture-admin','password':self.password})
        setup=self.request('account/2fa/setup',{'current_password':self.password}).json
        code=totp(setup['secret'],int(time.time())//30)
        result=self.request('account/2fa/enable',{'current_password':self.password,'otp':code})
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(other.get('/api/bootstrap').status_code,401)
        self.request('logout');self.client.get('/login')
        with self.client.session_transaction() as s:csrf=s['csrf']
        data={'csrf':csrf,'username':'fixture-admin','password':self.password}
        self.assertEqual(self.client.post('/login',data=data).status_code,200)
        self.assertEqual(self.client.get('/api/profiles').status_code,401)
        data['otp']=result.json['recovery_codes'][0]
        self.assertEqual(self.client.post('/login',data=data).status_code,302)

    def test_verified_email_single_use_expiry_and_tls_smtp(self):
        recovery=self.state.recovery
        recovery.configure_smtp({'host':'smtp.example.invalid','sender':'dcc@example.invalid','username':'fixture','password':'secret-smtp-password'})
        self.assertNotIn('secret-smtp-password',str(self.state.rows('SELECT * FROM settings')))
        with patch('recovery.smtplib.SMTP') as smtp:
            recovery.send(self.user,'verify','fixture@example.invalid',self.sid)
            smtp.return_value.starttls.assert_called_once()
            smtp.return_value.login.assert_called_once_with('fixture','secret-smtp-password')
            msg=smtp.return_value.send_message.call_args.args[0]
            code=re.search(r'Code: ([A-F0-9]+)',msg.get_content()).group(1)
        self.assertIsNone(recovery.consume(self.user,'verify',code,'other-session'))
        self.assertEqual(recovery.consume(self.user,'verify',code,self.sid),'fixture@example.invalid')
        self.assertIsNone(recovery.consume(self.user,'verify',code,self.sid))
        with patch('recovery.smtplib.SMTP'):
            recovery.send(self.user,'verify','fixture@example.invalid',self.sid)
        self.state.execute('UPDATE email_tokens SET expires=0')
        self.assertIsNone(recovery.consume(self.user,'verify',code,self.sid))
        with self.app.test_request_context():
            for _ in range(5):recovery.throttle('test-fixture')
            with self.assertRaises(Exception) as error:recovery.throttle('test-fixture')
            self.assertEqual(error.exception.code,429)

    def test_email_reset_requires_password_prior_verified_email_and_emailed_code(self):
        _,codes=self.enable_mfa();recovery=self.state.recovery
        recovery.configure_smtp({'host':'smtp.example.invalid','sender':'dcc@example.invalid'})
        self.state.execute('INSERT INTO recovery_addresses VALUES(?,?)',(self.user,self.state.vault.encrypt(b'fixture@example.invalid')))
        client=self.app.test_client();client.get('/recover-2fa')
        with client.session_transaction() as s:csrf=s['csrf']
        with patch('recovery.smtplib.SMTP') as smtp:
            client.post('/recover-2fa',data={'csrf':csrf,'username':'fixture-admin','password':'wrong','stage':'request'})
            smtp.assert_not_called()
            client.post('/recover-2fa',data={'csrf':csrf,'username':'fixture-admin','password':self.password,'stage':'request'})
            msg=smtp.return_value.send_message.call_args.args[0]
            code=re.search(r'Code: ([A-F0-9]+)',msg.get_content()).group(1)
        self.assertTrue(self.state.mfa.enabled(self.user))
        client.post('/recover-2fa',data={'csrf':csrf,'stage':'confirm','code':code})
        self.assertFalse(self.state.mfa.enabled(self.user))
        self.assertEqual(self.state.rows('SELECT * FROM sessions'),[])

    def test_domain_and_mount_validation_preserve_host_boundaries(self):
        self.assertEqual(domain('DCC.HOME.ARPA'),'dcc.home.arpa')
        for value in ('https://dcc.example.com','x;bad.example','*.example.com','127.0.0.1','evil\n.example.com'):
            with self.assertRaises(ValueError):domain(value)
        self.assertEqual(mount_source(r'C:\Users\fixture\.ssh'),'/run/desktop/mnt/host/c/Users/fixture/.ssh')
        for value in ('../keys','/home/../root','//remote/keys'):
            with self.assertRaises(ValueError):mount_source(value)
        container=MagicMock();container.id='a'*64;container.attrs={'Image':'sha256:fixture','Config':{'Labels':{'com.docker.compose.project':'fixture'}}}
        with self.assertRaisesRegex(ValueError,'Compose'):mount_plan(container,'/fixture')
        with patch('host_setup.Path.is_file',return_value=False),self.assertRaisesRegex(ValueError,'only inside'):local_container(MagicMock())
        docker=MagicMock();docker.containers.create.return_value.wait.return_value={'StatusCode':0}
        test_directory(docker,'sha256:fixture','/fixture')
        mount=docker.containers.create.call_args.kwargs['mounts'][0]
        self.assertEqual(mount['Type'],'bind');self.assertTrue(mount['ReadOnly'])
        self.assertEqual(docker.containers.create.call_args.kwargs['network_mode'],'none')

    def test_public_domain_cookies_are_secure_without_breaking_local_origin(self):
        result=self.request('admin/domains',{'local':'dcc.home.arpa','public':'dcc.example.invalid','current_password':self.password},method='PUT')
        self.assertEqual(result.status_code,200,result.json)
        public=self.app.test_client().get('/login',base_url='https://dcc.example.invalid')
        self.assertIn('; Secure;',public.headers['Set-Cookie'])
        self.assertEqual(self.client.get('/api/profiles').status_code,200)
        self.assertEqual(self.client.get('/api/health',headers={'Host':'untrusted.invalid'}).status_code,400)

    def test_https_extension_has_persistent_configuration_and_retains_certificates_on_failure(self):
        client=MagicMock();container=MagicMock();container.id='a'*64;container.name='fixture-web'
        client.containers.list.return_value=[];client.networks.list.return_value=[]
        service=Domains(self.state)
        result=service.provision(client,container,'dcc.example.com')
        options=client.containers.create.call_args.kwargs
        self.assertEqual(result['url'],'https://dcc.example.com')
        self.assertIn('/config/Caddyfile',options['command'])
        self.assertEqual(options['ports'],{'80/tcp':80,'443/tcp':443})
        self.assertFalse('volumes_from' in options)
        proxy=client.containers.create.return_value
        self.assertEqual(proxy.put_archive.call_args.args[0],'/config')
        import tarfile
        with tarfile.open(fileobj=io.BytesIO(proxy.put_archive.call_args.args[1])) as archive:
            config=archive.extractfile('Caddyfile').read().decode()
        self.assertIn('reverse_proxy dcc-web-upstream:8789',config)
        self.assertNotIn('docker.sock',str(options))
        proxy.start.side_effect=RuntimeError('Port is occupied')
        with self.assertRaises(RuntimeError):service.provision(client,container,'dcc.example.com')
        proxy.remove.assert_called_with(force=True,v=False)

    def test_unsupported_public_domains_are_rejected_before_any_docker_change(self):
        client=MagicMock();container=MagicMock()
        for hostname in ('dcc.home.arpa','dcc.local','dcc.test','dcc.invalid',''):
            with self.assertRaises(ValueError):Domains(self.state).provision(client,container,hostname)
        client.images.pull.assert_not_called();client.networks.create.assert_not_called()

    def test_encrypted_backup_restores_keys_and_config_without_plaintext_database(self):
        self.upload()
        archive=ProfileTransfer(self.state).export(['ssh'],'fixture-backup-pass',True)
        with tempfile.TemporaryDirectory() as directory:
            other=State(directory,Fernet.generate_key());transfer=ProfileTransfer(other)
            plan,prepared,files=transfer.plan(archive,'fixture-backup-pass',shared_keys=True)
            self.assertEqual(len(plan['files']),2)
            ids=transfer.apply(prepared,files)
            restored=other.profile(ids[0],private=True)
            self.assertEqual(restored['credentials']['passphrase'],'fixture-passphrase')
            self.assertIsNotNone(connection_options(restored)['pkey'])
            self.assertEqual(restored['permissions'],['read'])
            self.assertNotIn(b'fixture.invalid',other.path.read_bytes())
            self.assertFalse((Path(directory)/'ssh/fixture.pem').exists())

    def test_profile_security_docs_render_internal_anchor_links(self):
        response=self.client.get('/docs/profiles-security')
        self.assertEqual(response.status_code,200)
        self.assertIn('href="/docs/configuration#ssh-agent"',response.get_data(as_text=True))


if __name__=='__main__':unittest.main()
