import copy
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compose_config import ComposeBlocked, ComposeConfig, ControlledWriter, digest, private_json, safe_path, semantic_merge
from compose_manager import ComposeStore, SafeComposeManager, SQLiteBackup
from notifications import NotificationService
from reports import ReportStore
from updater import UpdateService, ComposeProject


OLD = 'sha256:' + '1' * 64
NEW = 'sha256:' + '2' * 64
SOURCE = 'example/web@sha256:' + 'a' * 64
TARGET = 'example/web@sha256:' + 'b' * 64
BODY = b'ready\n'


class SemanticReviewTests(unittest.TestCase):
    def test_no_base_is_a_two_way_review_without_merged_output(self):
        result = semantic_merge(None, {'services': {}}, {'services': {}})
        self.assertTrue(result['two_way'])
        self.assertIsNone(result['merged'])
        self.assertIn('BASE', result['conflicts'])

    def test_preserves_local_fields_and_applies_independent_image_change(self):
        base = {'services': {'web': {'image': SOURCE, 'restart': 'no'}}}
        local = copy.deepcopy(base); local['services']['web']['restart'] = 'always'
        upstream = copy.deepcopy(base); upstream['services']['web']['image'] = TARGET
        result = semantic_merge(base, local, upstream)
        self.assertEqual(result['merged']['services']['web'], {'image': TARGET, 'restart': 'always'})
        self.assertEqual(result['conflicts'], [])

    def test_sensitive_conflicts_and_public_diff_hide_all_values(self):
        for field, original, local_value, upstream_value in (
            ('environment', {'PASSWORD': 'SECRET_A'}, {'PASSWORD': 'SECRET_B'}, {'PASSWORD': 'SECRET_C'}),
            ('ports', [{'target': 80, 'published': '80'}], [{'target': 80, 'published': '81'}], [{'target': 80, 'published': '82'}]),
            ('volumes', [{'target': '/data', 'source': 'a'}], [{'target': '/data', 'source': 'b'}], [{'target': '/data', 'source': 'c'}]),
            ('secrets', [{'target': '/secret', 'source': 'a'}], [{'target': '/secret', 'source': 'b'}], [{'target': '/secret', 'source': 'c'}]),
        ):
            with self.subTest(field=field):
                result = semantic_merge({'services': {'web': {field: original}}}, {'services': {'web': {field: local_value}}}, {'services': {'web': {field: upstream_value}}})
                self.assertTrue(result['conflicts'] or result['review_required'])
                public = {k:v for k,v in result.items() if k != 'merged'}
                self.assertNotIn('SECRET_', json.dumps(public))

    def test_command_lists_are_atomic_and_do_not_append(self):
        result = semantic_merge({'command': ['a']}, {'command': ['b']}, {'command': ['c']})
        self.assertEqual(result['merged']['command'], ['b'])
        self.assertEqual(result['conflicts'], ['command'])

    def test_upstream_only_sensitive_changes_are_reviewed_at_the_actual_field(self):
        base={'services':{'web':{'image':SOURCE,'environment':{'PRIVATE_NAME':'PRIVATE_OLD'}}}}
        upstream=copy.deepcopy(base);upstream['services']['web']['environment']['PRIVATE_NAME']='PRIVATE_NEW'
        result=semantic_merge(base,copy.deepcopy(base),upstream)
        self.assertIn('services.web.environment',result['review_required'])
        self.assertEqual(result['changes'][0]['path'],'services.web.environment')
        self.assertNotIn('PRIVATE_NAME',json.dumps({k:v for k,v in result.items() if k!='merged'}))

    def test_unique_mount_targets_merge_without_duplicate_volumes(self):
        base = {'volumes': [{'target': '/a', 'source': 'a'}, {'target': '/b', 'source': 'b'}]}
        local = copy.deepcopy(base); local['volumes'][0]['read_only'] = True
        upstream = copy.deepcopy(base); upstream['volumes'][1]['read_only'] = True
        result = semantic_merge(base, local, upstream)
        self.assertEqual(len(result['merged']['volumes']), 2)
        self.assertTrue(all(m['read_only'] for m in result['merged']['volumes']))

    def test_upstream_removal_never_discards_locally_modified_field(self):
        result = semantic_merge({'x': 'old'}, {'x': 'local'}, {})
        self.assertEqual(result['merged'], {'x': 'local'})
        self.assertEqual(result['conflicts'], ['x'])


class FileSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'image.json').write_text('{"services":{"web":{"image":"old"}}}', encoding='utf-8')
    def tearDown(self):
        self.temp.cleanup()

    def test_dot_traversal_rejected_even_if_it_resolves_inside_root(self):
        for path in ('../outside', 'sub/../image.json', self.root.parent / 'outside'):
            with self.subTest(path=str(path)), self.assertRaises(ComposeBlocked):
                safe_path(self.root, path)

    @unittest.skipUnless(os.name == 'posix', 'Linux symlinks and file ownership')
    def test_symlinks_inside_and_outside_the_root_are_rejected(self):
        (self.root / 'link').symlink_to(self.root / 'image.json')
        (self.root / 'outside').symlink_to('/etc/passwd')
        for path in ('link', 'outside'):
            with self.subTest(path=path), self.assertRaises(ComposeBlocked):
                safe_path(self.root, path)

    @unittest.skipUnless(os.name == 'posix', 'Linux hard links')
    def test_hard_links_are_rejected(self):
        os.link(self.root / 'image.json', self.root / 'hard')
        with self.assertRaises(ComposeBlocked):
            safe_path(self.root, 'hard')

    @unittest.skipUnless(os.name == 'posix', 'Production writer is Linux-only')
    def test_atomic_write_copies_original_preserves_mode_and_undo_is_compare_and_swap(self):
        path = self.root / 'image.json'; original = path.read_bytes(); os.chmod(path, 0o640)
        before = path.stat()
        writer = ControlledWriter(self.root, ['image.json'], self.root / 'backup')
        receipt = writer.replace('image.json', b'new', digest(original))
        self.assertEqual(Path(receipt['backup']).read_bytes(), original)
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        self.assertEqual((path.stat().st_uid, path.stat().st_gid), (before.st_uid, before.st_gid))
        writer.undo(receipt)
        self.assertEqual(path.read_bytes(), original)
        path.write_bytes(b'concurrent edit')
        with self.assertRaisesRegex(ComposeBlocked, 'files_changed'):
            writer.undo(receipt)

    @unittest.skipUnless(os.name == 'posix', 'Production writer is Linux-only')
    def test_no_write_outside_exact_grant_and_reject_changed_file(self):
        writer = ControlledWriter(self.root, ['image.json'], self.root / 'backup')
        with self.assertRaisesRegex(ComposeBlocked, 'write_not_granted'):
            writer.replace('other.json', b'new', digest(b''))
        with self.assertRaisesRegex(ComposeBlocked, 'files_changed'):
            writer.replace('image.json', b'new', digest(b'old'))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'state.sqlite';self.store=ComposeStore(self.path)
    def tearDown(self):
        self.temp.cleanup()

    def test_automation_is_off_and_database_unknown_by_default(self):
        self.assertEqual(self.store.settings('demo')['automation'], 'off')
        self.assertEqual(self.store.settings('demo')['mode'], 'monitor')
        self.assertEqual(self.store.settings('demo')['database_policy'], 'unknown')

    def test_invalid_conditional_consent_and_service_modes_are_rejected(self):
        for payload in ({'automation':'conditional'}, {'mode':'any'}, {'services':{'web':'any'}}):
            with self.assertRaises(ComposeBlocked):self.store.save_settings('demo',payload)

    def test_project_lock_prevents_duplicate_operations(self):
        operation=self.store.create('demo')
        with self.assertRaisesRegex(ComposeBlocked,'project_locked'):self.store.create('demo')
        self.store.release(operation);self.assertNotEqual(operation,self.store.create('demo'))

    def test_restart_of_deployment_never_replays_and_retains_project_lock(self):
        operation=self.store.create('demo');self.store.transition(operation,'APPLYING')
        restarted=ComposeStore(self.path)
        self.assertEqual(restarted.get(operation)['state'],'MANUAL_INTERVENTION')
        with self.assertRaisesRegex(ComposeBlocked,'project_locked'):restarted.create('demo')

    def test_restart_of_ready_plan_invalidates_consent(self):
        operation=self.store.create('demo');self.store.transition(operation,'READY');self.store.release(operation)
        restarted=ComposeStore(self.path)
        self.assertEqual(restarted.get(operation)['state'],'BLOCKED')

    def test_restart_after_durable_completion_releases_only_the_finished_lock(self):
        operation=self.store.create('demo');self.store.transition(operation,'COMPLETED')
        restarted=ComposeStore(self.path)
        self.assertEqual(restarted.get(operation)['state'],'COMPLETED')
        self.assertNotEqual(restarted.create('demo'),operation)

    def test_bad_state_compare_and_swap_is_rejected(self):
        operation=self.store.create('demo')
        with self.assertRaisesRegex(ComposeBlocked,'state_invalid'):
            self.store.transition(operation,'APPLYING',expected={'READY'})

    def test_project_schedule_uses_existing_calendar_and_claims_once(self):
        self.store.save_settings('demo',{'automation':'analyze','schedule':{'enabled':True,'kind':'daily','time':'03:00','timezone':'Europe/Warsaw'}})
        now=time.time()+86400
        self.assertEqual(self.store.due(now),['demo'])
        self.assertIsNotNone(self.store.claim_schedule('demo',now))
        self.assertIsNone(self.store.claim_schedule('demo',now))

    def test_corrupt_database_fails_closed(self):
        broken=Path(self.temp.name)/'broken.sqlite';broken.write_bytes(b'not a database')
        with self.assertRaises(sqlite3.DatabaseError):ComposeStore(broken)


class SQLiteBackupTests(unittest.TestCase):
    def test_online_backup_and_isolated_restore_leave_live_data_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'live.sqlite'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE evidence(value TEXT)');db.execute('INSERT INTO evidence VALUES(?)',('PRIVATE_DATA',))
            db.close()
            before=path.read_bytes()
            result=SQLiteBackup.verify(root,'live.sqlite',root/'backup')
            self.assertTrue(result['verified']);self.assertTrue(result['restore_tested']);self.assertFalse(result['production_restore'])
            self.assertEqual(path.read_bytes(),before)
            self.assertNotIn('PRIVATE_DATA',json.dumps(result))

    def test_bad_sqlite_is_not_reported_as_verified(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'live.sqlite').write_bytes(b'not sqlite')
            with self.assertRaisesRegex(ComposeBlocked,'backup_unverified'):SQLiteBackup.verify(root,'live.sqlite',root/'backup')


