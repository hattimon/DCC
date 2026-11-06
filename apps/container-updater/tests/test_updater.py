import json
import subprocess
import sys
import tempfile
import unittest
import base64
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from updater import (DCC_REMOTE_STOP_REQUIRED, DCC_REMOTE_UPDATE_LABEL, UpdateService,
                     compare_versions, friendly_registry_error, image_reference, load_catalog, normalized_repository, version_tuple)


class ImageReferenceTests(unittest.TestCase):
    def test_official_web_catalog_updates_older_installs_without_desktop_store_state(self):
        apps = json.loads((Path(__file__).resolve().parents[3] / 'dcc-catalog.json').read_text(encoding='utf-8'))['apps']
        target = next(app['image'] for app in apps if app['name'] == 'DCC Web')
        service = UpdateService.__new__(UpdateService)
        for version in ('0.1.0', '0.1.1', '0.1.2', '0.2.8', '0.2.9'):
            candidate = service._catalog_candidate('ghcr.io/hattimon/dcc-web:' + version, apps)
            self.assertTrue(candidate.available)
            self.assertEqual(candidate.target_image, target)
        self.assertIsNone(service._catalog_candidate(target, apps))

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

    def _dcc_web_https_pair(self):
        network = "dcc-web-https-0123456789-network"
        web = self._container(
            Config={"Image": "ghcr.io/hattimon/dcc-web:0.1.4", "Labels": {}},
            HostConfig={"NetworkMode": "bridge", "AutoRemove": False},
            NetworkSettings={"Networks": {
                "bridge": {},
                network: {"Aliases": ["dcc-web", "dcc-web-upstream"], "IPAMConfig": None},
            }},
            Mounts=[],
        )
        web.name = "dcc-web"
        proxy_name = network.removesuffix("-network")
        proxy = SimpleNamespace(
            id="proxy-id",
            name=proxy_name,
            attrs={
                "Config": {"Image": "caddy:2", "Labels": {"io.dcc.web.proxy": "dcc-web"}},
                "HostConfig": {"NetworkMode": network},
                "NetworkSettings": {"Networks": {network: {}}},
                "Mounts": [],
            },
        )
        return web, proxy, network

    def test_managed_dcc_web_https_network_is_supported_with_its_caddy_peer(self):
        web, proxy, network = self._dcc_web_https_pair()
        updater = self._container()
        updater.id = "updater-id"
        updater.name = "dcc-container-updater"

        self.assertEqual(UpdateService._dcc_web_proxy_attachment(web, [web, proxy, updater]),
                         (network, "dcc-web-https-0123456789", ("dcc-web", "dcc-web-upstream")))
        self.assertIsNone(UpdateService._unsupported_reason(web, [web, proxy, updater]))
        self.assertIsNone(UpdateService.automatic_dependency_blocker(web, [web, proxy, updater]))

    def test_dcc_web_update_accepts_only_verified_stopped_remote_access_peer(self):
        web, proxy, _https = self._dcc_web_https_pair()
        owner = "0123456789abcdef"
        sidecar_name = "dcc-remote-access-" + owner
        ingress, egress = sidecar_name + "-panel", sidecar_name + "-egress"
        web.attrs["NetworkSettings"]["Networks"][ingress] = {"Aliases": ["dcc-remote-panel"]}
        sidecar = SimpleNamespace(id="sidecar-id", name=sidecar_name, attrs={
            "Config": {
                "Image": "docker.io/openziti/zrok2:2.0.9@sha256:" + "a" * 64,
                "Labels": {"io.dcc.remote-access": owner},
            },
            "HostConfig": {"NetworkMode": egress},
            "NetworkSettings": {"Networks": {ingress: {}, egress: {}}},
            "State": {"Status": "exited"},
        })
        inventory = [web, proxy, sidecar]
        self.assertIsNone(UpdateService._unsupported_reason(web, inventory))
        self.assertIn("DCC Remote Access", UpdateService._unsupported_reason(sidecar, inventory))

        sidecar.attrs["State"]["Status"] = "running"
        self.assertIn("Wyłącz dostęp zdalny", UpdateService._unsupported_reason(web, inventory))
        sidecar.attrs["State"]["Status"] = "exited"
        web.attrs["NetworkSettings"]["Networks"]["unrelated-net"] = {}
        self.assertIsNotNone(UpdateService._unsupported_reason(web, inventory))
        del web.attrs["NetworkSettings"]["Networks"]["unrelated-net"]
        self.assertIsNotNone(UpdateService._unsupported_reason(web, [web, proxy]))
        sidecar.attrs["Config"]["Labels"]["io.dcc.remote-access"] = "f" * 16
        self.assertIsNotNone(UpdateService._unsupported_reason(web, inventory))

    def test_custom_peer_or_static_network_config_keeps_dcc_web_update_blocked(self):
        web, proxy, network = self._dcc_web_https_pair()
        peer = SimpleNamespace(
            id="unrelated-id", name="unrelated",
            attrs={"NetworkSettings": {"Networks": {network: {}}}, "Mounts": []},
        )
        self.assertIsNone(UpdateService._dcc_web_proxy_attachment(web, [web, proxy, peer]))
        self.assertIsNotNone(UpdateService._unsupported_reason(web, [web, proxy, peer]))

        web.attrs["NetworkSettings"]["Networks"][network]["IPAMConfig"] = {"IPv4Address": "172.31.0.20"}
        self.assertIsNone(UpdateService._dcc_web_proxy_attachment(web, [web, proxy]))

    def test_unverified_https_network_explains_how_to_update_safely(self):
        web, proxy, _network = self._dcc_web_https_pair()
        proxy.attrs["Config"]["Labels"] = {}
        reason = UpdateService._unsupported_reason(web, [web, proxy])
        self.assertIn("usuń rozszerzenie HTTPS", reason)
        self.assertIn("Samo zatrzymanie Caddy", reason)
        from i18n import translate_text
        self.assertIn("remove the HTTPS extension", translate_text(reason, "en"))

    def test_managed_https_exception_does_not_accept_changed_peers_or_namespaces(self):
        for change in ("label", "image", "peer_network", "namespace", "alias", "other_web"):
            with self.subTest(change=change):
                web, proxy, network = self._dcc_web_https_pair()
                if change == "label":
                    proxy.attrs["Config"]["Labels"]["io.dcc.web.proxy"] = "other-web"
                elif change == "image":
                    proxy.attrs["Config"]["Image"] = "example/caddy:2"
                elif change == "peer_network":
                    proxy.attrs["NetworkSettings"]["Networks"]["bridge"] = {}
                elif change == "namespace":
                    web.attrs["HostConfig"]["NetworkMode"] = "container:other"
                elif change == "alias":
                    web.attrs["NetworkSettings"]["Networks"][network]["Aliases"] = []
                else:
                    web.attrs["Config"]["Image"] = "example/dcc-web:0.1.7"
                self.assertIsNone(UpdateService._dcc_web_proxy_attachment(web, [web, proxy]))
                self.assertIsNotNone(UpdateService._unsupported_reason(web, [web, proxy]))

    def test_registry_update_never_bypasses_runtime_blocker_and_reports_storage(self):
        service = UpdateService(SimpleNamespace(), catalog_loader=lambda: [])
        container = self._container(
            HostConfig={"NetworkMode": "service-net", "AutoRemove": False},
            NetworkSettings={"Networks": {"service-net": {}}},
            Mounts=[{"Type": "volume", "Destination": "/data"},
                    {"Type": "bind", "Destination": "/config"}],
        )
        with patch.object(service, '_registry_digest', return_value=(True, 'new image')):
            result = service.inspect_container(container, [])
        self.assertTrue(result['update_available'])
        self.assertFalse(result['supported'])
        self.assertFalse(result['auto_update_supported'])
        self.assertEqual(result['persistent_mounts'], ['/config', '/data'])
        self.assertIn('sieć', result['message'])

    def test_explicitly_disabled_healthcheck_uses_running_startup_check(self):
        service = UpdateService(SimpleNamespace(), catalog_loader=lambda: [], wait_seconds=1)
        container = self._container(Config={'Healthcheck': {'Test': ['NONE']}})
        container.reload = lambda: None
        with patch('updater.time.monotonic', side_effect=[0, 0, 1]), patch('updater.time.sleep'):
            service._wait_until_healthy(container)

    def test_waits_through_docker_restart_state_until_healthy(self):
        service = UpdateService(SimpleNamespace(), catalog_loader=lambda: [], wait_seconds=10)
        states = iter([
            {"Status": "restarting", "Health": {"Status": "starting"}},
            {"Status": "running", "Health": {"Status": "starting"}},
            {"Status": "running", "Health": {"Status": "healthy"}},
        ])
        container = SimpleNamespace(
            attrs={"Config": {"Healthcheck": {"Test": ["CMD", "true"]}}, "State": {}},
            reload=lambda: container.attrs.update(State=next(states)),
        )
        with patch("updater.time.sleep"):
            service._wait_until_healthy(container)
        self.assertEqual(container.attrs["State"]["Health"]["Status"], "healthy")

    def test_automatic_updates_block_shared_data_and_namespace_dependents(self):
        service = UpdateService(SimpleNamespace(), catalog_loader=lambda: [])
        container = self._container(Mounts=[{'Type': 'volume', 'Name': 'shared', 'Destination': '/data', 'RW': True}])
        peer = SimpleNamespace(id='peer-id', name='reader', attrs={'Mounts': [{'Type': 'volume', 'Name': 'shared', 'Destination': '/state', 'RW': False}]})
        self.assertIn('trwałe dane', service.automatic_dependency_blocker(container, [container, peer]))
        peer.attrs = {'HostConfig': {'NetworkMode': 'container:' + container.id}}
        self.assertIn('przestrzeń', service.automatic_dependency_blocker(container, [container, peer]))
        peer.attrs = {'Mounts': [{'Type': 'volume', 'Name': 'different', 'Destination': '/state', 'RW': True}]}
        self.assertIsNone(service.automatic_dependency_blocker(container, [container, peer]))

    def test_automatic_updates_detect_overlapping_bind_paths(self):
        service = UpdateService(SimpleNamespace(), catalog_loader=lambda: [])
        container = self._container(Mounts=[{'Type': 'bind', 'Source': '/srv/app', 'Destination': '/data', 'RW': True}])
        peer = SimpleNamespace(id='peer-id', name='dependent', attrs={'Mounts': [{'Type': 'bind', 'Source': '/srv/app/database', 'Destination': '/state', 'RW': False}]})
        self.assertIsNotNone(service.automatic_dependency_blocker(container, [container, peer]))
        peer.attrs['Mounts'][0]['Source'] = '/srv/application'
        self.assertIsNone(service.automatic_dependency_blocker(container, [container, peer]))

    def test_updater_read_only_host_observation_does_not_block_application_update(self):
        container = self._container(Mounts=[{
            'Type': 'bind', 'Source': '/root/.n8n', 'Destination': '/home/node/.n8n', 'RW': True,
        }])
        panel = SimpleNamespace(id='panel-id', name='dcc-container-updater', attrs={'Mounts': [{
            'Type': 'bind', 'Source': '/root', 'Destination': '/root', 'RW': False,
        }]})
        self.assertIsNone(UpdateService.automatic_dependency_blocker(container, [container, panel]))
        panel.name = 'renamed-panel'
        panel.attrs['Config'] = {'Labels': {'com.hattimon.dcc-updater': 'true'}}
        self.assertIsNone(UpdateService.automatic_dependency_blocker(container, [container, panel]))

    def test_updater_observation_exception_requires_explicit_read_only_bind_mount(self):
        container = self._container(Mounts=[{
            'Type': 'bind', 'Source': '/root/.n8n', 'Destination': '/data', 'RW': True,
        }])
        for permission in (True, None, 'false'):
            with self.subTest(permission=permission):
                mount = {'Type': 'bind', 'Source': '/root', 'Destination': '/root'}
                if permission is not None:
                    mount['RW'] = permission
                panel = SimpleNamespace(id='panel-id', name='dcc-container-updater', attrs={'Mounts': [mount]})
                self.assertIn('trwałe dane', UpdateService.automatic_dependency_blocker(container, [container, panel]))

    def test_read_only_application_consumer_remains_a_dependency(self):
        container = self._container(Mounts=[{
            'Type': 'bind', 'Source': '/root/.n8n', 'Destination': '/data', 'RW': True,
        }])
        reader = SimpleNamespace(id='reader-id', name='application-reader', attrs={'Mounts': [{
            'Type': 'bind', 'Source': '/root', 'Destination': '/root', 'RW': False,
        }]})
        self.assertIn('application-reader', UpdateService.automatic_dependency_blocker(container, [container, reader]))

    def test_updater_named_volume_sharing_remains_a_dependency(self):
        container = self._container(Mounts=[{
            'Type': 'volume', 'Name': 'shared', 'Destination': '/data', 'RW': True,
        }])
        panel = SimpleNamespace(id='panel-id', name='dcc-container-updater', attrs={'Mounts': [{
            'Type': 'volume', 'Name': 'shared', 'Destination': '/observe', 'RW': False,
        }]})
        self.assertIn('trwałe dane', UpdateService.automatic_dependency_blocker(container, [container, panel]))

    def test_updater_read_only_mount_does_not_hide_explicit_or_other_dependencies(self):
        container = self._container(Mounts=[{
            'Type': 'bind', 'Source': '/root/.n8n', 'Destination': '/data', 'RW': True,
        }])
        panel = SimpleNamespace(id='panel-id', name='dcc-container-updater', attrs={'Mounts': [{
            'Type': 'bind', 'Source': '/root', 'Destination': '/root', 'RW': False,
        }]})
        panel.attrs['HostConfig'] = {'VolumesFrom': [container.id + ':ro']}
        self.assertIn('VolumesFrom', UpdateService.automatic_dependency_blocker(container, [container, panel]))
        panel.attrs['HostConfig'] = {'NetworkMode': 'container:' + container.id}
        self.assertIn('przestrzeń', UpdateService.automatic_dependency_blocker(container, [container, panel]))
        panel.attrs['HostConfig'] = {}
        peer = SimpleNamespace(id='peer-id', name='actual-dependent', attrs={'Mounts': [{
            'Type': 'bind', 'Source': '/root/.n8n', 'Destination': '/data', 'RW': True,
        }]})
        self.assertIn('actual-dependent', UpdateService.automatic_dependency_blocker(container, [container, panel, peer]))

    def test_host_monitor_read_only_ancestor_views_do_not_share_application_data(self):
        container = self._container(Mounts=[{
            'Type': 'bind', 'Source': '/mnt/nvme/apps/n8n', 'Destination': '/data', 'RW': True,
        }])
        monitor = SimpleNamespace(id='monitor-id', name='system-monitor', attrs={
            'HostConfig': {'PidMode': 'host'},
            'Mounts': [
                {'Type': 'bind', 'Source': '/', 'Destination': '/host', 'RW': False},
                {'Type': 'bind', 'Source': '/mnt/nvme', 'Destination': '/disk', 'RW': False},
            ],
        })
        self.assertIsNone(UpdateService.automatic_dependency_blocker(container, [container, monitor]))
        monitor.attrs['HostConfig'] = {}
        self.assertIn('system-monitor', UpdateService.automatic_dependency_blocker(container, [container, monitor]))

    def test_host_monitor_direct_data_mounts_and_writable_views_remain_blocked(self):
        container = self._container(Mounts=[{
            'Type': 'bind', 'Source': '/srv/data', 'Destination': '/data', 'RW': True,
        }])
        for source, writable in (('/srv/data', False), ('/srv/data/database', False), ('/srv', True)):
            with self.subTest(source=source, writable=writable):
                monitor = SimpleNamespace(id='monitor-id', name='system-monitor', attrs={
                    'HostConfig': {'PidMode': 'host'},
                    'Mounts': [
                        {'Type': 'bind', 'Source': '/', 'Destination': '/host', 'RW': False},
                        {'Type': 'bind', 'Source': source, 'Destination': '/application', 'RW': writable},
                    ],
                })
                self.assertIn('system-monitor', UpdateService.automatic_dependency_blocker(container, [container, monitor]))

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


