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
