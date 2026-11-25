import json
import os
import socket
import socketserver
import tempfile
import threading
import time
import unittest
from pathlib import Path

from backend.config import parse_sockets
from backend.kiri_client import KiriError, UnixTransport, VerifiedKiri, identify
from backend.resources import sanitized_logs, stats
from fixtures import ENGINE, VERSION


class ConnectorTest(unittest.TestCase):
    def test_negotiation_pins_supported_range_and_identifies_kiri(self):
        self.assertEqual(identify(ENGINE, VERSION)["api"], "1.47")
        self.assertEqual(identify(ENGINE, {**VERSION, "ApiVersion": "1.45"})["api"], "1.45")
        for version in ({**VERSION, "MinAPIVersion": "1.48"}, {**VERSION, "ApiVersion": "2.0"},
                        {**VERSION, "ApiVersion": "1.25"}, {**VERSION, "MinAPIVersion": None}):
            with self.assertRaisesRegex(KiriError, "api_version"):
                identify(ENGINE, version)
        for header, body in (("Docker/27.5.1", VERSION), (ENGINE, {**VERSION, "Components": []}),
                             (ENGINE, {**VERSION, "Platform": {"Name": "Docker"}})):
            with self.assertRaisesRegex(KiriError, "bad_engine"):
                identify(header, body)

    def test_config_has_no_fallback(self):
        self.assertEqual(parse_sockets("{}"), {})
        self.assertEqual(parse_sockets('{"lab": "/run/kiri/docker.sock"}'), {"lab": "/run/kiri/docker.sock"})
        for path in ("/var/run/docker.sock", "/run/docker.sock", "/private/var/run/docker.sock",
                     "/run../foo/../docker.sock", "//root.sock", "/run//kiri.sock", "https://test.invalid/socket"):
            with self.assertRaises(ValueError):
                parse_sockets(json.dumps({"lab": path}))

    def test_retry_bounded_and_only_for_transport_failures(self):
        class Intermittent:
            attempts = 0

            def get(self, path, limit, expected=None):
                self.attempts += 1
                if self.attempts == 1:
                    raise KiriError("disconnected")
                return ENGINE, "application/json", json.dumps(VERSION).encode()

        transport = Intermittent()
        self.assertEqual(VerifiedKiri(transport).identity["version"], "0.2.2")
        self.assertEqual(transport.attempts, 2)

        class Denied:
            attempts = 0

            def get(self, path, limit, expected=None):
                self.attempts += 1
                raise KiriError("permission_denied")

        transport = Denied()
        with self.assertRaisesRegex(KiriError, "permission_denied"):
            VerifiedKiri(transport)
        self.assertEqual(transport.attempts, 1)

    def test_malformed_logs_and_missing_stats(self):
        with self.assertRaisesRegex(KiriError, "bad_response"):
            sanitized_logs("application/vnd.docker.multiplexed-stream", b"\x01\0\0\0\0\0\0\x20short")
        redacted = sanitized_logs("text/plain", b"safe\n-----BEGIN PRIVATE KEY-----\nhidden\n-----END PRIVATE KEY-----\n")
        self.assertNotIn("hidden", redacted)
        self.assertIn("[REDACTED]", redacted)
        self.assertIsNone(stats({"cpu_stats": {"online_cpus": 8}})["cpu_percent"])
        self.assertIsNone(stats({})["rx_bytes"])


@unittest.skipUnless(os.name == "posix" and hasattr(socket, "AF_UNIX"), "Linux/macOS filesystem Unix socket tests")
class UnixTransportTest(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory(prefix="kiri-sock-")
        self.addCleanup(root.cleanup)
        self.path = Path(root.name).resolve() / "fixture.sock"
        self.response = (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nServer: Kiri/0.2.2 (linux)\r\n"
                         b"Content-Length: 2\r\nConnection: close\r\n\r\n{}")
        self.delay = 0

        class Handler(socketserver.StreamRequestHandler):
            def handle(handler):
                method = handler.rfile.readline()
                if not method.startswith(b"GET /version HTTP/"):
                    return
                while handler.rfile.readline() not in (b"\r\n", b""):
                    pass
                time.sleep(self.delay)
                try:
                    handler.wfile.write(self.response)
                except BrokenPipeError:
                    pass

        server = socketserver.UnixStreamServer(str(self.path), Handler)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)

    def test_explicit_unix_socket_passes_and_rejects_wrong_server(self):
        client = UnixTransport(self.path)
        self.assertEqual(client.get("/version", 100, ENGINE)[2], b"{}")
        with self.assertRaisesRegex(KiriError, "bad_engine"):
            client.get("/version", 100, "Docker/27")
        link = self.path.with_name("alias.sock")
        link.symlink_to(self.path)
        with self.assertRaisesRegex(KiriError, "socket_invalid"):
            UnixTransport(link).get("/version", 100)

    def test_timeout_and_body_limits(self):
        client = UnixTransport(self.path, timeout=.08)
        with self.assertRaisesRegex(KiriError, "large_response"):
            client.get("/version", 1)
        self.delay = .17
        with self.assertRaisesRegex(KiriError, "timeout"):
            client.get("/version", 100)
        self.delay = 0
        with self.assertRaisesRegex(KiriError, "socket_missing"):
            UnixTransport(self.path.with_name("missing.sock")).get("/version", 100)

    def test_truncated_response_is_disconnected(self):
        self.response = self.response.replace(b"Content-Length: 2", b"Content-Length: 8")
        with self.assertRaisesRegex(KiriError, "disconnected"):
            UnixTransport(self.path).get("/version", 100)
