import json
import subprocess
import sys
import tempfile
import unittest
import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from updater import UpdateService, compare_versions, friendly_registry_error, image_reference, load_catalog, normalized_repository, version_tuple


class ImageReferenceTests(unittest.TestCase):
    def test_parses_registry_ports_tags_and_digests(self):
        self.assertEqual(image_reference("registry.example:5000/team/app:1.2.3"), ("registry.example:5000/team/app", "1.2.3"))
        self.assertEqual(image_reference("ghcr.io/team/app@sha256:abcdef"), ("ghcr.io/team/app", "latest"))
        self.assertEqual(normalized_repository("nginx:latest"), "docker.io/library/nginx")
        self.assertEqual(normalized_repository("docker.io/nginx:1.0"), "docker.io/library/nginx")

    def test_numeric_version_comparison_avoids_lexicographic_order(self):
        self.assertEqual(compare_versions(version_tuple("1.3.10"), version_tuple("1.3.9")), 1)
        self.assertEqual(compare_versions(version_tuple("v1.3"), version_tuple("1.3.0")), 0)


class CatalogLoadingTests(unittest.TestCase):
    def test_catalog_falls_back_to_github_api_when_raw_github_is_unavailable(self):
        catalog_bytes = json.dumps({"apps": [{"image": "example/service:2"}]}).encode("utf-8")
        api_response = json.dumps({
            "encoding": "base64",
            "content": base64.b64encode(catalog_bytes).decode("ascii"),
        }).encode("utf-8")

        class Response:
            def __init__(self, content):
                self.content = content

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return self.content

        with patch("updater.urllib.request.urlopen", side_effect=[URLError("raw host timed out"), Response(api_response)]) as open_url:
            apps = load_catalog()

        self.assertEqual(apps, [{"image": "example/service:2"}])
        self.assertEqual(open_url.call_count, 2)
        self.assertIn("api.github.com", open_url.call_args_list[1].args[0].full_url)


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

    def test_cinema_hub_catalog_offers_139_to_138(self):
        cinema_hub = {"image": "ghcr.io/hattimon/cinema-hub:1.3.9", "latest_release": "v1.3.9"}

        result = self.service._catalog_candidate("ghcr.io/hattimon/cinema-hub:1.3.8", [cinema_hub])

        self.assertTrue(result.available)
        self.assertEqual(result.target_image, "ghcr.io/hattimon/cinema-hub:1.3.9")


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

    def test_digest_only_config_uses_a_unique_local_tag_for_registry_checks(self):
        local_image = SimpleNamespace(attrs={
            "RepoTags": ["ghcr.io/example/rss-bridge:latest"],
            "RepoDigests": ["ghcr.io/example/rss-bridge@sha256:old"],
            "Os": "linux",
            "Architecture": "arm64",
        })

        class Api:
            def inspect_distribution(self, image):
                self.asserted_image = image
                return {
                    "Platforms": [{
                        "os": "linux",
                        "architecture": "arm64",
                    }],
                    "Descriptor": {"digest": "sha256:new"},
                }

        api = Api()
        client = SimpleNamespace(api=api, images=SimpleNamespace(get=lambda _identifier: local_image))
        service = UpdateService(client, catalog_loader=lambda: [])
        container = self._container(
            Config={"Image": "sha256:container-image", "Labels": {}},
            Image="sha256:container-image",
        )
        result = service.inspect_container(container, [])
        self.assertTrue(result["update_available"])
        self.assertEqual(result["target_image"], "ghcr.io/example/rss-bridge:latest")
        self.assertEqual(api.asserted_image, "ghcr.io/example/rss-bridge:latest")

    def test_registry_current_digest_does_not_hide_catalog_fetch_failure(self):
        image = "ghcr.io/hattimon/cinema-hub:1.3.8"
        local_image = SimpleNamespace(attrs={
            "RepoTags": [image],
            "RepoDigests": ["ghcr.io/hattimon/cinema-hub@sha256:local"],
            "Os": "linux",
            "Architecture": "arm64",
        })

        class Api:
            def inspect_distribution(self, _image):
                return {
                    "Platforms": [{
                        "os": "linux",
                        "architecture": "arm64",
                    }],
                    "Descriptor": {"digest": "sha256:local"},
                }

        container = self._container(
            Config={"Image": image, "Labels": {}},
            Image="sha256:container-image",
            HostConfig={"NetworkMode": "bridge", "AutoRemove": False, "PortBindings": {}},
            NetworkSettings={"Networks": {"bridge": {}}, "Ports": {}},
            State={"Status": "running"},
        )
        client = SimpleNamespace(
            api=Api(),
            images=SimpleNamespace(get=lambda _identifier: local_image),
        )
        service = UpdateService(client, catalog_loader=lambda: [])

        result = service.inspect_container(
            container,
            [],
            catalog_error="Nie udało się pobrać katalogu DCC: timeout raw.githubusercontent.com",
            all_containers=[container],
        )

        self.assertFalse(result["update_available"])
        self.assertFalse(result["supported"])
        self.assertFalse(result["auto_update_supported"])
        self.assertTrue(result["check_error"])
        self.assertIn("katalog DCC jest niedostępny", result["message"])
        self.assertIn("raw.githubusercontent.com", result["message"])


