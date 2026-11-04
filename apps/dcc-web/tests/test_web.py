import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import time
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch,MagicMock
from types import SimpleNamespace
import subprocess
import threading
import tomllib

APP_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP_ROOT))
sys.path.insert(0,str(APP_ROOT.parents[1]))
from cryptography.fernet import Fernet
from werkzeug.security import check_password_hash,generate_password_hash
from web import create_app,DEFAULT_SETTINGS,provision_random_admin
from state import State
from security import CAPABILITIES,redact,validate_profile
from catalogs import Catalogs,install_plan,fetch_public,validate_catalog,image_repo
from mcp_preview import MCPService,stdio
from client_adapters import export_client
from engine import DockerBackend,EngineError
from ports import published_ports,enrich_containers,inventory,parse_bindings
from remote_api import VerifiedProfileAdapter,ssh_docker_client
from ai_assistant import validate_connection,proposal
from fixtures import FakeBackend
from dcc_catalog import parse_access_details


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        FakeBackend.commands=[]
        FakeBackend.unavailable=False
        self.app=create_app({"TESTING":True,"DATA_DIR":self.temp.name,"MASTER_KEY":Fernet.generate_key()},backend_factory=FakeBackend)
        self.state=self.app.extensions['dcc_state']
        self.client=self.app.test_client()
        self.client.get('/login')
        with self.client.session_transaction() as session:self.csrf=session['csrf']
        response=self.client.post('/setup',data={'username':'review-admin','password':'ReviewPassword-44-long','csrf':self.csrf})
        self.assertEqual(response.status_code,302)
        with self.client.session_transaction() as session:self.csrf=session['csrf']
        self.state.save_profile('local',{'name':'Review Docker','kind':'local','permissions':sorted(CAPABILITIES)})

    def request(self,path,data=None,method='POST',**kwargs):
        return self.client.open('/api/'+path,method=method,json={'profile':'local',**(data or {})},headers={'X-CSRF-Token':self.csrf},**kwargs)

    def confirmation(self,action,target,profile='local'):
        response=self.request('confirmations',{'action':action,'target':target,'profile':profile})
        self.assertEqual(response.status_code,200,response.json)
        return response.json['confirmation']

    def wait(self,response):
        self.assertEqual(response.status_code,202,response.json)
        for _ in range(100):
            value=self.client.get('/api/jobs/'+response.json['id']).json
            if value['status']!='running':
                self.assertEqual(value['status'],'success',value)
                return value.get('result')
            time.sleep(.01)
        self.fail('Job did not complete')

    def wait_failure(self,response):
        self.assertEqual(response.status_code,202,response.json)
        for _ in range(100):
            value=self.client.get('/api/jobs/'+response.json['id']).json
            if value['status']!='running':
                self.assertEqual(value['status'],'error',value)
                return value
            time.sleep(.01)
        self.fail('Expected job failure did not complete')

    def wait_scan(self,response):
        self.assertEqual(response.status_code,202,response.json)
        for _ in range(200):
            value=self.client.get('/api/catalog/installed/'+response.json['id'])
            self.assertEqual(value.status_code,200,value.get_data(as_text=True))
            if value.json['status']!='running':
                return value.json
            time.sleep(.01)
        self.fail('Installed application scan did not complete')

    def test_lan_first_start_creates_one_random_admin_and_exposes_it_for_install_result(self):
        with tempfile.TemporaryDirectory() as directory:
            state=State(directory,Fernet.generate_key())
            credentials=provision_random_admin(state)
            self.assertIsNotNone(credentials)
            username,password=credentials
            self.assertEqual(username,'admin')
            self.assertGreaterEqual(len(password),24)
            user=state.rows('SELECT name,password FROM users')[0]
            self.assertEqual(user['name'],'admin')
            self.assertTrue(check_password_hash(user['password'],password))
            self.assertNotIn(password.encode(),state.path.read_bytes())
            self.assertIsNone(provision_random_admin(state))
            found=parse_access_details(f'DCC_WEB_INITIAL_CREDENTIALS username={username} password={password}',lang='EN')
            self.assertIn(('Username','admin'),found)
            self.assertIn(('Password',password),found)

    def test_authentication_cookie_and_logout(self):
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertEqual(self.client.get('/api/bootstrap').json['user']['name'],'review-admin')
        self.assertEqual(self.request('logout',{}).status_code,200)
        self.assertEqual(self.client.get('/api/containers').status_code,401)
        cookie_object=self.client.get_cookie('dcc_web_session')
        cookie='HttpOnly; SameSite='+cookie_object.same_site if cookie_object.http_only else ''
        self.assertIn('HttpOnly',cookie)
        self.assertIn('SameSite=Strict',cookie)

    def test_password_is_hashed_and_no_default_password_exists(self):
        user=self.state.rows('SELECT * FROM users')[0]
        self.assertTrue(user['password'].startswith('scrypt:'))
        self.assertNotIn('ReviewPassword-44-long',self.state.path.read_bytes().decode('latin1'))
        self.assertEqual(self.client.post('/setup',data={'csrf':self.csrf}).status_code,302)

    def test_login_rate_limit(self):
        self.request('logout',{})
        self.client.get('/login')
        with self.client.session_transaction() as session:csrf=session['csrf']
        for _ in range(8):
            self.client.post('/login',data={'username':'missing','password':'incorrect','csrf':csrf})
        self.assertEqual(self.client.post('/login',data={'username':'missing','password':'incorrect','csrf':csrf}).status_code,429)

    def test_csrf_origin_host_and_cors(self):
        self.assertEqual(self.client.post('/api/profiles',json={}).status_code,403)
        self.assertEqual(self.client.post('/api/profiles',json={},headers={'X-CSRF-Token':self.csrf,'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.get('/api/bootstrap',headers={'Host':'evil.example'}).status_code,400)
        response=self.client.get('/api/bootstrap',headers={'Origin':'https://evil.example'})
        self.assertNotIn('Access-Control-Allow-Origin',response.headers)
        self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
        self.assertNotEqual(self.client.get('/',headers={'Upgrade':'websocket','Connection':'Upgrade'}).status_code,101)

    def test_profile_credentials_encrypted_and_export_omits_them(self):
        value={'name':'SSH host','kind':'ssh','host':'server.example','username':'docker','credentials':{'password':'Do-not-store-in-plain-text-77'}}
        response=self.request('profiles',value)
        self.assertEqual(response.status_code,201,response.json)
        profile=self.state.profile(response.json['id'],private=True)
        self.assertEqual(profile['credentials']['password'],value['credentials']['password'])
        self.assertNotIn(value['credentials']['password'],self.client.get('/api/profiles/export').get_data(as_text=True))
        for filename in Path(self.temp.name).glob('*'):
            if filename.is_file():self.assertNotIn(value['credentials']['password'].encode(),filename.read_bytes())

    def test_profiles_default_read_only_and_invalid_transport_rejected(self):
        response=self.request('profiles',{'name':'New host','kind':'local'})
        self.assertEqual(response.status_code,201)
        profile=response.json['id']
        self.assertEqual(self.state.profile(profile)['permissions'],['read'])
        self.assertEqual(self.request('containers/abc/start',{'profile':profile}).status_code,403)
        self.assertEqual(self.request('profiles',{'name':'Bad','kind':'ssh','host':'-oProxyCommand=bad','username':'x'}).status_code,400)
        self.assertEqual(self.request('profiles',{'name':'Bad','kind':'tcp','endpoint':'tcp://server:2375','tls_verify':False}).status_code,400)

    def test_import_export_legacy_profiles_and_tunnel(self):
        response=self.request('profiles/import',{'profiles':[{'name':'Old SSH','mode':'ssh','ssh_target':'user@server','ssh_port':22,'ssh_password':'not-imported'}]})
        self.assertEqual(response.status_code,200,response.json)
        profile=self.state.profile(response.json['added'][0],private=True)
        self.assertEqual(profile['kind'],'ssh')
        self.assertEqual(profile['credentials'],{})
        self.assertEqual(validate_profile({'name':'Tunnel','kind':'tunnel','endpoint':'tcp://127.0.0.1:23750'})['kind'],'tunnel')
        with self.assertRaises(ValueError):validate_profile({'name':'Tunnel','kind':'tunnel','endpoint':'tcp://remote:2375'})

    def test_container_read_filter_inspect_and_stats(self):
        response=self.client.get('/api/containers?q=redis&status=running')
        self.assertEqual(len(response.json['containers']),1)
        detail=self.client.get('/api/containers/redis').json
        self.assertNotIn('fixture-secret',json.dumps(detail))
        first=self.client.get('/api/monitoring').json
        second=self.client.get('/api/monitoring').json
        self.assertEqual(len(first['stats']),3)
        self.assertEqual(len(second['history']),2)

    def test_container_listing_reads_restart_policies_in_one_safe_batch(self):
        backend = DockerBackend({'kind':'local'})
        entries = [{'ID':'one','Status':'Up 1 hour'}, {'ID':'two','Status':'Exited'}, {'ID':'three','Status':'Up'}]
        with patch.object(backend, 'json', side_effect=[entries,[{'ID':'one','RestartPolicy':'unless-stopped'},
                                                               {'ID':'two','RestartPolicy':'no'},
                                                               {'ID':'three','RestartPolicy':'on-failure'}]]) as request:
            values = backend.containers()
        self.assertEqual([v['RestartPolicy'] for v in values], ['unless-stopped','no','on-failure'])
        self.assertEqual(request.call_count,2)
        self.assertIn('HostConfig.RestartPolicy.Name',request.call_args.args[0][2])
        with patch.object(backend,'json',side_effect=[entries,EngineError('removed during inspect')]):
            self.assertTrue(all(v['RestartPolicy'] is None for v in backend.containers()))

    def test_container_mutations_require_single_use_bound_confirmation(self):
        self.assertEqual(self.request('containers/redis/stop',{}).status_code,409)
        nonce=self.confirmation('container.stop','redis')
        self.assertEqual(self.request('containers/redis/start',{'confirmation':nonce}).status_code,409)
        self.assertEqual(self.request('containers/redis/stop',{'confirmation':nonce}).status_code,200)
        self.assertEqual(self.request('containers/redis/stop',{'confirmation':nonce}).status_code,409)
        self.assertIn(['stop','redis'],FakeBackend.commands)

    def test_viewer_cannot_mutate_or_manage_profiles(self):
        with self.client.session_transaction() as session:
            digest=hashlib.sha256(session['sid'].encode()).hexdigest()
        user_id=self.state.rows('SELECT user_id FROM sessions WHERE token=?',(digest,))[0]['user_id']
        self.state.execute("UPDATE users SET role='viewer' WHERE id=?",(user_id,))
        self.assertEqual(self.client.get('/api/containers').status_code,200)
        self.assertEqual(self.request('containers/redis/start',{}).status_code,403)
        self.assertEqual(self.request('profiles',{'name':'x'}).status_code,403)
        self.assertEqual(self.client.get('/api/mcp/grants').status_code,403)

    def test_logs_filter_tail_download_and_redaction(self):
        response=self.client.get('/api/logs/redis?q=ERROR&tail=200')
        self.assertIn('Example failure',response.json['logs'])
        self.assertNotIn('Server ready',response.json['logs'])
        raw=self.client.get('/api/logs/redis?download=1')
        self.assertIn('attachment',raw.headers['Content-Disposition'])
        self.assertNotIn('fixture-secret',raw.get_data(as_text=True))

    def test_resources_volume_protection_and_confirmed_pull(self):
        for kind in ('images','volumes','networks'):
            self.assertEqual(self.client.get('/api/resources/'+kind).status_code,200)
        nonce=self.confirmation('volumes.remove','protected-data')
        self.assertEqual(self.request('resources/volumes/remove',{'target':'protected-data','confirmation':nonce,'delete_data':True}).status_code,409)
        nonce=self.confirmation('images.pull','alpine:3.22')
        self.wait(self.request('resources/images/pull',{'target':'alpine:3.22','confirmation':nonce}))
        self.assertIn(['image','pull','alpine:3.22'],FakeBackend.commands)

    def test_catalog_same_68_entries_multi_category_search_and_installed(self):
        catalogs=self.app.extensions['dcc_catalogs']
        self.assertEqual(len(catalogs.fallback),68)
        for category in ('DCC','Aktualizacje'):
            response=self.client.get('/api/catalog?category='+category)
            matches=[v for v in response.json['apps'] if v['name']=='DCC Container Updater']
            self.assertEqual(len(matches),1,category)
        self.assertEqual(self.client.get('/api/catalog').json['categories'][:4],['all','installed','DCC','AI'])
        self.assertEqual(len(self.client.get('/api/catalog?q=CoNtAiNeR%20UpDaTeR').json['apps']),1)
        self.assertEqual(len(self.client.get('/api/catalog?q=nonexistent-fixture-app').json['apps']),0)
        scan=self.wait_scan(self.request('catalog/installed',{}))
        self.assertEqual(scan['status'],'success',scan)
        matches=[v for v in self.client.get('/api/catalog?category=installed').json['apps'] if v['name']=='DCC Container Updater']
        self.assertEqual(len(matches),1,'installed')

    def test_catalog_is_fast_while_slow_installed_host_scan_runs_in_background(self):
        entered,release=threading.Event(),threading.Event()
        def slow_containers(engine):
            entered.set()
            release.wait(3)
            return FakeBackend.entries
        with patch.object(FakeBackend,'containers',slow_containers):
            response=self.client.get('/api/catalog?q=DCC%20Web')
            self.assertEqual(response.status_code,200,response.get_data(as_text=True))
            self.assertEqual(len(response.json['apps']),1)
            self.assertFalse(response.json['installed_known'])
            self.assertFalse(entered.is_set(),'catalog rendering must not contact Docker')
            scan=self.request('catalog/installed',{})
            self.assertEqual(scan.status_code,202,scan.json)
            self.assertTrue(entered.wait(1),'installed scan should run on its own worker')
            while_scan=self.client.get('/api/catalog?category=installed')
            self.assertEqual(while_scan.status_code,200)
            self.assertTrue(while_scan.json['installed_pending'])
            self.assertTrue(any(v['name']=='DCC Web' for v in self.client.get('/api/catalog').json['apps']))
            release.set()
            self.assertEqual(self.wait_scan(scan)['status'],'success')

    def test_catalog_unavailable_host_reports_scan_failure_without_hiding_store(self):
        FakeBackend.unavailable=True
        response=self.client.get('/api/catalog')
        self.assertEqual(response.status_code,200)
        self.assertIsNone(response.json['connected'])
        self.assertFalse(response.json['installed_known'])
        self.assertGreater(len(response.json['apps']),50)
        scan=self.wait_scan(self.request('catalog/installed',{}))
        self.assertEqual(scan['status'],'error')
        refreshed=self.client.get('/api/catalog')
        self.assertEqual(refreshed.status_code,200)
        self.assertTrue(refreshed.json['installed_error'])
        self.assertGreater(len(refreshed.json['apps']),50)

    def test_live_catalog_replaces_bundled_web_version_without_duplicate_or_id_change(self):
        catalogs = self.app.extensions['dcc_catalogs']
        current = next(app for app in catalogs.all() if app['name'] == 'DCC Web')
        catalogs.fallback = [dict(app, image='ghcr.io/hattimon/dcc-web:0.1.0')
                             if app['name'] == 'DCC Web' else dict(app) for app in catalogs.fallback]
        response = self.client.get('/api/catalog?q=DCC%20Web&category=DCC')
        apps = response.json['apps']
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]['image'], current['image'])
        self.assertEqual(apps[0]['id'], current['id'])
        self.assertEqual(apps[0]['category_labels'], ['Administracja', 'DCC', 'WWW'])
        self.assertEqual(self.client.get('/api/catalog?q=dcc-web:0.1.0').json['apps'], [])

    def test_stale_sources_and_duplicate_versions_leave_one_latest_web_in_every_category(self):
        catalogs = self.app.extensions['dcc_catalogs']
        current = next(app for app in catalogs.all() if app['name'] == 'DCC Web')
        stale = dict(current, image='ghcr.io/hattimon/dcc-web:0.1.1')
        # Existing database from an older image, plus an imported old catalog.
        self.state.execute("UPDATE sources SET cache=? WHERE id='official'", (json.dumps([stale]),))
        self.request('catalog/sources', {'source': 'legacy.json', 'contents': {'apps': [stale, current, stale]}})
        for category in ('all', 'DCC', 'Administracja', 'WWW'):
            response = self.client.get('/api/catalog', query_string={'q': 'DCC Web', 'category': category})
            self.assertEqual([app['image'] for app in response.json['apps']], [current['image']], category)
        self.assertEqual(self.client.get('/api/catalog?q=dcc-web:0.1.1').json['apps'], [])
        with patch('catalogs.fetch_public', side_effect=OSError('offline')):
            catalogs.refresh()
        self.assertEqual([a['image'] for a in catalogs.all() if a['name'] == 'DCC Web'], [current['image']])

    def test_refreshed_official_catalog_controls_membership_not_bundled_apps(self):
        catalogs = self.app.extensions['dcc_catalogs']
        new = {'name': 'New remote app', 'image': 'example/new:1', 'category': 'WWW'}
        with patch.object(catalogs, 'download', return_value=[new]):
            catalogs.refresh('official')
        self.assertEqual([a['name'] for a in catalogs.all()], ['New remote app'])
        with patch.object(catalogs, 'download', side_effect=ValueError('offline')):
            catalogs.refresh('official')
        self.assertEqual([a['name'] for a in catalogs.all()], ['New remote app'])

    def test_legacy_override_keeps_dcc_membership(self):
        current=next(v for v in self.app.extensions['dcc_catalogs'].all() if v['name']=='DCC Container Updater')
        old={k:v for k,v in current.items() if k not in {'categories','categories_en','id'}}
        self.request('catalog/sources',{'source':'legacy.json','contents':{'apps':[old]}})
        apps=self.client.get('/api/catalog?category=DCC').json['apps']
        names=[v['name'] for v in apps]
        self.assertEqual(names.count('DCC Container Updater'),1)
        self.assertEqual(names.count('DCC Web'),1)
        self.assertEqual(len(names),len(set(names)))

    def test_catalog_validation_sources_cache_and_main_protection(self):
        self.assertEqual(self.request('catalog/validate',{'contents':{'apps':'wrong'}}).status_code,400)
        response=self.request('catalog/sources',{'source':'catalog.json','contents':{'apps':[{'name':'Fixture app','image':'fixture/app:1','category':'Tools'}]}})
        self.assertEqual(response.status_code,201,response.json)
        ident=response.json['id']
        self.assertEqual(len(self.client.get('/api/catalog/sources/'+ident+'/apps').json['apps']),1)
        self.assertEqual(self.request('catalog/sources/official',{},method='DELETE').status_code,409)
        self.assertEqual(self.request('catalog/sources/official',{'enabled':False},method='PUT').status_code,409)
        self.request('catalog/sources/'+ident,{'enabled':False},method='PUT')
        self.assertEqual(len(self.client.get('/api/catalog?q=Fixture%20app').json['apps']),0)
        with patch('catalogs.fetch_public',side_effect=OSError('offline')):
            self.app.extensions['dcc_catalogs'].refresh('official')
        self.assertEqual(len(self.app.extensions['dcc_catalogs'].all()),68)
        self.assertTrue(self.app.extensions['dcc_catalogs'].sources()[0]['error'])

    def test_install_preview_warnings_conflicts_and_uninstall_retain_volumes(self):
        entry=next(v for v in self.app.extensions['dcc_catalogs'].all() if v['name']=='DCC Container Updater')
        # Name and port are deliberately changed in this isolated fixture.
        config={'name':'new-updater','host_port':'18788'}
        preview=self.request('install/preview',{'app':entry['id'],'configuration':config})
        self.assertEqual(preview.status_code,200,preview.json)
        self.assertIn('docker-socket',preview.json['warnings'])
        nonce=self.confirmation('install',entry['id'])
        missing_ack=self.request('install',{'app':entry['id'],'configuration':config,'confirmation':nonce})
        failed=self.wait_failure(missing_ack)
        self.assertIn('Acknowledge',failed['error'])
        nonce=self.confirmation('install',entry['id'])
        self.wait(self.request('install',{'app':entry['id'],'configuration':config,'acknowledged':preview.json['warnings'],'confirmation':nonce}))
        nonce=self.confirmation('uninstall',entry['id'])
        result=self.wait(self.request('uninstall',{'app':entry['id'],'confirmation':nonce}))
        self.assertTrue(result['volumes_retained'])
        self.assertFalse(any('volume' in cmd and 'rm' in cmd for cmd in FakeBackend.commands))

    def test_uninstall_returns_job_while_slow_host_lookup_runs(self):
        entry=next(v for v in self.app.extensions['dcc_catalogs'].all() if v['name']=='DCC Container Updater')
        entered,release=threading.Event(),threading.Event()
        def slow_containers(engine):
            entered.set()
            release.wait(3)
            return FakeBackend.entries
        nonce=self.confirmation('uninstall',entry['id'])
        with patch.object(FakeBackend,'containers',slow_containers):
            response=self.request('uninstall',{'app':entry['id'],'confirmation':nonce})
            self.assertEqual(response.status_code,202,response.get_data(as_text=True))
            self.assertTrue(entered.wait(1),'uninstall worker should begin independently')
            release.set()
            result=self.wait(response)
        self.assertTrue(result['volumes_retained'])

    def test_all_canonical_presets_have_parseable_safe_options(self):
        engine=FakeBackend({})
        with patch.object(engine,'containers',return_value=[]):
            for index,app in enumerate(self.app.extensions['dcc_catalogs'].fallback):
                if app.get('build_context') or app.get('engines')==['disabled']:
                    continue
                with self.subTest(app=app['name']):
                    plan=install_plan(app,{},engine)
                    self.assertEqual(plan['args'][0],'run')

    def test_install_blocks_shell_arguments_bad_ports_and_architecture(self):
        engine=FakeBackend({})
        base={'name':'Demo','image':'demo:latest','default_name':'demo'}
        for extra in ('--env-file /etc/shadow','--context malicious','; powershell bad'):
            with self.assertRaises(ValueError):install_plan(dict(base,extra=extra),{},engine)
        with self.assertRaises(ValueError):install_plan(base,{'host_port':'99999','container_port':'80'},engine)
        with self.assertRaises(ValueError):install_plan(dict(base,archs=['arm64']),{},engine)
        plan=install_plan(dict(base,extra='-p 53:53/tcp -p 53:53/udp'),{},engine)
        self.assertIn('53:53/udp',plan['args'])

    def test_compose_actions_confirm_and_never_remove_volumes(self):
        self.assertEqual(self.client.get('/api/compose').status_code,200)
        self.assertEqual(self.request('compose/review-project/config',{}).status_code,200)
        self.assertEqual(self.request('compose/review-project/down',{}).status_code,409)
        nonce=self.confirmation('compose.down','review-project')
        self.wait(self.request('compose/review-project/down',{'confirmation':nonce}))
        self.assertIn(['compose','down','review-project'],FakeBackend.commands)
        self.assertFalse(any('--volumes' in cmd for cmd in FakeBackend.commands))

    def test_compose_import_validates_and_saved_project_is_manageable(self):
        nonce=self.confirmation('compose.import','fixture')
        response=self.request('compose/import',{'name':'fixture','content':'services: {}','confirmation':nonce})
        self.assertEqual(response.status_code,200,response.json)
        self.assertTrue(Path(response.json['file']).is_file())
        self.assertIn('fixture',[v['Name'] for v in self.client.get('/api/compose').json['projects']])
        self.assertEqual(self.request('compose/fixture/config',{}).status_code,200)

    def test_compose_config_and_job_results_redact_secret_fields(self):
        with patch.object(FakeBackend,'compose',return_value=json.dumps({'services':{'app':{'environment':{'PASSWORD':'not-for-browser'}}}})):
            response=self.request('compose/review-project/config',{})
            self.assertEqual(response.status_code,200)
            self.assertNotIn('not-for-browser',response.get_data(as_text=True))
        jobs=self.app.extensions['dcc_jobs']
        owner=self.client.get('/api/bootstrap').json['user']['id']
        value=jobs.start(owner,'local','fixture',lambda:{'token':'not-for-browser'})
        for _ in range(100):
            response=self.client.get('/api/jobs/'+value['id'])
            if response.json['status']!='running':break
            time.sleep(.01)
        self.assertNotIn('not-for-browser',response.get_data(as_text=True))

    def test_settings_five_themes_audio_clamps_and_persistence(self):
        self.assertEqual(self.client.get('/api/settings').json['theme'], 'ocean')
        self.assertTrue(DEFAULT_SETTINGS['audio']['enabled'])
        self.assertTrue(self.client.get('/api/settings').json['audio']['enabled'])
        for theme in ('obsidian','violet','ocean','arctic','emerald'):
            response=self.request('settings',{'theme':theme,'accent':'#12ab34','intensity':200,'audio':{'enabled':True,'master':400,'effects':40,'notifications':-10,'style':'warm'}},method='PUT')
            self.assertEqual(response.status_code,200,response.json)
            self.assertEqual(response.json['audio']['master'],100)
            self.assertEqual(response.json['audio']['notifications'],0)
            self.assertEqual(self.client.get('/api/settings').json['theme'],theme)
        self.assertEqual(self.request('settings',{'accent':'url(javascript:bad)'},method='PUT').status_code,400)

    def test_static_assets_audio_and_media_traversal(self):
        for name in ('app.js','app.css','audio/soft/success.wav','audio/clear/error.wav','audio/warm/tab.wav'):
            response=self.client.get('/static/'+name)
            self.assertEqual(response.status_code,200,name)
            response.close()
        self.assertEqual(self.client.get('/media?path=../../README.md').status_code,404)

    def test_mcp_grants_read_scope_revocation_and_safe_export(self):
        response=self.request('mcp/grants',{'name':'Fixture MCP','profiles':['local'],'tools':['list_containers','container_logs']})
        self.assertEqual(response.status_code,201,response.json)
        grant=response.json
        service=MCPService(self.state,grant['token'],FakeBackend)
        self.assertIn('dcc-container-updater',service.call('list_containers',{'profile':'local'})['content'][0]['text'])
        with self.assertRaises(PermissionError):service.call('container_remove',{'profile':'local'})
        with self.assertRaises(PermissionError):service.call('list_containers',{'profile':'other'})
        self.assertNotIn('fixture-secret',service.call('container_logs',{'profile':'local','container':'redis'})['content'][0]['text'])
        self.assertNotIn(grant['token'],self.client.get('/api/mcp/config/'+grant['id']).get_data(as_text=True))
        self.request('mcp/grants/'+grant['id'],{},method='DELETE')
        with self.assertRaises(PermissionError):service.call('list_containers',{'profile':'local'})

    def test_mcp_write_grants_reauthenticate_and_recheck_profile_permissions(self):
        rejected=self.request('mcp/grants',{'profiles':['local'],'mode':'write','tools':['container_restart']})
        self.assertEqual(rejected.status_code,403)
        created=self.request('mcp/grants',{'profiles':['local'],'mode':'write','tools':['container_restart'],
                                            'current_password':'ReviewPassword-44-long'})
        self.assertEqual(created.status_code,201,created.json)
        service=MCPService(self.state,created.json['token'],FakeBackend)
        initialized=service.handle({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}})
        self.assertNotIn('error',initialized)
        service.handle({'jsonrpc':'2.0','method':'notifications/initialized'})
        tools=service.handle({'jsonrpc':'2.0','id':2,'method':'tools/list'})['result']['tools']
        self.assertEqual([item['name'] for item in tools],['container_restart'])
        self.assertFalse(tools[0]['annotations']['readOnlyHint'])
        result=service.call('container_restart',{'profile':'local','container':'dcc-container-updater'})
        self.assertIn('"ok": true',result['content'][0]['text'])
        self.assertIn(['restart','dcc-container-updater'],FakeBackend.commands)
        with self.assertRaises(PermissionError):service.call('container_start',{'profile':'local','container':'redis'})
        self.state.save_profile('local',{'name':'Review Docker','kind':'local','permissions':['read']})
        with self.assertRaises(PermissionError):service.call('container_restart',{'profile':'local','container':'redis'})

    def test_mcp_create_container_validates_ports_volumes_and_keeps_secrets_out_of_results(self):
        created=self.request('mcp/grants',{'profiles':['local'],'mode':'write','tools':['create_container'],
                                            'current_password':'ReviewPassword-44-long'})
        self.assertEqual(created.status_code,201,created.json)
        service=MCPService(self.state,created.json['token'],FakeBackend)
        args={'profile':'local','name':'mcp-demo','image':'example/demo:1','ports':[{'host_port':18788,'container_port':8080}],
              'volumes':[{'name':'demo_data','container_path':'/data'}],'environment':{'APP_PASSWORD':'private-fixture-value'}}
        result=service.call('create_container',args)
        self.assertIn('"ok": true',result['content'][0]['text'])
        self.assertNotIn('private-fixture-value',result['content'][0]['text'])
        self.assertIn('127.0.0.1:18788:8080/tcp',FakeBackend.commands[-1])
        self.assertIn('demo_data:/data',FakeBackend.commands[-1])
        self.assertNotIn('private-fixture-value',str(self.state.rows('SELECT * FROM audit')))
        with self.assertRaises(ValueError):
            service.call('create_container',{**args,'name':'mcp-conflict','ports':[{'host_port':8788,'container_port':80}]})
        with self.assertRaises(ValueError):
            service.call('create_container',{**args,'name':'mcp-bind','ports':[{'host_port':18789,'container_port':80,'host_ip':'0.0.0.0'}]})

    def test_mcp_container_removal_requires_separate_grant_and_preserves_volumes(self):
        values={'profiles':['local'],'mode':'write','tools':['container_remove'],'current_password':'ReviewPassword-44-long'}
        self.assertEqual(self.request('mcp/grants',values).status_code,400)
        values['allow_destructive']=True
        grant=self.request('mcp/grants',values)
        self.assertEqual(grant.status_code,201,grant.json)
        service=MCPService(self.state,grant.json['token'],FakeBackend)
        self.assertTrue(json.loads(service.call('container_remove',{'profile':'local','container':'redis'})['content'][0]['text'])['ok'])
        self.assertIn(['remove','redis'],FakeBackend.commands)
        self.assertFalse(any('volume' in command and 'rm' in command for command in FakeBackend.commands))

    def test_mcp_stdio_framing_unknown_methods_and_no_credentials_in_output(self):
        grant=self.request('mcp/grants',{'profiles':['local']}).json
        stream=io.StringIO('\n'.join(json.dumps(v) for v in [
            {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}},
            {'jsonrpc':'2.0','method':'notifications/initialized'},
            {'jsonrpc':'2.0','id':2,'method':'tools/list'},
            {'jsonrpc':'2.0','id':3,'method':'unknown'},
        ])+'\n[]\n')
        output=io.StringIO()
        with patch.dict('os.environ',{'DCC_MCP_TOKEN':grant['token']}):stdio(self.state,stream,output)
        replies=[json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(replies[0]['result']['protocolVersion'],'2025-11-25')
        self.assertEqual(replies[1]['result']['tools'][0]['annotations']['readOnlyHint'],True)
        self.assertEqual(replies[2]['error']['code'],-32601)
        self.assertNotIn(grant['token'],output.getvalue())

    def test_security_redaction_and_public_catalog_fetch_reject_private_networks(self):
        self.assertEqual(redact({'password':'private','Env':['TOKEN=secret']}),{'password':'••••','Env':['TOKEN=••••']})
        for url in ('http://example.com/catalog.json','file:///etc/passwd','https://user:secret@example.com/catalog.json'):
            with self.assertRaises(ValueError):fetch_public(url)
        with patch('catalogs.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ValueError):fetch_public('https://internal.example/catalog.json')

    def test_partial_profile_edit_retains_permissions_users_and_credentials(self):
        self.state.save_profile('restricted',{'name':'Restricted','kind':'local','permissions':['read'],'users':['one-user']},{'password':'private-value'})
        self.assertEqual(self.request('profiles/restricted',{'name':'Renamed'},method='PUT').status_code,200)
        profile=self.state.profile('restricted',private=True)
        self.assertEqual(profile['users'],['one-user'])
        self.assertEqual(profile['permissions'],['read'])
        self.assertEqual(profile['credentials']['password'],'private-value')

    def test_expired_confirmation_and_invalid_bulk_target_do_not_execute(self):
        nonce=self.confirmation('container.stop','redis')
        self.state.execute('UPDATE confirmations SET expires=0')
        self.assertEqual(self.request('containers/redis/stop',{'confirmation':nonce}).status_code,409)
        self.assertEqual(self.request('bulk',{'targets':['--all'],'action':'remove'}).status_code,400)
        self.assertFalse(FakeBackend.commands)

    def test_balena_category_and_engine_filter_and_registry_port_identity(self):
        catalog=self.app.extensions['dcc_catalogs']
        self.assertIn('Balena OS',catalog.view()['categories'])
        for app in catalog.view(category='Balena OS',engine_kind='balena')['apps']:
            self.assertTrue(not app.get('engines') or 'balena' in app['engines'] or 'any' in app['engines'])
        self.assertEqual(image_repo('registry.example:5000/team/app:1'),'registry.example:5000/team/app')
        self.assertEqual(image_repo('registry.example:5000/team/app'),'registry.example:5000/team/app')

    def test_command_transports_use_argument_arrays_verified_tls_and_no_shell(self):
        result=SimpleNamespace(stdout='{}',stderr='',returncode=0)
        for profile,prefix in [({'kind':'local','context':'review'},['docker','--context','review']),({'kind':'tcp','endpoint':'tcp://review:2376','credentials':{'tls_ca':'ca.pem'}},['docker','--host','tcp://review:2376','--tlsverify','--tlscacert','ca.pem']),({'kind':'wsl','distro':'Ubuntu'},['wsl.exe','--distribution','Ubuntu','--exec','docker'])]:
            with self.subTest(kind=profile['kind']),patch('engine.subprocess.run',return_value=result) as run,patch('engine.os.name','nt'),patch('engine.subprocess.CREATE_NO_WINDOW',0,create=True):
                DockerBackend(profile).info()
                self.assertEqual(run.call_args.args[0][:len(prefix)],prefix)
                self.assertFalse(run.call_args.kwargs.get('shell',False))
        with patch('engine.subprocess.run',side_effect=subprocess.TimeoutExpired('docker',1)):
            with self.assertRaises(EngineError):DockerBackend({'kind':'local'}).info()

    def test_ssh_transport_rejects_unknown_hosts_and_quotes_container_command(self):
        client=MagicMock();stdin=MagicMock();stdout=MagicMock();stderr=MagicMock()
        stdout.read.return_value=b'ok';stderr.read.return_value=b'';stdout.channel.recv_exit_status.return_value=0
        client.exec_command.return_value=(stdin,stdout,stderr)
        with patch('engine.paramiko.SSHClient',return_value=client):
            DockerBackend({'kind':'ssh','host':'example','username':'review'}).run(['exec','fixture','echo','a; touch /bad'])
        self.assertIn("'a; touch /bad'",client.exec_command.call_args.args[0])
        self.assertEqual(type(client.set_missing_host_key_policy.call_args.args[0]).__name__,'RejectPolicy')
        client.close.assert_called_once()

    def test_configuration_delegates_to_existing_updater_and_retains_environment(self):
        container=SimpleNamespace(attrs={'Config':{'Image':'demo:1','Env':['OLD=retained','CHANGE=old']}},image=SimpleNamespace(id='sha256:existing'))
        client=MagicMock();client.containers.get.return_value=container
        service=MagicMock();service.update_one.return_value={'success':True}
        module=SimpleNamespace(UpdateService=MagicMock(return_value=service))
        nonce=self.confirmation('container.configure','fixture')
        with patch('docker.from_env',return_value=client),patch.dict(sys.modules,{'dcc_shared_update_service':module}):
            self.wait(self.request('configuration/fixture',{'changes':{'environment':{'CHANGE':'new'}},'confirmation':nonce}))
        args,kwargs=service.update_one.call_args
        self.assertEqual(set(args[2]['config']['environment']),{'OLD=retained','CHANGE=new'})
        self.assertTrue(kwargs['_image_already_pulled'])
        self.assertEqual(kwargs['_expected_image_id'],'sha256:existing')
        client.close.assert_called_once()

    def test_mcp_requires_initialization_and_client_exports_are_secret_free(self):
        grant=self.request('mcp/grants',{'profiles':['local']}).json
        service=MCPService(self.state,grant['token'],FakeBackend)
        self.assertIn('error',service.handle({'id':1,'method':'tools/list'}))
        service.handle({'id':2,'method':'initialize','params':{'protocolVersion':'2025-11-25'}})
        self.assertIn('error',service.handle({'id':3,'method':'tools/list'}))
        service.handle({'method':'notifications/initialized'})
        self.assertIn('tools',service.handle({'id':4,'method':'tools/list'})['result'])
        codex=export_client('OpenAI Codex','C:\\Python\\python.exe',['web.py'])
        self.assertEqual(tomllib.loads(codex['configuration'])['mcp_servers']['dcc']['env_vars'],['DCC_MCP_TOKEN'])
        vscode=export_client('VS Code / GitHub Copilot','python',['web.py'])['configuration']
        self.assertTrue(vscode['inputs'][0]['password'])
        self.assertIn('dcc',export_client('Claude Desktop','python',['web.py'])['configuration']['mcpServers'])
        self.assertNotIn(grant['token'],json.dumps(codex)+json.dumps(vscode))

    def test_container_mcp_export_uses_verified_container_nonroot_entrypoint_and_environment(self):
        grant=self.request('mcp/grants',{'profiles':['local'],'client':'OpenAI Codex'}).json
        docker_client=MagicMock()
        with patch.dict('os.environ',{'DCC_WEB_CONTAINER_NAME':'dcc-web'}), \
                patch('docker.from_env',return_value=docker_client), \
                patch('host_setup.local_container',return_value=SimpleNamespace(name='fixture-web-custom')):
            response=self.client.get('/api/mcp/config/'+grant['id'])
        self.assertEqual(response.status_code,200,response.json)
        config=tomllib.loads(response.json['configuration'])['mcp_servers']['dcc']
        self.assertEqual(config['command'],'docker')
        self.assertEqual(config['env_vars'],['DCC_MCP_TOKEN'])
        self.assertEqual(config['args'][:7],['exec','-i','--env','DCC_MCP_TOKEN','fixture-web-custom',
            '/usr/local/bin/dcc-web-entrypoint',sys.executable])
        self.assertEqual(config['args'][-1],'--mcp-stdio')
        self.assertNotIn(grant['token'],json.dumps(response.json))
        docker_client.close.assert_called_once()

    def test_local_docs_routes_and_about_are_available(self):
        self.assertEqual(self.client.get('/about').status_code,200)
        for name in ('installation','configuration','security','catalogs','mcp','ai','themes-audio','feature-matrix','testing'):
            response=self.client.get('/docs/'+name)
            self.assertEqual(response.status_code,200,name)
            self.assertGreater(len(response.data),100)
            self.assertTrue(response.mimetype=='text/html',name)
            self.assertIn(b'markdown-content',response.data,name)
            self.assertIn(b'docs.css',response.data,name)
        security=self.client.get('/docs/security').get_data(as_text=True)
        self.assertIn('<h1',security)
        self.assertIn('<h2',security)
        self.assertIn('<ul>',security)
        matrix=self.client.get('/docs/feature-matrix').get_data(as_text=True)
        self.assertIn('<table>',matrix)

    def test_default_english_language_persists_polish_and_english(self):
        self.assertEqual(self.client.get('/api/settings').json['language'],'EN')
        self.assertIn(b'Active profile',self.client.get('/').data)
        for language,label in [('PL','Aktywny profil'),('EN','Active profile')]:
            self.assertEqual(self.request('settings',{'language':language},method='PUT').status_code,200)
            self.assertEqual(self.client.get('/api/bootstrap').json['settings']['language'],language)
            self.assertIn(label,self.client.get('/').get_data(as_text=True))
        self.assertEqual(self.request('settings',{'language':'XX'},method='PUT').status_code,400)

    def test_documentation_preserves_language_and_resolves_internal_links(self):
        names=('installation','configuration','profiles-security','security','catalogs','mcp','ai','themes-audio','feature-matrix','testing')
        for language in ('PL','EN'):
            self.assertEqual(self.request('settings',{'language':language},method='PUT').status_code,200)
            pages={}
            for name in names:
                response=self.client.get('/docs/'+name)
                self.assertEqual(response.status_code,200,name)
                page=response.get_data(as_text=True)
                self.assertIn('<html lang="'+language.lower()+'"',page,name)
                self.assertIn('href="/docs/configuration?lang='+language+'"',page,name)
                pages[name]=page
            self.assertIn('Konfiguracja i profile' if language=='PL' else 'Configuration and profiles',pages['configuration'])
            self.assertIn('<pre><code>',pages['installation'])
            self.assertIn('Otwórz panel' if language=='PL' else 'Open panel',pages['configuration'])
            for name,page in pages.items():
                article=re.search(r'<article[^>]*>(.*?)</article>',page,re.S).group(1)
                for href in re.findall(r'href="([^"]+)"',article):
                    target=urlsplit(href)
                    if target.scheme or target.netloc or not target.path.startswith('/docs/'):
                        continue
                    destination=target.path.removeprefix('/docs/')
                    self.assertIn(destination,pages,(name,href))
                    self.assertEqual(parse_qs(target.query).get('lang'),[language],(name,href))
                    if target.fragment:
                        self.assertIn('id="'+target.fragment+'"',pages[destination],(name,href))
        self.assertIn('<html lang="pl"',self.client.get('/docs/configuration?lang=PL').get_data(as_text=True))

    def test_panel_links_use_remote_host_and_ipv6_without_javascript_urls(self):
        entries=[{'Ports':'0.0.0.0:9443->9443/tcp, [::]:8080->80/tcp, 127.0.0.1:5000->5000/tcp, 0.0.0.0:53->53/udp'}]
        result=enrich_containers(entries,{'kind':'ssh','host':'192.168.1.7'})[0]
        self.assertEqual([p['url'] for p in result['PanelLinks']],['https://192.168.1.7:9443','http://192.168.1.7:8080'])
        value=enrich_containers([{'Ports':'[::]:8080->80/tcp'}],{'kind':'ssh','host':'2001:db8::10'})[0]
        self.assertEqual(value['PanelLinks'][0]['url'],'http://[2001:db8::10]:8080')
        self.assertEqual(len(published_ports('0.0.0.0:8000-8002->80-82/tcp')),3)
        response=self.client.get('/api/containers')
        self.assertTrue(response.json['containers'][0]['PanelLinks'])

    def test_panel_links_deduplicate_dual_stack_without_losing_bindings_or_distinct_hosts(self):
        ports='0.0.0.0:8788->8788/tcp, [::]:8788->8788/tcp, 127.0.0.1:8788->8788/tcp, 192.0.2.7:8788->8788/tcp, 0.0.0.0:8080->80/tcp'
        entry=enrich_containers([{'Ports':ports}],{'kind':'local'},'127.0.0.1')[0]
        self.assertEqual([v['url'] for v in entry['PanelLinks']],['http://127.0.0.1:8788','http://192.0.2.7:8788','http://127.0.0.1:8080'])
        self.assertEqual(len(entry['PublishedPorts']),5)
        remote=enrich_containers([{'Ports':ports}],{'kind':'ssh','host':'192.168.1.7'})[0]
        self.assertEqual(len(remote['PanelLinks']),3)

    def test_infrastructure_is_profile_scoped_and_exposes_only_host_summary(self):
        response=self.client.get('/api/infrastructure')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['name'],'local-review')
        self.assertEqual(response.json['cpus'],8)
        self.assertEqual(response.json['architecture'],'x86_64')
        self.assertNotIn('credentials',response.json)
        self.assertEqual(response.json['address'],'localhost')
        self.assertEqual(self.request('admin/domains',{'local':'192.168.0.222','public':'','current_password':'ReviewPassword-44-long'},method='PUT').status_code,200)
        lan_client=self.app.test_client();base_url='http://192.168.0.222:8790'
        login=lan_client.get('/login',base_url=base_url)
        with lan_client.session_transaction(base_url=base_url) as session:csrf=session['csrf']
        login=lan_client.post('/login',base_url=base_url,data={'csrf':csrf,'username':'review-admin','password':'ReviewPassword-44-long'})
        self.assertEqual(login.status_code,302)
        lan_response=lan_client.get('/api/infrastructure',base_url=base_url)
        self.assertEqual(lan_response.status_code,200,lan_response.json)
        self.assertEqual(lan_response.json['address'],'192.168.0.222:8790')
        self.state.save_profile('remote-address',{'name':'Remote address test','kind':'ssh','host':'docker.example.test','port':22,'permissions':sorted(CAPABILITIES)})
        remote=self.client.get('/api/infrastructure?profile=remote-address')
        self.assertEqual(remote.status_code,200)
        self.assertEqual(remote.json['address'],'docker.example.test')
        self.assertNotIn('credentials',remote.json)
        self.state.save_profile('remote-address-port',{'name':'Remote address port test','kind':'ssh','host':'docker.example.test','port':2222,'permissions':sorted(CAPABILITIES)})
        remote_port=self.client.get('/api/infrastructure?profile=remote-address-port')
        self.assertEqual(remote_port.status_code,200)
        self.assertEqual(remote_port.json['address'],'docker.example.test:2222')
        self.request('logout')
        self.assertEqual(self.client.get('/api/infrastructure').status_code,401)

    def test_bulk_autostart_preserves_confirmation_scope_and_rejects_duplicates(self):
        targets=['a'*64,'b'*64]
        digest=hashlib.sha256(json.dumps(targets,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(self.request('bulk',{'targets':targets,'action':'autostart-on'}).status_code,409)
        for action in ('autostart-on','autostart-off'):
            result=self.wait(self.request('bulk',{'targets':targets,'action':action,'confirmation':self.confirmation('bulk.'+action,digest)}))
            self.assertTrue(all(v['ok'] for v in result))
            self.assertIn([action,targets[0]],FakeBackend.commands)
        self.assertEqual(self.request('bulk',{'targets':[targets[0],targets[0]],'action':'start'}).status_code,400)

    def test_port_conflicts_offer_free_ports_and_preview_locks_resolved_configuration(self):
        data=self.request('install/ports',{'ports':[8788]}).json
        self.assertEqual(data['suggested']['8788'],8789)
        app={'name':'Test','image':'alpine:3.22'}
        with self.assertRaisesRegex(ValueError,'Suggested free port'):
            install_plan(app,{'name':'new-test','host_port':'8788','container_port':'80'},FakeBackend({}))
        plan=install_plan(app,{'name':'new-test','host_port':'8788','container_port':'80','auto_port':True},FakeBackend({}))
        self.assertIn('8789:80',plan['args'])
        self.assertEqual(plan['port_changes'][0]['from'],8788)
        self.assertEqual(plan['resolved_configuration']['auto_port'],False)
        self.assertEqual(plan['resolved_configuration']['host_port'],'8789')

    def test_mcp_grants_allow_2000_days_and_no_expiry_with_revocation(self):
        value=self.request('mcp/grants',{'profiles':['local'],'days':2000}).json
        metadata=json.loads(self.state.rows('SELECT data FROM grants WHERE id=?',(value['id'],))[0]['data'])
        self.assertGreater(metadata['expires'],time.time()+1999*86400)
        value=self.request('mcp/grants',{'profiles':['local'],'unlimited':True}).json
        metadata=json.loads(self.state.rows('SELECT data FROM grants WHERE id=?',(value['id'],))[0]['data'])
        self.assertIsNone(metadata['expires'])
        service=MCPService(self.state,value['token'],FakeBackend)
        self.assertTrue(service.call('list_containers',{'profile':'local'})['content'])
        self.request('mcp/grants/'+value['id'],{},method='DELETE')
        with self.assertRaises(PermissionError):service.grant()

    def test_ai_connection_encrypts_key_and_preserves_it_on_partial_credential_update(self):
        config={'provider':'compatible','endpoint':'http://127.0.0.1:1234/v1','model':'local-coder','enabled':True,'allow_local':True,'api_key':'not-in-export'}
        response=self.request('ai/connection',config,method='PUT')
        self.assertEqual(response.status_code,200,response.json)
        self.assertTrue(response.json['has_key'])
        self.assertNotIn('not-in-export',response.get_data(as_text=True))
        self.assertNotIn(b'not-in-export',self.state.path.read_bytes())
        config['api_key']=''
        self.assertEqual(self.request('ai/connection',config,method='PUT').status_code,200)
        self.assertTrue(self.client.get('/api/ai/connection').json['has_key'])
        with self.assertRaises(ValueError):validate_connection(dict(config,allow_local=False))
        with self.assertRaises(ValueError):validate_connection(dict(config,endpoint='https://user:secret@example.net/v1'))

    def test_ai_proposes_configuration_only_and_never_executes_docker_commands(self):
        self.request('ai/connection',{'provider':'compatible','endpoint':'https://example.net/v1','model':'coder','enabled':True},method='PUT')
        answer={'configuration':{'name':'proposed','image':'alpine:3.22','host_port':'8788','container_port':'80','extra':'','command':'sleep 60','environment':{}},'explanation':'Reviewed proposal'}
        with patch('ai_assistant.request_json',return_value={'choices':[{'message':{'content':json.dumps(answer)}}]}) as request_ai:
            response=self.request('ai/propose',{'prompt':'Fix this configuration','configuration':{'image':'alpine:3.22','environment':{'PASSWORD':'never-send-me'}},'send_context':True,'auto_port':True})
        self.assertEqual(response.status_code,200,response.json)
        self.assertFalse(response.json['executed'])
        self.assertEqual(response.json['configuration']['host_port'],'8789')
        self.assertNotIn('never-send-me',str(request_ai.call_args))
        self.assertFalse(FakeBackend.commands)

    def test_ai_provider_adapters_and_unsafe_proposals_are_rejected(self):
        answer={'configuration':{'name':'example','image':'alpine:3.22','extra':'--env-file /etc/shadow'},'explanation':'test'}
        self.request('ai/connection',{'provider':'ollama','endpoint':'http://127.0.0.1:11434','model':'coder','enabled':True,'allow_local':True},method='PUT')
        with patch('ai_assistant.request_json',return_value={'response':json.dumps(answer)}):
            self.assertEqual(self.request('ai/propose',{'prompt':'test'}).status_code,400)
        config={'name':'proposed','image':'alpine:3.22'}
        for provider,response in [('openai',{'output':[{'content':[{'type':'output_text','text':json.dumps({'configuration':config})}]}]}),('ollama',{'response':json.dumps({'configuration':config})})]:
            with patch('ai_assistant.request_json',return_value=response) as request_ai:
                value,_=proposal({'provider':provider,'model':'test'},'request',{}, {},'EN')
                self.assertEqual(value['name'],'proposed')
                self.assertTrue(request_ai.call_args.args[1].endswith('/responses' if provider=='openai' else '/api/generate'))

    def test_edit_port_validation_supports_ipv6_and_rejects_bad_bindings(self):
        value=parse_bindings('8080:80/tcp\n[::1]:8443:443/tcp\n127.0.0.1:5353:53/udp')
        self.assertEqual(value['80/tcp'][0],{'HostIp':'','HostPort':'8080'})
        self.assertEqual(value['443/tcp'][0]['HostIp'],'::1')
        for text in ('70000:80','127.0.0.1:22:0','--publish-all','example.com:80:80'):
            with self.assertRaises(ValueError):parse_bindings(text)

    def test_ssh_api_transport_verifies_host_and_keeps_password_out_of_url(self):
        profile={'kind':'ssh','host':'example','username':'operator','credentials':{'password':'only-in-vault'}}
        ssh=MagicMock()
        with patch('remote_api.paramiko.SSHClient',return_value=ssh):
            adapter=VerifiedProfileAdapter(profile)
            self.assertEqual(type(ssh.set_missing_host_key_policy.call_args.args[0]).__name__,'RejectPolicy')
            self.assertEqual(ssh.connect.call_args.kwargs['password'],'only-in-vault')
            connection=adapter.get_connection('http+docker://ssh/version')._new_conn()
            connection.connect()
            ssh.get_transport.return_value.open_session.return_value.exec_command.assert_called_with('docker system dial-stdio')
            adapter.close()
        client=MagicMock();client.api._retrieve_server_version.return_value='1.55'
        with patch('remote_api.docker.DockerClient',return_value=client) as create,patch('remote_api.VerifiedProfileAdapter'):
            self.assertIs(ssh_docker_client(profile),client)
        self.assertEqual(create.call_args.kwargs['version'],'1.44')
        self.assertNotIn('only-in-vault',str(create.call_args))
        self.assertEqual(client.api._version,'1.55')

    def test_ai_edit_proposal_keeps_own_name_and_published_ports(self):
        self.request('ai/connection',{'provider':'compatible','endpoint':'https://example.net/v1','model':'coder','enabled':True},method='PUT')
        answer={'configuration':{'name':'dcc-container-updater','image':'ghcr.io/hattimon/dcc-container-updater:latest','host_port':'8788','container_port':'8788','extra':''}}
        with patch('ai_assistant.request_json',return_value={'choices':[{'message':{'content':json.dumps(answer)}}]}):
            response=self.request('ai/propose',{'prompt':'Keep existing ports','target':'dcc-container-updater','configuration':answer['configuration'],'auto_port':True})
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['configuration']['host_port'],'8788')

    def test_ai_endpoint_change_does_not_forward_a_previous_provider_secret(self):
        config={'provider':'compatible','endpoint':'https://first.example/v1','model':'coder','enabled':True,'api_key':'do-not-forward'}
        self.assertEqual(self.request('ai/connection',config,method='PUT').status_code,200)
        config.update(endpoint='https://other.example/v1',api_key='')
        self.assertFalse(self.request('ai/connection',config,method='PUT').json['has_key'])
        self.assertEqual(self.request('ai/connection',dict(config,api_key='bad\r\nheader'),method='PUT').status_code,400)

    def test_lifecycle_cannot_race_an_active_update_or_install_job(self):
        jobs=self.app.extensions['dcc_jobs'];jobs.active.add('local')
        nonce=self.confirmation('container.stop','redis')
        self.assertEqual(self.request('containers/redis/stop',{'confirmation':nonce}).status_code,400)
        self.assertFalse(FakeBackend.commands)
        jobs.active.clear()
        nonce=self.confirmation('container.stop','redis')
        self.assertEqual(self.request('containers/redis/stop',{'confirmation':nonce}).status_code,200)


if __name__=='__main__':unittest.main()
