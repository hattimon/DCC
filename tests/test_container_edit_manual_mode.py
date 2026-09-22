import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import DockerControlCenter as dcc


class _FakeContainer:
    def __init__(self, name, attrs):
        self.name = name
        self.attrs = attrs

    def reload(self):
        return None


class _FakeContainers:
    def list(self, all=True):
        return []


class _FakeClient:
    def __init__(self):
        self.containers = _FakeContainers()


class ContainerEditManualModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_edit_mode_keeps_real_container_fields_when_catalog_refreshes(self):
        initial_args = [
            "run",
            "-d",
            "--name",
            "hqtrader-api",
            "-p",
            "8000:8000",
            "-e",
            "MODE=prod",
            "hqtrader-api:local",
        ]
        refreshed = dcc.default_image_catalog()[:2]

        with patch.object(dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]), patch.object(
            dcc, "load_cached_deployment_catalog", return_value=[]
        ), patch.object(dcc, "save_cached_deployment_catalog"):
            dialog = dcc.NewContainerDialog(
                _FakeClient(),
                dcc.TEXTS["EN"],
                initial_args=initial_args,
                edit_mode=True,
                existing_name="hqtrader-api",
                lang="EN",
            )

            self.assertTrue(dialog.manual_configuration_mode)
            self.assertEqual(dialog.catalog_list.currentRow(), -1)
            self.assertEqual(dialog.name_edit.text(), "hqtrader-api")
            self.assertEqual(dialog.image_edit.text(), "hqtrader-api:local")
            self.assertEqual(dialog.cport_edit.text(), "8000")
            self.assertEqual(dialog.hport_edit.text(), "8000")
            self.assertIn("hqtrader-api", dialog.app_title_label.text())

            dialog.on_external_catalog_refresh_finished(refreshed, [])

            self.assertTrue(dialog.manual_configuration_mode)
            self.assertEqual(dialog.catalog_list.currentRow(), -1)
            self.assertEqual(dialog.name_edit.text(), "hqtrader-api")
            self.assertEqual(dialog.image_edit.text(), "hqtrader-api:local")
            self.assertIn("hqtrader-api", dialog.app_title_label.text())
            dialog.close()

    def test_new_container_starts_in_store_and_can_switch_to_manual_mode(self):
        with patch.object(dcc, "load_deployment_repository_sources", return_value=[dcc.DEFAULT_DEPLOYMENT_REPOSITORY]), patch.object(
            dcc, "load_cached_deployment_catalog", return_value=[]
        ):
            dialog = dcc.NewContainerDialog(_FakeClient(), dcc.TEXTS["EN"], lang="EN")
            self.assertFalse(dialog.manual_configuration_mode)
            self.assertEqual(dialog.catalog_list.currentRow(), 0)
            self.assertTrue(dialog.image_edit.text())

            dialog.select_manual_configuration()
            self.assertTrue(dialog.manual_configuration_mode)
            self.assertEqual(dialog.catalog_list.currentRow(), -1)
            self.assertIn("Custom container", dialog.app_title_label.text())
            dialog.close()

    def test_reconstructed_run_args_preserve_runtime_configuration(self):
        container = _FakeContainer(
            "demo",
            {
                "Config": {
                    "Image": "example/demo:latest",
                    "Env": ["A=B"],
                    "Labels": {"custom.label": "yes"},
                    "User": "1000:1000",
                    "WorkingDir": "/app",
                    "Entrypoint": ["/entry.sh", "--serve"],
                    "Cmd": ["--port", "8080"],
                },
                "HostConfig": {
                    "RestartPolicy": {"Name": "unless-stopped"},
                    "NetworkMode": "demo-net",
                    "Privileged": False,
                    "ReadonlyRootfs": True,
                    "AutoRemove": False,
                    "CapAdd": ["NET_ADMIN"],
                    "CapDrop": [],
                    "Dns": ["1.1.1.1"],
                    "ExtraHosts": ["host.docker.internal:host-gateway"],
                    "Devices": [],
                    "Memory": 536870912,
                    "NanoCpus": 1500000000,
                    "ShmSize": 134217728,
                    "Tmpfs": {"/tmp": "rw,size=64m"},
                },
                "Mounts": [
                    {
                        "Type": "volume",
                        "Name": "demo-data",
                        "Source": "/var/lib/docker/volumes/demo-data/_data",
                        "Destination": "/data",
                        "Mode": "rw",
                        "RW": True,
                    }
                ],
                "NetworkSettings": {
                    "Ports": {"8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "18080"}]}
                },
            },
        )

        args = dcc.MainWindow.container_run_args(None, container)

        self.assertIn("demo-data:/data:rw", args)
        self.assertNotIn("/var/lib/docker/volumes/demo-data/_data:/data:rw", args)
        self.assertIn("demo-net", args)
        self.assertIn("--read-only", args)
        self.assertIn("--entrypoint", args)
        image_index = args.index("example/demo:latest")
        self.assertLess(args.index("--entrypoint"), image_index)
        self.assertEqual(args[image_index + 1 :], ["--serve", "--port", "8080"])


if __name__ == "__main__":
    unittest.main()
