"""Write-only, registry-scoped credentials with one reversible change per registry."""
import copy
import json
import os
import re
import threading

from updater import normalized_repository


def registry_name(value):
    if not isinstance(value, str):
        raise ValueError('Nieprawidłowy adres rejestru.')
    value = value.strip().lower()
    if value.startswith('https://'):
        value = value[8:]
    value = value.rstrip('/')
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*(?::[0-9]{1,5})?', value) or len(value) > 253:
        raise ValueError('Podaj nazwę hosta rejestru, np. ghcr.io lub docker.io, bez ścieżki.')
    if ':' in value and not 1 <= int(value.rsplit(':',1)[1]) <= 65535:
        raise ValueError('Nieprawidłowy port rejestru.')
    return 'docker.io' if value in ('index.docker.io','registry-1.docker.io') else value


class RegistryAccessStore:
    def __init__(self, path):
        self.path, self.lock = path, threading.RLock()
        self.state = {'entries':{}, 'previous':{}}
        self.corrupt = False
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding='utf-8'))
                for section in ('entries','previous'):
                    if not isinstance(data.get(section),dict):raise ValueError('Invalid registry state')
                    for host,values in data[section].items():
                        if registry_name(host) != host:raise ValueError('Invalid registry key')
                        if values is None and section == 'previous':continue
                        if (not isinstance(values,dict) or any(not isinstance(values.get(key),str) or not values[key]
                                for key in ('username','password'))):raise ValueError('Invalid registry entry')
                self.state = data
        except (OSError,ValueError,TypeError,AttributeError):
            self.corrupt = True

    def public(self):
        with self.lock:
            return {'storage_error':self.corrupt,'registries':[
                {'registry':host,'username':self.state['entries'].get(host,{}).get('username',''),
                 'configured':host in self.state['entries'],'can_undo':host in self.state['previous']}
                for host in sorted(set(self.state['entries']) | set(self.state['previous']))]}

    def change(self, host, action, username='', password=''):
        host = registry_name(host)
        with self.lock:
            if self.corrupt:raise ValueError('Plik danych rejestru jest uszkodzony; sprawdź go ręcznie.')
            state = copy.deepcopy(self.state)
            if action == 'undo':
                if host not in state['previous']:raise ValueError('Brak zmiany rejestru do cofnięcia.')
                previous = state['previous'].pop(host)
                if previous is None:state['entries'].pop(host,None)
                else:state['entries'][host] = previous
            elif action in ('save','remove'):
                state['previous'][host] = copy.deepcopy(state['entries'].get(host))
                if action == 'remove':state['entries'].pop(host,None)
                else:
                    if (not isinstance(username,str) or not username.strip() or len(username)>256
                            or not isinstance(password,str) or len(password)>4096
                            or any(char in username+password for char in '\r\n\0')):
                        raise ValueError('Podaj prawidłowego użytkownika i hasło lub token rejestru.')
                    password = password or state['entries'].get(host,{}).get('password','')
                    if not password:raise ValueError('Podaj hasło lub token rejestru.')
                    state['entries'][host] = {'username':username.strip(),'password':password}
            else:raise ValueError('Nieprawidłowa operacja na danych rejestru.')
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(state,ensure_ascii=False),encoding='utf-8')
            try:os.chmod(temporary,0o600)
            except OSError:pass
            temporary.replace(self.path)
            self.state = state
        return self.public()

    def for_image(self, image):
        with self.lock:
            if self.corrupt:return None
            host = registry_name(normalized_repository(image).split('/',1)[0])
            entry = self.state['entries'].get(host)
            return copy.deepcopy(entry) if entry else None
