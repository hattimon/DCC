import base64
import copy
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cinema_windows import export_script, eligible, windows_path
from compose_config import ComposeBlocked
from test_compose_manager import Fixture


class WindowsCinemaPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.fixture=Fixture(Path(self.temp.name))
        self.container=self.fixture.container
        self.container.id='c'*64
        self.container.attrs['Config']['Image']='ghcr.io/hattimon/cinema-hub:1.3.9'
        self.container.attrs['Config']['Env']=['PASSWORD=PRIVATE_TEST_VALUE']
        labels=self.container.attrs['Config']['Labels']
        labels['com.docker.compose.project.working_dir']='D:\\CODEX\\Cinema Hub'
        labels['com.docker.compose.project.config_files']='D:\\CODEX\\Cinema Hub\\compose.yaml,D:\\CODEX\\Cinema Hub\\.private\\local.json'
        self.container.attrs['Mounts']=[{'Type':'volume','Name':'cinema-state-existing','Destination':'/data','RW':True}]
        self.fixture.service.catalog_loader=lambda:[{'image':'ghcr.io/hattimon/cinema-hub:1.3.10'}]
        self.fixture.client.api=SimpleNamespace(inspect_distribution=lambda image:{'Descriptor':{'digest':'sha256:'+'d'*64}})

    def tearDown(self):self.temp.cleanup()

    def test_export_pins_catalog_target_preserves_exact_identity_and_excludes_secrets(self):
        script=export_script(self.fixture.service,'demo')
        encoded=re.search(r"FromBase64String\('([^']+)'\)",script).group(1)
        plan=json.loads(base64.b64decode(encoded))
        self.assertEqual(plan['target_tag'],'ghcr.io/hattimon/cinema-hub:1.3.10')
        self.assertEqual(plan['target_image'],'ghcr.io/hattimon/cinema-hub@sha256:'+'d'*64)
        self.assertEqual(plan['volume'],'cinema-state-existing')
        self.assertEqual(plan['files'][1],'D:\\CODEX\\Cinema Hub\\.private\\local.json')
        self.assertNotIn('PRIVATE_TEST_VALUE',script)
        self.assertNotIn('__DCC_',script)
        self.assertIn('param([switch]$Apply',script)

    def test_shared_volume_blocks_export(self):
        peer=copy.deepcopy(self.container);peer.id='e'*64
        peer.attrs['Config']['Labels']={}
        self.fixture.containers.append(peer)
        with self.assertRaisesRegex(ComposeBlocked,'external_dependency'):export_script(self.fixture.service,'demo')

    def test_other_repository_linux_and_multiple_replicas_are_not_eligible(self):
        self.assertTrue(eligible([self.container]))
        self.assertFalse(eligible([self.container,self.container]))
        self.container.attrs['Config']['Image']='other/cinema:latest'
        self.assertFalse(eligible([self.container]))
        for path in ('/srv/cinema','D:\\CODEX\\..\\secret','D:\\CODEX\\cinema\nmalicious','\\\\server\\share'):
            with self.subTest(path=path),self.assertRaises(ComposeBlocked):windows_path(path)

    def test_no_digest_or_catalog_failure_never_exports_a_mutable_target(self):
        self.fixture.client.api.inspect_distribution=lambda image:{'Descriptor':{}}
        with self.assertRaisesRegex(ComposeBlocked,'windows_target_unavailable'):export_script(self.fixture.service,'demo')
        self.fixture.service._catalog_cache=None
        self.fixture.service.catalog_loader=lambda:(_ for _ in ()).throw(RuntimeError('PRIVATE_ACCESS_TOKEN'))
        with self.assertRaisesRegex(ComposeBlocked,'windows_catalog_unavailable') as error:export_script(self.fixture.service,'demo')
        self.assertNotIn('PRIVATE_ACCESS_TOKEN',str(error.exception))

    def test_export_route_requires_auth_and_does_not_run_an_update(self):
        from web import create_app
        app=create_app(Path(self.temp.name)/'web',service_factory=lambda:self.fixture.service,print_credentials=False)
        client=app.test_client()
        path='/api/compose/projects/demo/windows-cinema'
        self.assertEqual(client.get(path).status_code,401)
        with client.session_transaction() as state:state['authenticated']=True
        response=client.get(path)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(response.get_json()['filename'],'dcc-cinema-windows.ps1')
        self.assertFalse(self.fixture.pulls)
        self.assertFalse(self.fixture.commands)


