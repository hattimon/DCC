"""Isolated Kiri discovery tests; never connect to a real host socket."""
import unittest

from backend.discovery import discover
from backend.kiri_client import Connector
from fixtures import FixtureTransport


class DiscoveryTest(unittest.TestCase):
    def test_empty_socket_map_needs_host_configuration(self):
        self.assertEqual(discover(Connector({}, FixtureTransport)),
                         {"status": "unconfigured", "reason": "transport_not_configured"})

    def test_verified_kiri_and_inventory_required(self):
        ready = discover(Connector({"docker": "docker", "local": "local"}, FixtureTransport))
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["endpoint"], "local")
        self.assertEqual(ready["engine"]["version"], "0.2.2")
        self.assertEqual(discover(Connector({"docker": "docker"}, FixtureTransport)),
                         {"status": "blocked", "reason": "bad_engine"})

    def test_permission_error_overrides_an_offline_alias(self):
        self.assertEqual(discover(Connector({"offline": "offline", "denied": "denied"}, FixtureTransport)),
                         {"status": "blocked", "reason": "permission_denied"})
