"""Background updates use persisted registry access without a browser session."""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DCC_UPDATER_DATA', tempfile.mkdtemp(prefix='dcc-schedule-auth-tests-'))

from scheduler import DEFAULT_CONFIG
from updater import UpdateService
from web import create_app


class ScheduledRegistryAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(self.temp.name, print_credentials=False)
        self.container = SimpleNamespace(id='n8n-id', name='n8n', attrs={
            'Image': 'sha256:old',
            'Config': {'Image': 'n8nio/n8n:latest', 'Labels': {}},
            'HostConfig': {'NetworkMode': 'bridge'},
            'NetworkSettings': {'Networks': {'bridge': {}}},
            'State': {'Status': 'running'},
            'Mounts': [{'Type': 'bind', 'Source': '/root/.n8n',
                        'Destination': '/home/node/.n8n', 'RW': True}],
        })
        self.panel = SimpleNamespace(id='panel-id', name='dcc-container-updater', attrs={
            'Image': 'sha256:panel',
            'Config': {'Image': 'ghcr.io/hattimon/dcc-container-updater:latest',
                       'Labels': {'com.hattimon.dcc-updater': 'true'}},
            'HostConfig': {'NetworkMode': 'bridge'},
            'State': {'Status': 'running'},
            'Mounts': [{'Type': 'bind', 'Source': '/root', 'Destination': '/root', 'RW': False}],
        })
        image = SimpleNamespace(id='sha256:old', attrs={
            'Os': 'linux', 'Architecture': 'arm64',
            'RepoTags': ['n8nio/n8n:latest'], 'RepoDigests': ['n8nio/n8n@sha256:old'],
        })
        monitor = SimpleNamespace(id='monitor-id', name='system-monitor', attrs={
            'Image': 'sha256:monitor',
            'Config': {'Image': 'ghcr.io/example/system-monitor:latest', 'Labels': {}},
            'HostConfig': {'NetworkMode': 'host', 'PidMode': 'host'},
            'State': {'Status': 'running'},
            'Mounts': [{'Type': 'bind', 'Source': '/', 'Destination': '/host', 'RW': False}],
        })
        self.docker = SimpleNamespace(
            api=SimpleNamespace(inspect_distribution=Mock(return_value={
                'Descriptor': {'digest': 'sha256:new'},
                'Platforms': [{'os': 'linux', 'architecture': 'arm64'}],
            })),
            images=SimpleNamespace(get=Mock(return_value=image), pull=Mock()),
            containers=SimpleNamespace(
                list=Mock(return_value=[self.container, self.panel, monitor]),
                get=Mock(return_value=self.container),
            ),
        )

    def tearDown(self):
        self.temp.cleanup()

    def wait_job(self):
        manager = self.app.extensions['dcc_updater_jobs']
        deadline = time.monotonic() + 3
        while manager.snapshot()['status'] in {'queued', 'running'} and time.monotonic() < deadline:
            time.sleep(.01)
        state = manager.snapshot()
        self.assertEqual(state['status'], 'done', state)
        return state['results']

    def test_persisted_credentials_work_for_logged_out_schedule_and_manual_update(self):
        credentials = {'username': 'registry-user', 'password': 'TEST_REGISTRY_TOKEN'}
        browser = self.app.test_client()
        with browser.session_transaction() as session:
            session.update(authenticated=True, csrf_token='test-token')
        headers = {'X-CSRF-Token': 'test-token'}
        response = browser.post('/api/registry-access', headers=headers, json={
            'registry': 'docker.io', **credentials,
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(credentials['password'], response.get_data(as_text=True))
        self.assertEqual(browser.post('/logout', data={'csrf_token': 'test-token'}).status_code, 302)
        self.assertEqual(browser.get('/api/containers').status_code, 401)

        # Reload the app to prove the credentials are durable rather than part
        # of the logged-in session or an in-memory request context.
        self.app = create_app(self.temp.name, print_credentials=False)
        self.app.extensions['dcc_updater_schedule'].save({
            **DEFAULT_CONFIG, 'enabled': True, 'action': 'update',
            'targets': [{'name': 'n8n', 'repository': 'docker.io/n8nio/n8n'}],
        }, time.time() - 86400)

        def replace_without_docker_mutation(service, _container, image, _instructions=None):
            service._pull_image_with_retry(image)
            return 'Updated in test'

        with patch('web.docker.from_env', return_value=self.docker), \
                patch.object(UpdateService, '_catalog', return_value=([], None)), \
                patch.object(UpdateService, 'update_one', autospec=True,
                             side_effect=replace_without_docker_mutation):
            # This tick runs outside a Flask request, with no authenticated
            # browser; use the real service, scanner and automatic checks.
            self.assertTrue(self.app.extensions['dcc_updater_scheduler_tick']())
            scheduled = self.wait_job()
            self.assertTrue(scheduled['ok'], scheduled)
            self.assertEqual(scheduled['updates'][0]['name'], 'n8n')
            self.assertTrue(scheduled['updates'][0]['ok'])
            self.docker.images.pull.assert_called_once_with('n8nio/n8n:latest', auth_config=credentials)
            scheduled_auth = self.docker.images.pull.call_args.kwargs['auth_config']
            self.assertEqual(self.app.test_client().get('/api/containers').status_code, 401)

            manual = self.app.test_client()
            with manual.session_transaction() as session:
                session.update(authenticated=True, csrf_token='test-token')
            response = manual.post('/api/update', headers=headers, json={'container_ids': ['n8n-id']})
            self.assertEqual(response.status_code, 202)
            result = self.wait_job()
            self.assertTrue(result['updates'][0]['ok'])
            self.assertEqual(self.docker.images.pull.call_count, 2)
            self.assertEqual(self.docker.images.pull.call_args.kwargs['auth_config'], scheduled_auth)

        for call in self.docker.api.inspect_distribution.call_args_list:
            if call.args[0] == 'n8nio/n8n:latest':
                self.assertEqual(call.kwargs['auth_config'], credentials)
            else:
                self.assertNotIn('auth_config', call.kwargs)
        self.assertNotIn(credentials['password'], json.dumps(scheduled))
        self.assertNotIn(credentials['password'], json.dumps(result))


if __name__ == '__main__':
    unittest.main()