class Fixture:
    def __init__(self, root):
        self.root=root;self.project=root/'project';self.project.mkdir()
        self.base={'name':'demo','services':{'web':{'image':SOURCE,'healthcheck':{'test':['CMD','true']},'networks':{'default':None}}},'networks':{'default':{'name':'demo_default'}}}
        self.target=copy.deepcopy(self.base);self.target['services']['web']['image']=TARGET
        private_json(self.project/'compose.json',self.base)
        private_json(self.project/'images.json',{'services':{'web':{'image':SOURCE}}})
        self.container=SimpleNamespace(id='container-one',name='demo-web-1',attrs={
            'Image':OLD,'Config':{'Image':SOURCE,'Labels':{'com.docker.compose.project':'demo','com.docker.compose.service':'web',
                'com.docker.compose.project.working_dir':str(self.project),'com.docker.compose.project.config_files':','.join(str(self.project/f) for f in ('compose.json','images.json'))}},
            'State':{'Status':'running','Health':{'Status':'healthy'}},'HostConfig':{},'Mounts':[],
            'NetworkSettings':{'Networks':{'demo_default':{}},'Ports':{}}})
        self.container.reload=lambda:None
        self.container.attrs['Config']['Labels']['com.docker.compose.config-hash']=digest(self.base['services']['web'])
        self.container.exec_run=lambda *a,**kw:(1,b'PRIVATE_BODY') if self.fail_app else (0,BODY)
        self.containers=[self.container];self.commands=[];self.pulls=[]
        self.fail_apply=self.fail_rollback=self.fail_health=self.fail_app=False
        old=SimpleNamespace(id=OLD,attrs={'Os':'linux','Architecture':'amd64','Config':{}},tag=lambda *a,**kw:True)
        new=SimpleNamespace(id=NEW,attrs={'Os':'linux','Architecture':'amd64','Config':{}},tag=lambda *a,**kw:True)
        self.images={SOURCE:old,TARGET:new,OLD:old,NEW:new}
        self.client=SimpleNamespace(containers=SimpleNamespace(list=lambda **kw:list(self.containers)),
            images=SimpleNamespace(get=lambda ref:self.images[ref]),info=lambda:{'OSType':'linux','Architecture':'amd64'})
        self.service=UpdateService(self.client,catalog_loader=lambda:[],compose_roots=[str(root)])
        self.service._pull_image_with_retry=lambda image,**kw:self.pulls.append(image)
        self.service._registry_digest=lambda *a:(True,'')
        self.service._local_image=lambda c:self.images[c.attrs['Image']]
        self.service._load_compose_project=lambda c:(ComposeProject('demo','web',self.project,(self.project/'compose.json',self.project/'images.json'),copy.deepcopy(self.base)),None)
        self.manager=SafeComposeManager(root/'data',lambda:self.service,ReportStore(root/'reports.json'),runner=self.run)
        folder=self.manager.trust_root/'demo';folder.mkdir()
        private_json(folder/'base.json',self.base);private_json(folder/'upstream.json',self.target)
        self.approval={'project':'demo','approved':True,'root':str(self.project),'files':['compose.json','images.json'],
            'source':{'revision':'fixture-commit-0123','base':'base.json','upstream':'upstream.json',
                'base_sha256':digest((folder/'base.json').read_bytes()),'upstream_sha256':digest((folder/'upstream.json').read_bytes())},
            'profile':{'kind':'stateless-v1','approved':True,'services':{'web':{'source_image_id':OLD,'target_image':TARGET,
                'application_check':{'kind':'http-sha256','port':8080,'path':'/ready','body_sha256':digest(BODY)}}}},
            'write':{'file':'images.json'}}
        self.folder=folder;self.save_approval()
        evidence={'schema':1,'source_model_sha256':digest(self.base),'target_model_sha256':digest(self.target),
                  'versions':{'web':{'source':[OLD],'target':TARGET}},'isolated':True,'application_checks_passed':True,
                  'persistent_data':[],'external_data_dependencies':[],'test_suite':'fixture-isolated-smoke'}
        private_json(folder/'evidence.json',evidence)
        self.approval['profile']['evidence']={'file':'evidence.json','sha256':digest((folder/'evidence.json').read_bytes())}
        self.save_approval()
        self.manager.discover()
        self.manager.store.save_settings('demo',{'mode':'manual','database_policy':'none'})

    def save_approval(self):private_json(self.folder/'approval.json',self.approval)

    def run(self,args,**kwargs):
        self.commands.append(list(args));files=[Path(args[i+1]) for i,v in enumerate(args) if v=='--file']
        model={}
        for path in files:
            incoming=json.loads(path.read_text(encoding='utf-8'))
            for key,value in incoming.items():
                if key=='services':
                    for name,config in value.items():model.setdefault('services',{}).setdefault(name,{}).update(config)
                else:model[key]=value
        if 'up' in args:
            rollback=model['services']['web']['image']==SOURCE
            if (rollback and self.fail_rollback) or (not rollback and self.fail_apply):
                return SimpleNamespace(returncode=1,stdout='',stderr='PRIVATE_PASSWORD=do-not-leak')
            ref=model['services']['web']['image'];self.container.attrs['Image']=self.images[ref].id
            self.container.attrs['State']['Health']['Status']='unhealthy' if self.fail_health and not rollback else 'healthy'
            self.container.attrs['Config']['Labels']['com.docker.compose.config-hash']=digest(model['services']['web'])
            return SimpleNamespace(returncode=0,stdout='',stderr=' Container web Started\n')
        if '--hash' in args:
            return SimpleNamespace(returncode=0,stdout='\n'.join(name+' '+digest(value) for name,value in model['services'].items()),stderr='')
        return SimpleNamespace(returncode=0,stdout='' if '--quiet' in args else json.dumps(model),stderr='')


class ManagerAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.fixture=Fixture(Path(self.temp.name));self.manager=self.fixture.manager
    def tearDown(self):self.temp.cleanup()

    def test_monitoring_does_not_mutate_and_legacy_auto_permission_is_not_inherited(self):
        self.manager.store.save_settings('demo',{})
        result=self.manager.analyze('demo')
        self.assertIn('consent_required',result['blockers']);self.assertFalse(self.fixture.pulls)
        self.assertFalse(any('up' in command for command in self.fixture.commands))

    def test_discovery_checks_the_pinned_approved_target_and_shows_its_version(self):
        checked=[]
        self.fixture.service._registry_digest=lambda image,local:(checked.append(image) or True,'')
        result=self.manager.discover(check_updates=True)
        self.assertEqual(checked,[TARGET]);self.assertEqual(result[0]['services'][0]['target_image'],TARGET)
        self.assertEqual(result[0]['status'],'update_available')

    def test_discovery_finds_new_version_tags_from_catalog_without_an_approved_profile(self):
        (self.fixture.folder/'approval.json').unlink()
        self.fixture.container.attrs['Config']['Image']='ghcr.io/hattimon/cinema-hub:1.3.9'
        self.fixture.service.catalog_loader=lambda:[{'image':'ghcr.io/hattimon/cinema-hub:1.3.10'}]
        checked=[]
        self.fixture.service._registry_digest=lambda image,local:(checked.append(image) or True,'')
        project=self.manager.discover(check_updates=True)[0]
        self.assertEqual(checked,['ghcr.io/hattimon/cinema-hub:1.3.10'])
        self.assertEqual(project['services'][0]['target_image'],'ghcr.io/hattimon/cinema-hub:1.3.10')
        self.assertTrue(project['services'][0]['update_available'])
        self.assertEqual(project['source'],'unapproved')
        self.assertEqual(self.fixture.pulls,[])

    def test_catalog_target_is_not_reported_as_available_when_registry_check_fails(self):
        (self.fixture.folder/'approval.json').unlink()
        self.fixture.container.attrs['Config']['Image']='ghcr.io/hattimon/cinema-hub:1.3.9'
        self.fixture.service.catalog_loader=lambda:[{'image':'ghcr.io/hattimon/cinema-hub:1.3.10'}]
        self.fixture.service._registry_digest=lambda image,local:(None,'registry unavailable')

        project=self.manager.discover(check_updates=True)[0]

        service=project['services'][0]
        self.assertEqual(service['target_image'],'ghcr.io/hattimon/cinema-hub:1.3.10')
        self.assertIsNone(service['update_available'])
        self.assertEqual(service['check_diagnostics'],['image_check_failed'])
        self.assertEqual(project['status'],'review_required')
        self.assertEqual(self.fixture.pulls,[])

    def test_missing_original_image_does_not_hide_other_services_or_projects(self):
        from docker.errors import ImageNotFound
        from docker.models.containers import Container

        missing=copy.deepcopy(self.fixture.container.attrs)
        missing.update(Id='missing-container',Name='/demo-missing-1',Image='sha256:'+'f'*64)
        missing['Config']['Labels']['com.docker.compose.service']='missing'
        broken=Container(attrs=missing,client=self.fixture.client)
        peer=copy.deepcopy(self.fixture.container);peer.id='peer';peer.name='other-web-1'
        peer.attrs['Config']['Labels']['com.docker.compose.project']='other'
        self.fixture.containers[:]=[broken,self.fixture.container,peer]
        get_image=self.fixture.client.images.get
        def lookup(ref):
            if ref in ('sha256:'+'f'*64,'f'*64):raise ImageNotFound('PRIVATE_IMAGE_ERROR')
            return get_image(ref)
        self.fixture.client.images.get=lookup
        self.fixture.service._local_image=UpdateService._local_image.__get__(self.fixture.service)
        checked=[]
        self.fixture.service._registry_digest=lambda image,local:(checked.append(image) or False,'')

        projects=self.manager.discover(check_updates=True)

        self.assertEqual([project['name'] for project in projects],['demo','other'])
        services={entry['name']:entry for entry in projects[0]['services']}
        self.assertIsNone(services['missing']['update_available'])
        self.assertEqual(services['missing']['check_diagnostics'],['local_image_unavailable'])
        self.assertFalse(services['web']['update_available'])
        self.assertIn('local_image_unavailable',projects[0]['blockers'])
        self.assertEqual(projects[0]['status'],'review_required')
        self.assertEqual(projects[1]['status'],'up_to_date')
        self.assertEqual(len(checked),2)
        self.assertNotIn('PRIVATE_IMAGE_ERROR',json.dumps(projects))
        self.assertEqual(self.fixture.pulls,[])

    def test_registry_exception_is_reported_per_service_and_does_not_hide_projects(self):
        peer=copy.deepcopy(self.fixture.container);peer.id='peer'
        peer.attrs['Config']['Labels']['com.docker.compose.project']='other'
        self.fixture.containers.append(peer)
        with patch.object(self.fixture.service,'_registry_digest',side_effect=[RuntimeError('PRIVATE_TOKEN'),(False,'')]):
            projects=self.manager.discover(check_updates=True)
        self.assertEqual(len(projects),2)
        self.assertEqual(projects[0]['services'][0]['check_diagnostics'],['image_check_failed'])
        self.assertIsNone(projects[0]['services'][0]['update_available'])
        self.assertEqual(projects[1]['status'],'up_to_date')
        self.assertNotIn('PRIVATE_TOKEN',json.dumps(projects))

    def test_unknown_replica_prevents_false_up_to_date_in_either_order(self):
        peer=copy.deepcopy(self.fixture.container);peer.id='peer'
        for results in ([(None,''),(False,'')],[(False,''),(None,'')],[(None,''),(True,'')]):
            with self.subTest(results=results):
                self.fixture.containers[:]=[self.fixture.container,peer]
                with patch.object(self.fixture.service,'_registry_digest',side_effect=results):
                    project=self.manager.discover(check_updates=True)[0]
                self.assertEqual(project['services'][0]['check_diagnostics'],['image_check_failed'])
                expected=True if any(value is True for value,_ in results) else None
                self.assertIs(project['services'][0]['update_available'],expected)
                self.assertEqual(project['status'],'update_available' if expected else 'review_required')

    def test_checkboxes_without_pinned_isolated_test_evidence_do_not_prove_compatibility(self):
        self.fixture.approval['profile'].pop('evidence');self.fixture.save_approval()
        self.assertIn('compatibility_unverified',self.manager.analyze('demo')['blockers'])

    def test_missing_base_blocks_automatic_three_way(self):
        self.fixture.approval['source'].pop('base');self.fixture.save_approval()
        result=self.manager.analyze('demo')
        self.assertEqual(result['state'],'BLOCKED');self.assertIn('base_missing',result['blockers'])

    def test_no_compose_file_is_fail_closed(self):
        (self.fixture.project/'compose.json').unlink()
        self.assertEqual(self.manager.analyze('demo')['state'],'BLOCKED')

    def test_missing_write_permission_does_not_bypass_preflight(self):
        self.fixture.approval.pop('write');self.fixture.save_approval()
        self.assertIn('write_not_granted',self.manager.analyze('demo')['blockers'])

    def test_database_unknown_even_when_an_image_has_no_database_name(self):
        self.manager.store.save_settings('demo',{'mode':'conditional','automation':'conditional'})
        self.assertIn('database_unknown',self.manager.analyze('demo')['blockers'])

    def test_migration_checkbox_cannot_enable_a_production_executor(self):
        self.manager.store.save_settings('demo',{'mode':'migration','database_policy':'approved_migration'})
        blockers=self.manager.analyze('demo')['blockers']
        self.assertIn('migration_adapter_unavailable',blockers);self.assertIn('database_unknown',blockers)

    def test_shared_external_network_blocks_project_deployment(self):
        peer=copy.deepcopy(self.fixture.container);peer.id='other';peer.name='other';peer.attrs['Config']['Labels']={}
        self.fixture.containers.append(peer)
        self.assertIn('external_dependency',self.manager.analyze('demo')['blockers'])

    def test_port_conflict_blocks_even_if_peer_is_stopped(self):
        self.fixture.base['services']['web']['ports']=[{'target':8080,'published':'8080'}]
        private_json(self.fixture.project/'compose.json',self.fixture.base)
        peer=copy.deepcopy(self.fixture.container);peer.id='other';peer.name='other';peer.attrs['Config']['Labels']={};peer.attrs['NetworkSettings']={}
        peer.attrs['HostConfig']={'PortBindings':{'8080/tcp':[{'HostPort':'8080','HostIp':'0.0.0.0'}]}}
        self.fixture.containers.append(peer)
        # Keep ports local in three-way review.
        self.assertIn('port_conflict',self.manager.analyze('demo')['blockers'])

    def test_unknown_dependencies_are_not_started(self):
        self.fixture.base['services']['web']['depends_on']={'missing':{'condition':'service_started'}}
        private_json(self.fixture.project/'compose.json',self.fixture.base)
        self.assertIn('dependency_unknown',self.manager.analyze('demo')['blockers'])

    def test_unverified_backup_does_not_enable_migration(self):
        self.fixture.approval['backup']={'adapter':'unknown'};self.fixture.save_approval()
        result=self.manager.check_backup('demo')
        self.assertEqual(result['state'],'BLOCKED');self.assertNotIn('approved',result)

    def test_untrusted_hash_change_and_traversal_block(self):
        self.fixture.approval['source']['upstream']='../outside.json';self.fixture.save_approval()
        self.assertIn('path_unsafe',self.manager.analyze('demo')['blockers'])

    def test_untracked_compose_environment_and_env_file_escape_are_blocked(self):
        (self.fixture.project/'.env').write_text('COMPOSE_FILE=/outside/compose.yml\n',encoding='utf-8')
        self.assertIn('input_closure_unknown',self.manager.analyze('demo')['blockers'])
        (self.fixture.project/'.env').unlink()
        self.fixture.base['services']['web']['env_file']=['../outside.env']
        private_json(self.fixture.project/'compose.json',self.fixture.base)
        self.assertIn('path_unsafe',self.manager.analyze('demo')['blockers'])

    def test_profiles_and_lifecycle_hooks_cannot_execute(self):
        self.fixture.base['services']['web'].update(profiles=['optional'],pre_start=[{'command':'do-not-execute'}])
        private_json(self.fixture.project/'compose.json',self.fixture.base)
        result=self.manager.analyze('demo')
        self.assertIn('profiles_unknown',result['blockers']);self.assertIn('service_unsupported',result['blockers'])
        self.assertFalse(any('up' in args for args in self.fixture.commands))

    def test_public_operations_reports_and_api_never_expose_configuration(self):
        self.fixture.base['services']['web']['environment']={'PRIVATE_PASSWORD':'PRIVATE_VALUE'}
        private_json(self.fixture.project/'compose.json',self.fixture.base)
        operation=self.manager.analyze('demo')
        public=json.dumps([operation,self.manager.store.history('demo'),self.manager.reports.snapshot()])
        self.assertNotIn('PRIVATE_VALUE',public);self.assertNotIn('PRIVATE_PASSWORD',public)

    def test_monitoring_scheduled_check_never_pulls_or_deploys(self):
        self.manager.store.save_settings('demo',{'automation':'check','schedule':{'enabled':True,'kind':'daily','time':'03:00'}})
        self.manager.run_due(time.time()+86400,lambda message:None)
        self.assertFalse(self.fixture.pulls)
        self.assertFalse(any('up' in args for args in self.fixture.commands))


