import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from updater import UpdateService, compare_versions, image_reference, normalized_repository, version_tuple


class ImageReferenceTests(unittest.TestCase):
    def test_parses_registry_ports_tags_and_digests(self):
        self.assertEqual(image_reference("registry.example:5000/team/app:1.2.3"), ("registry.example:5000/team/app", "1.2.3"))
        self.assertEqual(image_reference("ghcr.io/team/app@sha256:abcdef"), ("ghcr.io/team/app", "latest"))
        self.assertEqual(normalized_repository("nginx:latest"), "docker.io/library/nginx")
        self.assertEqual(normalized_repository("docker.io/nginx:1.0"), "docker.io/library/nginx")

    def test_numeric_version_comparison_avoids_lexicographic_order(self):
        self.assertEqual(compare_versions(version_tuple("1.3.10"), version_tuple("1.3.9")), 1)
        self.assertEqual(compare_versions(version_tuple("v1.3"), version_tuple("1.3.0")), 0)


class CatalogCandidateTests(unittest.TestCase):
    def setUp(self):
        self.service = UpdateService(SimpleNamespace(), catalog_loader=lambda: [])
        self.apps = [{
            "image": "ghcr.io/hattimon/cinema-hub:1.3.7",
            "latest_release": "v1.3.7",
        }]

    def test_catalog_offers_newer_image(self):
        result = self.service._catalog_candidate("ghcr.io/hattimon/cinema-hub:1.3.5", self.apps)
        self.assertTrue(result.available)
        self.assertEqual(result.target_image, "ghcr.io/hattimon/cinema-hub:1.3.7")

    def test_catalog_does_not_offer_downgrade_or_equal_version(self):
        equal = self.service._catalog_candidate("ghcr.io/hattimon/cinema-hub:1.3.7", self.apps)
        newer = self.service._catalog_candidate("ghcr.io/hattimon/cinema-hub:1.4.0", self.apps)
        self.assertIsNone(equal)
        self.assertFalse(newer.available)

    def test_catalog_can_compare_a_pinned_image_to_latest_tag_release(self):
        apps = [{"image": "example/service:latest", "latest_release": "v2.4.0"}]
        newer = self.service._catalog_candidate("example/service:2.3.9", apps)
        current = self.service._catalog_candidate("example/service:2.4.0", apps)
        self.assertTrue(newer.available)
        self.assertFalse(current.available)


class ContainerSafetyTests(unittest.TestCase):
    def _container(self, **overrides):
        attrs = {
            "Config": {"Image": "example/service:latest", "Labels": {}},
            "HostConfig": {"NetworkMode": "bridge", "AutoRemove": False},
            "NetworkSettings": {"Networks": {"bridge": {}}},
            "State": {"Status": "running"},
        }
        attrs.update(overrides)
        return SimpleNamespace(id="0123456789abcdef", name="example", attrs=attrs, status="running")

    def test_compose_container_is_marked_unsupported(self):
        service = UpdateService(SimpleNamespace(), catalog_loader=lambda: [])
        container = self._container(Config={"Image": "example/service:latest", "Labels": {"com.docker.compose.project": "media"}})
        result = service.inspect_container(container, [])
        self.assertFalse(result["supported"])
        self.assertIn("Compose", result["message"])

    def test_custom_network_container_is_marked_unsupported(self):
        service = UpdateService(SimpleNamespace(), catalog_loader=lambda: [])
        container = self._container(
            HostConfig={"NetworkMode": "media-net", "AutoRemove": False},
            NetworkSettings={"Networks": {"media-net": {}}},
        )
        result = service.inspect_container(container, [])
        self.assertFalse(result["supported"])


if __name__ == "__main__":
    unittest.main()
