"""Reviewed, operator-run Windows workflow for Cinema Hub's SQLite volume.

The web container cannot resolve Windows Compose paths. It exports a local
PowerShell workflow instead of granting write mounts or bypassing Compose gates.
"""
import base64
import json
import re
from pathlib import Path, PureWindowsPath

from compose_config import ComposeBlocked
from updater import COMPOSE_CONFIG_FILES_LABEL, COMPOSE_PROJECT_LABEL, COMPOSE_SERVICE_LABEL, COMPOSE_WORKING_DIR_LABEL, normalized_repository

REPOSITORY = 'ghcr.io/hattimon/cinema-hub'
RESOURCES = Path(__file__).parent / 'windows'


def eligible(members):
    if len(members) != 1:
        return False
    attrs = members[0].attrs
    labels = (attrs.get('Config') or {}).get('Labels') or {}
    return (normalized_repository(str((attrs.get('Config') or {}).get('Image') or '')) == REPOSITORY
            and bool(re.match(r'^[A-Za-z]:[\\/]', str(labels.get(COMPOSE_WORKING_DIR_LABEL) or ''))))


def windows_path(value):
    if (not isinstance(value, str) or len(value) > 1000 or any(c in value for c in '\r\n\0')
            or not re.match(r'^[A-Za-z]:[\\/]', value) or '..' in PureWindowsPath(value).parts):
        raise ComposeBlocked('path_unsafe')
    return str(PureWindowsPath(value))


def export_script(service, project):
    containers = service.client.containers.list(all=True, ignore_removed=True)
    members = [c for c in containers if ((c.attrs.get('Config') or {}).get('Labels') or {}).get(COMPOSE_PROJECT_LABEL) == project]
    if not eligible(members):
        raise ComposeBlocked('windows_cinema_scope')
    container = members[0]
    labels = container.attrs['Config']['Labels']
    root = windows_path(labels[COMPOSE_WORKING_DIR_LABEL])
    files = [windows_path(p.strip()) for p in str(labels.get(COMPOSE_CONFIG_FILES_LABEL) or '').split(',') if p.strip()]
    if not files or len(files) > 8 or len(set(files)) != len(files):
        raise ComposeBlocked('files_missing')
    mounts = container.attrs.get('Mounts') or []
    if (len(mounts) != 1 or mounts[0].get('Type') != 'volume' or mounts[0].get('Destination') != '/data'
            or not mounts[0].get('RW') or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}', str(mounts[0].get('Name') or ''))):
        raise ComposeBlocked('data_policy_required')
    volume = mounts[0]['Name']
    if any(c.id != container.id and any(m.get('Name') == volume for m in c.attrs.get('Mounts') or []) for c in containers):
        raise ComposeBlocked('external_dependency')
    local = service._local_image(container)
    if local is None:
        raise ComposeBlocked('local_image_unavailable')
    current, error = service._named_local_image(container, local)
    if error or normalized_repository(current) != REPOSITORY:
        raise ComposeBlocked('image_check_failed')
    apps, catalog_error = service._catalog()
    if catalog_error:
        raise ComposeBlocked('windows_catalog_unavailable')
    candidate = service._catalog_candidate(current, apps)
    target = candidate.target_image if candidate and candidate.available else current
    if normalized_repository(target) != REPOSITORY or '@' in target:
        raise ComposeBlocked('windows_target_unavailable')
    distribution = service.client.api.inspect_distribution(target)
    checksum = str((distribution.get('Descriptor') or {}).get('digest') or '')
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', checksum):
        raise ComposeBlocked('windows_target_unavailable')
    plan = {'schema': 1, 'project': project, 'service': labels.get(COMPOSE_SERVICE_LABEL), 'root': root,
            'files': files, 'container_id': str(container.id), 'source_image_id': str(container.attrs.get('Image') or ''),
            'volume': volume, 'target_tag': target, 'target_image': REPOSITORY + '@' + checksum}
    for field in ('project', 'service'):
        if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{0,127}', str(plan[field] or '')):
            raise ComposeBlocked('windows_cinema_scope')
    if not re.fullmatch(r'[a-f0-9]{64}', plan['container_id']) or not re.fullmatch(r'sha256:[a-f0-9]{64}', plan['source_image_id']):
        raise ComposeBlocked('runtime_changed')
    encode = lambda value: base64.b64encode(value).decode('ascii')
    template = (RESOURCES / 'cinema-update.ps1').read_text(encoding='utf-8')
    return template.replace('__DCC_PLAN_BASE64__', encode(json.dumps(plan, ensure_ascii=False).encode('utf-8'))).replace(
        '__DCC_SQLITE_BASE64__', encode((RESOURCES / 'cinema-sqlite.mjs').read_bytes()))
