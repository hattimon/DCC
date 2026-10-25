import sys
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from updater import SELF_IMAGE, SELF_LABEL, SELF_UPDATE_HELPER_LABEL, UpdateService


OLD_ID = "sha256:" + "a" * 64
NEW_ID = "sha256:" + "b" * 64
NEW_REFERENCE = "ghcr.io/hattimon/dcc-container-updater@sha256:" + "d" * 64


class SelfUpdateTests(unittest.TestCase):
    def setUp(self):
        self.container = SimpleNamespace(
            id="c" * 64,
            name="dcc-container-updater",
            attrs={
                "Image": OLD_ID,
                "Config": {
                    "Image": SELF_IMAGE,
                    "Labels": {SELF_LABEL: "true"},
                    "ExposedPorts": {"8788/tcp": {}},
                },
                "HostConfig": {
                    "NetworkMode": "bridge",
                    "AutoRemove": False,
                    "Binds": ["/var/run/docker.sock:/var/run/docker.sock"],
                    "PortBindings": {"8788/tcp": [{"HostPort": "8788"}]},
                },
                "NetworkSettings": {"Networks": {"bridge": {}}},
                "State": {"Status": "running"},
                "Mounts": [{
                    "Type": "bind",
                    "Source": "/var/run/docker.sock",
                    "Destination": "/var/run/docker.sock",
                    "RW": True,
                }],
            },
        )
        self.container.stop = Mock()
        self.old_image = SimpleNamespace(id=OLD_ID, attrs={
            "RepoTags": [SELF_IMAGE],
            "RepoDigests": ["ghcr.io/hattimon/dcc-container-updater@sha256:old"],
            "Os": "linux",
            "Architecture": "arm64",
        })
        self.new_image = SimpleNamespace(id=NEW_ID, attrs={
            "RepoTags": [SELF_IMAGE],
            "RepoDigests": [NEW_REFERENCE],
            "Os": "linux",
            "Architecture": "arm64",
        })

        class Api:
            def inspect_distribution(_self, _image):
                return {
                    "Platforms": [
                        {"os": "linux", "architecture": "amd64"},
                        {"os": "linux", "architecture": "arm64", "variant": "v8"},
                        {"os": "unknown", "architecture": "unknown"},
                    ],
                    "Descriptor": {"digest": "sha256:new"},
                }

        class Images:
            def __init__(_self, outer):
                _self.outer = outer
                _self.pulls = []

            def get(_self, image):
                if image in {OLD_ID, SELF_IMAGE}:
                    return _self.outer.old_image if image == OLD_ID else _self.outer.new_image
                if image in {NEW_ID, NEW_REFERENCE}:
                    return _self.outer.new_image
                raise KeyError(image)

            def pull(_self, image):
                _self.pulls.append(image)

        class Containers:
            def __init__(_self, outer):
                _self.outer = outer
                _self.run_args = None
                _self.other_containers = []

            def list(_self, all=False, ignore_removed=False):
                return [_self.outer.container, *_self.other_containers]

            def get(_self, identifier):
                if identifier in {_self.outer.container.id, _self.outer.container.name}:
                    return _self.outer.container
                raise KeyError(identifier)

            def run(_self, *args, **kwargs):
                _self.run_args = (args, kwargs)
                return SimpleNamespace(id="helper-id")

        self.client = SimpleNamespace(api=Api())
        self.client.images = Images(self)
        self.client.containers = Containers(self)
        self.service = UpdateService(self.client)

    def test_panel_detects_new_image_and_offers_manual_update(self):
        result = self.service.check_self_update()
        self.assertTrue(result["checked"])
        self.assertTrue(result["update_available"])
        self.assertTrue(result["supported"])
        self.assertEqual(result["target_image"], SELF_IMAGE)

    def sdk_inventory_with_removed_job(self):
        from docker.errors import NotFound
        from docker.models.containers import ContainerCollection

        attrs={**self.container.attrs,'Id':self.container.id,'Name':'/dcc-container-updater'}
        def inspect(identifier):
            if identifier=='removed-job':raise NotFound('No such container: removed-job')
            return attrs
        self.client.api.containers=Mock(return_value=[{'Id':'removed-job'},{'Id':self.container.id}])
        self.client.api.inspect_container=Mock(side_effect=inspect)
        self.client.containers=ContainerCollection(client=self.client)

    def test_real_sdk_removed_job_does_not_abort_panel_check(self):
        self.sdk_inventory_with_removed_job()
        result=self.service.check_self_update()
        self.assertTrue(result['checked'])
        self.assertTrue(result['update_available'])
        self.assertTrue(result['supported'])
        self.client.api.containers.assert_called_once()
        self.container.stop.assert_not_called()
        self.assertEqual(self.client.images.pulls,[])

    def test_real_sdk_missing_panel_is_not_replaced_by_another_container(self):
        from docker.errors import NotFound
        self.sdk_inventory_with_removed_job()
        self.client.api.inspect_container.side_effect=NotFound('No such container')
        result=self.service.check_self_update()
        self.assertFalse(result['checked'])
        self.assertFalse(result['update_available'])
        self.assertEqual(self.client.images.pulls,[])

    def test_real_sdk_daemon_error_is_not_ignored_as_a_removed_job(self):
        from docker.errors import APIError
        self.sdk_inventory_with_removed_job()
        self.client.api.inspect_container.side_effect=APIError('daemon unavailable')
        with self.assertRaises(APIError):self.service.check_self_update()
        self.assertEqual(self.client.images.pulls,[])

    def test_self_update_uses_new_image_helper_without_stopping_current_process(self):
        progress = []
        result = self.service.start_self_update(progress.append)
        self.assertTrue(result["started"])
        self.assertEqual(self.client.images.pulls, [SELF_IMAGE])
        self.container.stop.assert_not_called()

        args, kwargs = self.client.containers.run_args
        self.assertEqual(args[0], NEW_ID)
        self.assertEqual(kwargs["command"], ["python", "/app/self_update.py", self.container.id, NEW_ID])
        self.assertEqual(kwargs["name"], "dcc-updater-self-update-helper")
        self.assertEqual(kwargs["network_mode"], "none")
        self.assertEqual(kwargs["cap_drop"], ["ALL"])
        self.assertEqual(kwargs["security_opt"], ["no-new-privileges:true"])
        self.assertEqual(kwargs["labels"][SELF_UPDATE_HELPER_LABEL], "true")
        self.assertEqual(kwargs["volumes"]["/var/run/docker.sock"]["bind"], "/var/run/docker.sock")

    def test_current_image_does_not_launch_a_helper_or_pull(self):
        self.client.api.inspect_distribution = lambda _image: {
            "Platforms": [
                {"os": "linux", "architecture": "amd64"},
                {"os": "linux", "architecture": "arm64", "variant": "v8"},
                {"os": "unknown", "architecture": "unknown"},
            ],
            "Descriptor": {"digest": "sha256:old"},
        }
        result = self.service.start_self_update()
        self.assertFalse(result["started"])
        self.assertFalse(result["update_available"])
        self.assertTrue(result["checked"])
        self.assertIn("jest aktualny. Nie ma nowszego obrazu.", result["message"])
        self.assertIsNone(self.client.containers.run_args)
        self.assertEqual(self.client.images.pulls, [])

    def test_registry_failure_leaves_current_panel_running(self):
        self.client.api.inspect_distribution = Mock(side_effect=RuntimeError("TLS handshake timeout"))
        with patch("updater.time.sleep"):
            result = self.service.start_self_update()
        self.assertFalse(result["started"])
        self.assertFalse(result["update_available"])
        self.container.stop.assert_not_called()
        self.assertIsNone(self.client.containers.run_args)
        self.assertEqual(self.client.images.pulls, [])

    def test_conflicting_published_port_blocks_self_update_before_pull(self):
        other = SimpleNamespace(
            id="d" * 64,
            name="other-service",
            attrs={
                "Config": {"Image": "example/service:latest", "Labels": {}},
                "HostConfig": {
                    "NetworkMode": "bridge",
                    "PortBindings": {"8080/tcp": [{"HostPort": "8788"}]},
                },
                "NetworkSettings": {"Networks": {"bridge": {}}},
                "State": {"Status": "exited"},
            },
        )
        self.client.containers.other_containers.append(other)
        result = self.service.start_self_update()
        self.assertTrue(result["update_available"])
        self.assertFalse(result["supported"])
        self.assertFalse(result["started"])
        self.assertIn("other-service", result["message"])
        self.assertEqual(self.client.images.pulls, [])
        self.assertIsNone(self.client.containers.run_args)

    def test_helper_accepts_only_a_self_container_and_official_pinned_image(self):
        with patch.object(self.service, "update_one", return_value="updated") as update_one:
            result = self.service.replace_self_from_helper(self.container.id, NEW_ID)
        self.assertEqual(result, "updated")
        update_one.assert_called_once_with(
            self.container,
            NEW_REFERENCE,
            _allow_self=True,
            _image_already_pulled=True,
            _expected_image_id=NEW_ID,
        )
        with self.assertRaisesRegex(ValueError, "identyfikator obrazu"):
            self.service.replace_self_from_helper(self.container.id, "--invalid")

    def test_helper_will_not_replace_panel_without_a_verified_immutable_named_reference(self):
        self.new_image.attrs['RepoDigests']=[]
        with patch.object(self.service,'update_one') as replace:
            with self.assertRaisesRegex(RuntimeError,'Brak przypiętej nazwy'):
                self.service.replace_self_from_helper(self.container.id,NEW_ID)
            replace.assert_not_called()
        self.container.stop.assert_not_called()

    def test_helper_rejects_digest_resolving_to_an_unexpected_image(self):
        original_get=self.client.images.get
        def resolve(reference):
            return self.old_image if reference==NEW_REFERENCE else original_get(reference)
        with patch.object(self.client.images,'get',side_effect=resolve), patch.object(self.service,'update_one') as replace:
            with self.assertRaisesRegex(RuntimeError,'Brak przypiętej nazwy'):
                self.service.replace_self_from_helper(self.container.id,NEW_ID)
            replace.assert_not_called()

    def test_wrong_replacement_image_is_rolled_back_before_it_can_start(self):
        self.container.rename=Mock()
        self.container.start=Mock()
        self.container.remove=Mock()
        replacement=SimpleNamespace(attrs={'Image':OLD_ID},start=Mock(),stop=Mock(),remove=Mock())
        self.client.api.create_container_from_config=Mock(return_value={'Id':'replacement-id'})
        original_get=self.client.containers.get
        with patch.object(self.client.containers,'get',side_effect=lambda value:replacement if value=='replacement-id' else original_get(value)), \
                patch.object(self.service,'_create_config',return_value={}):
            with self.assertRaises(RuntimeError):
                self.service.update_one(self.container,NEW_REFERENCE,_allow_self=True,_image_already_pulled=True,_expected_image_id=NEW_ID)
        replacement.start.assert_not_called()
        replacement.remove.assert_called_once_with(v=False)
        self.container.start.assert_called_once()
        self.assertEqual(self.container.rename.call_args.args[0],self.container.name)
        self.container.remove.assert_not_called()

    def test_named_digest_is_recognised_by_existing_desktop_store_matching(self):
        source=Path(__file__).resolve().parents[3]/'DockerControlCenter.py'
        if not source.exists():self.skipTest('Desktop source is not included in standalone app checkout')
        names={'normalize_container_image','container_image_name','template_matches_container'}
        module=ast.parse(source.read_text(encoding='utf-8-sig'))
        functions=ast.Module(body=[node for node in module.body if isinstance(node,ast.FunctionDef) and node.name in names],type_ignores=[])
        scope={'ImageTemplate':SimpleNamespace}
        exec(compile(functions,str(source),'exec'),scope)
        template=SimpleNamespace(image=SELF_IMAGE,default_name='dcc-container-updater')
        running=SimpleNamespace(name=template.default_name,attrs={'Config':{'Image':NEW_ID}})
        self.assertFalse(scope['template_matches_container'](template,running))
        running.attrs['Config']['Image']=NEW_REFERENCE
        self.assertTrue(scope['template_matches_container'](template,running))

    def test_manual_container_update_cannot_enable_self_replacement(self):
        with self.assertRaisesRegex(RuntimeError, "samego panelu"):
            self.service.update_one(self.container, NEW_ID)


if __name__ == "__main__":
    unittest.main()
