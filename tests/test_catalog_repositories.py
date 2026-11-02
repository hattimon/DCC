import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import DockerControlCenter as dcc


class CatalogRepositoryTests(unittest.TestCase):
    def test_official_catalog_controls_membership_and_offline_fallback_is_retained(self):
        bundled = dcc.image_template_from_dict({'name': 'Removed app', 'image': 'example/removed:1'})
        live = dcc.image_template_from_dict({'name': 'New app', 'image': 'example/new:1'}, dcc.DEFAULT_DEPLOYMENT_REPOSITORY)
        self.assertEqual(dcc.store_catalog([bundled], [live]), [live])
        self.assertEqual(dcc.store_catalog([bundled], []), [bundled])

    def test_stale_cache_cannot_replace_newer_bundled_version(self):
        new = dcc.image_template_from_dict({'name': 'DCC Web', 'image': 'ghcr.io/hattimon/dcc-web:0.1.3'})
        old = dcc.image_template_from_dict({'name': 'DCC Web', 'image': 'ghcr.io/hattimon/dcc-web:0.1.1'})
        for catalogs in (([new], [old]), ([old], [new]), ([old, new, old],)):
            self.assertEqual([app.image for app in dcc.merge_catalog_lists(*catalogs)], [new.image])

    def test_refresh_replaces_bundled_image_version_and_preserves_other_apps(self):
        old = dcc.image_template_from_dict({
            "name": "DCC Web", "image": "ghcr.io/hattimon/dcc-web:0.1.1",
            "category": "DCC", "categories": ["Administracja", "WWW"],
            "features": ["Stored metadata"],
        })
        refreshed = dcc.image_template_from_dict({
            "name": "DCC Web", "image": "ghcr.io/hattimon/dcc-web:0.1.2", "category": "DCC",
        })
        preview = dcc.image_template_from_dict({
            "name": "DCC Web Preview", "image": "ghcr.io/hattimon/dcc-web:preview", "category": "DCC",
        })
        other_repository = dcc.image_template_from_dict({
            "name": "DCC Web", "image": "example.org/dcc-web:1", "category": "DCC",
        })
        merged = dcc.merge_catalog_lists([old, preview, other_repository], [refreshed])
        self.assertEqual(len(merged), 3)
        current = next(item for item in merged if item.image == refreshed.image)
        self.assertNotIn(old.image, [item.image for item in merged])
        self.assertEqual(current.categories_for("PL"), ["DCC", "Administracja", "WWW"])
        self.assertEqual(current.features, old.features)
        self.assertIn(preview, merged)
        self.assertIn(other_repository, merged)

    def test_catalog_update_identity_handles_registry_ports_and_digests(self):
        from dcc_catalog import catalog_application_key
        old = catalog_application_key("Example", "registry.example:5000/team/app:1")
        self.assertEqual(old, catalog_application_key("Example", "registry.example:5000/team/app:2"))
        self.assertEqual(old, catalog_application_key("Example", "registry.example:5000/team/app@sha256:abcdef"))
        self.assertNotEqual(old, catalog_application_key("Example", "registry.example:5001/team/app:2"))

    def test_refresh_preserves_intentional_versioned_container_variants(self):
        current = dcc.image_template_from_dict({
            "name": "Uptime Kuma", "image": "louislam/uptime-kuma:2", "default_name": "uptime-kuma",
        })
        legacy = dcc.image_template_from_dict({
            "name": "Uptime Kuma", "image": "louislam/uptime-kuma:1", "default_name": "uptime-kuma-v1-disabled",
        })
        refreshed = dcc.image_template_from_dict({
            "name": "Uptime Kuma", "image": "louislam/uptime-kuma:2.1", "default_name": "uptime-kuma",
        })
        self.assertEqual(dcc.merge_catalog_lists([current, legacy], [refreshed]), [refreshed, legacy])

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

    def test_multiple_categories_accept_plural_only_and_optional_translations(self):
        template = dcc.image_template_from_dict(
            {
                "name": "Demo extension",
                "image": "example/demo:latest",
                "categories": [" DCC ", "AI / UI", "DCC", "", None],
                "categories_en": ["DCC", "AI / UI"],
            }
        )
        self.assertEqual(template.categories_for("PL"), ["DCC", "AI / UI"])
        self.assertEqual(template.categories_for("EN"), ["DCC", "AI / UI"])
        fallback = dcc.image_template_from_dict(
            {"name": "Demo", "image": "example/demo:latest", "category": "AI", "categories": ["DCC"]}
        )
        self.assertEqual(fallback.categories_for("EN"), ["AI", "DCC"])
        malformed = dcc.image_template_from_dict(
            {"name": "Legacy", "image": "example/legacy:latest", "category": "AI", "categories": "DCC"}
        )
        self.assertEqual(malformed.categories_for("PL"), ["AI"])

    def test_catalog_cache_roundtrip_preserves_multiple_and_legacy_categories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_file = Path(temp_dir) / "catalog.json"
            legacy_data = {"name": "Legacy", "image": "example/legacy:latest", "category": "AI"}
            cache_file.write_text(json.dumps({"apps": [legacy_data]}), encoding="utf-8")
            with patch.object(dcc, "DEPLOYMENT_CATALOG_CACHE_FILE", cache_file):
                legacy = dcc.load_cached_deployment_catalog()[0]
                self.assertEqual(legacy.categories_for("EN"), ["AI"])
                updater = next(
                    item for item in dcc.load_bundled_deployment_catalog() if item.name == "DCC Container Updater"
                )
                dcc.save_cached_deployment_catalog([legacy, updater])
                loaded_legacy, loaded_updater = dcc.load_cached_deployment_catalog()
                self.assertEqual(loaded_legacy.categories_for("PL"), ["AI"])
                self.assertEqual(loaded_updater.categories_for("PL"), ["Aktualizacje 🔄", "DCC"])
                self.assertEqual(loaded_updater.categories_for("EN"), ["Updates 🔄", "DCC"])
                self.assertEqual(loaded_updater.repository_source, dcc.DEFAULT_DEPLOYMENT_REPOSITORY)

    def test_extended_catalog_metadata_is_parsed(self):
        parsed = dcc.image_template_from_dict(
            {
                "name": "Metadata test",
                "image": "example/test:latest",
                "requires": ["postgresql", " redis ", ""],
                "gpu": True,
                "ram_min_mb": 2048,
                "storage_type": "persistent",
                "backup_priority": "high",
                "security_exposure": "reverse_proxy_required",
                "compose_required": True,
                "balena_verified": False,
            }
        )
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.requires, ["postgresql", "redis"])
        self.assertTrue(parsed.gpu)
        self.assertEqual(parsed.ram_min_mb, 2048)
        self.assertEqual(parsed.storage_type, "persistent")
        self.assertEqual(parsed.backup_priority, "high")
        self.assertEqual(parsed.security_exposure, "reverse_proxy_required")
        self.assertTrue(parsed.compose_required)
        self.assertFalse(parsed.balena_verified)


if __name__ == "__main__":
    unittest.main()
