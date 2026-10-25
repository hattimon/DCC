"""Fail-closed Safe Compose Update Manager integrated with DCC's job queue.

The initial executable deployment adapter is intentionally narrow: reviewed,
digest-pinned, stateless projects, image-only changes, one replica per service,
no outside dependencies, and a locally granted existing image override file.
Database migrations have no production executor. SQLite backups are verified on
isolated copies and never restored over a live database by this manager.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path

from compose_config import (ComposeBlocked, ComposeConfig, ControlledWriter, digest,
                            private_json, read_bytes, safe_path, semantic_merge)
from scheduler import validate_config, next_run
from updater import (COMPOSE_CONFIG_FILES_LABEL, COMPOSE_PROJECT_LABEL, COMPOSE_SERVICE_LABEL,
                     COMPOSE_WORKING_DIR_LABEL, SELF_LABEL, normalized_repository)


MODES = ('monitor', 'manual', 'conditional', 'migration')
POLICIES = ('unknown', 'none', 'compatible', 'approved_migration', 'admin')
AUTOMATION = ('off', 'check', 'analyze', 'conditional')
STAGES = ('DETECTED', 'ANALYZING', 'PLAN_READY', 'CONFIG_VALIDATED', 'BACKUP_VERIFIED',
          'MIGRATION_PRECHECK', 'READY', 'APPLYING', 'HEALTH_CHECK', 'APPLICATION_CHECK', 'COMPLETED')
TERMINAL = {'COMPLETED', 'BLOCKED', 'FAILED', 'RESTORED', 'MANUAL_INTERVENTION', 'CANCELLED'}
MUTATING = {'APPLYING', 'HEALTH_CHECK', 'APPLICATION_CHECK', 'ROLLBACK_PENDING', 'ROLLING_BACK'}
DEFAULTS = {'mode': 'monitor', 'automation': 'off', 'database_policy': 'unknown', 'services': {}, 'schedule': None}
IMAGE_ID = re.compile(r'sha256:[0-9a-f]{64}')
PINNED = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9./:_-]*@sha256:[0-9a-f]{64}')
DATABASE = re.compile(r'postgres|mariadb|mysql|mongo|redis|valkey|sqlite|mssql|cassandra|couch|influx|clickhouse', re.I)


class _Rows:
    def __init__(self, rows):
        self.rows = rows
    def fetchone(self):
        return self.rows[0] if self.rows else None
    def fetchall(self):
        return list(self.rows)
    def __iter__(self):
        return iter(self.rows)


class _Database:
    """Short connections: no idle file handles or cross-thread transactions."""
    def __init__(self, path, lock):
        self.path, self.lock, self.local = path, lock, threading.local()

    def __enter__(self):
        self.lock.acquire()
        try:
            if not getattr(self.local, 'connection', None):
                self.local.connection = sqlite3.connect(self.path, timeout=10)
                self.local.depth = 0
                self.local.connection.execute('PRAGMA synchronous=FULL')
                self.local.connection.row_factory = sqlite3.Row
            self.local.depth += 1
            return self
        except Exception:
            connection = getattr(self.local, 'connection', None)
            if connection is not None:
                connection.close()
                self.local.connection = None
            self.lock.release()
            raise

    def __exit__(self, kind, value, tb):
        try:
            self.local.depth -= 1
            if not self.local.depth:
                try:
                    self.local.connection.rollback() if kind else self.local.connection.commit()
                finally:
                    self.local.connection.close()
                    self.local.connection = None
        finally:
            self.lock.release()

    def execute(self, sql, parameters=()):
        if not getattr(self.local, 'connection', None):
            with self:
                return self.execute(sql, parameters)
        cursor = self.local.connection.execute(sql, parameters)
        return _Rows(cursor.fetchall() if cursor.description else [])

    def executescript(self, sql):
        with self:
            self.local.connection.executescript(sql)

    def commit(self):
        pass  # Each explicit context commits durably on exit.


class ComposeStore:
    """SQLite FULL durability, compare-and-swap stages and persistent locks."""
    def __init__(self, path):
        self.path, self.lock = Path(path), threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = _Database(self.path, self.lock)
        self.db.execute('PRAGMA synchronous=FULL')
        os.chmod(self.path, 0o600)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS projects(name TEXT PRIMARY KEY, settings TEXT NOT NULL, next_run REAL, last_run TEXT);
            CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, project TEXT NOT NULL, state TEXT NOT NULL,
                created REAL NOT NULL, updated REAL NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, operation TEXT NOT NULL, at REAL NOT NULL,
                state TEXT NOT NULL, code TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS locks(project TEXT PRIMARY KEY, operation TEXT NOT NULL);
        ''')
        self.db.commit()
        # Never replay an interrupted operation or release an uncertain lock.
        with self.lock, self.db:
            for row in self.db.execute('SELECT id,state FROM operations').fetchall():
                if row['state'] in MUTATING:
                    self._transition(row['id'], 'MANUAL_INTERVENTION', 'restart_uncertain')
                elif row['state'] not in TERMINAL:
                    self._transition(row['id'], 'BLOCKED', 'restart_review_required')
                    self.db.execute('DELETE FROM locks WHERE operation=?', (row['id'],))
                elif row['state'] != 'MANUAL_INTERVENTION':
                    self.db.execute('DELETE FROM locks WHERE operation=?', (row['id'],))

    def settings(self, name):
        with self.lock:
            row = self.db.execute('SELECT settings FROM projects WHERE name=?', (name,)).fetchone()
            return {**copy.deepcopy(DEFAULTS), **json.loads(row[0])} if row else copy.deepcopy(DEFAULTS)

    def save_settings(self, name, payload):
        if not isinstance(payload, dict):
            raise ComposeBlocked('settings_invalid')
        config = {key: copy.deepcopy(payload.get(key, value)) for key, value in DEFAULTS.items()}
        if (config['mode'] not in MODES or config['automation'] not in AUTOMATION
                or config['database_policy'] not in POLICIES or not isinstance(config['services'], dict)
                or len(config['services']) > 100):
            raise ComposeBlocked('settings_invalid')
        if config['automation'] == 'conditional' and config['mode'] != 'conditional':
            raise ComposeBlocked('consent_required')
        for service, mode in config['services'].items():
            if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}', service) or mode not in MODES:
                raise ComposeBlocked('settings_invalid')
        schedule = config['schedule']
        if schedule is not None:
            if not isinstance(schedule, dict):
                raise ComposeBlocked('settings_invalid')
            # Reuse all existing IANA/DST/calendar validation and next-run math.
            schedule = validate_config({**schedule, 'action': 'scan', 'targets': [], 'panel_first': False})
            config['schedule'] = schedule
        with self.lock, self.db:
            if self.db.execute('SELECT 1 FROM locks WHERE project=?', (name,)).fetchone():
                raise ComposeBlocked('project_locked')
            self.db.execute('INSERT INTO projects(name,settings,next_run) VALUES(?,?,?) '
                            'ON CONFLICT(name) DO UPDATE SET settings=excluded.settings,next_run=excluded.next_run',
                            (name, json.dumps(config), next_run(schedule, time.time()) if schedule else None))
            # Any changed policy invalidates previously approved plans.
            for row in self.db.execute('SELECT id,state FROM operations WHERE project=?', (name,)).fetchall():
                if row['state'] not in TERMINAL:
                    self._transition(row['id'], 'BLOCKED', 'settings_changed')
        return config

    def create(self, project):
        operation = uuid.uuid4().hex
        with self.lock, self.db:
            if self.db.execute('SELECT 1 FROM locks WHERE project=?', (project,)).fetchone():
                raise ComposeBlocked('project_locked')
            self.db.execute('INSERT INTO locks VALUES(?,?)', (project, operation))
            now = time.time()
            self.db.execute('INSERT INTO operations VALUES(?,?,?,?,?,?)',
                            (operation, project, 'DETECTED', now, now, '{}'))
            self.db.execute('INSERT INTO events(operation,at,state,code) VALUES(?,?,?,?)',
                            (operation, now, 'DETECTED', 'detected'))
        return operation

    def _transition(self, operation, state, code='', payload=None):
        now = time.time()
        if payload is None:
            self.db.execute('UPDATE operations SET state=?,updated=? WHERE id=?', (state, now, operation))
        else:
            self.db.execute('UPDATE operations SET state=?,updated=?,payload=? WHERE id=?',
                            (state, now, json.dumps(payload), operation))
        self.db.execute('INSERT INTO events(operation,at,state,code) VALUES(?,?,?,?)',
                        (operation, now, state, code))

    def transition(self, operation, state, code='', *, payload=None, expected=None):
        if state not in set(STAGES) | TERMINAL | MUTATING:
            raise ComposeBlocked('state_invalid')
        with self.lock, self.db:
            row = self.db.execute('SELECT state FROM operations WHERE id=?', (operation,)).fetchone()
            if not row or (expected is not None and row[0] not in expected):
                raise ComposeBlocked('state_invalid')
            self._transition(operation, state, code, payload)

    def release(self, operation):
        with self.lock, self.db:
            self.db.execute('DELETE FROM locks WHERE operation=?', (operation,))

    def acquire(self, operation, project):
        with self.lock, self.db:
            try:
                self.db.execute('INSERT INTO locks VALUES(?,?)', (project, operation))
            except sqlite3.IntegrityError:
                raise ComposeBlocked('project_locked') from None

    def get(self, operation, *, public=True):
        with self.lock:
            row = self.db.execute('SELECT * FROM operations WHERE id=?', (operation,)).fetchone()
            if not row:
                raise ComposeBlocked('operation_unknown')
            result = dict(row)
            payload = json.loads(result.pop('payload'))
            if public:
                result.update({key: payload[key] for key in ('blockers', 'diff', 'approved', 'checks', 'versions', 'backup', 'dry_run', 'action', 'deployed') if key in payload})
            else:
                result['payload'] = payload
            result['events'] = [dict(item) for item in self.db.execute(
                'SELECT at,state,code FROM events WHERE operation=? ORDER BY seq', (operation,))]
            return result

    def history(self, project):
        with self.lock:
            ids = [row[0] for row in self.db.execute('SELECT id FROM operations WHERE project=? ORDER BY created DESC LIMIT 30', (project,))]
            return [self.get(item) for item in ids]

    def requires_intervention(self):
        with self.lock:
            return bool(self.db.execute("SELECT 1 FROM operations WHERE state='MANUAL_INTERVENTION' LIMIT 1").fetchone())

    def due(self, now):
        with self.lock:
            return [row[0] for row in self.db.execute('SELECT name FROM projects WHERE next_run<=?', (now,))
                    if self.settings(row[0])['automation'] != 'off']

    def claim_schedule(self, project, now):
        with self.lock, self.db:
            row = self.db.execute('SELECT next_run FROM projects WHERE name=?', (project,)).fetchone()
            config = self.settings(project)
            if not row or row[0] is None or row[0] > now or config['automation'] == 'off':
                return None
            # Consume the due time before doing anything, including analysis.
            self.db.execute('UPDATE projects SET next_run=?,last_run=? WHERE name=?',
                            (next_run(config['schedule'], now), json.dumps({'at': now, 'status': 'claimed'}), project))
            return config

    def schedule_status(self, project):
        with self.lock:
            row = self.db.execute('SELECT next_run,last_run FROM projects WHERE name=?', (project,)).fetchone()
            return {'next_run': row['next_run'], 'last_run': json.loads(row['last_run']) if row['last_run'] else None} if row else {'next_run': None, 'last_run': None}

    def finish_schedule(self, project, status, code):
        with self.lock, self.db:
            self.db.execute('UPDATE projects SET last_run=? WHERE name=?',
                            (json.dumps({'at': time.time(), 'status': status, 'code': code}), project))


class SQLiteBackup:
    """Online SQLite snapshot plus integrity check on an isolated restored copy.

    This verifies SQLite structural integrity only, not application invariants or
    cross-database consistency. It never grants migration/deployment readiness.
    """
    @staticmethod
    def verify(root, relative, destination):
        source = safe_path(root, relative, max_size=None)
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
        backup, restored = destination / 'backup.sqlite', destination / 'restore-test.sqlite'
        started = time.monotonic()
        def progress(_status, _remaining, _total):
            if time.monotonic() - started > 60:
                raise ComposeBlocked('backup_timeout')
        try:
            with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=5)) as src:
                with closing(sqlite3.connect(backup)) as out:
                    src.backup(out, pages=128, progress=progress, sleep=0.01)
            os.chmod(backup, 0o600)
            shutil.copyfile(backup, restored)
            os.chmod(restored, 0o600)
            with closing(sqlite3.connect(restored.as_uri() + '?mode=ro', uri=True)) as test:
                if test.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                    raise ComposeBlocked('backup_unverified')
            checksum = hashlib.sha256()
            with backup.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    checksum.update(chunk)
            return {'adapter': 'sqlite-online-v1', 'verified': True, 'restore_tested': True,
                    'sha256': checksum.hexdigest(), 'checked_at': time.time(),
                    'scope': 'sqlite_structure_only', 'production_restore': False}
        except (sqlite3.Error, OSError):
            raise ComposeBlocked('backup_unverified') from None


class SafeComposeManager:
    def __init__(self, data_dir, service_factory, reports, *, runner=None):
        self.root = Path(data_dir) / 'safe-compose'
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.trust_root = self.root / 'trusted'
        self.trust_root.mkdir(exist_ok=True, mode=0o700)
        self.store = ComposeStore(self.root / 'state.sqlite')
        self.service_factory, self.reports, self.runner = service_factory, reports, runner
        self.catalog = {}
        self.lock = threading.RLock()
        for row in self.store.db.execute("SELECT id,project FROM operations WHERE state='MANUAL_INTERVENTION'").fetchall():
            self.event(row['project'], row['id'], 'intervention', 'error', 'restart_uncertain')

    def event(self, project, operation, event, status, code):
        self.reports.append('compose_' + event, status, message=code,
                            details=[{'name': project, 'result': code}], project=project, operation_id=operation)

    def trust(self, project):
        folder = safe_path(self.trust_root, project, directory=True)
        raw = read_bytes(folder, 'approval.json')
        try:
            trust = json.loads(raw)
        except (ValueError, TypeError):
            raise ComposeBlocked('source_unapproved') from None
        if trust.get('project') != project or trust.get('approved') is not True:
            raise ComposeBlocked('source_unapproved')
        return trust, folder, digest(raw)

    def verify_profile_evidence(self, trust, folder, source_model, target_model, versions):
        """A UI checkbox cannot manufacture version compatibility evidence.

        The locally approved bundle must pin a separately reviewed isolated test
        report to the complete input/target models and exact source image IDs.
        This is evidence ingestion, not an assertion that DCC ran those tests.
        """
        evidence = (trust.get('profile') or {}).get('evidence') or {}
        try:
            raw = read_bytes(folder, evidence.get('file', ''))
            report = json.loads(raw)
        except (ComposeBlocked, ValueError, TypeError):
            raise ComposeBlocked('compatibility_unverified') from None
        if (digest(raw) != evidence.get('sha256') or report.get('schema') != 1
                or report.get('source_model_sha256') != digest(source_model)
                or report.get('target_model_sha256') != digest(target_model)
                or report.get('versions') != versions or report.get('isolated') is not True
                or report.get('application_checks_passed') is not True
                or report.get('persistent_data') != [] or report.get('external_data_dependencies') != []
                or not isinstance(report.get('test_suite'), str) or not report['test_suite'].strip()):
            raise ComposeBlocked('compatibility_unverified')

    def discover(self, progress=lambda _message: None, *, check_updates=False):
        service = self.service_factory()
        containers = service.client.containers.list(all=True)
        groups = {}
        for container in containers:
            labels = (container.attrs.get('Config') or {}).get('Labels') or {}
            name = labels.get(COMPOSE_PROJECT_LABEL)
            if not name or not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{0,127}', name):
                continue
            groups.setdefault(name, []).append(container)
        result = []
        for name, members in sorted(groups.items()):
            progress('Docker Compose: ' + name)
            item = {'name': name, 'services': [], 'settings': self.store.settings(name), 'status': 'review_required',
                    'config_files': [], 'networks': [], 'volumes': [], 'databases': [], 'source': 'unapproved',
                    'analyzed_at': None, 'updated_at': None, 'blockers': []}
            histories = self.store.history(name)
            if histories:
                item['last_operation'] = histories[0]
                item['analyzed_at'] = next((entry['created'] for entry in histories if entry.get('action') == 'update'), None)
                item['status'] = histories[0]['state'].lower()
                item['updated_at'] = next((entry['updated'] for entry in histories if entry.get('deployed')), None)
            trust = None
            try:
                trust, _folder, _hash = self.trust(name)
                item['source'] = str(trust.get('source', {}).get('revision', 'unapproved'))[:160]
            except (ComposeBlocked, OSError):
                pass
            by_service = {}
            for container in members:
                labels = (container.attrs.get('Config') or {}).get('Labels') or {}
                svc = labels.get(COMPOSE_SERVICE_LABEL) or 'unknown'
                entry = by_service.setdefault(svc, {'name': svc, 'replicas': 0, 'images': [], 'image_ids': [],
                                                       'update_available': None, 'dependencies': [], 'database': False,
                                                       'check_diagnostics': []})
                entry['replicas'] += 1
                image = str((container.attrs.get('Config') or {}).get('Image') or '')
                if image not in entry['images']:
                    entry['images'].append(image)
                target = (((trust or {}).get('profile') or {}).get('services') or {}).get(svc, {}).get('target_image', '')
                if PINNED.fullmatch(target) and normalized_repository(target) == normalized_repository(image):
                    entry['target_image'] = target
                entry['image_ids'].append(str(container.attrs.get('Image') or ''))
                entry['database'] |= bool(DATABASE.search(image))
                item['config_files'] = sorted(set(item['config_files']) | set(str(labels.get(COMPOSE_CONFIG_FILES_LABEL) or '').split(',')))
                if check_updates:
                    try:
                        local = service._local_image(container)
                        if local is None:
                            entry['check_diagnostics'].append('local_image_unavailable')
                            item['blockers'].append('local_image_unavailable')
                            available = None
                        else:
                            available, _detail = service._registry_digest(entry.get('target_image') or image, local)
                            if available is None:
                                entry['check_diagnostics'].append('image_check_failed')
                    except Exception:
                        # A missing image, registry outage or one stale replica
                        # must not hide every Compose project on the host.
                        available = None
                        entry['check_diagnostics'].append('image_check_failed')
                    if available is True:
                        entry['update_available'] = True
                    elif entry['update_available'] is not True:
                        entry['update_available'] = None if entry['check_diagnostics'] else available
                item['networks'] = sorted(set(item['networks']) | set((container.attrs.get('NetworkSettings') or {}).get('Networks') or {}))
                item['volumes'] = sorted(set(item['volumes']) | {str(m.get('Name') or m.get('Source') or '') for m in container.attrs.get('Mounts') or []})
            # Read labels/files through the existing loader for display only. The
            # deployment path below uses a fresh, complete, strict snapshot.
            try:
                project, error = service._load_compose_project(members[0])
                if project:
                    for svc, entry in by_service.items():
                        cfg = project.config['services'].get(svc, {})
                        entry['dependencies'] = sorted(service._compose_depends_on(cfg))
                        entry['profiles'] = cfg.get('profiles') or []
                    item['location'] = str(project.working_dir)
                else:
                    item['blockers'].append('files_missing')
            except Exception:
                item['blockers'].append('compose_validation_failed')
            item['services'] = list(by_service.values())
            item['blockers'] = sorted(set(item['blockers']))
            for entry in item['services']:
                entry['check_diagnostics'] = sorted(set(entry['check_diagnostics']))
            item['databases'] = [entry['name'] for entry in item['services'] if entry['database']]
            if not histories and any(entry['update_available'] for entry in item['services']):
                item['status'] = 'update_available'
            elif not histories and check_updates and all(entry['update_available'] is False for entry in item['services']):
                item['status'] = 'up_to_date'
            result.append(item)
        with self.lock:
            self.catalog = {item['name']: item for item in result}
        return result

    def projects(self):
        with self.lock:
            result = copy.deepcopy(list(self.catalog.values()))
        for project in result:
            project['settings'] = self.store.settings(project['name'])
            project['schedule_status'] = self.store.schedule_status(project['name'])
            history = self.store.history(project['name'])
            if history:
                project.update(last_operation=history[0], status=history[0]['state'].lower(),
                               analyzed_at=next((op['created'] for op in history if op.get('action') == 'update'), None))
                project['updated_at'] = next((op['updated'] for op in history if op.get('deployed')), None)
        return result

    def require_project(self, project):
        if project not in self.catalog:
            raise ComposeBlocked('project_unknown')

    def config(self, project, trust, members):
        root = Path(trust.get('root', ''))
        service = self.service_factory()
        if not root.is_absolute() or not service._path_is_under(root, service.compose_roots):
            raise ComposeBlocked('path_unsafe')
        files = trust.get('files')
        if not isinstance(files, list) or not files or any(not isinstance(path, str) or Path(path).is_absolute() for path in files):
            raise ComposeBlocked('files_missing')
        config = ComposeConfig(project, root, files, binary=service.compose_bin,
                               profiles=trust.get('profiles') or (), **({'runner': self.runner} if self.runner else {}))
        expected_files = [str(path) for path in config.files]
        for container in members:
            labels = (container.attrs.get('Config') or {}).get('Labels') or {}
            if str(labels.get(COMPOSE_WORKING_DIR_LABEL) or '') != str(root):
                raise ComposeBlocked('project_identity_changed')
            actual = [str(safe_path(root, p.strip())) for p in str(labels.get(COMPOSE_CONFIG_FILES_LABEL) or '').split(',') if p.strip()]
            if actual != expected_files:
                raise ComposeBlocked('input_closure_unknown')
            if str(labels.get('com.docker.compose.project.environment_file') or ''):
                raise ComposeBlocked('input_closure_unknown')
        return config

    def members(self, project, service):
        all_containers = service.client.containers.list(all=True)
        members = [c for c in all_containers if ((c.attrs.get('Config') or {}).get('Labels') or {}).get(COMPOSE_PROJECT_LABEL) == project]
        if not members:
            raise ComposeBlocked('project_unknown')
        return members, all_containers

    def source_models(self, trust, folder):
        source = trust.get('source') or {}
        if not re.fullmatch(r'[a-zA-Z0-9_.:/@+-]{1,200}', str(source.get('revision', ''))):
            raise ComposeBlocked('source_unapproved')
        output = []
        for key in ('base', 'upstream'):
            if not source.get(key):
                if key == 'base':
                    output.append(None)
                    continue
                raise ComposeBlocked('source_unapproved')
            raw = read_bytes(folder, source[key])
            if digest(raw) != source.get(key + '_sha256'):
                raise ComposeBlocked('source_changed')
            try:
                value = json.loads(raw)
            except (ValueError, TypeError):
                raise ComposeBlocked('source_unapproved') from None
            if not isinstance(value, dict) or not isinstance(value.get('services'), dict):
                raise ComposeBlocked('source_unapproved')
            output.append(value)
        return output

    def preflight(self, project, config, snapshot, merged, trust, settings, members, all_containers):
        blockers, checks = [], []
        service = self.service_factory()
        profile = trust.get('profile') or {}
        models = snapshot['model']['services']
        targets = (merged or {}).get('services') or {}
        if settings['mode'] == 'monitor':
            blockers.append('consent_required')
        if settings['mode'] == 'migration':
            blockers.append('migration_adapter_unavailable')
        if settings['database_policy'] != 'none':
            blockers.append('database_unknown')
        if profile.get('kind') != 'stateless-v1' or profile.get('approved') is not True:
            blockers.append('profile_unapproved')
        if not merged or set(models) != set(targets) or not models:
            return ['service_scope_changed', *blockers], checks
        if snapshot['model'].get('volumes') or merged.get('volumes'):
            blockers.append('data_policy_required')
        if config.profiles or any(s.get('profiles') for s in targets.values()):
            blockers.append('profiles_unknown')
        by_service = {}
        for container in members:
            labels = (container.attrs.get('Config') or {}).get('Labels') or {}
            by_service.setdefault(labels.get(COMPOSE_SERVICE_LABEL), []).append(container)
            if labels.get(SELF_LABEL) == 'true' or service._is_self(container):
                blockers.append('panel_separate')
        if set(by_service) != set(models):
            blockers.append('service_scope_changed')
        review = profile.get('services') or {}
        old_no_images, new_no_images = copy.deepcopy(snapshot['model']), copy.deepcopy(merged)
        for name, model in targets.items():
            old_no_images['services'][name].pop('image', None)
            new_no_images['services'][name].pop('image', None)
            allowed = review.get(name) or {}
            replicas = by_service.get(name, [])
            if settings['services'].get(name, settings['mode']) == 'monitor':
                blockers.append('service_consent_required')
            if settings['services'].get(name, settings['mode']) == 'migration':
                blockers.append('migration_adapter_unavailable')
            if settings['mode'] == 'conditional' and settings['services'].get(name, 'conditional') != 'conditional':
                blockers.append('service_consent_required')
            if len(replicas) != 1 or int((model.get('deploy') or {}).get('replicas', model.get('scale', 1))) != 1:
                blockers.append('replicas_unsupported')
                continue
            container = replicas[0]
            labels = (container.attrs.get('Config') or {}).get('Labels') or {}
            if labels.get('com.docker.compose.config-hash') != snapshot['service_hashes'].get(name):
                blockers.append('runtime_changed')
            source_id = str(container.attrs.get('Image') or '')
            image = str(model.get('image') or '')
            if (not IMAGE_ID.fullmatch(source_id) or allowed.get('source_image_id') != source_id
                    or allowed.get('target_image') != image or not PINNED.fullmatch(image)
                    or not PINNED.fullmatch(str(models[name].get('image') or ''))
                    or normalized_repository(image) != normalized_repository(str(models[name].get('image') or ''))):
                blockers.append('compatibility_unverified')
            if DATABASE.search(image) or model.get('volumes') or container.attrs.get('Mounts') or model.get('volumes_from'):
                blockers.append('data_policy_required')
            if ((container.attrs.get('State') or {}).get('Status') != 'running'
                    or ((container.attrs.get('State') or {}).get('Health') or {}).get('Status') != 'healthy'
                    or not (model.get('healthcheck') or {}).get('test') or (model.get('healthcheck') or {}).get('disable')
                    or (model.get('healthcheck') or {}).get('test') == ['NONE']):
                blockers.append('health_required')
            probe = allowed.get('application_check') or {}
            if (probe.get('kind') != 'http-sha256' or type(probe.get('port')) is not int or not 1 <= probe['port'] <= 65535
                    or not re.fullmatch(r'/[a-zA-Z0-9/_.-]*', str(probe.get('path', '')))
                    or not re.fullmatch(r'[a-f0-9]{64}', str(probe.get('body_sha256', '')))):
                blockers.append('application_check_required')
            unsafe = ('build', 'develop', 'pre_start', 'post_start', 'pre_stop', 'post_stop', 'privileged', 'devices', 'cap_add', 'external_links', 'links', 'volumes_from', 'provider', 'use_api_socket')
            if any(model.get(key) for key in unsafe) or model.get('network_mode') or model.get('pid') or model.get('ipc'):
                blockers.append('service_unsupported')
            if (model.get('deploy') or {}).get('resources', {}).get('reservations', {}).get('devices'):
                blockers.append('service_unsupported')
            # Complete project scope, with Compose dependency ordering. Unknown
            # dependencies or cycles block instead of invoking arbitrary services.
            dependencies = service._compose_depends_on(model)
            if not dependencies.issubset(targets):
                blockers.append('dependency_unknown')
            others = [c for c in all_containers if c not in members]
            if service._compose_port_conflict(container, model, all_containers):
                blockers.append('port_conflict')
            own_networks = set((container.attrs.get('NetworkSettings') or {}).get('Networks') or {})
            for other in others:
                networks = set((other.attrs.get('NetworkSettings') or {}).get('Networks') or {})
                if own_networks & networks or service.automatic_dependency_blocker(container, [other]):
                    blockers.append('external_dependency')
        if old_no_images != new_no_images:
            blockers.append('config_change_adapter_unavailable')
        visiting, visited = set(), set()
        def visit(name):
            if name in visiting:
                blockers.append('dependency_cycle')
                return
            if name in visited:
                return
            visiting.add(name)
            for dep in service._compose_depends_on(targets[name]):
                if dep in targets:
                    visit(dep)
            visiting.remove(name)
            visited.add(name)
        for name in targets:
            visit(name)
        write = trust.get('write') or {}
        relative = write.get('file', '')
        try:
            path = safe_path(config.root, relative)
            if path not in config.files or config.files[-1] != path or path.suffix != '.json' or path.name in ('.env', 'approval.json'):
                raise ComposeBlocked('write_not_granted')
            original = json.loads(read_bytes(config.root, relative))
            if (not isinstance(original, dict) or set(original) != {'services'} or
                    any(not isinstance(v, dict) or set(v) != {'image'} for v in original['services'].values())):
                raise ComposeBlocked('write_not_granted')
            if os.name != 'posix' or not os.access(path.parent, os.W_OK) or not os.access(path, os.W_OK):
                raise ComposeBlocked('write_not_granted')
            if path.stat().st_uid != os.geteuid() or path.stat().st_gid != os.getegid():
                raise ComposeBlocked('write_not_granted')  # No added CHOWN capability.
            if hasattr(os, 'statvfs') and os.statvfs(path).f_flag & getattr(os, 'ST_RDONLY', 1):
                raise ComposeBlocked('write_not_granted')
        except (ComposeBlocked, OSError, ValueError, TypeError):
            blockers.append('write_not_granted')
        checks.extend(['compose_config_quiet', 'input_hashes', 'project_scope', 'dependencies', 'ports', 'networks',
                       'replicas', 'data_inventory', 'profile_versions', 'health_policy', 'application_policy', 'write_grant'])
        return sorted(set(blockers)), checks

    def analyze(self, project, progress=lambda _message: None, *, dry_run=False):
        self.require_project(project)
        operation = self.store.create(project)
        payload = {'blockers': [], 'checks': [], 'approved': False, 'dry_run': dry_run, 'action': 'update', 'deployed': False}
        try:
            self.store.transition(operation, 'ANALYZING')
            progress('ANALYZING')
            trust, folder, trust_hash = self.trust(project)
            service = self.service_factory()
            members, all_containers = self.members(project, service)
            config = self.config(project, trust, members)
            snapshot = config.snapshot()
            base, upstream = self.source_models(trust, folder)
            review = semantic_merge(base, snapshot['model'], upstream)
            merged = review.pop('merged')
            payload['diff'] = review
            payload.update(trust_hash=trust_hash, snapshot=snapshot, target=merged,
                           settings_hash=digest(self.store.settings(project)),
                           runtime={str(c.id): digest({key: c.attrs.get(key) for key in ('Image', 'Config', 'HostConfig', 'Mounts', 'NetworkSettings')}) for c in members},
                           versions={name: {'source': [str(c.attrs.get('Image') or '') for c in members
                                                     if ((c.attrs.get('Config') or {}).get('Labels') or {}).get(COMPOSE_SERVICE_LABEL) == name],
                                            'target': str(model.get('image') or '')} for name, model in (merged or {}).get('services', {}).items()})
            try:
                self.verify_profile_evidence(trust, folder, snapshot['model'], merged, payload['versions'])
            except ComposeBlocked:
                payload['blockers'].append('compatibility_unverified')
            self.store.transition(operation, 'PLAN_READY', payload=payload)
            blockers, checks = self.preflight(project, config, snapshot, merged, trust, self.store.settings(project), members, all_containers)
            blockers.extend(payload['blockers'])
            if review['conflicts']:
                blockers.append('config_conflict' if base is not None else 'base_missing')
            if review['review_required']:
                blockers.append('sensitive_change_review')
            if dry_run:
                checks.append('dry_run_no_changes')
            payload.update(blockers=sorted(set(blockers)), checks=checks)
            if blockers:
                self.store.transition(operation, 'BLOCKED', 'preflight_blocked', payload=payload)
                for code in payload['blockers']:
                    self.event(project, operation, 'blocked', 'warning', code)
            else:
                self.store.transition(operation, 'CONFIG_VALIDATED', payload=payload)
                payload['backup'] = {'adapter': 'stateless-v1', 'data_backup': 'not_applicable',
                                     'reason': 'no_persistent_mounts_in_reviewed_project', 'production_restore': False}
                self.store.transition(operation, 'BACKUP_VERIFIED', payload=payload)
                self.store.transition(operation, 'MIGRATION_PRECHECK', 'stateless_profile')
                self.store.transition(operation, 'READY', payload=payload)
                self.event(project, operation, 'approval', 'info', 'approval_required')
        except ComposeBlocked as exc:
            payload['blockers'] = [str(exc)]
            self.store.transition(operation, 'BLOCKED', str(exc), payload=payload)
            self.event(project, operation, 'blocked', 'warning', str(exc))
        except Exception:
            payload['blockers'] = ['analysis_failed']
            self.store.transition(operation, 'FAILED', 'analysis_failed', payload=payload)
            self.event(project, operation, 'failed', 'error', 'analysis_failed')
        finally:
            self.store.release(operation)
        return self.store.get(operation)

    def approve(self, operation):
        current = self.store.get(operation, public=False)
        payload = current['payload']
        if current['state'] != 'READY' or payload.get('dry_run'):
            raise ComposeBlocked('state_invalid')
        trust, _folder, trust_hash = self.trust(current['project'])
        if trust_hash != payload['trust_hash'] or digest(self.store.settings(current['project'])) != payload['settings_hash']:
            raise ComposeBlocked('files_changed')
        payload['approved'] = True
        payload['approved_at'] = time.time()
        self.store.transition(operation, 'READY', 'admin_approved', payload=payload, expected={'READY'})
        return self.store.get(operation)

    def cancel(self, operation):
        self.store.transition(operation, 'CANCELLED', 'cancelled', expected=set(STAGES[:7]) | {'READY'})
        return self.store.get(operation)

    def check_backup(self, project):
        self.require_project(project)
        operation = self.store.create(project)
        payload = {'checks': [], 'blockers': [], 'action': 'backup', 'deployed': False}
        try:
            self.store.transition(operation, 'ANALYZING', 'backup_check')
            trust, _folder, _hash = self.trust(project)
            cfg = trust.get('backup') or {}
            if cfg.get('adapter') != 'sqlite-online-v1':
                raise ComposeBlocked('backup_adapter_unavailable')
            approved_root = Path(trust.get('root', ''))
            service = self.service_factory()
            if not service._path_is_under(approved_root, service.compose_roots):
                raise ComposeBlocked('path_unsafe')
            payload['backup'] = SQLiteBackup.verify(approved_root, cfg.get('file', ''), self.root / 'backups' / operation)
            payload['checks'] = ['sqlite_online_snapshot', 'isolated_restore', 'sqlite_integrity_check']
            # This is a backup verification operation, never an update approval.
            self.store.transition(operation, 'COMPLETED', 'backup_verified', payload=payload)
            self.event(project, operation, 'backup', 'success', 'backup_verified')
        except ComposeBlocked as exc:
            payload['blockers'] = [str(exc)]
            self.store.transition(operation, 'BLOCKED', str(exc), payload=payload)
            self.event(project, operation, 'backup', 'warning', str(exc))
        finally:
            self.store.release(operation)
        return self.store.get(operation)

    def _verify_current(self, operation, service):
        project, payload = operation['project'], operation['payload']
        trust, folder, trust_hash = self.trust(project)
        if trust_hash != payload['trust_hash'] or digest(self.store.settings(project)) != payload['settings_hash']:
            raise ComposeBlocked('files_changed')
        # Reverify pinned input models too (not just the approval manifest).
        self.source_models(trust, folder)
        self.verify_profile_evidence(trust, folder, payload['snapshot']['model'], payload['target'], payload['versions'])
        members, all_containers = self.members(project, service)
        runtime = {str(c.id): digest({key: c.attrs.get(key) for key in ('Image', 'Config', 'HostConfig', 'Mounts', 'NetworkSettings')}) for c in members}
        if runtime != payload['runtime']:
            raise ComposeBlocked('runtime_changed')
        config = self.config(project, trust, members)
        snapshot = config.snapshot()
        if snapshot != payload['snapshot']:
            raise ComposeBlocked('files_changed')
        blockers, _checks = self.preflight(project, config, snapshot, payload['target'], trust,
                                            self.store.settings(project), members, all_containers)
        if blockers:
            raise ComposeBlocked(blockers[0])
        for name, expected in payload['versions'].items():
            actual = [str(c.attrs.get('Image') or '') for c in members
                      if ((c.attrs.get('Config') or {}).get('Labels') or {}).get(COMPOSE_SERVICE_LABEL) == name]
            if actual != expected['source']:
                raise ComposeBlocked('runtime_changed')
        return trust, config, members

    def _health_and_application(self, project, service, trust, target, stage):
        members, _all = self.members(project, service)
        expected = target['services']
        by_name = {}
        for container in members:
            container.reload()
            name = ((container.attrs.get('Config') or {}).get('Labels') or {}).get(COMPOSE_SERVICE_LABEL)
            by_name.setdefault(name, []).append(container)
        if set(by_name) != set(expected) or any(len(v) != 1 for v in by_name.values()):
            raise ComposeBlocked('service_scope_changed')
        for name, containers in by_name.items():
            container = containers[0]
            image = service.client.images.get(expected[name]['image'])
            if container.attrs.get('Image') != image.id:
                raise ComposeBlocked('runtime_changed')
            state = container.attrs.get('State') or {}
            if state.get('Status') != 'running' or (state.get('Health') or {}).get('Status') != 'healthy':
                raise ComposeBlocked('health_failed')
            if stage == 'application':
                probe = trust['profile']['services'][name]['application_check']
                # Fixed adapter, no shell, redirects, proxy, external scripts or
                # credentials; response bytes are compared and never persisted.
                command = ['curl', '--noproxy', '*', '--fail', '--silent', '--max-time', '5', '--max-filesize', '65536',
                           '--proto', '=http', f"http://127.0.0.1:{probe['port']}{probe['path']}"]
                exit_code, output = container.exec_run(command, user='65534', privileged=False)
                if exit_code != 0 or not isinstance(output, bytes) or len(output) > 65536 or digest(output) != probe['body_sha256']:
                    raise ComposeBlocked('application_check_failed')

    def execute(self, operation_id, progress=lambda _message: None, *, automatic=False):
        operation = self.store.get(operation_id, public=False)
        payload, project = operation['payload'], operation['project']
        settings = self.store.settings(project)
        if operation['state'] != 'READY' or payload.get('dry_run'):
            raise ComposeBlocked('state_invalid')
        if automatic:
            if settings['mode'] != 'conditional' or settings['automation'] != 'conditional':
                raise ComposeBlocked('consent_required')
        elif not payload.get('approved') or settings['mode'] not in ('manual', 'conditional'):
            raise ComposeBlocked('consent_required')
        if time.time() - operation['updated'] > 1800:
            raise ComposeBlocked('plan_expired')
        self.store.acquire(operation_id, project)
        receipt, mutated, config, writer, write_attempted = None, False, None, None, False
        try:
            if self.store.requires_intervention():
                raise ComposeBlocked('compose_admin_intervention')
            service = self.service_factory()
            trust, config, members = self._verify_current(operation, service)
            # Verify rollback's application test against the known old version.
            self._health_and_application(project, service, trust, payload['snapshot']['model'], 'application')
            # Pull exact digests and check actual image platform before applying.
            info = service.client.info()
            architecture = {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(info.get('Architecture'), info.get('Architecture'))
            if info.get('OSType') != 'linux' or architecture not in ('amd64', 'arm64'):
                raise ComposeBlocked('platform_unsupported')
            for name, model in payload['target']['services'].items():
                progress('PREPARING: ' + name)
                platform = model.get('platform') or 'linux/' + architecture
                if platform != 'linux/' + architecture:
                    raise ComposeBlocked('platform_unsupported')
                service._pull_image_with_retry(model['image'], platform=platform)
                image = service.client.images.get(model['image'])
                if image.attrs.get('Os') != 'linux' or image.attrs.get('Architecture') != architecture:
                    raise ComposeBlocked('platform_unsupported')
                if image.attrs.get('Config', {}).get('Volumes'):
                    raise ComposeBlocked('data_policy_required')
                old_image = service.client.images.get(payload['versions'][name]['source'][0])
                if old_image.attrs.get('Config', {}).get('Volumes'):
                    raise ComposeBlocked('data_policy_required')
                if old_image.tag('dcc-safe-compose-rollback', tag=operation_id + '-' + name) is not True:
                    raise ComposeBlocked('rollback_image_unavailable')
            # Recheck after all slow network operations, before the first write.
            trust, config, members = self._verify_current(operation, service)
            folder = self.root / 'operations' / operation_id
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            private_json(folder / 'original-model.json', payload['snapshot']['model'])
            candidate = folder / 'candidate.json'
            private_json(candidate, payload['target'])
            # Standalone resolved model is not used to deploy: this comparison
            # proves the generated image-only override has Compose semantics.
            override = {'services': {name: {'image': model['image']} for name, model in payload['target']['services'].items()}}
            private_json(folder / 'override.json', override)
            proposed_files = (*config.files[:-1], folder / 'override.json')
            if config.model(files=proposed_files) != payload['target']:
                raise ComposeBlocked('effective_model_mismatch')
            config.run(['config', '--quiet'], files=proposed_files)
            writer = ControlledWriter(config.root, [trust['write']['file']], folder / 'config-backup')
            self.store.transition(operation_id, 'APPLYING', 'apply_started', expected={'READY'})
            self.event(project, operation_id, 'started', 'running', 'apply_started')
            progress('APPLYING')
            # Persist rollback intent before touching either config or Docker.
            payload['override_before'] = read_bytes(config.root, trust['write']['file']).decode('utf-8')
            payload['override_after_hash'] = digest(json.dumps(override, ensure_ascii=False, indent=2).encode('utf-8'))
            self.store.transition(operation_id, 'APPLYING', 'write_intent', payload=payload)
            write_attempted = True
            receipt = writer.replace(trust['write']['file'], json.dumps(override, ensure_ascii=False, indent=2).encode('utf-8'),
                                     payload['snapshot']['hashes'][str(config.files[-1])])
            payload['write_receipt'] = receipt
            self.store.transition(operation_id, 'APPLYING', 'config_written', payload=payload)
            if config.model() != payload['target']:
                raise ComposeBlocked('effective_model_mismatch')
            mutated = True  # Command timeout/partial project replacement is uncertain.
            config.run(['up', '--detach', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', str(service.wait_seconds),
                        *payload['target']['services']], timeout=service.wait_seconds + 90)
            self.store.transition(operation_id, 'HEALTH_CHECK', 'health_check')
            self.event(project, operation_id, 'progress', 'running', 'health_check')
            progress('HEALTH_CHECK')
            self._health_and_application(project, service, trust, payload['target'], 'health')
            self.store.transition(operation_id, 'APPLICATION_CHECK', 'application_check')
            self.event(project, operation_id, 'progress', 'running', 'application_check')
            progress('APPLICATION_CHECK')
            self._health_and_application(project, service, trust, payload['target'], 'application')
            actual = config.snapshot()
            expected_hashes = {**payload['snapshot']['hashes'], str(config.files[-1]): receipt['after']}
            if (actual['model'] != payload['target'] or actual['hashes'] != expected_hashes
                    or actual['absent'] != payload['snapshot']['absent']):
                raise ComposeBlocked('files_changed')
            # Keep copies and pinned rollback images; never prune on failure/success.
            payload['deployed'] = True
            self.store.transition(operation_id, 'COMPLETED', 'completed', payload=payload)
            self.event(project, operation_id, 'completed', 'success', 'completed')
        except Exception as exc:
            code = str(exc) if isinstance(exc, ComposeBlocked) else 'deployment_failed'
            payload['blockers'] = [code]
            if mutated:
                self.store.transition(operation_id, 'ROLLBACK_PENDING', code, payload=payload)
                self.event(project, operation_id, 'rollback_started', 'running', 'rollback_started')
                try:
                    self.store.transition(operation_id, 'ROLLING_BACK', 'rollback_started')
                    progress('ROLLING_BACK')
                    # Only this adapter's verified stateless projects reach here.
                    rollback = copy.deepcopy(payload['snapshot']['model'])
                    # Original image references are required to be digest pinned.
                    # Restore the existing override before Compose so labels
                    # still identify the original, approved set of files.
                    writer.undo(receipt)
                    if config.snapshot() != payload['snapshot']:
                        raise ComposeBlocked('files_changed')
                    for name in rollback['services']:
                        if service.client.images.get(rollback['services'][name]['image']).id != payload['versions'][name]['source'][0]:
                            raise ComposeBlocked('rollback_image_unavailable')
                    config.run(['config', '--quiet'])
                    config.run(['up', '--detach', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', str(service.wait_seconds),
                                *rollback['services']], timeout=service.wait_seconds + 90)
                    self._health_and_application(project, service, trust, rollback, 'application')
                    self.store.transition(operation_id, 'RESTORED', 'stateless_images_restored', payload=payload)
                    self.event(project, operation_id, 'restored', 'warning', 'stateless_images_restored')
                except Exception:
                    self.store.transition(operation_id, 'MANUAL_INTERVENTION', 'rollback_failed', payload=payload)
                    self.event(project, operation_id, 'rollback_failed', 'error', 'rollback_failed')
            elif receipt:
                try:
                    writer.undo(receipt)
                    self.store.transition(operation_id, 'FAILED', code, payload=payload)
                except Exception:
                    self.store.transition(operation_id, 'MANUAL_INTERVENTION', 'config_restore_failed', payload=payload)
                    self.event(project, operation_id, 'intervention', 'error', 'config_restore_failed')
            elif write_attempted:
                self.store.transition(operation_id, 'MANUAL_INTERVENTION', 'write_result_uncertain', payload=payload)
                self.event(project, operation_id, 'intervention', 'error', 'write_result_uncertain')
            else:
                self.store.transition(operation_id, 'BLOCKED', code, payload=payload)
            self.event(project, operation_id, 'failed', 'error', code)
        finally:
            current = self.store.get(operation_id)
            if current['state'] in TERMINAL - {'MANUAL_INTERVENTION'}:
                self.store.release(operation_id)
        return self.store.get(operation_id)

    def run_due(self, now, progress):
        results = []
        for project in self.store.due(now):
            config = self.store.claim_schedule(project, now)
            if not config:
                continue
            try:
                self.discover(progress, check_updates=True)
                if project not in self.catalog:
                    raise ComposeBlocked('project_unknown')
                if config['automation'] == 'check':
                    if any(s['update_available'] for s in self.catalog[project]['services']):
                        self.event(project, '', 'available', 'info', 'update_available')
                    self.store.finish_schedule(project, 'success', 'checked')
                    continue
                operation = self.analyze(project, progress)
                if config['automation'] == 'conditional' and operation['state'] == 'READY':
                    operation = self.execute(operation['id'], progress, automatic=True)
                results.append(operation)
                self.store.finish_schedule(project, operation['state'], 'completed')
            except Exception as exc:
                code = str(exc) if isinstance(exc, ComposeBlocked) else 'analysis_failed'
                self.store.finish_schedule(project, 'error', code)
                self.event(project, '', 'failed', 'error', code)
        return {'compose_operations': results}
