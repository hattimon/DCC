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

    def test_release_filter_skips_android_and_prerelease_tags(self):
        releases = [
            {
                "tag_name": "android-v1.3.8",
                "html_url": "https://github.com/example/cinema/releases/tag/android-v1.3.8",
                "draft": False,
                "prerelease": False,
            },
            {
                "tag_name": "v1.3.8-rc.1",
                "html_url": "https://github.com/example/cinema/releases/tag/v1.3.8-rc.1",
                "draft": False,
                "prerelease": True,
            },
            {
                "tag_name": "v1.3.7",
                "html_url": "https://github.com/example/cinema/releases/tag/v1.3.7",
                "draft": False,
                "prerelease": False,
            },
            {
                "tag_name": "v1.3.6",
                "html_url": "https://github.com/example/cinema/releases/tag/v1.3.6",
                "draft": False,
                "prerelease": False,
            },
        ]
        with patch.object(maintenance, "github_json", return_value=releases) as github_json:
            self.assertEqual(
                maintenance.latest_release("example/cinema", r"v\d+\.\d+\.\d+"),
                ("v1.3.7", "https://github.com/example/cinema/releases/tag/v1.3.7"),
            )
        github_json.assert_called_once_with("/repos/example/cinema/releases?per_page=100&page=1")

    def test_release_image_tag_updates_only_after_multiplatform_image_is_published(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dcc-catalog.json"
            path.write_text(
                json.dumps(
                    {
                        "apps": [
                            {
                                "name": "Cinema Hub",
                                "image": "ghcr.io/example/cinema:1.3.6",
                                "upstream_repo": "example/cinema",
                                "release_tag_pattern": r"v\d+\.\d+\.\d+",
                                "image_tag_from_release": "strip-v",
                                "archs": ["amd64", "arm64"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(
                maintenance,
                "latest_release",
                return_value=("v1.3.7", "https://github.com/example/cinema/releases/tag/v1.3.7"),
            ), patch.object(maintenance, "registry_image_supports_architectures", return_value=True) as image_check:
                checked, changed = maintenance.update_release_metadata(path)

            app = json.loads(path.read_text(encoding="utf-8"))["apps"][0]
            self.assertEqual((checked, changed), (1, 1))
            self.assertEqual(app["image"], "ghcr.io/example/cinema:1.3.7")
            self.assertEqual(app["latest_release"], "v1.3.7")
            image_check.assert_called_once_with("ghcr.io/example/cinema:1.3.7", ["amd64", "arm64"])

    def test_release_metadata_stays_on_published_image_when_new_image_is_incomplete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dcc-catalog.json"
            original_app = {
                "name": "Cinema Hub",
                "image": "ghcr.io/example/cinema:1.3.6",
                "upstream_repo": "example/cinema",
                "latest_release": "v1.3.6",
                "latest_release_url": "https://github.com/example/cinema/releases/tag/v1.3.6",
                "release_tag_pattern": r"v\d+\.\d+\.\d+",
                "image_tag_from_release": "strip-v",
                "archs": ["amd64", "arm64"],
            }
            path.write_text(json.dumps({"apps": [original_app]}), encoding="utf-8")
            with patch.object(
                maintenance,
                "latest_release",
                return_value=("v1.3.7", "https://github.com/example/cinema/releases/tag/v1.3.7"),
            ), patch.object(maintenance, "registry_image_supports_architectures", return_value=False):
                checked, changed = maintenance.update_release_metadata(path)

            self.assertEqual((checked, changed), (1, 0))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["apps"][0], original_app)

    def test_cinema_hub_catalog_tracks_stable_server_release_and_image(self):
        catalog_path = Path(__file__).resolve().parents[1] / "dcc-catalog.json"
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        app = next(item for item in payload["apps"] if item.get("upstream_repo") == "hattimon/CINEMA-HUB")
        self.assertEqual(app["latest_release"], "v1.3.7")
        self.assertEqual(app["image"], "ghcr.io/hattimon/cinema-hub:1.3.7")
        self.assertEqual(app["release_tag_pattern"], r"v[0-9]+\.[0-9]+\.[0-9]+")
        self.assertEqual(app["image_tag_from_release"], "strip-v")

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
