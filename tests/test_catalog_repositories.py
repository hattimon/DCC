import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import DockerControlCenter as dcc


class CatalogRepositoryTests(unittest.TestCase):
    def test_primary_repository_is_always_present_and_not_persisted_as_custom(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_file = Path(temp_dir) / "repositories.json"
            with patch.object(dcc, "DEPLOYMENT_REPOSITORIES_FILE", repo_file):
                dcc.save_deployment_repository_sources(
                    [
                        dcc.DEFAULT_DEPLOYMENT_REPOSITORY,
                        "https://github.com/example/catalog",
                        "https://github.com/example/catalog/",
                    ]
                )

                saved = json.loads(repo_file.read_text(encoding="utf-8"))
                self.assertEqual(saved["repositories"], ["https://github.com/example/catalog"])

                loaded = dcc.load_deployment_repository_sources()
                self.assertEqual(loaded[0], dcc.DEFAULT_DEPLOYMENT_REPOSITORY)
                self.assertEqual(loaded[1:], ["https://github.com/example/catalog"])

    def test_primary_repository_normalization_handles_git_and_trailing_slash(self):
        self.assertTrue(dcc.is_primary_deployment_repository("https://github.com/hattimon/DCC/"))
        self.assertTrue(dcc.is_primary_deployment_repository("https://github.com/hattimon/DCC.git"))

    def test_github_repository_resolves_canonical_catalog_first(self):
        candidates = dcc._catalog_source_candidates(dcc.DEFAULT_DEPLOYMENT_REPOSITORY)
        self.assertEqual(
            candidates[0],
            "https://raw.githubusercontent.com/hattimon/DCC/main/dcc-catalog.json",
        )
        self.assertIn(
            "https://raw.githubusercontent.com/hattimon/DCC/master/dcc-catalog.json",
            candidates,
        )

    def test_root_catalog_is_valid_and_contains_apps(self):
        catalog_path = Path(__file__).resolve().parents[1] / "dcc-catalog.json"
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)
        self.assertGreaterEqual(len(payload["apps"]), 50)
        parsed = [dcc.image_template_from_dict(item, dcc.DEFAULT_DEPLOYMENT_REPOSITORY) for item in payload["apps"]]
        self.assertTrue(all(item is not None for item in parsed))


if __name__ == "__main__":
    unittest.main()
