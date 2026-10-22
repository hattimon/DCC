"""Bounded local event history, independent of future notification transports."""

from __future__ import annotations

import copy
import json
import logging
import math
import os
import secrets
import threading
import time
from pathlib import Path


class ReportStore:
    def __init__(self, path: Path, on_event=None) -> None:
        self.path = path
        self.lock = threading.RLock()
        self.on_event = on_event
        self.entries = []
        self.storage_error = False
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(data, list) or any(
                    not isinstance(item, dict) or not isinstance(item.get('id'), str)
                    or type(item.get('occurred_at')) not in {int, float} or not math.isfinite(item['occurred_at'])
                    or item.get('status') not in {'success','warning','error','info','running'}
                    or not isinstance(item.get('kind'), str) or not isinstance(item.get('details'), list)
                    for item in data):
                    raise ValueError('Invalid reports')
                self.entries = data[:200]
        except (OSError, ValueError, TypeError):
            self.storage_error = True

    def _write(self):
        if self.storage_error:
            return
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.entries, ensure_ascii=False, indent=2), encoding='utf-8')
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(self.path)

    def append(self, kind, status, *, message='', details=None, updated=0, scanned=0, **fields):
        event = {'id': secrets.token_urlsafe(12), 'version': 1, 'occurred_at': time.time(),
                 'kind': kind, 'status': status, 'message': str(message)[:3000],
                 'details': (details or [])[:40], 'issues': len(details or []), 'updated': updated, 'scanned': scanned,
                 'delivery': {}, **fields}
        with self.lock:
            self.entries.insert(0, event)
            self.entries = self.entries[:200]
            try:
                self._write()
            except OSError:
                self.storage_error = True
                logging.getLogger(__name__).warning('Could not persist updater reports.')
        if self.on_event:
            self.on_event(copy.deepcopy(event))
        return event['id']

    def snapshot(self, page=1, issues_only=False):
        with self.lock:
            entries = [item for item in self.entries if not issues_only or item.get('status') in {'error','warning'}]
            pages = max(1, (len(entries) + 9) // 10)
            page = min(max(1, page), pages)
            return {'entries': copy.deepcopy(entries[(page-1)*10:page*10]), 'page': page,
                    'pages': pages, 'total': len(entries), 'storage_error': self.storage_error}

    def delivery(self, event_id, channel, status, message=''):
        with self.lock:
            for event in self.entries:
                if event['id'] == event_id:
                    event.setdefault('delivery', {})[channel] = {'status': status, 'message': message, 'at': time.time()}
                    try:
                        self._write()
                    except OSError:
                        self.storage_error = True
                    return not self.storage_error
        return False

    def panel_started(self, image):
        with self.lock:
            if any(item.get('kind') == 'panel_update' and item.get('status') == 'running' and item.get('image') == image for item in self.entries):
                return
        self.append('panel_update', 'running', message='Trwa aktualizacja panelu.', image=image)

    def resolve_panel(self, image=None, failed_message=None):
        changed = []
        with self.lock:
            for item in self.entries:
                if item.get('kind') != 'panel_update' or item.get('status') != 'running':
                    continue
                if image and item.get('image') == image:
                    item.update(status='success', message='Panel został zaktualizowany.', finished_at=time.time())
                elif failed_message or time.time() - item['occurred_at'] > 600:
                    item.update(status='error', message=failed_message or 'Panel nie potwierdził aktualizacji w terminie.', finished_at=time.time())
                else:
                    continue
                changed.append(copy.deepcopy(item))
            if changed:
                try:
                    self._write()
                except OSError:
                    self.storage_error = True
        if self.on_event:
            for item in changed:
                self.on_event(item)

    def record_job(self, job):
        kind, result = job.get('kind'), job.get('results') or {}
        if isinstance(result, dict) and result.get('waiting'):
            return
        if job.get('status') == 'error':
            self.append(kind, 'error', message=job.get('progress', ''))
            return
        if kind == 'self_update_check':
            if isinstance(result, dict):
                self.resolve_panel(result.get('current_image_id'))
                if not result.get('checked'):
                    self.append(kind, 'warning', message=result.get('message', ''))
            return
        if isinstance(result, dict) and result.get('started'):
            if kind == 'schedule':
                self.append(kind, 'info', message='Harmonogram oczekuje na aktualizację panelu.')
            return
        outcomes = result.get('updates', []) if isinstance(result, dict) else []
        containers = result.get('containers', []) if isinstance(result, dict) else result if isinstance(result, list) else []
        failures = [{'name': item.get('name', ''), 'result': str(item.get('result', ''))[:1000]} for item in outcomes if not item.get('ok')]
        issues = [{'name': item.get('name', ''), 'result': str(item.get('auto_update_reason') or item.get('message', ''))[:1000]} for item in containers
                  if not item.get('is_panel') and (item.get('check_error') or (item.get('update_available') and not item.get('supported')))]
        scan_operation = kind == 'scan' or (kind == 'auto_update' and not outcomes) or (kind == 'schedule' and isinstance(result, dict) and result.get('action') == 'scan')
        if not scan_operation:
            issues = []  # Unselected services must not turn a successful update into an alert.
        if kind == 'auto_update' and not outcomes and not containers:
            return
        if (kind == 'auto_update' and not outcomes) or (kind == 'schedule' and isinstance(result, dict) and result.get('action') == 'scan'):
            kind = 'schedule_scan' if kind == 'schedule' else 'scan'
        if kind == 'self_update':
            if isinstance(result, dict) and not result.get('update_available') and result.get('checked'):
                return
            self.resolve_panel(failed_message=result.get('message', '') if isinstance(result, dict) else None)
        status = 'error' if failures or kind == 'self_update' or (isinstance(result, dict) and result.get('ok') is False) else 'warning' if issues else 'success'
        self.append(kind, status, message=result.get('message', '') if isinstance(result, dict) else '',
                    details=failures or issues, updated=sum(bool(item.get('ok')) for item in outcomes), scanned=len(containers))