class LocalImageLookupTests(unittest.TestCase):
    def test_missing_sdk_image_property_does_not_raise_or_resolve_a_moved_tag(self):
        from docker.errors import ImageNotFound
        from docker.models.containers import Container

        image_id = 'sha256:' + 'a' * 64
        images = Mock()
        images.get.side_effect = ImageNotFound('original image metadata is missing')
        client = SimpleNamespace(images=images)
        container = Container(attrs={'Image': image_id, 'Config': {'Image': 'example/web:latest'}}, client=client)

        self.assertIsNone(UpdateService(client)._local_image(container))
        self.assertEqual([call.args[0] for call in images.get.call_args_list], [image_id, 'a' * 64])
        images.pull.assert_not_called()

    def test_cached_image_fallback_is_preserved_when_direct_lookup_fails(self):
        image = SimpleNamespace(id='original-image')
        images = SimpleNamespace(get=Mock(side_effect=RuntimeError('lookup unavailable')))
        container = SimpleNamespace(attrs={'Image': 'original-image'}, image=image)
        self.assertIs(UpdateService(SimpleNamespace(images=images))._local_image(container), image)


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

    def test_update_uses_new_image_command_when_old_command_was_its_default(self):
        old_entrypoint = ["/usr/bin/tini", "-g", "--"]
        self.container.attrs["Config"].update(
            Cmd=["sh", "/app/ops/public-start.sh"],
            Entrypoint=old_entrypoint,
        )
        self.container.image = SimpleNamespace(attrs={"Config": {
            "Cmd": ["sh", "/app/ops/public-start.sh"],
            "Entrypoint": old_entrypoint,
        }})
        target_config = {
            "Cmd": ["sh", "/app/ops/start.sh"],
            "Entrypoint": old_entrypoint,
        }

        config = self.service._create_config(
            self.container,
            "ghcr.io/hattimon/cinema-hub:1.3.15",
            target_image_config=target_config,
        )

        self.assertEqual(config["command"], ["sh", "/app/ops/start.sh"])
        self.assertEqual(config["entrypoint"], old_entrypoint)
        data_mount = next(m for m in config["host_config"]["Mounts"] if m["Target"] == "/data")
        self.assertEqual(data_mount["Source"], "service-data")

    def test_update_preserves_a_custom_command_override(self):
        old_entrypoint = ["/usr/bin/tini", "-g", "--"]
        custom_entrypoint = ["/bin/custom-entrypoint"]
        self.container.attrs["Config"].update(
            Cmd=["node", "custom-entry.mjs"],
            Entrypoint=custom_entrypoint,
        )
        self.container.image = SimpleNamespace(attrs={"Config": {
            "Cmd": ["sh", "/app/ops/public-start.sh"],
            "Entrypoint": old_entrypoint,
        }})

        config = self.service._create_config(
            self.container,
            "ghcr.io/hattimon/cinema-hub:1.3.15",
            target_image_config={
                "Cmd": ["sh", "/app/ops/start.sh"],
                "Entrypoint": old_entrypoint,
            },
        )

        self.assertEqual(config["command"], ["node", "custom-entry.mjs"])
        self.assertEqual(config["entrypoint"], custom_entrypoint)

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


