"""Compose-native normalization, conservative semantic review and bounded writes.

No remote retrieval, YAML constructors, shell commands or host helper containers.
Resolved models (including secrets) are private; public diffs contain paths only.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path


MAX_FILE = 4 * 1024 * 1024
SENSITIVE = {'environment', 'env_file', 'ports', 'volumes', 'secrets', 'configs',
             'networks', 'depends_on', 'command', 'entrypoint', 'healthcheck',
             'labels', 'build', 'deploy', 'profiles', 'restart', 'user', 'privileged',
             'cap_add', 'devices', 'network_mode', 'post_start', 'pre_stop'}


class ComposeBlocked(ValueError):
    """Only stable diagnostic codes; never include subprocess output or data."""


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.dcc-', dir=path.parent)
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def safe_path(root, value, *, directory=False, max_size=MAX_FILE):
    """Reject dot traversal and every symlink/junction, even inside the root."""
    root, raw = Path(root), Path(value)
    if '..' in raw.parts or '..' in root.parts or not root.is_absolute():
        raise ComposeBlocked('path_unsafe')
    path = raw if raw.is_absolute() else root / raw
    try:
        path.relative_to(root)
        for item in (root, *root.parents, path, *path.parents):
            if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
                raise ComposeBlocked('path_unsafe')
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
        if (not resolved.is_dir() if directory else not resolved.is_file()):
            raise ComposeBlocked('files_missing')
        if not directory and ((max_size is not None and resolved.stat().st_size > max_size) or resolved.stat().st_nlink != 1):
            raise ComposeBlocked('path_unsafe')
        return resolved
    except (OSError, ValueError, RuntimeError):
        raise ComposeBlocked('path_unsafe') from None


def read_bytes(root, value):
    path = safe_path(root, value)
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        before = os.fstat(fd)
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(MAX_FILE + 1)
        after = os.fstat(fd)
        if (len(raw) > MAX_FILE or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or (before.st_ino, before.st_dev, before.st_mtime_ns, before.st_size)
                != (after.st_ino, after.st_dev, after.st_mtime_ns, after.st_size)
                or path.stat().st_ino != after.st_ino):
            raise ComposeBlocked('files_changed')
        return raw
    finally:
        os.close(fd)


class ComposeConfig:
    def __init__(self, project, root, files, binary='docker-compose', runner=subprocess.run, profiles=()):
        if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{0,127}', project):
            raise ComposeBlocked('project_unknown')
        self.project, self.root = project, Path(root)
        safe_path(self.root, self.root, directory=True)
        self.files = tuple(safe_path(self.root, path) for path in files)
        if not self.files or len(self.files) > 16:
            raise ComposeBlocked('files_missing')
        self.binary, self.runner, self.profiles = binary, runner, tuple(profiles)
        if any(not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}', name) for name in self.profiles):
            raise ComposeBlocked('profiles_unknown')

    def run(self, arguments, *, files=None, timeout=45):
        args = [self.binary, '--project-name', self.project, '--project-directory', str(self.root)]
        for name in self.profiles:
            args.extend(('--profile', name))
        for path in self.files if files is None else files:
            args.extend(('--file', str(path)))
        # Do not inherit arbitrary COMPOSE_ variables or interpolate updater secrets.
        allowed = ('PATH', 'HOME', 'USERPROFILE', 'SYSTEMROOT', 'TEMP', 'TMP', 'DOCKER_HOST',
                   'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH', 'DOCKER_CONFIG', 'XDG_RUNTIME_DIR')
        env = {key: os.environ[key] for key in allowed if key in os.environ}
        env.update(COMPOSE_DISABLE_ENV_FILE='0', COMPOSE_MENU='0', COMPOSE_ANSI='never')
        try:
            result = self.runner(args + arguments, cwd=str(self.root), env=env, check=False,
                                 capture_output=True, text=True, encoding='utf-8', timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            raise ComposeBlocked('compose_command_failed') from None
        if result.returncode or (arguments[0] == 'config' and result.stderr.strip()):
            # Warnings (missing variables/includes/unsupported fields) fail closed.
            raise ComposeBlocked('compose_validation_failed')
        return result.stdout

    def model(self, files=None, *, raw=False):
        args = ['config', '--format', 'json']
        if raw:
            args += ['--no-env-resolution', '--no-interpolate']
        try:
            model = json.loads(self.run(args, files=files))
        except (TypeError, json.JSONDecodeError):
            raise ComposeBlocked('compose_validation_failed') from None
        if not isinstance(model, dict) or not isinstance(model.get('services'), dict) or not model['services']:
            raise ComposeBlocked('compose_validation_failed')
        return model

    def snapshot(self):
        """Fingerprint explicit files, optional .env and all env/config/secret inputs.

        include/extends are rejected until their recursive input closure is known.
        Profiles are recorded but require a profile-aware deployment adapter.
        """
        paths = set(self.files)
        env = self.root / '.env'
        absent = []
        if env.exists() or env.is_symlink():
            paths.add(safe_path(self.root, env))
            if re.search(r'(?m)^\s*(?:export\s+)?(?:COMPOSE_|DOCKER_)[A-Z0-9_]*\s*=', read_bytes(self.root, env).decode('utf-8-sig')):
                raise ComposeBlocked('input_closure_unknown')
        else:
            absent.append(str(env))
        raw_model = self.model(raw=True)
        # Compose may expand include/extends before emitting JSON. Inspect all
        # source files too, so their hidden transitive inputs cannot evade CAS.
        for path in self.files:
            text = read_bytes(self.root, path).decode('utf-8-sig')
            if re.search(r'(?m)^\s*(?:["\x27]?(?:include|extends)["\x27]?)\s*:', text) or re.search(r'"(?:include|extends)"\s*:', text):
                raise ComposeBlocked('input_closure_unknown')
        if raw_model.get('include') or any(s.get('extends') for s in raw_model['services'].values()):
            raise ComposeBlocked('input_closure_unknown')
        for service in raw_model['services'].values():
            env_files = service.get('env_file') or []
            if isinstance(env_files, (str, dict)):
                env_files = [env_files]
            for entry in env_files:
                path = entry.get('path') if isinstance(entry, dict) else entry
                if not path or '$' in str(path):
                    raise ComposeBlocked('input_closure_unknown')
                candidate = Path(path) if Path(path).is_absolute() else self.root / path
                if isinstance(entry, dict) and entry.get('required') is False and not candidate.exists():
                    absent.append(str(candidate))
                else:
                    paths.add(safe_path(self.root, candidate))
        for section in ('secrets', 'configs'):
            for resource in (raw_model.get(section) or {}).values():
                if resource.get('environment') or resource.get('content') is not None:
                    raise ComposeBlocked('input_closure_unknown')
                if resource.get('file'):
                    paths.add(safe_path(self.root, resource['file']))
        hashes = {str(path): digest(read_bytes(self.root, path)) for path in sorted(paths)}
        model = self.model()
        self.run(['config', '--quiet'])
        service_hashes = {}
        for line in self.run(['config', '--hash', '*']).splitlines():
            parts = line.split()
            if len(parts) != 2 or not re.fullmatch(r'[0-9a-f]{64}', parts[1]):
                raise ComposeBlocked('compose_validation_failed')
            service_hashes[parts[0]] = parts[1]
        if set(service_hashes) != set(model['services']):
            raise ComposeBlocked('input_closure_unknown')
        if hashes != {str(path): digest(read_bytes(self.root, path)) for path in sorted(paths)}:
            raise ComposeBlocked('files_changed')
        if any(Path(path).exists() or Path(path).is_symlink() for path in absent):
            raise ComposeBlocked('files_changed')
        return {'hashes': hashes, 'absent': absent, 'model': model, 'model_hash': digest(model),
                'service_hashes': service_hashes, 'files': [str(path) for path in self.files], 'profiles': list(self.profiles)}


_MISSING = object()


def semantic_merge(base, local, upstream):
    """Three-way on CLI-normalized models, not a second Compose YAML merger.

    Maps recurse. Compose unique-resource lists are indexed using spec identities;
    command/entrypoint/healthcheck.test and other ordered lists stay atomic.
    Sensitive upstream changes always require explicit review even without a
    textual conflict. Missing BASE yields a two-way review, never an auto merge.
    Public changes intentionally omit ALL values (including command/label data).
    """
    changes, conflicts, reviews = [], [], []

    def public_path(path):
        # Environment/label names can themselves contain private data.
        for index, part in enumerate(path):
            if part in {'environment', 'labels', 'secrets', 'configs'}:
                return '.'.join(path[:index + 1])
        return '.'.join(path)

    def walk(b, l, u, path):
        if l == u or u == b:
            return copy.deepcopy(l) if l is not _MISSING else _MISSING
        field = public_path(path)
        sensitive = bool(set(path) & SENSITIVE)
        if all(isinstance(value, dict) for value in (b, l, u)):
            result = {}
            for key in sorted(set(b) | set(l) | set(u)):
                item = walk(b.get(key, _MISSING), l.get(key, _MISSING), u.get(key, _MISSING), (*path, key))
                if item is not _MISSING:
                    result[key] = item
            return result
        if l == b:
            changes.append({'path': field, 'action': 'removed' if u is _MISSING else 'added' if b is _MISSING else 'changed'})
            if sensitive:
                reviews.append(field)
            return copy.deepcopy(u) if u is not _MISSING else _MISSING
        unique = path[-1] if path else ''
        if unique in {'volumes', 'ports', 'secrets', 'configs'} and all(isinstance(v, list) for v in (b, l, u)):
            def index(items):
                result = {}
                for item in items:
                    if not isinstance(item, dict):
                        raise ValueError()
                    key = (item.get('host_ip', ''), item.get('target'), item.get('published'), item.get('protocol', 'tcp')) if unique == 'ports' else item.get('target')
                    if not key or key in result:
                        raise ValueError()
                    result[key] = item
                return result
            try:
                bi, li, ui = index(b), index(l), index(u)
                result = []
                for key in dict.fromkeys([*li, *ui, *bi]):
                    item = walk(bi.get(key, _MISSING), li.get(key, _MISSING), ui.get(key, _MISSING), path)
                    if item is not _MISSING:
                        result.append(item)
                if result != l and sensitive:
                    reviews.append(field)
                return result
            except ValueError:
                pass
        conflicts.append(field)
        return copy.deepcopy(l) if l is not _MISSING else _MISSING

    if base is None:
        # Deliberately no merged output without provenance.
        return {'merged': None, 'changes': [], 'conflicts': ['BASE'], 'review_required': ['two_way_review'], 'two_way': True,
                'local_hash': digest(local), 'upstream_hash': digest(upstream)}
    merged = walk(base, local, upstream, ())
    return {'merged': merged, 'changes': changes, 'conflicts': sorted(set(conflicts)),
            'review_required': sorted(set(reviews)), 'two_way': False}


class ControlledWriter:
    """Single-file CAS replacement under a locally installed exact file grant.

    The parent is opened once with O_NOFOLLOW; dir_fd operations prevent parent
    substitution on Linux. This adapter deliberately fails closed on Windows.
    Grants cannot be created through the web API. Copies contain secrets and
    belong in the private updater data volume. No multi-file atomicity claim.
    """
    def __init__(self, root, approved_files, backup_dir):
        self.root, self.approved = Path(root), set(approved_files)
        self.backup_dir = Path(backup_dir)

    def replace(self, relative, content, expected_hash):
        if os.name != 'posix' or not hasattr(os, 'O_NOFOLLOW'):
            raise ComposeBlocked('write_adapter_unavailable')
        if relative not in self.approved or not isinstance(content, bytes) or len(content) > MAX_FILE:
            raise ComposeBlocked('write_not_granted')
        target = safe_path(self.root, relative)
        original = read_bytes(self.root, relative)
        if digest(original) != expected_hash:
            raise ComposeBlocked('files_changed')
        self.backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = self.backup_dir / (expected_hash + '.original')
        if not backup.exists():
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(original)
                stream.flush()
                os.fsync(stream.fileno())
        elif digest(backup.read_bytes()) != expected_hash:
            raise ComposeBlocked('backup_unverified')
        # Walk from / using held directory descriptors. Checking resolve() then
        # opening a deep absolute path would still allow an ancestor swap.
        directory = os.open(target.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for component in target.parent.parts[1:]:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
        except Exception:
            os.close(directory)
            raise ComposeBlocked('path_unsafe') from None
        temporary = '.dcc-' + os.urandom(16).hex()
        try:
            old = os.stat(target.name, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(old.st_mode) or old.st_nlink != 1:
                raise ComposeBlocked('path_unsafe')
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
                os.fchown(stream.fileno(), old.st_uid, old.st_gid)
                os.fchmod(stream.fileno(), stat.S_IMODE(old.st_mode))
                stream.flush()
                os.fsync(stream.fileno())
            if digest(read_bytes(self.root, relative)) != expected_hash:
                raise ComposeBlocked('files_changed')
            current = os.stat(target.name, dir_fd=directory, follow_symlinks=False)
            if (current.st_ino, current.st_dev, current.st_mtime_ns) != (old.st_ino, old.st_dev, old.st_mtime_ns):
                raise ComposeBlocked('files_changed')
            parent = target.parent.stat()
            opened = os.fstat(directory)
            if (parent.st_ino, parent.st_dev) != (opened.st_ino, opened.st_dev):
                raise ComposeBlocked('path_unsafe')
            os.replace(temporary, target.name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.close(directory)
        return {'backup': str(backup), 'before': expected_hash, 'after': digest(content), 'file': relative}

    def undo(self, receipt):
        backup = Path(receipt['backup'])
        safe_path(self.backup_dir, backup)
        original = backup.read_bytes()
        if digest(original) != receipt['before']:
            raise ComposeBlocked('backup_unverified')
        return self.replace(receipt['file'], original, receipt['after'])