@unittest.skipUnless(os.name == 'posix', 'Production adapter requires Linux')
class DeploymentTests(unittest.TestCase):
    setUp = ManagerAnalysisTests.setUp
    tearDown = ManagerAnalysisTests.tearDown
    def ready(self,approve=True,dry_run=False):
        result=self.manager.analyze('demo',dry_run=dry_run)
        self.assertEqual(result['state'],'READY',result)
        return self.manager.approve(result['id']) if approve else result

    def test_no_admin_approval_blocks_manual_deployment(self):
        operation=self.ready(approve=False)
        with self.assertRaisesRegex(ComposeBlocked,'consent_required'):self.manager.execute(operation['id'])
        self.assertFalse(self.fixture.pulls)

    def test_actual_plan_preserves_configuration_and_pins_target(self):
        operation=self.ready();result=self.manager.execute(operation['id'])
        self.assertEqual(result['state'],'COMPLETED',result)
        self.assertEqual(self.fixture.container.attrs['Image'],NEW)
        self.assertEqual(json.loads((self.fixture.project/'images.json').read_text())['services']['web']['image'],TARGET)
        self.assertEqual(json.loads((self.fixture.project/'compose.json').read_text()),self.fixture.base)
        stages=[entry['state'] for entry in result['events']]
        for stage in ('CONFIG_VALIDATED','BACKUP_VERIFIED','MIGRATION_PRECHECK','APPLYING','HEALTH_CHECK','APPLICATION_CHECK','COMPLETED'):self.assertIn(stage,stages)
        self.assertTrue(self.fixture.pulls)
        self.assertTrue(all('--no-build' in cmd and '--pull' in cmd and '--remove-orphans' not in cmd for cmd in self.fixture.commands if 'up' in cmd))

    def test_local_change_after_approval_is_detected_before_pull(self):
        operation=self.ready();(self.fixture.project/'images.json').write_text('{"services":{"web":{"image":"tampered"}}}')
        result=self.manager.execute(operation['id'])
        self.assertEqual(result['state'],'BLOCKED');self.assertIn('files_changed',result['blockers']);self.assertFalse(self.fixture.pulls)

    def test_change_during_pull_is_detected_before_write(self):
        operation=self.ready()
        self.fixture.service._pull_image_with_retry=lambda *a,**kw:(self.fixture.project/'images.json').write_text('{"services":{"web":{"image":"changed"}}}')
        result=self.manager.execute(operation['id'])
        self.assertEqual(result['state'],'BLOCKED');self.assertFalse(any('up' in args for args in self.fixture.commands))

    def test_new_optional_env_file_after_analysis_invalidates_plan(self):
        operation=self.ready();(self.fixture.project/'.env').write_text('NEW_INPUT=1\n',encoding='utf-8')
        result=self.manager.execute(operation['id'])
        self.assertEqual(result['state'],'BLOCKED');self.assertIn('files_changed',result['blockers']);self.assertFalse(self.fixture.pulls)

    def test_runtime_configuration_drift_invalidates_plan(self):
        operation=self.ready();self.fixture.container.attrs['HostConfig']['Memory']=123
        result=self.manager.execute(operation['id'])
        self.assertEqual(result['state'],'BLOCKED');self.assertIn('runtime_changed',result['blockers'])

    def test_partial_file_write_failure_is_uncertain_and_does_not_start_docker(self):
        import stat
        operation=self.ready();fsync=os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):raise OSError('simulated directory fsync failure')
            return fsync(fd)
        with patch('compose_config.os.fsync',side_effect=fail_directory):result=self.manager.execute(operation['id'])
        self.assertEqual(result['state'],'MANUAL_INTERVENTION',result)
        self.assertFalse(any('up' in args for args in self.fixture.commands))
        with self.assertRaisesRegex(ComposeBlocked,'project_locked'):self.manager.analyze('demo')

    def test_old_application_probe_must_pass_before_deployment(self):
        operation=self.ready();self.fixture.fail_app=True
        result=self.manager.execute(operation['id'])
        self.assertEqual(result['state'],'BLOCKED');self.assertIn('application_check_failed',result['blockers']);self.assertFalse(self.fixture.pulls)

    def test_dry_run_cannot_be_approved_or_applied(self):
        operation=self.ready(approve=False,dry_run=True)
        with self.assertRaises(ComposeBlocked):self.manager.approve(operation['id'])
        with self.assertRaises(ComposeBlocked):self.manager.execute(operation['id'])

    def test_cancelled_or_completed_plan_cannot_be_replayed(self):
        operation=self.ready();self.manager.cancel(operation['id'])
        with self.assertRaises(ComposeBlocked):self.manager.execute(operation['id'])
        operation=self.ready();self.manager.execute(operation['id'])
        with self.assertRaises(ComposeBlocked):self.manager.execute(operation['id'])

    def test_health_failure_restores_only_stateless_images_and_config(self):
        operation=self.ready();self.fixture.fail_health=True
        result=self.manager.execute(operation['id'])
        self.assertEqual(result['state'],'RESTORED',result);self.assertEqual(self.fixture.container.attrs['Image'],OLD)
        self.assertEqual(json.loads((self.fixture.project/'images.json').read_text())['services']['web']['image'],SOURCE)

    def test_failed_rollback_retains_lock_and_reports_intervention_without_secret_output(self):
        operation=self.ready();self.fixture.fail_apply=True;self.fixture.fail_rollback=True
        result=self.manager.execute(operation['id'])
        self.assertEqual(result['state'],'MANUAL_INTERVENTION',result)
        with self.assertRaisesRegex(ComposeBlocked,'project_locked'):self.manager.analyze('demo')
        reports=json.dumps(self.manager.reports.snapshot())
        self.assertIn('compose_rollback_failed',reports);self.assertNotIn('PRIVATE_PASSWORD',reports)

    def test_wrong_platform_blocks_before_up(self):
        operation=self.ready();self.fixture.images[TARGET].attrs['Architecture']='arm64'
        result=self.manager.execute(operation['id'])
        self.assertEqual(result['state'],'BLOCKED');self.assertIn('platform_unsupported',result['blockers'])

    def test_image_declared_volumes_block_hidden_persistence(self):
        operation=self.ready();self.fixture.images[TARGET].attrs['Config']['Volumes']={'/data':{}}
        result=self.manager.execute(operation['id'])
        self.assertEqual(result['state'],'BLOCKED');self.assertIn('data_policy_required',result['blockers'])

    def test_conditional_deployment_requires_both_project_optins(self):
        operation=self.ready(approve=False)
        with self.assertRaisesRegex(ComposeBlocked,'consent_required'):self.manager.execute(operation['id'],automatic=True)
        self.manager.store.save_settings('demo',{'mode':'conditional','automation':'conditional','database_policy':'none'})
        operation=self.ready(approve=False)
        self.assertEqual(self.manager.execute(operation['id'],automatic=True)['state'],'COMPLETED')

    def test_coordinated_project_updates_include_every_approved_dependency(self):
        fixture=self.fixture
        worker=copy.deepcopy(fixture.base['services']['web'])
        fixture.base['services']['worker']=worker
        fixture.base['services']['web']['depends_on']={'worker':{'condition':'service_healthy'}}
        fixture.target=copy.deepcopy(fixture.base)
        for model in fixture.target['services'].values():model['image']=TARGET
        peer=copy.deepcopy(fixture.container);peer.id='worker-container';peer.name='demo-worker-1'
        peer.attrs['Config']['Labels']['com.docker.compose.service']='worker'
        peer.reload=lambda:None;peer.exec_run=lambda *args,**kwargs:(0,BODY)
        fixture.containers.append(peer)
        for container in fixture.containers:
            name=container.attrs['Config']['Labels']['com.docker.compose.service']
            container.attrs['Config']['Labels']['com.docker.compose.config-hash']=digest(fixture.base['services'][name])
        fixture.approval['profile']['services']['worker']=copy.deepcopy(fixture.approval['profile']['services']['web'])
        private_json(fixture.project/'compose.json',fixture.base)
        private_json(fixture.project/'images.json',{'services':{name:{'image':SOURCE} for name in fixture.base['services']}})
        private_json(fixture.folder/'base.json',fixture.base);private_json(fixture.folder/'upstream.json',fixture.target)
        for key in ('base','upstream'):fixture.approval['source'][key+'_sha256']=digest((fixture.folder/(key+'.json')).read_bytes())
        evidence={'schema':1,'source_model_sha256':digest(fixture.base),'target_model_sha256':digest(fixture.target),
                  'versions':{name:{'source':[OLD],'target':TARGET} for name in fixture.base['services']},'isolated':True,
                  'application_checks_passed':True,'persistent_data':[],'external_data_dependencies':[],'test_suite':'coordinated-fixture'}
        private_json(fixture.folder/'evidence.json',evidence)
        fixture.approval['profile']['evidence']['sha256']=digest((fixture.folder/'evidence.json').read_bytes());fixture.save_approval()
        operation=self.ready()
        original=fixture.run
        def run(args,**kwargs):
            result=original(args,**kwargs)
            if 'up' in args:
                peer.attrs['Image']=fixture.container.attrs['Image']
                peer.attrs['Config']['Labels']['com.docker.compose.config-hash']=digest(fixture.target['services']['worker'])
            return result
        self.manager.runner=run
        result=self.manager.execute(operation['id'])
        self.assertEqual(result['state'],'COMPLETED',result)
        up=[args for args in fixture.commands if 'up' in args]
        self.assertEqual(len(up),1);self.assertIn('web',up[0]);self.assertIn('worker',up[0])


