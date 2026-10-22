import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DCC_UPDATER_DATA", tempfile.mkdtemp(prefix="dcc-updater-tests-"))

from updater import UpdateService
from web import AutoUpdateStore, JobManager, create_app


class WebSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(self.temp.name, print_credentials=False)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def _csrf(self, page="/login"):
        response = self.client.get(page)
        self.assertEqual(response.status_code, 200)
        import re
        match = re.search(rb'name="csrf-token" content="([^"]+)"', response.data)
        if not match:
            match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        return match.group(1).decode()

    def test_panel_requires_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        api = self.client.get("/api/containers")
        self.assertEqual(api.status_code, 401)

    def test_login_requires_csrf_token_and_valid_password(self):
        password = self.app.extensions["dcc_updater_initial_password"]
        csrf = self._csrf()
        rejected = self.client.post("/login", data={"password": password})
        self.assertEqual(rejected.status_code, 400)
        accepted = self.client.post("/login", data={"csrf_token": csrf, "password": password})
        self.assertEqual(accepted.status_code, 302)
        panel = self.client.get("/")
        self.assertEqual(panel.status_code, 200)
        self.assertIn(b"Docker", panel.data)
        self.assertIn(b"Compose services require manual review", panel.data)
        self.assertIn(b'lang="en"', panel.data)

    def test_api_post_requires_csrf_token(self):
        password = self.app.extensions["dcc_updater_initial_password"]
        csrf = self._csrf()
        self.client.post("/login", data={"csrf_token": csrf, "password": password})
        response = self.client.post("/api/scan")
        self.assertEqual(response.status_code, 400)

    def test_reports_and_notification_settings_require_login_and_mutations_require_csrf(self):
        for route in ('/api/reports','/api/notifications'):
            self.assertEqual(self.client.get(route).status_code,401)
        with self.client.session_transaction() as state:
            state.update(authenticated=True,csrf_token='test-token')
        for route in ('/api/notifications','/api/notifications/test'):
            self.assertEqual(self.client.post(route,json={}).status_code,400)
        reports=self.app.extensions['dcc_updater_reports']
        for index in range(12):reports.append('update','error' if index==0 else 'success')
        self.assertEqual(len(self.client.get('/api/reports?page=2').get_json()['entries']),2)
        self.assertEqual(self.client.get('/api/reports?issues_only=1').get_json()['total'],1)
        self.assertEqual(self.client.get('/api/reports?page=invalid').status_code,200)

    def test_notification_api_never_returns_tokens_and_test_delivery_requires_explicit_request(self):
        with self.client.session_transaction() as state:
            state.update(authenticated=True,csrf_token='test-token')
        headers={'X-CSRF-Token':'test-token'}
        service=self.app.extensions['dcc_updater_notifications']
        calls=[]
        service.transport=lambda *args: calls.append(args) or {'ok':True}
        config={'enabled':True,'telegram':{'enabled':True,'bot_token':'12345:TEST_TOKEN','chat_id':'123456'}}
        result=self.client.post('/api/notifications',json=config,headers=headers)
        self.assertEqual(result.status_code,200)
        self.assertNotIn(b'TEST_TOKEN',result.data)
        self.assertNotIn(b'TEST_TOKEN',self.client.get('/api/notifications').data)
        self.assertEqual(calls,[])
        for payload in ([],{'channel':[]},{'channel':'unknown'}):
            self.assertEqual(self.client.post('/api/notifications/test',json=payload,headers=headers).status_code,400)
        self.assertEqual(self.client.post('/api/notifications/test',json={'channel':'telegram'},headers=headers).status_code,200)
        self.assertEqual(len(calls),1)

    def test_language_defaults_to_english_and_last_selection_survives_logout_and_new_session(self):
        self.assertIn(b'lang="en"', self.client.get('/login').data)
        csrf = self._csrf()
        self.assertEqual(self.client.post('/language', data={'language': 'pl'}).status_code, 400)
        self.client.post('/language', data={'language': 'pl', 'csrf_token': csrf})
        self.client.post('/login', data={'csrf_token': csrf, 'password': self.app.extensions['dcc_updater_initial_password']})
        self.assertIn(b'lang="pl"', self.client.get('/').data)
        self.client.post('/logout', data={'csrf_token': self._csrf('/')})
        fresh_client = self.app.test_client()
        self.assertIn(b'lang="pl"', fresh_client.get('/login').data)
        self.assertEqual((Path(self.temp.name) / 'language').read_text(), 'pl')

    def test_english_diagnostics_do_not_translate_container_names_or_image_references(self):
        from i18n import localize_payload
        payload = {'name': 'Obraz jest aktualny.', 'current_image': 'rejestr:latest',
                   'message': 'Obraz jest aktualny.', 'source': 'digest rejestru',
                   'updates': [{'result': 'Brak dostępnej aktualizacji.'}]}
        localized = localize_payload(payload, 'en')
        self.assertEqual(localized['name'], payload['name'])
        self.assertEqual(localized['current_image'], payload['current_image'])
        self.assertEqual(localized['message'], 'The image is up to date.')
        self.assertEqual(localized['updates'][0]['result'], 'No update is available.')
        self.assertEqual(localize_payload(payload, 'pl'), payload)

    def test_panel_update_decision_blocks_scan_then_defer_releases_startup_auto_queue(self):
        calls = []

        class Service:
            client = SimpleNamespace(ping=lambda: None)

            def check_self_update(self, _progress):
                calls.append('check')
                return {'checked': True, 'supported': True, 'update_available': True}

            def scan(self, _progress):
                calls.append('scan')
                return [{'id': 'one', 'name': 'generic', 'current_image': 'example/service:latest',
                         'supported': True, 'update_available': True}]

            def update_selected(self, ids, _progress, *, automatic=False):
                calls.append(('update', ids))
                return [{'name': 'generic', 'ok': True, 'result': 'updated'}]

        with patch.dict(os.environ, {'DCC_UPDATER_STARTUP_DELAY': '300'}):
            app = create_app(self.temp.name, service_factory=Service, print_credentials=False,
                             startup_auto_updates=True)
        app.extensions['dcc_updater_auto_updates'].set('generic', 'example/service:latest', True)
        client = app.test_client()
        with client.session_transaction() as state:
            state.update(authenticated=True, csrf_token='test-token')
        headers = {'X-CSRF-Token': 'test-token'}

        def wait():
            manager = app.extensions['dcc_updater_jobs']
            deadline = time.monotonic() + 2
            while manager.snapshot()['status'] in {'queued', 'running'} and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertEqual(manager.snapshot()['status'], 'done')
            return manager.snapshot()

        self.assertEqual(client.post('/api/self-update/check', json={}, headers=headers).status_code, 202)
        wait()
        self.assertEqual(calls, ['check'])
        self.assertEqual(client.post('/api/scan', json={}, headers=headers).status_code, 409)
        self.assertEqual(calls, ['check'])
        self.assertEqual(client.post('/api/scan', json={'defer_panel_update': True}, headers=headers).status_code, 202)
        result = wait()['results']
        self.assertEqual(calls, ['check', 'scan', ('update', ['one']), 'scan'])
        self.assertTrue(result['updates'][0]['ok'])
        self.assertEqual(client.post('/api/scan', json={}, headers=headers).status_code, 202)
        wait()
        self.assertEqual(calls.count(('update', ['one'])), 1)

    def test_last_scan_cache_and_time_survive_language_change_without_a_new_scan(self):
        calls = []

        class Service:
            def check_self_update(self, _progress):
                calls.append('check')
                return {'checked': True, 'update_available': False}

            def scan(self, _progress):
                calls.append('scan')
                return [{'id': 'one', 'name': 'generic', 'current_image': 'example/service:latest',
                         'supported': True, 'message': 'Obraz jest aktualny.'}]

        app = create_app(self.temp.name, service_factory=Service, print_credentials=False)
        client = app.test_client()
        with client.session_transaction() as state:
            state.update(authenticated=True, csrf_token='test-token')
        headers = {'X-CSRF-Token': 'test-token'}

        def wait():
            manager = app.extensions['dcc_updater_jobs']
            deadline = time.monotonic() + 2
            while manager.snapshot()['status'] in {'queued', 'running'} and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertEqual(manager.snapshot()['status'], 'done')

        self.assertIsNone(client.get('/api/containers').get_json()['scanned_at'])
        client.post('/api/self-update/check', json={}, headers=headers)
        wait()
        self.assertEqual(calls, ['check'])
        before = time.time()
        client.post('/api/scan', json={}, headers=headers)
        wait()
        first = client.get('/api/containers').get_json()
        self.assertGreaterEqual(first['scanned_at'], before)
        self.assertEqual(first['containers'][0]['message'], 'The image is up to date.')
        client.post('/language', data={'csrf_token': 'test-token', 'language': 'pl'})
        client.get('/')
        client.post('/api/self-update/check', json={}, headers=headers)
        wait()
        second = client.get('/api/containers').get_json()
        self.assertEqual(second['scanned_at'], first['scanned_at'])
        self.assertEqual(second['containers'][0]['message'], 'Obraz jest aktualny.')
        self.assertEqual(calls, ['check', 'scan', 'check'])
        reloaded_app = create_app(self.temp.name, service_factory=Service, print_credentials=False)
        reloaded_client = reloaded_app.test_client()
        with reloaded_client.session_transaction() as state:
            state.update(authenticated=True)
        restored = reloaded_client.get('/api/containers').get_json()
        self.assertEqual(restored['scanned_at'], first['scanned_at'])
        self.assertEqual(restored['containers'][0]['name'], 'generic')
        self.assertEqual(calls, ['check', 'scan', 'check'])

    def test_panel_exposes_manual_self_update_controls(self):
        password = self.app.extensions["dcc_updater_initial_password"]
        csrf = self._csrf()
        self.client.post("/login", data={"csrf_token": csrf, "password": password})
        response = self.client.get("/")
        self.assertIn(b"Check panel update", response.data)
        self.assertIn(b"Update panel", response.data)

    def test_auto_scan_refresh_is_optin_persistent_and_csrf_protected(self):
        with self.client.session_transaction() as state:
            state.update(authenticated=True, csrf_token='settings-test')
        headers = {'X-CSRF-Token': 'settings-test'}
        self.assertFalse(self.client.get('/api/containers').get_json()['auto_scan_on_refresh'])
        self.assertEqual(self.client.post('/api/scan-settings', json={'auto_scan_on_refresh': True}).status_code, 400)
        self.assertEqual(self.client.post('/api/scan-settings', json={'auto_scan_on_refresh': 'true'}, headers=headers).status_code, 400)
        self.assertEqual(self.client.post('/api/scan-settings', json={'auto_scan_on_refresh': True}, headers=headers).status_code, 200)
        restarted = create_app(self.temp.name, print_credentials=False).test_client()
        with restarted.session_transaction() as state:
            state.update(authenticated=True)
        self.assertTrue(restarted.get('/api/containers').get_json()['auto_scan_on_refresh'])
        self.assertIsNone(restarted.get('/api/containers').get_json()['scanned_at'])

    def test_schedule_is_disabled_by_default_and_requires_csrf(self):
        self.assertEqual(self.client.get('/api/schedule').status_code, 401)
        with self.client.session_transaction() as state:
            state.update(authenticated=True, csrf_token='schedule-test')
        config = self.client.get('/api/schedule').get_json()['config']
        self.assertFalse(config['enabled'])
        self.assertFalse(config['panel_first'])
        self.assertEqual(self.client.post('/api/schedule', json=config).status_code, 400)
        self.assertEqual(self.client.post('/api/schedule', json=config, headers={'X-CSRF-Token': 'schedule-test'}).status_code, 200)

    def test_schedule_update_targets_are_validated_and_bound_to_actual_repositories(self):
        from scheduler import DEFAULT_CONFIG
        class Service:
            client = SimpleNamespace(containers=SimpleNamespace(get=lambda name: SimpleNamespace(name=name, attrs={'Config': {'Image': 'ghcr.io/example/app:1'}})))
            _is_self = staticmethod(lambda container: container.name == 'panel')
            _is_compose = staticmethod(lambda container: container.name == 'compose')
            _unsupported_reason = staticmethod(lambda _container: None)
        app = create_app(self.temp.name, service_factory=Service, print_credentials=False)
        client = app.test_client()
        with client.session_transaction() as state:
            state.update(authenticated=True, csrf_token='schedule-test')
        headers = {'X-CSRF-Token': 'schedule-test'}
        payload = {**DEFAULT_CONFIG, 'enabled': True, 'action': 'update', 'targets': [{'name': 'generic', 'repository': 'untrusted/different'}]}
        response = client.post('/api/schedule', json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['config']['targets'], [{'name': 'generic', 'repository': 'ghcr.io/example/app'}])
        for name in ['panel', 'compose']:
            payload['targets'] = [{'name': name, 'repository': 'ghcr.io/example/app'}]
            self.assertEqual(client.post('/api/schedule', json=payload, headers=headers).status_code, 400)
        self.assertEqual(client.get('/api/schedule').get_json()['config']['targets'][0]['name'], 'generic')

    def test_schedule_all_mode_can_be_saved_without_scanning_or_selecting_containers(self):
        from scheduler import DEFAULT_CONFIG
        def unexpected_docker_call():
            self.fail('Saving all mode must not scan or query Docker.')
        app = create_app(self.temp.name, service_factory=unexpected_docker_call, print_credentials=False)
        client = app.test_client()
        with client.session_transaction() as state:
            state.update(authenticated=True, csrf_token='schedule-test')
        response = client.post('/api/schedule', json={**DEFAULT_CONFIG, 'enabled':True, 'action':'update_all'},
                               headers={'X-CSRF-Token':'schedule-test'})
        self.assertEqual(response.status_code,200)
        config = client.get('/api/schedule').get_json()['config']
        self.assertEqual(config['action'],'update_all')
        self.assertEqual(config['targets'],[])
        self.assertFalse(config['panel_first'])

    def test_preferences_require_login_and_csrf_and_persist_after_restart(self):
        self.assertEqual(self.client.get('/api/preferences').status_code,401)
        with self.client.session_transaction() as state:
            state.update(authenticated=True,csrf_token='test-token')
        self.assertEqual(self.client.get('/api/preferences').get_json(),{'theme':'red','sounds_enabled':True,'sound_style':'soft','show_unavailable':False})
        payload={'theme':'green','sounds_enabled':False,'sound_style':'chime','show_unavailable':True}
        self.assertEqual(self.client.post('/api/preferences',json=payload).status_code,400)
        self.assertEqual(self.client.post('/api/preferences',json=payload,headers={'X-CSRF-Token':'test-token'}).status_code,200)
        reloaded=create_app(self.temp.name,print_credentials=False)
        client=reloaded.test_client()
        self.assertIn(b'data-theme="green"',client.get('/login').data)
        with client.session_transaction() as state:state['authenticated']=True
        self.assertEqual(client.get('/api/preferences').get_json(),payload)

    def test_invalid_preferences_never_replace_saved_settings(self):
        with self.client.session_transaction() as state:state.update(authenticated=True,csrf_token='test-token')
        for payload in ([],{'theme':'unknown'},{'theme':[]},{'sounds_enabled':'false'},{'sound_style':{}},{'show_unavailable':'true'}):
            self.assertEqual(self.client.post('/api/preferences',json=payload,headers={'X-CSRF-Token':'test-token'}).status_code,400)
        self.assertEqual(self.client.get('/api/preferences').get_json()['theme'],'red')

    def test_infrastructure_reports_docker_host_instead_of_container_os_and_caches_safe_fields(self):
        calls=[]
        def info():
            calls.append('info')
            return {'Name':'rpi-server','OperatingSystem':'Ubuntu 22.04.5 LTS','OSType':'linux','Architecture':'aarch64',
                    'ServerVersion':'29.0.1','KernelVersion':'6.8.0-raspi','NCPU':4,'MemTotal':8*2**30,'unrelated_secret':'DO_NOT_RETURN'}
        app=create_app(self.temp.name,service_factory=lambda:SimpleNamespace(client=SimpleNamespace(info=info)),print_credentials=False)
        client=app.test_client()
        self.assertEqual(client.get('/api/infrastructure').status_code,401)
        with client.session_transaction() as state:state['authenticated']=True
        response=client.get('/api/infrastructure')
        self.assertTrue(response.get_json()['available'])
        self.assertEqual(response.get_json()['operating_system'],'Ubuntu 22.04.5 LTS')
        self.assertEqual(response.get_json()['architecture'],'aarch64')
        self.assertNotIn(b'DO_NOT_RETURN',response.data)
        client.get('/api/infrastructure')
        self.assertEqual(calls,['info'])

    def test_unavailable_infrastructure_is_nonblocking_and_does_not_leak_exception(self):
        def broken():raise RuntimeError('PRIVATE_CONNECTION_STRING')
        app=create_app(self.temp.name,service_factory=broken,print_credentials=False)
        client=app.test_client()
        with client.session_transaction() as state:state['authenticated']=True
        result=client.get('/api/infrastructure')
        self.assertEqual(result.status_code,200)
        self.assertFalse(result.get_json()['available'])
        self.assertNotIn(b'PRIVATE_CONNECTION_STRING',result.data)

    def test_self_update_actions_require_authentication_and_csrf(self):
        self.assertEqual(self.client.post("/api/self-update/check").status_code, 401)
        self.assertEqual(self.client.post("/api/self-update").status_code, 401)
        password = self.app.extensions["dcc_updater_initial_password"]
        csrf = self._csrf()
        self.client.post("/login", data={"csrf_token": csrf, "password": password})
        self.assertEqual(self.client.post("/api/self-update/check").status_code, 400)
        self.assertEqual(self.client.post("/api/self-update").status_code, 400)

    def test_password_change_checks_length_and_current_password(self):
        password = self.app.extensions["dcc_updater_initial_password"]
        csrf = self._csrf()
        self.client.post("/login", data={"csrf_token": csrf, "password": password})
        csrf = self._csrf("/")
        short = self.client.post("/api/password", json={"old_password": password, "new_password": "short"}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(short.status_code, 400)
        changed = self.client.post("/api/password", json={"old_password": password, "new_password": "a-much-better-password"}, headers={"X-CSRF-Token": csrf})
        self.assertEqual(changed.status_code, 200)

    def test_auto_update_preferences_persist_and_are_bound_to_image_repository(self):
        path = Path(self.temp.name) / "auto_update_containers.json"
        store = AutoUpdateStore(path)
        store.set("media", "ghcr.io/example/media:1.0", True)
        self.assertTrue(store.is_enabled("media", "ghcr.io/example/media:1.1"))
        self.assertFalse(store.is_enabled("media", "ghcr.io/example/other:1.1"))

        reloaded = AutoUpdateStore(path)
        self.assertTrue(reloaded.is_enabled("media", "ghcr.io/example/media:2.0"))
        reloaded.set("media", "", False)
        self.assertFalse(store.is_enabled("media", "ghcr.io/example/media:1.0"))

    def test_corrupt_auto_update_settings_fail_closed_without_overwriting_file(self):
        path = Path(self.temp.name) / "auto_update_containers.json"
        path.write_text("{invalid", encoding="utf-8")
        store = AutoUpdateStore(path)
        self.assertEqual(store.snapshot(), {})
        with self.assertRaises(ValueError):
            store.set("media", "ghcr.io/example/media:1.0", True)
        self.assertEqual(path.read_text(encoding="utf-8"), "{invalid")

    def test_auto_update_api_requires_login_and_saves_only_supported_containers(self):
        container = SimpleNamespace(
            id="a1b2c3d4",
            name="media",
            attrs={
                "Config": {"Image": "ghcr.io/example/media:1.0", "Labels": {}},
                "HostConfig": {"NetworkMode": "bridge", "AutoRemove": False},
                "NetworkSettings": {"Networks": {"bridge": {}}},
                "State": {"Status": "running"},
            },
        )

        class Containers:
            def get(self, identifier):
                if identifier in {container.id, container.name}:
                    return container
                raise KeyError(identifier)

        service = UpdateService(SimpleNamespace(containers=Containers()), catalog_loader=lambda: [])
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(directory, service_factory=lambda: service, print_credentials=False)
            app.config["TESTING"] = True
            client = app.test_client()
            password = app.extensions["dcc_updater_initial_password"]
            login_page = client.get("/login")
            import re
            csrf = re.search(rb'name="csrf-token" content="([^"]+)"', login_page.data).group(1).decode()
            client.post("/login", data={"csrf_token": csrf, "password": password})
            panel = client.get("/")
            csrf = re.search(rb'name="csrf-token" content="([^"]+)"', panel.data).group(1).decode()

            enabled = client.post(
                "/api/auto-update",
                json={"name": "media", "container_id": container.id, "enabled": True},
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(enabled.status_code, 200)
            store = app.extensions["dcc_updater_auto_updates"]
            self.assertTrue(store.is_enabled("media", "ghcr.io/example/media:1.0"))

            disabled = client.post(
                "/api/auto-update",
                json={"name": "media", "enabled": False},
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(disabled.status_code, 200)
            self.assertFalse(store.is_enabled("media", "ghcr.io/example/media:1.0"))

    def test_compose_auto_update_is_rejected(self):
        container = SimpleNamespace(
            id="compose-id",
            name="media",
            attrs={
                "Config": {
                    "Image": "ghcr.io/example/media:1.0",
                    "Labels": {"com.docker.compose.project": "media"},
                },
            },
        )

        class Containers:
            def get(self, _identifier):
                return container

        service = UpdateService(SimpleNamespace(containers=Containers()), catalog_loader=lambda: [])
        with tempfile.TemporaryDirectory(dir=self.temp.name) as directory:
            app = create_app(directory, service_factory=lambda: service, print_credentials=False)
            app.config["TESTING"] = True
            client = app.test_client()
            password = app.extensions["dcc_updater_initial_password"]
            login_page = client.get("/login")
            import re
            csrf = re.search(rb'name="csrf-token" content="([^"]+)"', login_page.data).group(1).decode()
            client.post("/login", data={"csrf_token": csrf, "password": password})
            panel = client.get("/")
            csrf = re.search(rb'name="csrf-token" content="([^"]+)"', panel.data).group(1).decode()
            response = client.post(
                "/api/auto-update",
                json={"name": "media", "container_id": container.id, "enabled": True},
                headers={"X-CSRF-Token": csrf},
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("Compose", response.get_json()["error"])

    def test_job_manager_never_runs_two_container_jobs_at_once(self):
        manager = JobManager()
        entered = threading.Event()
        release = threading.Event()

        def work(_progress):
            entered.set()
            release.wait(2)
            return []

        started, _state = manager.start("update", work)
        self.assertTrue(started)
        self.assertTrue(entered.wait(1))
        second_started, _state = manager.start("auto_update", lambda _progress: [])
        self.assertFalse(second_started)
        release.set()
        deadline = time.monotonic() + 2
        while manager.snapshot()["status"] != "done" and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(manager.snapshot()["status"], "done")

    def test_job_results_remain_bound_to_their_id_when_another_browser_starts_a_job(self):
        manager = JobManager()
        first_started, first = manager.start('scan', lambda _progress: ['original result'])
        self.assertTrue(first_started)
        deadline = time.monotonic() + 2
        while manager.snapshot()['status'] != 'done' and time.monotonic() < deadline:
            time.sleep(.01)
        second_started, second = manager.start('self_update_check', lambda _progress: {'checked': True})
        self.assertTrue(second_started)
        self.assertEqual(manager.snapshot(first['id'])['results'], ['original result'])
        self.assertEqual(first['instance'], second['instance'])
        self.assertNotEqual(first['instance'], JobManager().snapshot()['instance'])

    def test_startup_checks_panel_and_waits_for_decision_without_updating_or_scanning(self):
        checked = threading.Event()
        calls = []

        class FakeClient:
            def ping(self):
                calls.append("ping")

        class FakeService:
            client = FakeClient()

            def check_self_update(self, _progress):
                calls.append("check")
                return {"checked": True, "update_available": True, "supported": True}

            def start_self_update(self, _progress):
                calls.append("start")
                return {"checked": True, "update_available": True, "started": True, "message": "started"}

            def scan(self, _progress):
                raise AssertionError("Other automatic updates are disabled in this test.")

        def run_startup(_manager, kind, work):
            self.assertEqual(kind, "auto_update")
            work(lambda _message: None)
            checked.set()
            return True, {}

        with patch.dict(os.environ, {"DCC_UPDATER_SELF_UPDATE_STARTUP_DELAY": "0"}), \
                patch.object(JobManager, "start", run_startup):
            create_app(
                self.temp.name,
                service_factory=FakeService,
                print_credentials=False,
                startup_auto_updates=False,
                startup_self_update=True,
            )
            self.assertTrue(checked.wait(2))

        self.assertEqual(calls, ["ping", "check"])


if __name__ == "__main__":
    unittest.main()
