import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "tools" / "update_catalog_metadata.py"
SPEC = importlib.util.spec_from_file_location("dcc_catalog_maintenance", SCRIPT_PATH)
maintenance = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(maintenance)


class CatalogMaintenanceTests(unittest.TestCase):
    def test_github_repo_is_derived_from_source_url(self):
        self.assertEqual(
            maintenance.app_repo({"source_url": "https://github.com/ItzCrazyKns/Vane"}),
            "ItzCrazyKns/Vane",
        )

    def test_release_metadata_updates_without_changing_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dcc-catalog.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "apps": [
                            {
                                "name": "Vane",
                                "image": "itzcrazykns1337/vane:latest",
                                "source_url": "https://github.com/ItzCrazyKns/Vane",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(
                maintenance,
                "latest_release",
                return_value=("v9.9.9", "https://github.com/ItzCrazyKns/Vane/releases/tag/v9.9.9"),
            ):
                checked, changed = maintenance.update_release_metadata(path)

            payload = json.loads(path.read_text(encoding="utf-8"))
            app = payload["apps"][0]
            self.assertEqual((checked, changed), (1, 1))
            self.assertEqual(app["image"], "itzcrazykns1337/vane:latest")
            self.assertEqual(app["upstream_repo"], "ItzCrazyKns/Vane")
            self.assertEqual(app["latest_release"], "v9.9.9")

    def test_discovery_never_writes_candidates_into_live_catalog(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            catalog = root / "dcc-catalog.json"
            candidates = root / "catalog" / "candidates.json"
            original = {
                "schema_version": 1,
                "apps": [
                    {
                        "name": "Existing",
                        "image": "example/existing:latest",
                        "source_url": "https://github.com/example/existing",
                    }
                ],
            }
            catalog.write_text(json.dumps(original), encoding="utf-8")
            fake_search = {
                "items": [
                    {
                        "full_name": "example/new-app",
                        "name": "new-app",
                        "html_url": "https://github.com/example/new-app",
                        "description": "New app",
                        "stargazers_count": 1000,
                        "language": "Python",
                        "topics": ["self-hosted"],
                        "updated_at": "2026-09-20T00:00:00Z",
                        "created_at": "2026-01-01T00:00:00Z",
                    }
                ]
            }
            with patch.object(maintenance, "github_json", return_value=fake_search):
                total, new = maintenance.discover_candidates(catalog, candidates, 30)

            self.assertEqual((total, new), (1, 1))
            self.assertEqual(json.loads(catalog.read_text(encoding="utf-8")), original)
            discovered = json.loads(candidates.read_text(encoding="utf-8"))["candidates"]
            self.assertEqual(discovered[0]["full_name"], "example/new-app")


if __name__ == "__main__":
    unittest.main()