class NotificationIntegrationTests(unittest.TestCase):
    def test_compose_information_progress_success_have_independent_optins(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);reports=ReportStore(root/'reports.json');service=NotificationService(root/'notifications.json',reports)
            config={'enabled':True,'telegram':{'enabled':True,'bot_token':'123:TEST','chat_id':'123'}}
            service.save(config);reports.on_event=service.enqueue
            for status in ('info','running','success'):reports.append('compose_started',status,message='apply_started')
            self.assertEqual(service.events.qsize(),0)
            for preference,status in (('compose_info','info'),('compose_progress','running'),('compose_success','success')):
                service.save({**config,preference:True});reports.append('compose_started',status,message='apply_started')
            self.assertEqual(service.events.qsize(),3)
            reports.append('compose_failed','error',message='health_failed')
            self.assertEqual(service.events.qsize(),4)

    def test_existing_transports_receive_localized_safe_event_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);reports=ReportStore(root/'reports.json');calls=[]
            service=NotificationService(root/'notifications.json',reports,transport=lambda *args:calls.append(args) or {'ok':True})
            service.save({'enabled':True,'compose_success':True,'telegram':{'enabled':True,'bot_token':'123:TEST','chat_id':'123'}})
            event_id=reports.append('compose_completed','success',message='completed')
            event=reports.snapshot()['entries'][0];service.deliver(event);service.deliver(event)
            self.assertEqual(len(calls),1);self.assertIn('Compose',calls[0][1]['text']);self.assertNotIn('TEST',calls[0][1]['text'])