class RegistryRetryTests(unittest.TestCase):
    class RegistryError(RuntimeError):
        def __init__(self):
            super().__init__("500 Server Error")
            self.explanation = "TLS handshake timeout while contacting registry-1.docker.io"

    def test_digest_check_retries_transient_registry_timeout(self):
        class Api:
            calls = 0

            def inspect_distribution(self, _image):
                self.calls += 1
                if self.calls == 1:
                    raise RegistryRetryTests.RegistryError()
                return {
                    "Platforms": [{
                        "os": "linux",
                        "architecture": "arm64",
                    }],
                    "Descriptor": {"digest": "sha256:new"},
                }

        api = Api()
        service = UpdateService(SimpleNamespace(api=api))
        image = SimpleNamespace(attrs={
            "Os": "linux",
            "Architecture": "arm64",
            "RepoDigests": ["cloudflare/cloudflared@sha256:old"],
        })
        with patch("updater.time.sleep") as sleep:
            available, message = service._registry_digest("cloudflare/cloudflared:latest", image)
        self.assertTrue(available)
        self.assertIn("Porównano", message)
        self.assertEqual(api.calls, 2)
        sleep.assert_called_once_with(2)

    def test_digest_check_explains_repeated_tls_timeout(self):
        class Api:
            calls = 0

            def inspect_distribution(self, _image):
                self.calls += 1
                raise RegistryRetryTests.RegistryError()

        api = Api()
        service = UpdateService(SimpleNamespace(api=api))
        with patch("updater.time.sleep"):
            available, message = service._registry_digest(
                "cloudflare/cloudflared:latest",
                SimpleNamespace(attrs={"RepoDigests": ["cloudflare/cloudflared@sha256:old"]}),
            )
        self.assertIsNone(available)
        self.assertIn("timeout TLS", message)
        self.assertIn("ponów próbę", message)
        self.assertEqual(api.calls, 3)

    def test_registry_errors_for_missing_arm_manifest_are_actionable(self):
        message = friendly_registry_error("no matching manifest for linux/arm/v7", "Pobieranie obrazu")
        self.assertIn("architektury hosta", message)
        self.assertIn("linux/arm64", message)

    def test_registry_digest_check_reports_missing_host_architecture(self):
        class Api:
            def inspect_distribution(self, _image):
                return {
                    "Platforms": [{
                        "os": "linux",
                        "architecture": "amd64",
                    }],
                    "Descriptor": {"digest": "sha256:index"},
                }

        service = UpdateService(SimpleNamespace(api=Api()))
        available, message = service._registry_digest(
            "example/service:latest",
            SimpleNamespace(attrs={
                "Os": "linux", "Architecture": "arm64", "RepoDigests": ["example/service@sha256:old"],
            }),
        )
        self.assertIsNone(available)
        self.assertIn("linux/arm64", message)
        self.assertIn("Dostępne platformy: linux/amd64", message)

    def test_engine_oci_platforms_without_descriptors_confirm_current_arm64_image(self):
        class Api:
            def inspect_distribution(self, _image):
                return {
                    "Descriptor": {"digest": "sha256:index"},
                    "Platforms": [
                        {"os": "linux", "architecture": "amd64"},
                        {"os": "linux", "architecture": "arm64", "variant": "v8"},
                        {"os": "unknown", "architecture": "unknown"},
                    ],
                }

        service = UpdateService(SimpleNamespace(api=Api()))
        available, message = service._registry_digest(
            "example/service:latest",
            SimpleNamespace(attrs={
                "Os": "linux", "Architecture": "arm64",
                "RepoDigests": ["example/service@sha256:index"],
            }),
        )
        self.assertIs(available, False)
        self.assertIn("Porównano digest", message)

    def test_unknown_platform_metadata_does_not_claim_architecture_is_missing(self):
        class Api:
            def inspect_distribution(self, _image):
                return {
                    "Descriptor": {"digest": "sha256:index"},
                    "Platforms": [{"os": "unknown", "architecture": "unknown"}],
                }

        service = UpdateService(SimpleNamespace(api=Api()))
        available, _message = service._registry_digest(
            "example/service:latest",
            SimpleNamespace(attrs={
                "Os": "linux", "Architecture": "arm64",
                "RepoDigests": ["example/service@sha256:index"],
            }),
        )
        self.assertIs(available, False)

    def test_registry_cache_does_not_share_platform_compatibility_between_architectures(self):
        class Api:
            def inspect_distribution(self, _image):
                return {
                    "Descriptor": {"digest": "sha256:index"},
                    "Platforms": [{"os": "linux", "architecture": "arm64"}],
                }

        service = UpdateService(SimpleNamespace(api=Api()))
        for arch, expected in (("arm64", False), ("amd64", None)):
            with self.subTest(architecture=arch):
                available, _message = service._registry_digest(
                    "example/service:latest",
                    SimpleNamespace(attrs={
                        "Os": "linux", "Architecture": arch,
                        "RepoDigests": ["example/service@sha256:index"],
                    }),
                )
                self.assertIs(available, expected)


class ComposeUpdateSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.compose_file = self.root / "compose.yaml"
        self.compose_file.write_text("services: {}\n", encoding="utf-8")
        self.compose_config = {
            "services": {
                "api": {"image": "example/service:2", "ports": [], "volumes": []},
            },
            "volumes": {},
        }
        self.container = SimpleNamespace(
            id="compose-container-1",
            name="media-api-1",
            status="running",
            attrs={
                "Image": "sha256:local-image",
                "Config": {
                    "Image": "example/service:1",
                    "Labels": {
                        "com.docker.compose.project": "media",
                        "com.docker.compose.service": "api",
                        "com.docker.compose.project.working_dir": str(self.root),
                        "com.docker.compose.project.config_files": str(self.compose_file),
                    },
                },
                "HostConfig": {"NetworkMode": "media_default", "AutoRemove": False},
                "NetworkSettings": {"Networks": {"media_default": {}}},
                "State": {"Status": "running"},
            },
        )
        self.local_image = SimpleNamespace(
            attrs={"RepoTags": ["example/service:1"], "RepoDigests": ["example/service@sha256:old"]},
            tag=lambda _repository, tag: True,
        )

        class Images:
            def __init__(inner_self):
                inner_self.removed = []

            def get(inner_self, _identifier):
                return self.local_image

            def remove(inner_self, reference):
                inner_self.removed.append(reference)

        self.images = Images()
        self.client = SimpleNamespace(images=self.images)
        self.service = UpdateService(self.client, catalog_loader=lambda: [], compose_roots=(str(self.root),))
        self.app = {"image": "example/service:2", "latest_release": "v2"}

    def tearDown(self):
        self.temp.cleanup()

    def _config_call(self, *args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, json.dumps(self.compose_config), "")

    def _scan(self, all_containers=None):
        with patch("updater.subprocess.run", side_effect=self._config_call):
            return self.service.inspect_container(
                self.container,
                [self.app],
                all_containers=all_containers or [self.container],
            )

    def test_compose_service_is_manually_updatable_without_restarting_dependencies(self):
        result = self._scan()
        self.assertTrue(result["supported"])
        self.assertTrue(result["update_available"])
        self.assertFalse(result["auto_update_supported"])
        self.assertEqual(result["target_image"], "example/service:2")

    def test_compose_file_must_declare_the_detected_target(self):
        self.compose_config["services"]["api"]["image"] = "example/service:1"
        result = self._scan()
        self.assertFalse(result["supported"])
        self.assertTrue(result["update_available"])
        self.assertIn("updater nie edytuje plików", result["message"])

    def test_compose_service_with_dependents_is_blocked_with_names(self):
        self.compose_config["services"]["worker"] = {
            "image": "example/worker:1",
            "depends_on": {"api": {"condition": "service_started"}},
            "volumes": [],
        }
        result = self._scan()
        self.assertFalse(result["supported"])
        self.assertIn("worker", result["message"])

    def test_compose_service_sharing_a_docker_network_is_blocked(self):
        other = SimpleNamespace(
            id="worker-container",
            name="media-worker-1",
            attrs={
                "Config": {"Labels": {}},
                "HostConfig": {"NetworkMode": "media_default"},
                "NetworkSettings": {"Networks": {"media_default": {}}},
            },
        )
        result = self._scan([self.container, other])
        self.assertFalse(result["supported"])
        self.assertIn("media-worker-1", result["message"])
        self.assertIn("współdzieli sieć Docker", result["message"])

    def test_compose_service_sharing_a_named_volume_is_blocked(self):
        self.compose_config["services"]["api"]["volumes"] = [
            {"type": "volume", "source": "shared-data", "target": "/data"}
        ]
        self.compose_config["services"]["worker"] = {
            "image": "example/worker:1",
            "volumes": [{"type": "volume", "source": "shared-data", "target": "/data"}],
        }
        result = self._scan()
        self.assertFalse(result["supported"])
        self.assertIn("współdzieli wolumen", result["message"])

    def test_compose_bind_mount_outside_read_only_roots_is_blocked(self):
        self.compose_config["services"]["api"]["volumes"] = [
            {"type": "bind", "source": "/var/lib/media-data", "target": "/data"}
        ]
        result = self._scan()
        self.assertFalse(result["supported"])
        self.assertIn("poza katalogami udostępnionymi", result["message"])

    def test_compose_host_port_conflict_is_reported_before_update(self):
        self.compose_config["services"]["api"]["ports"] = [
            {"target": 8080, "published": "18080", "protocol": "tcp", "host_ip": "0.0.0.0"}
        ]
        other = SimpleNamespace(
            id="other-container",
            name="other-service",
            attrs={
                "Config": {"Labels": {}},
                "HostConfig": {"PortBindings": {"9090/tcp": [{"HostPort": "18080"}]}},
                "NetworkSettings": {"Ports": {}},
            },
        )
        result = self._scan([self.container, other])
        self.assertFalse(result["supported"])
        self.assertIn("other-service", result["message"])
        self.assertIn("18080", result["message"])

    def test_compose_bind_mount_outside_read_only_roots_is_blocked(self):
        self.compose_config["services"]["api"]["volumes"] = [
            {"type": "bind", "source": "/var/lib/media-data", "target": "/data"}
        ]
        result = self._scan()
        self.assertFalse(result["supported"])
        self.assertIn("poza katalogami udostępnionymi", result["message"])

    def test_compose_host_port_conflict_is_reported_before_update(self):
        self.compose_config["services"]["api"]["ports"] = [
            {"target": 8080, "published": "18080", "protocol": "tcp", "host_ip": "0.0.0.0"}
        ]
        other = SimpleNamespace(
            id="other-container",
            name="other-service",
            attrs={
                "Config": {"Labels": {}},
                "HostConfig": {"PortBindings": {"9090/tcp": [{"HostPort": "18080"}]}},
                "NetworkSettings": {"Ports": {}},
            },
        )
        result = self._scan([self.container, other])
        self.assertFalse(result["supported"])
        self.assertIn("other-service", result["message"])
        self.assertIn("18080", result["message"])

    def test_scaled_compose_service_is_blocked(self):
        replica = SimpleNamespace(
            id="compose-container-2",
            attrs={"Config": {"Labels": {
                "com.docker.compose.project": "media",
                "com.docker.compose.service": "api",
            }}},
        )
        result = self._scan([self.container, replica])
        self.assertFalse(result["supported"])
        self.assertIn("replik", result["message"])

    def test_compose_update_pulls_then_updates_only_service_and_rolls_back_on_failure(self):
        commands = []
        rollback_contents = []

        def run(args, **kwargs):
            commands.append(list(args))
            for index, value in enumerate(args[:-1]):
                if value == "--file" and str(args[index + 1]).endswith("rollback.json"):
                    rollback_contents.append(Path(args[index + 1]).read_text(encoding="utf-8"))
            if args[-3:] == ["config", "--format", "json"]:
                return self._config_call(args, **kwargs)
            if "pull" in args:
                return subprocess.CompletedProcess(args, 0, "pobieranie", "")
            if args[-1] == "api":
                if any(str(value).endswith("rollback.json") for value in args):
                    return subprocess.CompletedProcess(args, 0, "restored", "")
                return subprocess.CompletedProcess(args, 1, "", "unhealthy after update")
            return subprocess.CompletedProcess(args, 0, "restored", "")

        with patch("updater.subprocess.run", side_effect=run), patch("updater.time.time", return_value=100):
            with self.assertRaisesRegex(RuntimeError, "przywrócono poprzedni obraz"):
                self.service._update_compose(self.container, "example/service:2", [self.container])

        update_command = commands[2]
        self.assertIn("--no-deps", update_command)
        self.assertIn("--no-build", update_command)
        self.assertIn("--pull", update_command)
        self.assertIn("never", update_command)
        self.assertIn("--wait", update_command)
        rollback_command = commands[3]
        self.assertGreater(rollback_command.count("--file"), 1)
        self.assertIn("dcc-updater-rollback:compose-cont-100", rollback_contents[0])
        self.assertEqual(self.images.removed, ["dcc-updater-rollback:compose-cont-100"])


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
    def test_transient_pull_retries_before_touching_the_running_container(self):
        events = []

        class FakeApi:
            def create_container_config(self, **kwargs):
                return kwargs

        class FakeImages:
            calls = 0

            def pull(self, _image):
                self.calls += 1
                events.append("pull")
                raise RuntimeError("500 Server Error: TLS handshake timeout")

        container = SimpleNamespace(
            id="container-123456",
            name="media",
            attrs={
                "Config": {"Image": "example/service:1", "Labels": {}},
                "HostConfig": {"NetworkMode": "bridge", "AutoRemove": False},
                "NetworkSettings": {"Networks": {"bridge": {}}},
                "State": {"Status": "running"},
                "Mounts": [],
            },
            stop=lambda **_kwargs: events.append("stop"),
        )
        images = FakeImages()
        service = UpdateService(SimpleNamespace(api=FakeApi(), images=images))
        with patch("updater.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "timeout TLS"):
                service.update_one(container, "example/service:2")
        self.assertEqual(images.calls, 3)
        self.assertEqual(events, ["pull", "pull", "pull"])

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
