"""Optional RFC 6238 TOTP, encrypted secrets and single-use recovery codes."""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from urllib.parse import quote, urlencode


def totp(secret, step, digits=6, algorithm='sha1'):
    raw = base64.b32decode(secret + '=' * (-len(secret) % 8))
    mac = hmac.new(raw, struct.pack('>Q', int(step)), getattr(hashlib, algorithm)).digest()
    offset = mac[-1] & 15
    value = struct.unpack('>I', mac[offset:offset+4])[0] & 0x7fffffff
    return str(value % 10**digits).zfill(digits)


class MFA:
    def __init__(self, state):
        self.state = state
        state.execute('CREATE TABLE IF NOT EXISTS mfa(user_id TEXT PRIMARY KEY, secret BLOB, enabled INTEGER, last_step INTEGER, recovery TEXT, pending_until REAL, binding TEXT)')

    def enabled(self, user):
        return bool(self.state.rows('SELECT enabled FROM mfa WHERE user_id=? AND enabled=1', (user,)))

    def begin(self, user, name, binding=''):
        secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
        with self.state.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM mfa WHERE user_id=? AND enabled=1',(user,)).fetchone():
                raise ValueError('2FA is already enabled')
            db.execute('INSERT OR REPLACE INTO mfa VALUES(?,?,0,-1,?,?,?)',
                       (user,self.state.vault.encrypt(secret.encode()),'[]',time.time()+600,hashlib.sha256(binding.encode()).hexdigest()))
        uri = 'otpauth://totp/'+quote('DCC Web:'+name, safe='')+'?'+urlencode({'secret':secret,'issuer':'DCC Web','algorithm':'SHA1','digits':6,'period':30})
        return {'secret':secret,'uri':uri}

    def _verify(self, db, user, code, pending=False, binding=''):
        code = str(code or '').strip().replace(' ', '').replace('-', '')[:64]
        row = db.execute('SELECT * FROM mfa WHERE user_id=?', (user,)).fetchone()
        if not row or bool(row['enabled']) == bool(pending):
            return False
        if pending and (row['pending_until'] < time.time() or not hmac.compare_digest(row['binding'],hashlib.sha256(binding.encode()).hexdigest())):
            return False
        if row['enabled']:
            hashes = json.loads(row['recovery'])
            digest = hashlib.sha256(code.upper().encode()).hexdigest()
            found = next((v for v in hashes if hmac.compare_digest(v,digest)), None)
            if found:
                hashes.remove(found)
                db.execute('UPDATE mfa SET recovery=? WHERE user_id=?', (json.dumps(hashes),user))
                return True
        if not code.isascii() or not code.isdigit() or len(code) != 6:
            return False
        secret = self.state.vault.decrypt(row['secret']).decode()
        current = int(time.time()) // 30
        for step in (current, current-1, current+1):
            if step > row['last_step'] and hmac.compare_digest(totp(secret,step),code):
                db.execute('UPDATE mfa SET last_step=? WHERE user_id=?', (step,user))
                return True
        return False

    def verify(self, user, code):
        with self.state.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return self._verify(db,user,code)

    def enable(self, user, code, binding=''):
        codes = [secrets.token_hex(8).upper() for _ in range(10)]
        hashes = [hashlib.sha256(code.encode()).hexdigest() for code in codes]
        with self.state.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not self._verify(db,user,code,pending=True,binding=binding):
                raise ValueError('Invalid or already used 2FA code')
            db.execute('UPDATE mfa SET enabled=1,recovery=? WHERE user_id=?', (json.dumps(hashes),user))
        return codes

    def disable(self, user, code):
        with self.state.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not self._verify(db,user,code):
                raise ValueError('Invalid or already used 2FA code')
            db.execute('DELETE FROM mfa WHERE user_id=?', (user,))