class ComposeWebTests(unittest.TestCase):
    def setUp(self):
        from web import create_app
        self.temp=tempfile.TemporaryDirectory();self.fixture=Fixture(Path(self.temp.name))
        self.app=create_app(Path(self.temp.name)/'web-data',service_factory=lambda:self.fixture.service,print_credentials=False)
        self.manager=self.app.extensions['dcc_updater_compose'];self.manager.runner=self.fixture.run
        shutil.copytree(self.fixture.folder,self.manager.trust_root/'demo');self.manager.discover()
        self.client=self.app.test_client()
    def tearDown(self):self.temp.cleanup()
    def login(self):
        with self.client.session_transaction() as state:state.update(authenticated=True,csrf_token='fixture-token')

    def test_compose_api_uses_existing_authentication_and_csrf(self):
        for path in ('/api/compose/projects','/api/compose/projects/demo/history','/api/compose/operations/unknown'):
            self.assertEqual(self.client.get(path).status_code,401)
        self.login()
        for path in ('/api/compose/discover','/api/compose/projects/demo/analyze','/api/compose/projects/demo/settings','/api/compose/operations/unknown/execute'):
            self.assertEqual(self.client.post(path,json={}).status_code,400)
        self.assertEqual(self.client.get('/api/compose/projects').get_json()['automation_default'],'off')

    def test_new_tab_and_controls_render_in_both_languages_all_six_themes(self):
        from i18n import strings
        self.login()
        for lang in ('en','pl'):
            with self.client.session_transaction() as state:state['language']=lang
            for theme in ('red','green','blue','navy','violet','amber'):
                self.client.post('/api/preferences',json={'theme':theme},headers={'X-CSRF-Token':'fixture-token'})
                page=self.client.get('/').get_data(as_text=True)
                self.assertIn('id="tab-compose"',page);self.assertIn(f'data-theme="{theme}"',page)
                self.assertIn(strings(lang)['compose_discover'],page)
                for tab in ('containers','schedule','reports','settings'):self.assertIn(f'id="tab-{tab}"',page)

    def test_api_cannot_accept_a_local_trust_bundle_or_arbitrary_host_paths(self):
        self.login()
        response=self.client.post('/api/compose/projects/unknown/settings',json={'root':'/etc','approved':True},headers={'X-CSRF-Token':'fixture-token'})
        self.assertEqual(response.status_code,400)

    def test_global_job_queue_blocks_new_mutations_after_uncertain_compose_operation(self):
        compose=self.app.extensions['dcc_updater_compose']
        jobs=self.app.extensions['dcc_updater_jobs']
        operation=compose.store.create('uncertain');compose.store.transition(operation,'MANUAL_INTERVENTION')
        called=[]
        for kind in ('update','self_update','auto_update','schedule','compose_execute'):
            started,state=jobs.start(kind,lambda progress:called.append(True))
            self.assertFalse(started);self.assertEqual(state['error'],'compose_admin_intervention')
        self.assertEqual(called,[])

    def test_api_analysis_uses_shared_queue_and_blocked_plans_cannot_be_approved(self):
        self.login();headers={'X-CSRF-Token':'fixture-token'}
        response=self.client.post('/api/compose/projects/demo/analyze',json={},headers=headers)
        self.assertEqual(response.status_code,202)
        job=response.get_json()
        for _ in range(200):
            job=self.client.get('/api/job?id='+job['id']).get_json()
            if job['status'] not in ('queued','running'):break
            time.sleep(.01)
        self.assertEqual(job['status'],'done');operation=job['results']
        self.assertEqual(operation['state'],'BLOCKED');self.assertIn('consent_required',operation['blockers'])
        self.assertEqual(self.client.post('/api/compose/operations/'+operation['id']+'/approve',json={},headers=headers).status_code,409)
        self.assertEqual(self.client.post('/api/compose/operations/'+operation['id']+'/execute',json={},headers=headers).status_code,409)
        self.assertEqual(self.client.get('/api/compose/projects/demo/history').get_json()['operations'][0]['id'],operation['id'])

    def test_discovery_job_completes_when_one_local_image_is_unavailable(self):
        self.login()
        self.fixture.service._local_image=lambda container:None
        response=self.client.post('/api/compose/discover',json={},headers={'X-CSRF-Token':'fixture-token'})
        self.assertEqual(response.status_code,202)
        job=response.get_json()
        for _ in range(200):
            job=self.client.get('/api/job?id='+job['id']).get_json()
            if job['status'] not in ('queued','running'):break
            time.sleep(.01)
        self.assertEqual(job['status'],'done')
        self.assertEqual(job['results']['projects'][0]['services'][0]['check_diagnostics'],['local_image_unavailable'])
        self.assertEqual(len(self.client.get('/api/compose/projects').get_json()['projects']),1)


