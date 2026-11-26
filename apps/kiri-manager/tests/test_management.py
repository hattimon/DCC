import io
import json
import unittest
from unittest.mock import patch

import paramiko
from backend.kiri_client import KiriError, VerifiedKiri, identify_docker
from backend.ssh_transport import SSHTransport, trusted_keys, COMMAND
from backend.storage import Storage
from fixtures import CID, ENGINE, VERSION, FixtureTransport
import test_app


class ActionTransport(FixtureTransport):
    calls = []
    status = "exited"
    name = "/test-container"
    fail = False
    image = "test/image"

    def get(self, path, limit, expected=None):
        if path == f"/v1.47/containers/{CID}/json":
            return ENGINE, "application/json", json.dumps({
                "Id": CID, "Name": self.name, "State": {"Status": self.status},
                "Config": {"Image": self.image}
            }).encode()
        return super().get(path, limit, expected)

    def request(self, method, path, limit, expected=None):
        self.calls.append((method, path, expected))
        if self.fail:
            raise KiriError("timeout", 504)
        return ENGINE, "", b""


class ManagementTest(unittest.TestCase):
    def setUp(self):
        ActionTransport.calls.clear()
        self.transport = ActionTransport("local")
        self.engine = VerifiedKiri(self.transport)

    def test_exact_mutations(self):
        for action in ("start", "stop", "restart", "pause", "unpause", "remove"):
            self.engine.container_action(CID, action, "test-container" if action == "remove" else CID)
        base = f"/v1.47/containers/{CID}"
        self.assertEqual(ActionTransport.calls, [
            ("POST", base+"/start", ENGINE), ("POST", base+"/stop?t=10", ENGINE),
            ("POST", base+"/restart?t=10", ENGINE), ("POST", base+"/pause", ENGINE),
            ("POST", base+"/unpause", ENGINE), ("DELETE", base+"?v=false&force=false", ENGINE)])

    def test_removal_guards(self):
        for key, action, confirm in (("invalid", "start", CID), (CID, "prune", CID),
                                     (CID, "remove", CID), (CID, "remove", "wrong")):
            with self.assertRaises(KiriError):
                self.engine.container_action(key, action, confirm)
        self.transport.status = "running"
        with self.assertRaises(KiriError):
            self.engine.container_action(CID, "remove", "test-container")
        self.transport.image = "ghcr.io/hattimon/dcc-kiri-manager:0.1.3"
        with self.assertRaises(KiriError):
            self.engine.container_action(CID, "stop", CID)
        self.assertEqual(ActionTransport.calls, [])

    def test_no_retry(self):
        self.transport.fail = True
        with self.assertRaises(KiriError):
            self.engine.container_action(CID, "restart", CID)
        self.assertEqual(len(ActionTransport.calls), 1)

    def test_docker_identity(self):
        value = {**VERSION, "Version": "28.1.1", "KiriVersion": None,
                 "Platform": {"Name": "Docker Engine - Community"}}
        self.assertEqual(identify_docker("Docker/28.1.1 (linux)", value)["kind"], "docker")
        with self.assertRaises(KiriError):
            identify_docker(ENGINE, value)


class ApiManagementTest(unittest.TestCase):
    setUp = test_app.AppTest.setUp
    change = test_app.AppTest.change
    login = test_app.AppTest.login
    profile = test_app.AppTest.profile

    def test_management_permissions_and_confirmation(self):
        self.connector.transport = ActionTransport
        ActionTransport.calls.clear()
        self.assertEqual(self.change(f"/api/profiles/{'0'*32}/containers/{CID}/action",
                                    {"action": "start", "revision": 1, "confirmation": CID}).status_code, 401)
        self.login()
        profile = self.profile()
        path = f"/api/profiles/{profile['id']}/containers/{CID}/action"
        body = {"action": "start", "revision": profile["revision"], "confirmation": CID}
        self.assertEqual(self.change(path, body, origin="http://evil.invalid").status_code, 403)
        self.assertEqual(self.change(path, {**body, "revision": 999}).status_code, 409)
        self.assertEqual(self.change(path, {**body, "confirmation": "wrong"}).status_code, 400)
        self.assertEqual(self.change(path, {**body, "action": "remove"}).status_code, 400)
        self.assertEqual(ActionTransport.calls, [])
        self.assertEqual(self.change(path, body).status_code, 200)
        self.assertEqual(self.change(path, {**body, "action": "remove", "confirmation": "test-container"}).status_code, 200)
        self.assertEqual(len(ActionTransport.calls), 2)
        other = self.profile(name="Other")
        self.assertEqual(self.change(f"/api/profiles/{other['id']}/containers/{CID}/action", body).status_code, 409)

    def test_ssh_encryption_and_no_secret_in_responses(self):
        self.login()
        key = paramiko.RSAKey.generate(1024)
        known = f"example.invalid {key.get_name()} {key.get_base64()}"
        password = "unique-test-only-secret-0123456789"
        payload = {"name": "Remote", "host": "linux", "runtime": "docker", "endpoint": "",
                   "transport": "ssh", "ssh_host": "example.invalid", "ssh_port": 22,
                   "ssh_username": "operator", "ssh_cli": "docker", "ssh_known_hosts": known,
                   "credentials": {"password": password}}
        response = self.change("/api/profiles", payload)
        self.assertEqual(response.status_code, 201, response.json)
        saved = response.json
        self.assertNotIn("credentials", saved)
        self.assertTrue(saved["has_credentials"])
        self.assertNotIn(password, self.web.get("/api/session").get_data(as_text=True))
        self.assertNotIn(password.encode(), self.store.path.read_bytes())
        self.assertEqual(self.store.connection_profile(saved["id"])["credentials"], {"password": password})
        edit = {k: v for k, v in payload.items() if k != "credentials"}
        edit["revision"] = saved["revision"]
        route = "/api/profiles/"+saved["id"]
        self.assertEqual(self.change(route, {**edit, "ssh_username": "other"}, method="PUT").status_code, 400)
        self.assertEqual(self.change(route, {**edit, "name": "Renamed"}, method="PUT").status_code, 200)
        self.assertEqual(self.store.connection_profile(saved["id"])["credentials"], {"password": password})
        self.store.key_path.unlink()
        with self.assertRaises(RuntimeError):
            Storage(self.config.data_dir)


