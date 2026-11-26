"""Private SQLite state for profiles, credentials, preferences and sessions."""
import hashlib
import json
import os
import sqlite3
import time
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

DEFAULTS = {"language": "en", "theme": "dark", "interval": 30, "onboarded": False}
DEFAULT_ADMIN_USERNAME = "admin"
SESSION_TTL = 8 * 60 * 60

MIGRATIONS = (
    (
        """CREATE TABLE profiles (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, host TEXT NOT NULL,
            runtime TEXT NOT NULL, endpoint TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1
        )""",
        """CREATE TABLE preferences (
            id INTEGER PRIMARY KEY CHECK(id = 1), payload TEXT NOT NULL,
            active TEXT REFERENCES profiles(id) ON DELETE SET NULL
        )""",
        "CREATE TABLE admin (id INTEGER PRIMARY KEY CHECK(id = 1), password_hash TEXT NOT NULL)",
        "CREATE TABLE sessions (digest TEXT PRIMARY KEY, expires INTEGER NOT NULL)",
        "INSERT INTO preferences (id, payload) VALUES (1, '{}')",
    ),
    ("ALTER TABLE admin ADD COLUMN username TEXT NOT NULL DEFAULT 'admin'",),
    (
        "ALTER TABLE profiles ADD COLUMN transport TEXT NOT NULL DEFAULT 'socket'",
        "ALTER TABLE profiles ADD COLUMN ssh_host TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE profiles ADD COLUMN ssh_port INTEGER NOT NULL DEFAULT 22",
        "ALTER TABLE profiles ADD COLUMN ssh_username TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE profiles ADD COLUMN ssh_cli TEXT NOT NULL DEFAULT 'docker'",
        "ALTER TABLE profiles ADD COLUMN ssh_known_hosts TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE profiles ADD COLUMN credentials BLOB",
    ),
)


