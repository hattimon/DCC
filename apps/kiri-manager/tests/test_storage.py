import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from backend.storage import MIGRATIONS, Storage


class StorageTest(unittest.TestCase):
    def test_migrations_keep_backup_and_roll_back_partial_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = MIGRATIONS[:1]
            with patch("backend.storage.MIGRATIONS", baseline):
                store = Storage(directory)
            store.update_preferences({"theme": "light"})
            migration = ("ALTER TABLE profiles ADD COLUMN label TEXT", "invalid SQL")
            with patch("backend.storage.MIGRATIONS", (*baseline, migration)):
                with self.assertRaises(sqlite3.OperationalError):
                    Storage(directory)
            saved, = Path(directory).glob("config-v1-*.sqlite3")
            with closing(sqlite3.connect(saved)) as connection:
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)
                self.assertIn("light", connection.execute("SELECT payload FROM preferences").fetchone()[0])
            self.assertEqual(store.preferences()["theme"], "light")
            with closing(store.connect()) as connection:
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)
                self.assertNotIn("label", {row["name"] for row in connection.execute("PRAGMA table_info(profiles)")})
            with patch("backend.storage.MIGRATIONS", (*baseline, (migration[0],))):
                upgraded = Storage(directory)
                with closing(upgraded.connect()) as connection:
                    self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(upgraded.preferences()["theme"], "light")

    def test_schema_two_profiles_and_rollback_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Actual 0.1.2 tables without a master key or SSH columns.
            with closing(sqlite3.connect(root / "config.sqlite3")) as conn, conn:
                for migration in MIGRATIONS[:2]:
                    for statement in migration:
                        conn.execute(statement)
                conn.execute("PRAGMA user_version=2")
                conn.execute("INSERT INTO profiles VALUES (?,?,?,?,?,?)",
                             ("a"*32, "Existing Kiri", "linux", "kiri", "local", 7))
                conn.execute("UPDATE preferences SET payload=?,active=? WHERE id=1",
                             ('{"theme":"light","language":"pl"}', "a"*32))
                conn.execute("INSERT INTO admin VALUES (1,?,?)", ("test-hash", "operator"))
            store = Storage(root)
            profile = store.profile("a"*32)
            self.assertEqual(profile["revision"], 7)
            self.assertEqual(profile["transport"], "socket")
            self.assertFalse(profile["has_credentials"])
            self.assertEqual(store.preferences()["active"], "a"*32)
            self.assertEqual(store.credentials()["username"], "operator")
            self.assertTrue(store.key_path.is_file())
            backup, = root.glob("config-v2-*.sqlite3")
            with closing(sqlite3.connect(backup)) as conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(conn.execute("SELECT revision FROM profiles").fetchone()[0], 7)
            with patch("backend.storage.MIGRATIONS", MIGRATIONS[:2]):
                with self.assertRaises(RuntimeError):
                    Storage(root)