class SSHTest(unittest.TestCase):
    def test_host_key_pin_and_fixed_command(self):
        key = paramiko.RSAKey.generate(1024)
        known = f"[example.invalid]:2222 {key.get_name()} {key.get_base64()}"
        self.assertTrue(trusted_keys("example.invalid", 2222, known).check("[example.invalid]:2222", key))
        with self.assertRaises(KiriError):
            trusted_keys("example.invalid", 22, known)
        with self.assertRaises(KiriError):
            trusted_keys("other.invalid", 2222, known)
        profile = {"ssh_host": "example.invalid", "ssh_port": 2222, "ssh_username": "operator",
                   "ssh_known_hosts": known, "credentials": {"password": "synthetic"}}
        with patch("backend.ssh_transport.paramiko.SSHClient") as factory:
            client = factory.return_value
            client.get_host_keys.return_value = paramiko.HostKeys()
            channel = client.get_transport.return_value.open_session.return_value
            data = b"HTTP/1.1 200 OK\r\nServer: Kiri/0.2.2 (linux)\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}"
            stream = io.BytesIO(data)
            channel.recv.side_effect = stream.read
            with SSHTransport(profile) as transport:
                self.assertEqual(transport.get("/version", 128)[2], b"{}")
            self.assertIsInstance(client.set_missing_host_key_policy.call_args.args[0], paramiko.RejectPolicy)
            self.assertFalse(client.connect.call_args.kwargs["allow_agent"])
            self.assertFalse(client.connect.call_args.kwargs["look_for_keys"])
            channel.exec_command.assert_called_once_with(COMMAND)
            self.assertIn(b"GET /version HTTP/1.1", channel.sendall.call_args.args[0])
            client.close.assert_called()



    def test_mutation_stays_on_verified_stream(self):
        key = paramiko.RSAKey.generate(1024)
        profile = {"ssh_host": "example.invalid", "ssh_port": 22, "ssh_username": "operator",
                   "ssh_known_hosts": f"example.invalid {key.get_name()} {key.get_base64()}",
                   "credentials": {"password": "synthetic"}}
        def response(body, status="200 OK", close=False):
            return (f"HTTP/1.1 {status}\r\nServer: {ENGINE}\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\nConnection: {'close' if close else 'keep-alive'}\r\n\r\n").encode() + body
        version = response(json.dumps(VERSION).encode())
        inspect = response(json.dumps({"Id": CID, "Name": "/test-container", "State": {"Status": "exited"}}).encode())
        mutation = response(b"", "204 No Content")
        for close_before_write in (False, True):
            with self.subTest(close_before_write=close_before_write), patch("backend.ssh_transport.paramiko.SSHClient") as factory:
                client = factory.return_value
                client.get_host_keys.return_value = paramiko.HostKeys()
                channel = client.get_transport.return_value.open_session.return_value
                messages = [version, version, (inspect.replace(b"keep-alive", b"close") if close_before_write else inspect), mutation]
                sent = []
                stream = io.BytesIO()
                def send(data):
                    nonlocal stream
                    sent.append(data)
                    stream = io.BytesIO(messages.pop(0))
                channel.sendall.side_effect = send
                channel.recv.side_effect = lambda size: stream.read(size)
                with SSHTransport(profile) as transport:
                    engine = VerifiedKiri(transport)
                    if close_before_write:
                        with self.assertRaises(KiriError):
                            engine.container_action(CID, "start", CID)
                    else:
                        engine.container_action(CID, "start", CID)
                self.assertEqual(client.get_transport.return_value.open_session.call_count, 2)
                self.assertEqual(len(sent), 3 if close_before_write else 4)
                if not close_before_write:
                    self.assertIn(b"POST /v1.47/containers/", sent[-1])
