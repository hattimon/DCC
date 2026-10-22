"""Opt-in error alerts. Secrets stay local; delivery never blocks Docker jobs."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import queue
import re
import smtplib
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from email.message import EmailMessage


DEFAULTS = {
    'enabled': False, 'scan_errors': False, 'language': 'en',
    'telegram': {'enabled': False, 'bot_token': '', 'chat_id': ''},
    'signal': {'enabled': False, 'url': '', 'number': '', 'recipients': '', 'bearer_token': ''},
    'whatsapp': {'enabled': False, 'access_token': '', 'phone_id': '', 'recipients': '',
                 'template': '', 'template_language': 'en_US', 'api_version': 'v25.0'},
    'email': {'enabled': False, 'host': '', 'port': '587', 'security': 'starttls',
              'username': '', 'password': '', 'sender': '', 'recipients': ''},
}
SECRETS = {'telegram': 'bot_token', 'signal': 'bearer_token', 'whatsapp': 'access_token', 'email': 'password'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def post_json(url, payload, headers=None):
    request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                     headers={'Content-Type': 'application/json', **(headers or {})}, method='POST')
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=10) as response:
            data = response.read(65536)
            return json.loads(data) if data else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'HTTP {exc.code}') from None
    except Exception as exc:
        raise RuntimeError(type(exc).__name__) from None


def recipients(value):
    return list(dict.fromkeys(part.strip() for part in re.split(r'[,;\s]+', value) if part.strip()))


def redact(text):
    text = re.sub(r'(?i)((?:password|token|secret|api[_-]?key)\s*[=:]\s*)[^\s,;]+', r'\1[redacted]', text)
    return re.sub(r'(https?://)[^/@\s]+:[^/@\s]+@', r'\1[redacted]@', text)


class NotificationService:
    def __init__(self, path: Path, reports, transport=post_json):
        self.path, self.reports, self.transport = path, reports, transport
        self.lock = threading.RLock()
        self.config = copy.deepcopy(DEFAULTS)
        self.storage_error = False
        self.events = queue.Queue(maxsize=50)
        self.stop = threading.Event()
        self.enabled_at = time.time()
        self.recent = {}
        try:
            if path.exists():
                payload = json.loads(path.read_text(encoding='utf-8'))
                self.config = self._validate(payload)
                self.enabled_at = float(payload.get('enabled_at', time.time()))
                if not math.isfinite(self.enabled_at):
                    raise ValueError('Invalid notification timestamp')
        except (OSError, ValueError, TypeError, KeyError):
            self.storage_error = True

    def _validate(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('Nieprawidłowe ustawienia powiadomień.')
        config = copy.deepcopy(DEFAULTS)
        for key in ('enabled', 'scan_errors'):
            value = payload.get(key, False)
            if not isinstance(value, bool):
                raise ValueError('Przełączniki powiadomień muszą mieć wartość true albo false.')
            config[key] = value
        config['language'] = payload.get('language', 'en')
        if config['language'] not in ('en', 'pl'):
            raise ValueError('Nieprawidłowy język powiadomień.')
        for channel, defaults in DEFAULTS.items():
            if channel not in SECRETS:
                continue
            values = payload.get(channel, {})
            if not isinstance(values, dict) or not isinstance(values.get('enabled', False), bool):
                raise ValueError('Nieprawidłowe ustawienia kanału powiadomień.')
            config[channel]['enabled'] = values.get('enabled', False)
            for key in defaults:
                if key == 'enabled':
                    continue
                value = values.get(key, defaults[key])
                if not isinstance(value, str) or len(value) > 2000 or any(char in value for char in '\r\0') or (key != 'recipients' and '\n' in value):
                    raise ValueError('Nieprawidłowe pole powiadomień.')
                config[channel][key] = value if key == 'password' else value.strip()
            active = config['enabled'] and config[channel]['enabled']
            if active:
                required = {'telegram': ('bot_token','chat_id'), 'signal': ('url','number','recipients'),
                            'whatsapp': ('access_token','phone_id','recipients','template','template_language','api_version'),
                            'email': ('host','port','security','sender','recipients')}[channel]
                if any(not config[channel][key] for key in required):
                    raise ValueError('Uzupełnij wymagane pola włączonego kanału powiadomień.')
                if channel == 'telegram' and (not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', config[channel]['bot_token']) or not re.fullmatch(r'-?[0-9]+|@[A-Za-z0-9_]+', config[channel]['chat_id'])):
                    raise ValueError('Nieprawidłowy token bota lub identyfikator czatu Telegram.')
                if channel == 'signal':
                    parsed = urllib.parse.urlsplit(config[channel]['url'])
                    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                        raise ValueError('Podaj adres HTTP/HTTPS zaufanej bramki Signal bez danych logowania w URL.')
                    if not re.fullmatch(r'\+?[0-9]{7,16}', config[channel]['number']):
                        raise ValueError('Podaj numer Signal z kodem kraju.')
                if channel in ('signal','whatsapp'):
                    numbers = recipients(config[channel]['recipients'])
                    if not numbers or len(numbers) > 10 or any(not re.fullmatch(r'\+?[0-9]{7,16}', number) for number in numbers):
                        raise ValueError('Podaj do 10 numerów odbiorców z kodem kraju.')
                if channel == 'whatsapp' and (not re.fullmatch(r'[0-9]+', config[channel]['phone_id']) or not re.fullmatch(r'v[0-9]+\.0', config[channel]['api_version']) or not re.fullmatch(r'[a-z0-9_]+', config[channel]['template']) or not re.fullmatch(r'[a-z]{2}(?:_[A-Z]{2})?', config[channel]['template_language'])):
                    raise ValueError('Nieprawidłowy identyfikator, wersja API lub szablon WhatsApp.')
                if channel == 'email':
                    values = config[channel]
                    addresses = recipients(values['recipients'])
                    if (not re.fullmatch(r'[A-Za-z0-9_.:-]+', values['host']) or not values['port'].isdigit()
                            or not 1 <= int(values['port']) <= 65535 or values['security'] not in ('starttls','tls')
                            or not 1 <= len(addresses) <= 10
                            or any(not re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+', address)
                                   for address in [values['sender'], *addresses])
                            or bool(values['username']) != bool(values['password'])):
                        raise ValueError('Nieprawidłowe ustawienia SMTP lub adres e-mail. Użyj TLS i do 10 odbiorców.')
        if config['enabled'] and not any(config[channel]['enabled'] for channel in SECRETS):
            raise ValueError('Włącz co najmniej jeden kanał powiadomień.')
        return config

    def public(self):
        with self.lock:
            config = copy.deepcopy(self.config)
        for channel, secret in SECRETS.items():
            config[channel]['secret_saved'] = bool(config[channel].pop(secret))
        return {**config, 'storage_error': self.storage_error}

    def save(self, payload):
        with self.lock:
            if self.storage_error:
                raise ValueError('Plik powiadomień jest uszkodzony; sprawdź go ręcznie.')
            merged = copy.deepcopy(payload)
            if not isinstance(merged, dict):
                raise ValueError('Nieprawidłowe ustawienia powiadomień.')
            for channel, secret in SECRETS.items():
                values = merged.setdefault(channel, {})
                if isinstance(values, dict):
                    if values.get('clear_secret') is True:
                        values[secret] = ''
                    elif not values.get(secret):
                        values[secret] = self.config[channel][secret]
            config = self._validate(merged)
            enabled_at = self.enabled_at if self.config['enabled'] else time.time()
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps({**config, 'enabled_at': enabled_at}, ensure_ascii=False, indent=2), encoding='utf-8')
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            temporary.replace(self.path)
            self.config, self.enabled_at = config, enabled_at
        return self.public()

    def enqueue(self, event):
        with self.lock:
            config = copy.deepcopy(self.config)
        if not config['enabled'] or self.storage_error or event.get('status') not in ('error','warning'):
            return
        if event.get('kind') in ('scan','self_update_check','schedule_scan') and not config['scan_errors']:
            return
        if event.get('occurred_at', 0) < self.enabled_at:
            return
        try:
            self.events.put_nowait(copy.deepcopy(event))
        except queue.Full:
            for channel in SECRETS:
                if config[channel]['enabled']:
                    self.reports.delivery(event['id'], channel, 'failed', 'Kolejka powiadomień jest pełna.')

    def format_message(self, event, language):
        from i18n import translate_text
        title = 'DCC Container Updater · błąd aktualizacji' if language == 'pl' else 'DCC Container Updater · update issue'
        lines = [title, time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(event['occurred_at']))]
        if event.get('message'):
            lines.append(translate_text(redact(event['message']), language)[:1000])
        for detail in event.get('details', [])[:5]:
            lines.append(f"{detail.get('name','')}: {translate_text(redact(detail.get('result','')), language)[:400]}")
        return '\n'.join(lines)[:3000]

    def send(self, channel, config, message):
        values = config[channel]
        if channel == 'email':
            mail = EmailMessage()
            mail['Subject'] = 'DCC Container Updater'
            mail['From'] = values['sender']
            mail['To'] = ', '.join(recipients(values['recipients']))
            mail.set_content(message)
            context = ssl.create_default_context()
            if values['security'] == 'tls':
                connection = smtplib.SMTP_SSL(values['host'], int(values['port']), timeout=10, context=context)
            else:
                connection = smtplib.SMTP(values['host'], int(values['port']), timeout=10)
            with connection as smtp:
                if values['security'] == 'starttls':
                    smtp.ehlo()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                if values['username']:
                    smtp.login(values['username'], values['password'])
                if smtp.send_message(mail):
                    raise RuntimeError('SMTP recipients rejected')
        elif channel == 'telegram':
            data = self.transport(f"https://api.telegram.org/bot{values['bot_token']}/sendMessage", {'chat_id': values['chat_id'], 'text': message, 'link_preview_options': {'is_disabled': True}})
            if data.get('ok') is not True:
                raise RuntimeError('Telegram API rejected the message')
        elif channel == 'signal':
            headers = {'Authorization': 'Bearer '+values['bearer_token']} if values['bearer_token'] else {}
            data = self.transport(values['url'].rstrip('/')+'/v2/send', {'message': message, 'number': values['number'], 'recipients': recipients(values['recipients'])}, headers)
            if isinstance(data, dict) and data.get('error'):
                raise RuntimeError('Signal gateway rejected the message')
        elif channel == 'whatsapp':
            for number in recipients(values['recipients']):
                data = self.transport(f"https://graph.facebook.com/{values['api_version']}/{values['phone_id']}/messages", {
                    'messaging_product': 'whatsapp', 'to': number.lstrip('+'), 'type': 'template',
                    'template': {'name': values['template'], 'language': {'code': values['template_language']},
                                 'components': [{'type': 'body', 'parameters': [{'type': 'text', 'text': ' '.join(message.split())[:1000]}]}]},
                }, {'Authorization': 'Bearer '+values['access_token']})
                if not data.get('messages'):
                    raise RuntimeError('WhatsApp API rejected the message')

    def deliver(self, event):
        with self.lock:
            config = copy.deepcopy(self.config)
        if not config['enabled']:
            return
        message = self.format_message(event, config['language'])
        fingerprint = hashlib.sha256(json.dumps([event.get('kind'), event.get('message'), event.get('details')], sort_keys=True).encode()).hexdigest()
        for channel in SECRETS:
            if not config[channel]['enabled'] or event.get('delivery', {}).get(channel, {}).get('status') == 'sent':
                continue
            key = (channel, fingerprint)
            if time.time() - self.recent.get(key, 0) < 3600:
                self.reports.delivery(event['id'], channel, 'suppressed', 'Powtarzający się alert wyciszony na godzinę.')
                continue
            try:
                if not self.reports.delivery(event['id'], channel, 'sending'):
                    continue
                self.send(channel, config, message)
                self.recent[key] = time.time()
                self.reports.delivery(event['id'], channel, 'sent')
            except Exception as exc:
                # Never persist exception URLs: Telegram tokens are part of the URL.
                reason = str(exc) if re.fullmatch(r'HTTP [0-9]{3}', str(exc)) else type(exc).__name__
                self.reports.delivery(event['id'], channel, 'failed', reason)

    def test(self, channel):
        if not isinstance(channel, str) or channel not in SECRETS:
            raise ValueError('Nieprawidłowy kanał powiadomień.')
        with self.lock:
            config = copy.deepcopy(self.config)
        if self.storage_error or not config['enabled'] or not config[channel]['enabled']:
            raise ValueError('Najpierw zapisz i włącz wybrany kanał powiadomień.')
        message = 'DCC Container Updater · test powiadomień' if config['language']=='pl' else 'DCC Container Updater · notification test'
        try:
            self.send(channel, config, message)
        except Exception as exc:
            reason = str(exc) if re.fullmatch(r'HTTP [0-9]{3}', str(exc)) else type(exc).__name__
            raise ValueError('Nie udało się wysłać powiadomienia testowego: '+reason) from None

    def start(self):
        # Rehydrate deduplication and unsent recent errors after an updater restart.
        recent_events = []
        first = self.reports.snapshot()
        for page in range(1, first['pages']+1):
            recent_events.extend(self.reports.snapshot(page)['entries'])
        for event in recent_events:
            fingerprint = hashlib.sha256(json.dumps([event.get('kind'), event.get('message'), event.get('details')], sort_keys=True).encode()).hexdigest()
            for channel, delivery in event.get('delivery', {}).items():
                if delivery.get('status') == 'sent':
                    self.recent[(channel, fingerprint)] = max(self.recent.get((channel, fingerprint), 0), delivery.get('at', 0))
            if time.time() - event.get('occurred_at', 0) < 86400:
                active = [channel for channel in SECRETS if self.config[channel]['enabled']]
                if any(not event.get('delivery', {}).get(channel) for channel in active):
                    self.enqueue(event)
        def worker():
            while not self.stop.is_set():
                try:
                    event = self.events.get(timeout=1)
                except queue.Empty:
                    continue
                try:
                    self.deliver(event)
                finally:
                    self.events.task_done()
        thread = threading.Thread(target=worker, name='dcc-updater-alerts', daemon=True)
        thread.start()
        return thread