class DccWebHttpsUpdateTests(unittest.TestCase):
    def _run_update(self, fail_replacement_start=False, active_tunnel=False):
        web, proxy, network_name = ContainerSafetyTests()._dcc_web_https_pair()
        events = []

        class FakeApi:
            def create_container_config(self, **kwargs):
                return kwargs

            def create_container_from_config(self, _config, name):
                events.append(("create", name))
                return {"Id": "replacement-id"}

        class FakeNetwork:
            def disconnect(self, container):
                events.append(("disconnect", container.name))

            def connect(self, container, aliases):
                events.append(("connect", container.name, aliases))

        replacement = SimpleNamespace(
            id="replacement-id", name="dcc-web",
            attrs={"Config": {"Image": "ghcr.io/hattimon/dcc-web:0.1.6"},
                   "Image": "sha256:new", "State": {"Status": "running"}},
            start=None,
            stop=lambda timeout: events.append(("stop-replacement", timeout)),
            remove=lambda v=False, force=False: events.append(("remove-replacement", v, force)),
        )

        class FakeContainers:
            def list(self, all=False, ignore_removed=False):
                return [web, proxy]

            def get(self, identifier):
                self.asserted_id = identifier
                return replacement

        class FakeImages:
            def pull(self, image):
                events.append(("pull", image))

            def get(self, _image):
                return SimpleNamespace(id="sha256:new", attrs={"Config": {"Labels": {DCC_REMOTE_UPDATE_LABEL: "1"}}})

        def start_replacement():
            events.append(("start-replacement",))
            if fail_replacement_start:
                raise RuntimeError("replacement failed")

        replacement.start = start_replacement

        web.stop = lambda timeout: events.append(("stop-old", timeout))
        web.rename = lambda name: (events.append(("rename-old", name)), setattr(web, "name", name))
        web.start = lambda: events.append(("start-old",))
        web.remove = lambda v=False: events.append(("remove-old", v))
        client = SimpleNamespace(
            api=FakeApi(), containers=FakeContainers(), images=FakeImages(),
            networks=SimpleNamespace(get=lambda name: self.assertEqual(name, network_name) or FakeNetwork()),
        )
        service = UpdateService(client, wait_seconds=1)
        with ExitStack() as stack:
            stack.enter_context(patch.object(service, "_wait_until_healthy", side_effect=lambda item: events.append(("healthy", item.id))))
            if active_tunnel:
                stack.enter_context(patch.object(service, "_unsupported_reason", return_value=DCC_REMOTE_STOP_REQUIRED))
                stack.enter_context(patch.object(service, "_dcc_web_attachments", return_value=(
                    {network_name: ("dcc-web", "dcc-web-upstream")}, (network_name, Mock(), ()),
                )))
                stack.enter_context(patch.object(service, "_verify_remote_networks"))
                stack.enter_context(patch.object(service, "_remote_update_control", side_effect=(
                    lambda item, operation, *args: events.append((operation, item.id, args)) or True
                )))
            if fail_replacement_start:
                with self.assertRaisesRegex(RuntimeError, "przywrócono poprzedni kontener"):
                    service.update_one(web, "ghcr.io/hattimon/dcc-web:0.1.6")
                return events, web
            message = service.update_one(web, "ghcr.io/hattimon/dcc-web:0.1.6")
        return message, events

    def test_update_moves_the_managed_proxy_alias_to_the_replacement(self):
        message, events = self._run_update()

        self.assertIn("Zaktualizowano", message)
        self.assertIn(("disconnect", "dcc-backup-0123456789"), events)
        self.assertIn(("connect", "dcc-web", ["dcc-web", "dcc-web-upstream"]), events)
        self.assertLess(events.index(("disconnect", "dcc-backup-0123456789")), events.index(("create", "dcc-web")))
        self.assertLess(events.index(("create", "dcc-web")), events.index(("connect", "dcc-web", ["dcc-web", "dcc-web-upstream"])))

    def test_failed_replacement_restores_the_original_https_alias_and_container(self):
        events, web = self._run_update(fail_replacement_start=True)
        self.assertEqual(web.name, "dcc-web")
        self.assertIn(("connect", "dcc-backup-0123456789", ["dcc-web", "dcc-web-upstream"]), events)
        self.assertIn(("rename-old", "dcc-web"), events)
        self.assertIn(("start-old",), events)

    def test_approved_tunnel_resumes_after_replacement_or_rollback_is_healthy(self):
        for rollback in (False, True):
            with self.subTest(rollback=rollback):
                result = self._run_update(fail_replacement_start=rollback, active_tunnel=True)
                events = result[0] if rollback else result[1]
                pause = next(event for event in events if event[0] == "pause")
                resume = next(event for event in events if event[0] == "resume")
                self.assertEqual(pause[2][0], resume[2][0])
                self.assertEqual(pause[2][1], "sha256:new")
                self.assertEqual(resume[1], pause[1] if rollback else "replacement-id")
                self.assertLess(events.index(pause), next(i for i, event in enumerate(events) if event[0] == "stop-old"))
                self.assertLess(events.index(("healthy", resume[1])), events.index(resume))

