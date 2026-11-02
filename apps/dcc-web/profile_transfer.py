"""Password-protected, portable backups. Private material never touches a temp file."""
import base64
import json
import secrets
from pathlib import Path

from profile_ssh import safe_name, inspect_file, digest, key_name, MAX_FILE
from security import validate_profile

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

FORMAT = 'dcc-web-encrypted-profiles'
MAX_BACKUP = 1_400_000


def password_key(password, salt):
    if not isinstance(password,str) or not 12 <= len(password) <= 256:
        raise ValueError('Backup password must have 12 to 256 characters')
    return base64.urlsafe_b64encode(Scrypt(salt=salt,length=32,n=2**15,r=8,p=1).derive(password.encode()))


def seal(payload,password):
    raw = json.dumps(payload).encode()
    if len(raw) > MAX_BACKUP:
        raise ValueError('Profile backup is too large')
    salt = secrets.token_bytes(16)
    cipher = Fernet(password_key(password,salt)).encrypt(raw)
    return {'format':FORMAT,'version':1,'kdf':'scrypt-32768-8-1','salt':base64.b64encode(salt).decode(),
            'payload':cipher.decode()}


def unseal(payload,password):
    if not isinstance(payload,dict) or payload.get('format') != FORMAT or payload.get('version') != 1 or payload.get('kdf') != 'scrypt-32768-8-1':
        raise ValueError('Unsupported encrypted profile backup')
    try:
        salt = base64.b64decode(payload['salt'],validate=True)
        if len(salt) != 16 or not isinstance(payload.get('payload'),str) or len(payload['payload']) > 1_900_000:
            raise ValueError()
        raw = Fernet(password_key(password,salt)).decrypt(payload['payload'].encode())
        if len(raw) > MAX_BACKUP:
            raise ValueError()
        value = json.loads(raw)
        if not isinstance(value,dict) or not isinstance(value.get('profiles'),list):
            raise ValueError()
        return value
    except (InvalidToken,KeyError,ValueError,TypeError):
        raise ValueError('Invalid backup password or damaged encrypted backup') from None


class ProfileTransfer:
    def __init__(self,state):
        self.state = state

    def export(self, identifiers, password, include_secrets):
        profiles = self.state.profiles()
        ids = {p['id'] for p in profiles}
        if identifiers is not None:
            if not isinstance(identifiers,list) or not identifiers or any(i not in ids for i in identifiers):
                raise ValueError('Select existing profiles to export')
            profiles = [p for p in profiles if p['id'] in identifiers]
        files, needed = [], set()
        if include_secrets:
            for profile in profiles:
                secret = dict(self.state.profile(profile['id'],private=True)['credentials'])
                secret.pop('private_key',None)
                profile['credentials'] = secret
                if profile.get('key_scope') == 'shared':
                    needed.update(['known_hosts',key_name(profile.get('key_path'))])
            for name in needed - {''}:
                saved = self.state.ssh.vault_file(name)
                path = self.state.ssh.managed / safe_name(name)
                if saved:
                    data = self.state.vault.decrypt(saved['private'])
                elif path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_FILE:
                    data = path.read_bytes()
                else:
                    continue
                inspect_file(name,data)
                files.append({'name':name,'data':base64.b64encode(data).decode()})
        return seal({'profiles':profiles,'ssh_files':files},password)

    def decode(self, incoming, password=''):
        trusted = False
        if isinstance(incoming,dict) and incoming.get('format') == FORMAT:
            incoming = unseal(incoming,password)
            trusted = True
        entries = incoming.get('profiles') if isinstance(incoming,dict) else incoming
        if not isinstance(entries,list) or not 1 <= len(entries) <= 100:
            raise ValueError('A profiles array with 1 to 100 entries is required')
        files = []
        for item in incoming.get('ssh_files',[]) if trusted else []:
            try:
                content = base64.b64decode(item['data'],validate=True)
                inspect_file(item['name'],content)
                files.append((item['name'],content))
            except (KeyError,ValueError,TypeError):
                raise ValueError('Invalid SSH file in encrypted backup') from None
        if len(files) > 20 or sum(len(data) for _,data in files) > 1024*1024:
            raise ValueError('SSH files exceed the import size limit')
        values = []
        for entry in entries:
            if not isinstance(entry,dict):
                raise ValueError('Invalid profile entry')
            original = entry
            if 'mode' in entry:
                username,_,host = str(entry.get('ssh_target','')).rpartition('@')
                entry = {'name':entry.get('name'),'kind':'ssh' if entry['mode']=='ssh' else 'tunnel',
                         'username':entry.get('ssh_username') or username,'host':host.strip('[]'),
                         'port':entry.get('ssh_port') or 22,'endpoint':entry.get('base_url',''),
                         'key_path':entry.get('ssh_key_path',''),'permissions':['read']}
            value = validate_profile(entry)
            value['permissions'] = ['read']
            # Only authenticated encrypted backups may contain portable credentials.
            secret = original.get('credentials',{}) if trusted else {}
            if not isinstance(secret,dict) or any(not isinstance(v,str) or len(v)>8192 for v in secret.values()):
                raise ValueError('Invalid encrypted profile credentials')
            values.append((value,secret))
        return values, files

    @staticmethod
    def identity(value):
        return tuple(str(value.get(k) or '') for k in ('name','kind','host','port','username','endpoint','context','distro'))

    def plan(self, incoming, password, indices=None, shared_keys=True, replace=False):
        values, files = self.decode(incoming,password)
        if indices is None:
            indices = list(range(len(values)))
        if not isinstance(indices,list) or not indices or any(type(i) is not int or not 0<=i<len(values) for i in indices):
            raise ValueError('Select profiles to import')
        existing = {self.identity(p):p for p in self.state.profiles()}
        uploaded = {f['name'] for f in self.state.ssh.settings()['files'] if f['kind']=='private key'}
        uploaded.update(name for name,data in files if inspect_file(name,data)['kind']=='private key')
        prepared, rows = [], []
        seen = set(existing)
        for index in sorted(set(indices)):
            value, secret = values[index]
            ident = self.identity(value)
            duplicate = ident in seen
            seen.add(ident)
            if shared_keys and value.get('kind') in {'ssh','balena'} and key_name(value.get('key_path')) in uploaded:
                value = dict(value,key_scope='shared',key_path=key_name(value.get('key_path')))
            prepared.append((value,secret,duplicate))
            rows.append({'index':index,'name':value['name'],'kind':value['kind'],'host':value.get('host',''),
                         'duplicate':duplicate,'matched_key':value.get('key_path') if value.get('key_scope')=='shared' else None})
        manifest = self.state.ssh.file_plan(files,replace) if files else None
        target = digest({'values':prepared,'files':manifest,'existing':self.state.profiles()})
        return {'target':target,'profiles':rows,'files':manifest['files'] if manifest else []}, prepared, files

    def apply(self, prepared, files):
        if files:
            self.state.ssh.write_files(files)
        added = []
        for value,secret,duplicate in prepared:
            if duplicate:
                continue
            ident = secrets.token_hex(10)
            self.state.save_profile(ident,value,secret)
            added.append(ident)
        return added
