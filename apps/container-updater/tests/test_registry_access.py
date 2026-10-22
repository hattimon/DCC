import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DCC_UPDATER_DATA',tempfile.mkdtemp(prefix='dcc-updater-tests-'))
from registry_access import RegistryAccessStore, registry_name
from updater import UpdateService, ComposeProject
from web import create_app


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'registry_credentials.json'
        self.store=RegistryAccessStore(self.path)

    def tearDown(self):self.temp.cleanup()

    def test_credentials_are_write_only_registry_scoped_and_survive_restart(self):
        result=self.store.change('ghcr.io','save','user','PRIVATE_TOKEN')
        self.assertNotIn('PRIVATE_TOKEN',json.dumps(result))
        self.assertEqual(RegistryAccessStore(self.path).for_image('ghcr.io/example/app:latest'),{'username':'user','password':'PRIVATE_TOKEN'})
        self.assertIsNone(self.store.for_image('docker.io/example/app'))
        self.assertIsNone(self.store.for_image('ghcr.io.attacker.example/app'))
        self.store.change('ghcr.io','save','user','')
        self.assertEqual(self.store.for_image('ghcr.io/example/app')['password'],'PRIVATE_TOKEN')

    def test_remove_and_undo_do_not_change_other_registries(self):
        self.store.change('ghcr.io','save','user','old')
        self.store.change('ghcr.io','save','user','new')
        self.store.change('docker.io','save','user','hub')
        self.store.change('ghcr.io','undo')
        self.assertEqual(self.store.for_image('ghcr.io/example/app')['password'],'old')
        self.store.change('ghcr.io','remove')
        self.assertIsNone(self.store.for_image('ghcr.io/example/app'))
        self.store.change('ghcr.io','undo')
        self.assertEqual(self.store.for_image('nginx')['password'],'hub')
        self.assertEqual(self.store.for_image('ghcr.io/example/app')['password'],'old')

    def test_invalid_credentials_and_corrupt_files_fail_closed(self):
        for host in ('https://user:pass@ghcr.io','ghcr.io/path','http://ghcr.io','host:99999'):
            with self.assertRaises(ValueError):registry_name(host)
        with self.assertRaises(ValueError):self.store.change('ghcr.io','save','user','bad\nsecret')
        self.path.write_text('{broken',encoding='utf-8')
        store=RegistryAccessStore(self.path)
        self.assertTrue(store.public()['storage_error'])
        self.assertIsNone(store.for_image('ghcr.io/example/app'))
        with self.assertRaises(ValueError):store.change('ghcr.io','save','user','password')
        self.assertEqual(self.path.read_text(),'{broken')

    def test_sdk_inspection_pull_and_compose_use_only_matching_registry_credentials(self):
        calls=[]
        def inspect(image,**kwargs):
            calls.append(('inspect',image,kwargs))
            return {'Descriptor':{'digest':'sha256:new'},'Platforms':[{'os':'linux','architecture':'arm64'}]}
        def pull(image,**kwargs):calls.append(('pull',image,kwargs))
        self.store.change('ghcr.io','save','user','SECRET')
        service=UpdateService(SimpleNamespace(api=SimpleNamespace(inspect_distribution=inspect),images=SimpleNamespace(pull=pull)),
                              registry_auth_loader=self.store.for_image)
        local=SimpleNamespace(attrs={'Os':'linux','Architecture':'arm64','RepoDigests':['ghcr.io/example/app@sha256:old']})
        self.assertTrue(service._registry_digest('ghcr.io/example/app:latest',local)[0])
        service._pull_image_with_retry('ghcr.io/example/app:latest')
        service._pull_image_with_retry('nginx:latest')
        self.assertEqual(calls[0][2]['auth_config']['password'],'SECRET')
        self.assertEqual(calls[1][2]['auth_config']['password'],'SECRET')
        self.assertEqual(calls[2][2],{})
        project=ComposeProject('project','app',Path(self.temp.name),(),{'services':{'app':{'image':'ghcr.io/example/app:latest','platform':'linux/arm64'}}})
        with patch.object(service,'_compose_command',side_effect=AssertionError('No credential subprocess')):
            service._compose_pull(project)
        self.assertEqual(calls[-1][2]['auth_config']['password'],'SECRET')
        self.assertEqual(calls[-1][2]['platform'],'linux/arm64')


class AdvancedApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.panel=SimpleNamespace(name='dcc-container-updater',attrs={'Config':{'Labels':{}}})
        self.app=create_app(self.temp.name,service_factory=lambda:SimpleNamespace(_find_self_container=lambda:self.panel),print_credentials=False)
        self.client=self.app.test_client()
        with self.client.session_transaction() as state:state.update(authenticated=True,csrf_token='test-token')
        self.headers={'X-CSRF-Token':'test-token'}

    def tearDown(self):self.temp.cleanup()

    def test_advanced_configuration_requires_authentication_csrf_and_hides_secrets(self):
        fresh=self.app.test_client()
        self.assertEqual(fresh.get('/api/registry-access').status_code,401)
        self.assertEqual(self.client.post('/api/registry-access',json={}).status_code,400)
        self.assertEqual(self.client.post('/api/advanced/mount-plan',json={'path':'/srv/app'}).status_code,400)
        result=self.client.post('/api/registry-access',json={'registry':'ghcr.io','username':'user','password':'PRIVATE_TOKEN'},headers=self.headers)
        self.assertEqual(result.status_code,200)
        self.assertNotIn(b'PRIVATE_TOKEN',result.data)
        self.assertNotIn(b'PRIVATE_TOKEN',self.client.get('/api/registry-access').data)

    def test_standalone_mount_plan_is_read_only_and_reversible_without_deleting_volumes(self):
        result=self.client.post('/api/advanced/mount-plan',json={'path':'/srv/project name'},headers=self.headers)
        self.assertEqual(result.status_code,200)
        plan=result.get_json()
        self.assertIn('readonly',plan['parameter'])
        self.assertNotIn('DAC_READ_SEARCH',plan['parameter'])
        self.assertIn('docker rename',plan['prepare'])
        self.assertIn('docker start dcc-container-updater',plan['undo'])
        self.assertNotIn(' -v',plan['undo'])
        self.assertNotIn('--volumes',plan['undo'])
        self.assertIn("'type=bind,source=/srv/project name",plan['parameter'])
        for path in ('/','/root','/srv/../etc','/srv/path,readonly=false','relative/path'):
            self.assertEqual(self.client.post('/api/advanced/mount-plan',json={'path':path},headers=self.headers).status_code,400)

    def test_compose_mount_plan_uses_detected_project_and_explicit_permission_optin(self):
        self.panel.attrs['Config']['Labels']={'com.docker.compose.project':'dcc','com.docker.compose.service':'updater',
             'com.docker.compose.project.config_files':'/srv/dcc project/compose.yaml','com.docker.compose.project.working_dir':'/srv/dcc project'}
        response=self.client.post('/api/advanced/mount-plan',json={'path':'/srv/apps/media','read_capability':True},headers=self.headers)
        self.assertEqual(response.status_code,200)
        plan=response.get_json()
        self.assertTrue(plan['compose'])
        self.assertIn('read_only: true',plan['compose_snippet'])
        self.assertIn('DAC_READ_SEARCH',plan['compose_snippet'])
        self.assertIn("'/srv/dcc project/compose.yaml'",plan['apply'])
        self.assertIn('up -d --no-deps updater',plan['apply'])
        self.assertIn('cp -p --',plan['undo'])


if __name__=='__main__':unittest.main()