@unittest.skipUnless(shutil.which('docker-compose'), 'Compose CLI integration runs in the isolated test image')
class RealComposeNormalizationTests(unittest.TestCase):
    def test_real_multi_file_env_secret_ports_and_resource_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'.env').write_text('IMAGE=example/web:1\n',encoding='utf-8')
            (root/'service.env').write_text('PRIVATE_PASSWORD=do-not-export\n',encoding='utf-8')
            (root/'secret.txt').write_text('PRIVATE_SECRET',encoding='utf-8')
            (root/'compose.yaml').write_text('''services:
  web:
    image: ${IMAGE}
    env_file: service.env
    ports: ["8080:80"]
    secrets: [credential]
    restart: unless-stopped
secrets:
  credential:
    file: secret.txt
''',encoding='utf-8')
            (root/'override.json').write_text('{"services":{"web":{"image":"example/web:2","deploy":{"resources":{"limits":{"memory":"128M"}}}}}}',encoding='utf-8')
            config=ComposeConfig('fixture',root,['compose.yaml','override.json'])
            snapshot=config.snapshot()
            self.assertEqual(snapshot['model']['services']['web']['image'],'example/web:2')
            for filename in ('.env','service.env','secret.txt','compose.yaml','override.json'):self.assertIn(str(root/filename),snapshot['hashes'])
            self.assertEqual(snapshot['model']['services']['web']['environment']['PRIVATE_PASSWORD'],'do-not-export')
            self.assertTrue(snapshot['model']['services']['web']['deploy']['resources']['limits']['memory'])

    def test_real_parser_missing_variable_blocks_without_exposing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'compose.yaml').write_text('services:\n  web:\n    image: ${MISSING_PRIVATE_IMAGE}\n',encoding='utf-8')
            with self.assertRaisesRegex(ComposeBlocked,'compose_validation_failed'):
                ComposeConfig('fixture',root,['compose.yaml']).snapshot()


if __name__ == '__main__':unittest.main()