def node_sqlite_available():
    if not shutil.which('node'):return False
    result=subprocess.run(['node','--no-warnings','-e',"try{process.exit(typeof require('node:sqlite').backup==='function'?0:1)}catch{process.exit(1)}"],capture_output=True,timeout=10)
    return result.returncode==0


@unittest.skipUnless(node_sqlite_available(),'Node SQLite backup integration is also exercised in the Windows host workflow')
class CinemaSQLiteBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'source';self.source.mkdir()
        self.backup=self.root/'backup';self.backup.mkdir()
        (self.source/'credentials.key').write_bytes(b'k'*32)
        self.db=sqlite3.connect(self.source/'cinema.sqlite')
        self.db.executescript("PRAGMA journal_mode=WAL;CREATE TABLE users(id TEXT PRIMARY KEY,password TEXT);CREATE TABLE sources(id TEXT PRIMARY KEY);CREATE TABLE settings(id TEXT PRIMARY KEY,value TEXT);INSERT INTO users VALUES('one','PRIVATE_PASSWORD_HASH');INSERT INTO settings VALUES('one','PRIVATE_SETTING');")
        self.db.commit()
        self.helper=Path(__file__).resolve().parents[1]/'windows/cinema-sqlite.mjs'
    def tearDown(self):self.db.close();self.temp.cleanup()
    def run_helper(self,mode,source,destination=None):
        return subprocess.run(['node','--no-warnings',str(self.helper),mode,str(source),*([str(destination)] if destination else [])],capture_output=True,text=True,encoding='utf-8',timeout=20)
    def test_online_wal_backup_is_restorable_and_keeps_the_key_and_accounts_private(self):
        result=self.run_helper('snapshot',self.source,self.backup)
        self.assertEqual(result.returncode,0,result.stderr)
        metadata=json.loads(result.stdout)
        self.assertEqual(metadata['tables']['users']['count'],1)
        self.assertNotIn('PRIVATE_',result.stdout)
        self.assertEqual((self.backup/'credentials.key').read_bytes(),b'k'*32)
        restored=sqlite3.connect(self.backup/'cinema.sqlite')
        self.assertEqual(restored.execute('SELECT password FROM users').fetchone()[0],'PRIVATE_PASSWORD_HASH')
        restored.close()
        self.assertEqual(self.db.execute('SELECT count(*) FROM users').fetchone()[0],1)
    def test_invalid_key_and_nonempty_destination_fail_without_overwrite(self):
        (self.source/'credentials.key').write_bytes(b'bad')
        result=self.run_helper('snapshot',self.source,self.backup)
        self.assertNotEqual(result.returncode,0)
        self.assertFalse((self.backup/'cinema.sqlite').exists())
        (self.source/'credentials.key').write_bytes(b'k'*32)
        (self.backup/'cinema.sqlite').write_bytes(b'preserve existing backup')
        result=self.run_helper('snapshot',self.source,self.backup)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual((self.backup/'cinema.sqlite').read_bytes(),b'preserve existing backup')
    def test_fingerprints_detect_schema_and_account_changes(self):
        before=json.loads(self.run_helper('inspect',self.source).stdout)
        self.db.execute("UPDATE users SET password='changed' WHERE id='one'");self.db.commit()
        changed=json.loads(self.run_helper('inspect',self.source).stdout)
        self.assertNotEqual(before['tables']['users']['sha256'],changed['tables']['users']['sha256'])
        self.assertEqual(before['schema_sha256'],changed['schema_sha256'])
        self.db.execute('ALTER TABLE users ADD COLUMN changed INTEGER');self.db.commit()
        changed=json.loads(self.run_helper('inspect',self.source).stdout)
        self.assertNotEqual(before['schema_sha256'],changed['schema_sha256'])


if __name__=='__main__':unittest.main()
