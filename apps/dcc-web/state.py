"""Private state, encrypted connection credentials and bounded audit records."""
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time

from cryptography.fernet import Fernet


def _dpapi(data, decrypt=False):
    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not function(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)):
        raise RuntimeError("Windows credential protection failed")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.windll.kernel32.LocalFree(output.data)


class State:
    def __init__(self, directory, master_key=None):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "dcc-web.sqlite3"
        key_path = self.directory / ("master-key.dpapi" if os.name == "nt" else "master-key")
        if master_key is None:
            if key_path.exists():
                master_key = key_path.read_bytes()
                if os.name == "nt":
                    master_key = _dpapi(master_key, decrypt=True)
            else:
                master_key = Fernet.generate_key()
                encoded = _dpapi(master_key) if os.name == "nt" else master_key
                with key_path.open("xb") as handle:
                    handle.write(encoded)
                key_path.chmod(0o600)
        if isinstance(master_key,str):
            master_key=master_key.encode()
        self.vault = Fernet(master_key)
        self.session_key = hashlib.sha256(master_key + b"dcc-web-sessions-v1").hexdigest()
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT UNIQUE, password TEXT, role TEXT);
                CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT, expires REAL);
                CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY, public TEXT, private BLOB);
                CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, source TEXT, enabled INTEGER, canonical INTEGER, cache TEXT, checked REAL, error TEXT);
                CREATE TABLE IF NOT EXISTS settings(user_id TEXT PRIMARY KEY, data TEXT);
                CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at REAL, user_id TEXT, action TEXT, target TEXT, result INTEGER);
                CREATE TABLE IF NOT EXISTS confirmations(token TEXT PRIMARY KEY, session TEXT, action TEXT, profile TEXT, target TEXT, expires REAL);
                CREATE TABLE IF NOT EXISTS attempts(address TEXT, at REAL);
                CREATE TABLE IF NOT EXISTS grants(id TEXT PRIMARY KEY, token TEXT UNIQUE, data TEXT, revoked INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY, profile TEXT, at REAL, data TEXT);
                CREATE TABLE IF NOT EXISTS compose_projects(profile TEXT, name TEXT, file TEXT, directory TEXT, PRIMARY KEY(profile,name));
            """)
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def rows(self, sql, values=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, values).fetchall()]

    def execute(self, sql, values=()):
        with self.connect() as db:
            return db.execute(sql, values).rowcount

    def profiles(self):
        return [dict(json.loads(row["public"]), id=row["id"]) for row in self.rows("SELECT id,public FROM profiles ORDER BY id")]

    def profile(self, profile_id, private=False):
        rows = self.rows("SELECT * FROM profiles WHERE id=?", (profile_id,))
        if not rows:
            raise ValueError("Profile not found")
        row = rows[0]
        result = dict(json.loads(row["public"]), id=row["id"])
        if private:
            result["credentials"] = json.loads(self.vault.decrypt(row["private"]))
        return result

    def save_profile(self, profile_id, public, private=None):
        old = self.rows("SELECT private FROM profiles WHERE id=?", (profile_id,))
        if private is not None and not isinstance(private,dict):
            raise ValueError("Credentials must be a JSON object")
        existing=json.loads(self.vault.decrypt(old[0]["private"])) if old else {}
        encoded = self.vault.encrypt(json.dumps(dict(existing,**(private or {}))).encode())
        self.execute("INSERT OR REPLACE INTO profiles VALUES(?,?,?)", (profile_id, json.dumps(public), encoded))

    def audit(self, user, action, target, result):
        with self.connect() as db:
            db.execute("INSERT INTO audit(at,user_id,action,target,result) VALUES(?,?,?,?,?)", (time.time(), user, action[:120], target[:160], result))
            db.execute("DELETE FROM audit WHERE id NOT IN (SELECT id FROM audit ORDER BY id DESC LIMIT 10000)")

    def confirm(self, session_id, action, profile, target):
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("DELETE FROM confirmations WHERE expires<?", (time.time(),))
            db.execute("INSERT INTO confirmations VALUES(?,?,?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), session_id, action, profile, target, time.time()+120))
        return token

    def consume(self, token, session_id, action, profile, target):
        digest = hashlib.sha256(str(token).encode()).hexdigest()
        # A single SQL deletion makes a confirmation usable exactly once.
        return self.execute("DELETE FROM confirmations WHERE token=? AND session=? AND action=? AND profile=? AND target=? AND expires>?", (digest, session_id, action, profile, target, time.time())) == 1

    def sample(self, profile, values):
        with self.connect() as db:
            db.execute("INSERT INTO samples(profile,at,data) VALUES(?,?,?)", (profile, time.time(), json.dumps(values)))
            db.execute("DELETE FROM samples WHERE id NOT IN (SELECT id FROM samples ORDER BY id DESC LIMIT 1000)")
