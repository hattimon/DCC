"""Private SQLite state for profiles, preferences, password hash and session digests."""
import hashlib
import json
import os
import sqlite3
import time
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import uuid4

DEFAULTS = {"language": "en", "theme": "dark", "interval": 30, "onboarded": False}
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
)


class Storage:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.root / "config.sqlite3"
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
            return [dict(row) for row in conn.execute("SELECT * FROM profiles ORDER BY name COLLATE NOCASE, id")]

    def profile(self, profile_id):
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
        return dict(row) if row else None

    def create_profile(self, values):
        profile_id = uuid4().hex
        with self.transaction() as conn:
            if conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] >= 32:
                return None
            conn.execute(
                "INSERT INTO profiles (id,name,host,runtime,endpoint) VALUES (?,?,?,?,?)",
                (profile_id, values["name"], values["host"], values["runtime"], values["endpoint"]),
            )
            conn.execute("UPDATE preferences SET active=? WHERE id=1 AND active IS NULL", (profile_id,))
        return self.profile(profile_id)

    def update_profile(self, profile_id, revision, values):
        with self.transaction() as conn:
            return conn.execute(
                """UPDATE profiles SET name=?,host=?,runtime=?,endpoint=?,revision=revision+1
                   WHERE id=? AND revision=?""",
                (values["name"], values["host"], values["runtime"], values["endpoint"], profile_id, revision),
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

    def password_hash(self):
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT password_hash FROM admin WHERE id=1").fetchone()
        return row[0] if row else None

    def set_password(self, password_hash, *, replace=False):
        with self.transaction() as conn:
            if conn.execute("SELECT 1 FROM admin WHERE id=1").fetchone() and not replace:
                return False
            conn.execute(
                "INSERT INTO admin VALUES (1,?) ON CONFLICT(id) DO UPDATE SET password_hash=excluded.password_hash",
                (password_hash,),
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
