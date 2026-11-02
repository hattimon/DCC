import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import install


class InstallerPortTests(unittest.TestCase):
    def test_local_context_endpoints_are_allowed_and_remote_contexts_are_rejected(self):
        for endpoint in (
            "unix:///var/run/docker.sock",
            "npipe:////./pipe/docker_engine",
            "tcp://127.0.0.1:2376",
            "tcp://localhost:2376",
        ):
            with self.subTest(endpoint=endpoint):
                install.validate_local_docker_endpoint(endpoint)
        for endpoint in ("ssh://docker.example", "tcp://192.0.2.10:2376", ""):
            with self.subTest(endpoint=endpoint), self.assertRaisesRegex(RuntimeError, "context is remote"):
                install.validate_local_docker_endpoint(endpoint)

    def test_docker_port_scan_uses_published_tcp_ports_and_ignores_udp(self):
        output = (
            "0.0.0.0:8789->8789/tcp, :::8789->8789/tcp\n"
            "127.0.0.1:8123->8123/tcp, 0.0.0.0:5353->53/udp"
        )
        self.assertEqual(install.docker_published_tcp_ports(output), {8123, 8789})

    def test_port_selection_skips_container_and_operating_system_conflicts(self):
        available = {8791, 8792}
        selected = install.choose_host_port(
            {8789, 8791}, start=8789, end=8792, is_available=lambda port: port in available,
        )
        self.assertEqual(selected, 8792)

    def test_port_selection_fails_when_scan_range_is_full(self):
        with self.assertRaisesRegex(RuntimeError, "No free localhost port"):
            install.choose_host_port({8789, 8790}, start=8789, end=8790, is_available=lambda _port: True)

    def test_saved_port_is_reused_only_when_still_available(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "compose.env"
            env_file.write_text("DCC_WEB_PORT=8790\n", encoding="utf-8")
            with patch.object(install, "active_container_ports", return_value=set()), patch.object(
                install, "host_port_is_available", return_value=True,
            ):
                self.assertEqual(install.selected_port(env_file), 8790)

    def test_saved_port_yields_to_existing_container(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "compose.env"
            env_file.write_text("DCC_WEB_PORT=8790\n", encoding="utf-8")
            with patch.object(install, "active_container_ports", return_value={8790}), patch.object(
                install, "host_port_is_available", return_value=True,
            ):
                self.assertEqual(install.selected_port(env_file), 8789)

    def test_env_update_preserves_other_values_and_has_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "compose.env"
            env_file.write_text("OTHER=value\nDCC_WEB_PORT=8789\n", encoding="utf-8")
            install.write_port(env_file, 8790)
            self.assertEqual(env_file.read_text(encoding="utf-8"), "OTHER=value\nDCC_WEB_PORT=8790\n")
            if os.name != "nt":
                self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)

    def test_compose_manifest_binds_loopback_and_supports_scanned_port(self):
        manifest = install.COMPOSE_FILE.read_text(encoding="utf-8")
        self.assertIn("ghcr.io/hattimon/dcc-web:0.1.4", manifest)
        self.assertIn("127.0.0.1:${DCC_WEB_PORT:-8789}:8789", manifest)


if __name__ == "__main__":
    unittest.main()