class Storage:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.root / "config.sqlite3"
        self.key_path = self.root / "master-key"
        if self.key_path.exists():
            if self.key_path.is_symlink() or (os.name != "nt" and self.key_path.stat().st_mode & 0o077):
                raise RuntimeError("Insecure master-key permissions")
            key = self.key_path.read_bytes()
        else:
            if self.path.exists():
                with closing(sqlite3.connect(self.path)) as conn:
                    columns = {row[1] for row in conn.execute("PRAGMA table_info(profiles)")}
                    if "credentials" in columns and conn.execute("SELECT 1 FROM profiles WHERE credentials IS NOT NULL LIMIT 1").fetchone():
                        raise RuntimeError("Missing master-key for existing SSH credentials")
            key = Fernet.generate_key()
            descriptor = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(key)
            except BaseException:
                self.key_path.unlink(missing_ok=True)
                raise
        self.vault = Fernet(key)
        self.migrate()

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=3)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def transaction(self):
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            yield conn

    def migrate(self):
        with self.transaction() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > len(MIGRATIONS):
                raise RuntimeError("Data directory requires a newer DCC Kiri Manager")
            if 0 < version < len(MIGRATIONS):
                self.backup(version)
            for new_version, statements in enumerate(MIGRATIONS[version:], version + 1):
                for statement in statements:
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version={new_version}")

    def backup(self, version):
        target = self.root / f"config-v{version}-{uuid4().hex}.sqlite3"
        temp = target.with_suffix(".tmp")
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        try:
            with closing(self.connect()) as source, closing(sqlite3.connect(temp)) as copy:
                source.backup(copy)
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)

    def preferences(self):
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT payload, active FROM preferences WHERE id=1").fetchone()
        return {**DEFAULTS, **json.loads(row["payload"]), "active": row["active"]}

    def update_preferences(self, changes):
        with self.transaction() as conn:
            current = conn.execute("SELECT payload FROM preferences WHERE id=1").fetchone()[0]
            payload = {**json.loads(current), **changes}
            conn.execute("UPDATE preferences SET payload=? WHERE id=1", (json.dumps(payload),))
        return self.preferences()

    def profiles(self):
        with closing(self.connect()) as conn:
            rows = conn.execute("SELECT * FROM profiles ORDER BY name COLLATE NOCASE, id")
            return [self._public_profile(row) for row in rows]

    def profile(self, profile_id):
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
        return self._public_profile(row) if row else None

    @staticmethod
    def _public_profile(row):
        result = dict(row)
        credentials = result.pop("credentials", None)
        result["has_credentials"] = bool(credentials)
        return result

    def connection_profile(self, profile_id):
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        encrypted = result.pop("credentials", None)
        try:
            result["credentials"] = json.loads(self.vault.decrypt(encrypted).decode()) if encrypted else {}
        except (InvalidToken, UnicodeDecodeError, ValueError, TypeError):
            raise RuntimeError("Stored connection credentials cannot be decrypted") from None
        result["has_credentials"] = bool(encrypted)
        return result

    def create_profile(self, values):
        profile_id = uuid4().hex
        encrypted = self.vault.encrypt(json.dumps(values.get("credentials", {})).encode()) if values.get("credentials") else None
        with self.transaction() as conn:
            if conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] >= 32:
                return None
            conn.execute(
                """INSERT INTO profiles
                   (id,name,host,runtime,endpoint,transport,ssh_host,ssh_port,ssh_username,ssh_cli,ssh_known_hosts,credentials)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (profile_id, values["name"], values["host"], values["runtime"], values["endpoint"],
                 values.get("transport", "socket"), values.get("ssh_host", ""), values.get("ssh_port", 22),
                 values.get("ssh_username", ""), values.get("ssh_cli", "docker"),
                 values.get("ssh_known_hosts", ""), encrypted),
            )
            conn.execute("UPDATE preferences SET active=? WHERE id=1 AND active IS NULL", (profile_id,))
        return self.profile(profile_id)

    def update_profile(self, profile_id, revision, values):
        encrypted = self.vault.encrypt(json.dumps(values["credentials"]).encode()) if values.get("credentials") else None
        with self.transaction() as conn:
            query = """UPDATE profiles SET name=?,host=?,runtime=?,endpoint=?,transport=?,ssh_host=?,ssh_port=?,
                   ssh_username=?,ssh_cli=?,ssh_known_hosts=?,revision=revision+1"""
            params = [values["name"], values["host"], values["runtime"], values["endpoint"],
                      values.get("transport", "socket"), values.get("ssh_host", ""), values.get("ssh_port", 22),
                      values.get("ssh_username", ""), values.get("ssh_cli", "docker"), values.get("ssh_known_hosts", "")]
            if "credentials" in values or values.get("transport", "socket") == "socket":
                query += ",credentials=?"
                params.append(encrypted)
            query += " WHERE id=? AND revision=?"
            params.extend((profile_id, revision))
            return conn.execute(
                query,
                params,
            ).rowcount == 1

    def activate(self, profile_id):
        with self.transaction() as conn:
            return conn.execute(
                """UPDATE preferences SET active=? WHERE id=1
                   AND EXISTS (SELECT 1 FROM profiles WHERE id=?)""", (profile_id, profile_id),
            ).rowcount == 1

    def delete_profile(self, profile_id, revision):
        with self.transaction() as conn:
            return conn.execute(
                "DELETE FROM profiles WHERE id=? AND revision=?", (profile_id, revision),
            ).rowcount == 1

    def credentials(self):
        with closing(self.connect()) as conn:
            return conn.execute("SELECT username, password_hash FROM admin WHERE id=1").fetchone()

    def set_password(self, password_hash, *, username=None, replace=False):
        with self.transaction() as conn:
            current = conn.execute("SELECT username FROM admin WHERE id=1").fetchone()
            if current and not replace:
                return False
            if username is None:
                username = current["username"] if current else DEFAULT_ADMIN_USERNAME
            conn.execute(
                """INSERT INTO admin (id, username, password_hash) VALUES (1,?,?)
                   ON CONFLICT(id) DO UPDATE SET username=excluded.username, password_hash=excluded.password_hash""",
                (username, password_hash),
            )
            conn.execute("DELETE FROM sessions")
            return True

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    def add_session(self, token, password_hash):
        now = int(time.time())
        with self.transaction() as conn:
            # A simultaneous password change must not create a session with the old password.
            if not conn.execute("SELECT 1 FROM admin WHERE id=1 AND password_hash=?", (password_hash,)).fetchone():
                return False
            conn.execute("DELETE FROM sessions WHERE expires<=?", (now,))
            conn.execute(
                """DELETE FROM sessions WHERE digest IN
                   (SELECT digest FROM sessions ORDER BY expires DESC LIMIT -1 OFFSET 31)"""
            )
            conn.execute("INSERT INTO sessions VALUES (?,?)", (self.digest(token), now + SESSION_TTL))
        return True

    def session_valid(self, token):
        with closing(self.connect()) as conn:
            return conn.execute(
                "SELECT 1 FROM sessions WHERE digest=? AND expires>?", (self.digest(token), int(time.time())),
            ).fetchone() is not None

    def revoke_session(self, token):
        with self.transaction() as conn:
            conn.execute("DELETE FROM sessions WHERE digest=?", (self.digest(token),))
