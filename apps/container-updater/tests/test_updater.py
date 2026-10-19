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

    def test_catalog_candidate_carries_explicit_update_instructions(self):
        instructions = {"host_config": {"RestartPolicy": {"Name": "always"}}}
        candidate = self.service._catalog_candidate(
            "ghcr.io/hattimon/cinema-hub:1.3.5",
            [{**self.apps[0], "update_instructions": instructions}],
        )
        self.assertEqual(candidate.update_instructions, instructions)


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


class PortConflictTests(unittest.TestCase):
    def setUp(self):
        self.service = UpdateService(SimpleNamespace(), catalog_loader=lambda: [])
        self.app = {
            "image": "ghcr.io/example/service:2",
            "latest_release": "v2",
        }

    @staticmethod
    def _container(identifier, name, host_bindings=None, runtime_ports=None):
        return SimpleNamespace(
            id=identifier,
            name=name,
            attrs={
                "Config": {"Image": "ghcr.io/example/service:1", "Labels": {}},
                "HostConfig": {
                    "NetworkMode": "bridge",
                    "AutoRemove": False,
                    "PortBindings": host_bindings or {},
                },
                "NetworkSettings": {"Networks": {"bridge": {}}, "Ports": runtime_ports or {}},
                "State": {"Status": "running"},
            },
        )

    def _scan(self, target_bindings, other_bindings, **kwargs):
        current = self._container("current-id", "current", target_bindings)
        other = self._container("other-id", "other", other_bindings, **kwargs.get("other_runtime", {}))
        return self.service.inspect_container(current, [self.app], all_containers=[current, other])

    def test_same_host_port_and_protocol_is_reported_as_conflict(self):
        result = self._scan(
            {"8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "18080"}]},
            {"9090/tcp": [{"HostIp": "", "HostPort": "18080"}]},
        )
        self.assertFalse(result["supported"])
        self.assertFalse(result["update_available"])
        self.assertIn("other", result["message"])
        self.assertIn("18080", result["message"])

    def test_distinct_specific_host_ips_and_protocols_do_not_conflict(self):
        separate_address = self._scan(
            {"8080/tcp": [{"HostIp": "192.0.2.10", "HostPort": "18080"}]},
            {"9090/tcp": [{"HostIp": "192.0.2.11", "HostPort": "18080"}]},
        )
        separate_protocol = self._scan(
            {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18080"}]},
            {"9090/udp": [{"HostIp": "127.0.0.1", "HostPort": "18080"}]},
        )
        self.assertTrue(separate_address["supported"])
        self.assertTrue(separate_address["update_available"])
        self.assertTrue(separate_protocol["supported"])
        self.assertTrue(separate_protocol["update_available"])

    def test_explicit_catalog_port_override_is_checked_before_update(self):
        app = {
            **self.app,
            "update_instructions": {
                "host_config": {
                    "PortBindings": {"8080/tcp": [{"HostIp": "", "HostPort": "18081"}]}
                }
            },
        }
        current = self._container("current-id", "current", {"8080/tcp": [{"HostPort": "18080"}]})
        other = self._container("other-id", "other", {"9090/tcp": [{"HostPort": "18081"}]})
        result = self.service.inspect_container(current, [app], all_containers=[current, other])
        self.assertFalse(result["supported"])
        self.assertIn("18081", result["message"])

    def test_runtime_published_ports_are_checked_even_if_configured_bindings_are_missing(self):
        current = self._container("current-id", "current", {"8080/tcp": [{"HostPort": "18080"}]})
        other = self._container(
            "other-id",
            "other",
            {},
            {"9090/tcp": [{"HostIp": "0.0.0.0", "HostPort": "18080"}]},
        )
        result = self.service.inspect_container(current, [self.app], all_containers=[current, other])
        self.assertFalse(result["supported"])
        self.assertIn("18080", result["message"])

    def test_port_ranges_overlap(self):
        self.assertTrue(self.service._ports_overlap("18080-18090", "18085"))
        self.assertFalse(self.service._ports_overlap("18080-18090", "18091"))


class ContainerConfigurationTests(unittest.TestCase):
    class FakeApi:
        def create_container_config(self, **kwargs):
            return kwargs

    def setUp(self):
        self.service = UpdateService(SimpleNamespace(api=self.FakeApi()), catalog_loader=lambda: [])
        self.container = SimpleNamespace(attrs={
            "Config": {
                "Image": "example/service:1",
                "Cmd": ["serve"],
                "Env": ["MODE=production", "PORT=8080"],
                "ExposedPorts": {"8080/tcp": {}},
                "Labels": {"owner": "dcc-test"},
                "Volumes": {"/data": {}},
                "WorkingDir": "/srv/app",
            },
            "HostConfig": {
                "NetworkMode": "bridge",
                "AutoRemove": False,
                "RestartPolicy": {"Name": "unless-stopped", "MaximumRetryCount": 0},
                "PortBindings": {"8080/tcp": [{"HostPort": "18080"}]},
            },
            "Mounts": [
                {"Type": "volume", "Name": "service-data", "Destination": "/data", "RW": True},
                {"Type": "bind", "Source": "/srv/config", "Destination": "/config", "RW": False, "Propagation": "rprivate"},
            ],
        })

    def test_default_update_preserves_runtime_configuration_and_data_mounts(self):
        config = self.service._create_config(self.container, "example/service:2")
        self.assertEqual(config["image"], "example/service:2")
        self.assertEqual(config["command"], ["serve"])
        self.assertEqual(config["environment"], ["MODE=production", "PORT=8080"])
        self.assertEqual(config["ports"], {"8080/tcp": {}})
        self.assertEqual(config["working_dir"], "/srv/app")
        self.assertEqual(config["host_config"]["RestartPolicy"]["Name"], "unless-stopped")
        self.assertEqual(config["host_config"]["PortBindings"]["8080/tcp"][0]["HostPort"], "18080")
        mounts = config["host_config"]["Mounts"]
        self.assertEqual({mount["Target"] for mount in mounts}, {"/data", "/config"})
        self.assertEqual(next(m for m in mounts if m["Target"] == "/data")["Source"], "service-data")
        self.assertTrue(next(m for m in mounts if m["Target"] == "/config")["ReadOnly"])

    def test_explicit_update_instructions_change_only_declared_options(self):
        config = self.service._create_config(
            self.container,
            "example/service:2",
            {
                "config": {"command": ["serve", "--safe-mode"]},
                "host_config": {"RestartPolicy": {"Name": "always"}, "Memory": 536870912},
            },
        )
        self.assertEqual(config["command"], ["serve", "--safe-mode"])
        self.assertEqual(config["environment"], ["MODE=production", "PORT=8080"])
        self.assertEqual(config["host_config"]["RestartPolicy"], {"Name": "always"})
        self.assertEqual(config["host_config"]["Memory"], 536870912)
        self.assertEqual(config["host_config"]["PortBindings"]["8080/tcp"][0]["HostPort"], "18080")
        self.assertEqual(len(config["host_config"]["Mounts"]), 2)

    def test_update_instructions_cannot_silently_change_network_mode(self):
        with self.assertRaisesRegex(ValueError, "niebezpieczne"):
            self.service._create_config(
                self.container,
                "example/service:2",
                {"host_config": {"NetworkMode": "host"}},
            )


class UpdateRollbackTests(unittest.TestCase):
    def test_docker_port_race_restores_old_container(self):
        events = []

        class FakeApi:
            def create_container_config(self, **kwargs):
                return kwargs

            def create_container_from_config(self, _config, name):
                events.append(("create", name))
                raise RuntimeError("Bind for 0.0.0.0:18080 failed: port is already allocated")

        class FakeImages:
            def pull(self, image):
                events.append(("pull", image))

        container = SimpleNamespace(
            id="1234567890abcdef",
            name="media",
            attrs={
                "Config": {"Image": "example/service:1", "Labels": {}},
                "HostConfig": {"NetworkMode": "bridge", "AutoRemove": False},
                "NetworkSettings": {"Networks": {"bridge": {}}},
                "State": {"Status": "running"},
                "Mounts": [],
            },
        )

        def stop(timeout):
            events.append(("stop", timeout))
            container.attrs["State"]["Status"] = "exited"

        def rename(name):
            events.append(("rename", name))
            container.name = name

        def start():
            events.append(("start",))
            container.attrs["State"]["Status"] = "running"

        container.stop = stop
        container.rename = rename
        container.start = start

        class FakeContainers:
            def list(self, all=False):
                return [container]

        client = SimpleNamespace(
            api=FakeApi(),
            images=FakeImages(),
            containers=FakeContainers(),
        )
        service = UpdateService(client)

        with self.assertRaisesRegex(RuntimeError, "Docker wykrył zajęty port"):
            service.update_one(container, "example/service:2")

        self.assertEqual(container.name, "media")
        self.assertEqual(container.attrs["State"]["Status"], "running")
        self.assertIn(("rename", "media"), events)
        self.assertIn(("start",), events)

if __name__ == "__main__":
    unittest.main()