class UpdateRollbackTests(unittest.TestCase):
    class DockerNotFound(Exception):
        status_code = 404

    def _visibility_fixture(self, missing_attempts, replacement_start_error=None, replacement_logs=b""):
        events = []

        class FakeApi:
            def create_container_config(self, **kwargs):
                return kwargs

            def create_container_from_config(self, config, name):
                events.append(("create", name))
                self.created_config = config
                return {"Id": "replacement-123456"}

            def remove_container(self, container_id, v=False, force=False):
                events.append(("remove-created-id", container_id, v, force))
                raise UpdateRollbackTests.DockerNotFound("already removed")

        class FakeImages:
            def pull(self, image):
                events.append(("pull", image))

            def get(self, image):
                events.append(("get-image", image))
                return SimpleNamespace(id="target-image", attrs={"Config": {
                    "Cmd": ["sh", "/app/ops/start.sh"],
                    "Entrypoint": ["/usr/bin/tini", "-g", "--"],
                    "Labels": {},
                }})

        old = SimpleNamespace(
            id="original-123456",
            name="cinema-hub",
            attrs={
                "Config": {
                    "Image": "ghcr.io/hattimon/cinema-hub:1.3.5",
                    "Cmd": ["sh", "/app/ops/public-start.sh"],
                    "Entrypoint": ["/usr/bin/tini", "-g", "--"],
                    "Labels": {},
                },
                "HostConfig": {"NetworkMode": "bridge", "AutoRemove": False},
                "NetworkSettings": {"Networks": {"bridge": {}}},
                "State": {"Status": "running"},
                "Mounts": [],
            },
            image=SimpleNamespace(attrs={"Config": {
                "Cmd": ["sh", "/app/ops/public-start.sh"],
                "Entrypoint": ["/usr/bin/tini", "-g", "--"],
            }}),
        )

        def stop(timeout):
            events.append(("stop-old", timeout))
            old.attrs["State"]["Status"] = "exited"

        def rename(name):
            events.append(("rename-old", name))
            old.name = name

        def start():
            events.append(("start-old",))
            old.attrs["State"]["Status"] = "running"

        old.stop = stop
        old.rename = rename
        old.start = start
        old.remove = lambda v=False: events.append(("remove-old", v))
        def start_replacement():
            events.append(("start-replacement",))
            if replacement_start_error is not None:
                raise replacement_start_error

        replacement = SimpleNamespace(
            id="replacement-123456",
            name="cinema-hub",
            attrs={"Config": {"Image": "ghcr.io/hattimon/cinema-hub:1.3.15", "Healthcheck": None},
                   "State": {"Status": "running"}},
            start=start_replacement,
            stop=lambda timeout: events.append(("stop-replacement", timeout)),
            remove=lambda v=False, force=False: events.append(("remove-replacement", v, force)),
            reload=lambda: None,
            logs=lambda tail=25: replacement_logs,
        )

        class FakeContainers:
            attempts = 0

            def list(self, all=False, ignore_removed=False):
                return [old]

            def get(self, identifier):
                self.attempts += 1
                events.append(("inspect-created-id", identifier))
                if self.attempts <= missing_attempts:
                    raise UpdateRollbackTests.DockerNotFound("not visible yet")
                return replacement

        api = FakeApi()
        containers = FakeContainers()
        containers.replacement = replacement
        service = UpdateService(SimpleNamespace(api=api, containers=containers, images=FakeImages()))
        return service, old, containers, events

    def test_restart_timeout_reports_startup_logs_and_redacts_secrets(self):
        service, old, containers, events = self._visibility_fixture(
            missing_attempts=0,
            replacement_logs=b"database connection refused token=PRIVATE_STARTUP_TOKEN",
        )
        data_mount = {"Type": "volume", "Name": "cinema-hub_cinema-state", "Destination": "/data", "RW": True}
        old.attrs["Mounts"] = [data_mount]
        service.wait_seconds = 1
        containers.replacement.attrs["State"]["Status"] = "restarting"
        with patch("updater.time.monotonic", side_effect=[0, 0, 2]), patch("updater.time.sleep"):
            with self.assertRaises(RuntimeError) as raised:
                service.update_one(old, "ghcr.io/hattimon/cinema-hub:1.3.15")

        message = str(raised.exception)
        self.assertIn("status: restarting", message)
        self.assertIn("database connection refused", message)
        self.assertIn("token=[redacted]", message)
        self.assertNotIn("PRIVATE_STARTUP_TOKEN", message)
        self.assertEqual(old.attrs["Mounts"], [data_mount])
        self.assertIn(("remove-replacement", False, True), events)
        self.assertNotIn(("remove-old", False), events)
        self.assertIn(("start-old",), events)
        replacement_config = service.client.api.created_config
        self.assertEqual(replacement_config["command"], ["sh", "/app/ops/start.sh"])
        self.assertEqual(
            next(m for m in replacement_config["host_config"]["Mounts"] if m["Target"] == "/data")["Source"],
            "cinema-hub_cinema-state",
        )

    def test_retries_transient_404_after_replacement_creation(self):
        service, old, containers, events = self._visibility_fixture(missing_attempts=1)
        with patch("updater.time.sleep") as sleep, patch.object(service, "_wait_until_healthy"):
            result = service.update_one(old, "ghcr.io/hattimon/cinema-hub:1.3.15")

        self.assertIn("Zaktualizowano", result)
        self.assertEqual(containers.attempts, 2)
        sleep.assert_called_once_with(0.1)
        self.assertIn(("remove-old", False), events)
        self.assertNotIn(("remove-created-id", "replacement-123456", False, True), events)

    def test_cleans_created_container_before_restoring_after_persistent_404(self):
        service, old, containers, events = self._visibility_fixture(missing_attempts=99)
        with patch("updater.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "przywrócono poprzedni kontener.*nie udostępnił go do odczytu"):
                service.update_one(old, "ghcr.io/hattimon/cinema-hub:1.3.15")

        self.assertEqual(containers.attempts, 5)
        self.assertIn(("remove-created-id", "replacement-123456", False, True), events)
        self.assertLess(events.index(("remove-created-id", "replacement-123456", False, True)), events.index(("rename-old", "cinema-hub")))
        self.assertIn(("start-old",), events)

    def test_rollback_reports_sanitized_original_failure(self):
        service, old, _containers, events = self._visibility_fixture(
            missing_attempts=0,
            replacement_start_error=RuntimeError(
                'startup rejected token=PRIVATE_TOKEN password="PRIVATE PASSWORD" Authorization: Bearer PRIVATE_BEARER'
            ),
            replacement_logs=b"startup rejected token=PRIVATE_LOG_TOKEN",
        )
        with self.assertRaises(RuntimeError) as raised:
            service.update_one(old, "ghcr.io/hattimon/cinema-hub:1.3.15")

        message = str(raised.exception)
        self.assertIn("RuntimeError: startup rejected", message)
        self.assertIn("token=[redacted]", message)
        self.assertIn("password=[redacted]", message)
        self.assertNotIn("PRIVATE", message)
        self.assertIn("logi startowe=startup rejected token=[redacted]", message)
        self.assertIn(("start-old",), events)

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

            def get(self, image):
                return SimpleNamespace(id="target-image", attrs={"Config": {}})

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
            def list(self, all=False, ignore_removed=False):
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
