import importlib
import json
import sys
import unittest
from unittest.mock import patch

from tools.catalog_review import REPO, candidate, prepare


class CatalogTest(unittest.TestCase):
    def test_candidate_replaces_only_kiri_and_is_idempotent(self):
        raw = (REPO / "dcc-catalog.json").read_text(encoding="utf-8")
        base = json.loads(raw)
        preview = prepare(raw)
        final = json.loads(preview)
        entry = candidate()
        self.assertEqual(final["apps"].count(entry), 1)
        self.assertEqual(
            [item for item in final["apps"] if item["name"] != entry["name"]],
            [item for item in base["apps"] if item["name"] != entry["name"]],
        )
        self.assertEqual(prepare(preview), preview)
        self.assertTrue(entry["homepage_url"].endswith("/DCC/kiri-manager/"))

    def test_existing_web_store_keeps_loopback_after_port_conflict(self):
        with patch.object(sys, "path", [str(REPO / "apps/dcc-web"), *sys.path]):
            catalogs = importlib.import_module("catalogs")
            ports = importlib.import_module("ports")

        class Engine:
            profile = {"kind": "local"}

            def info(self):
                return {"Architecture": "x86_64"}

            def containers(self):
                return [{"Names": "already-used", "Ports": "127.0.0.1:8796->8796/tcp"}]

        plan = catalogs.install_plan(candidate(), {"auto_port": True}, Engine())
        self.assertIn("127.0.0.1:8797:8796", plan["args"])
        self.assertNotIn("8797:8796", plan["args"])
        self.assertEqual(plan["port_changes"], [{"from": 8796, "to": 8797, "protocol": "tcp"}])
        container = {"Names": plan["name"], "Ports": "127.0.0.1:8797->8796/tcp", "Image": candidate()["image"]}
        links = ports.enrich_containers([container], Engine.profile)[0]["PanelLinks"]
        self.assertEqual(links[0]["url"], "http://127.0.0.1:8797")
        self.assertTrue(links[0]["loopback_only"])
