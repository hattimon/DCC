"""Manage one opt-in zrok tunnel for the local DCC Web installation."""
from contextlib import closing
import hashlib
import ipaddress
import json
import re
import secrets
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import docker
from docker.errors import DockerException, ImageNotFound, NotFound
from flask import abort, g, jsonify, request

from catalogs import fetch_public
from host_setup import local_container
from security import admin, trusted_https_request

VERSION = "0.1.0"
ZROK_VERSION = "2.0.9"
DIGEST = "sha256:00c5b65bbb5b7c045c1d23d35ab392f2edd43633ee8513c7a858899993f41d8f"
IMAGE = f"docker.io/openziti/zrok2:{ZROK_VERSION}@{DIGEST}"
LABEL = "io.dcc.remote-access"
SETTINGS = "__dcc_remote_access__"
PORT = 8791
NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{1,61})[a-z0-9]")
TOKEN = re.compile(r"[A-Za-z0-9]{8,128}")
PROVIDER = "share.zrok.io"
ENVIRONMENT = {"HOME": "/tmp", "ZROK2_API_ENDPOINT": "https://api-v2.zrok.io",
               "GODEBUG": "http2client=0,http2server=0"}
ACTIONS = frozenset({"install", "configure", "enable", "disable", "restart", "uninstall"})
WAIT = (Path(__file__).resolve().parents[1] / "dcc-remote-access" / "supervise.sh").read_text(encoding="utf-8")


class RemoteError(ValueError):
    """A message safe to display without showing zrok's raw output."""


def name_origin(name, reservation):
    zone = reservation.get("namespaceName")
    if reservation.get("namespaceToken") != "public" or zone != PROVIDER:
        raise RemoteError("The reservation is outside the supported hosted namespace.")
    return f"https://{name}.{zone}"


def public_probe(origin, nonce):
    # The hostname is taken from a validated hosted reservation. Use a pinned
    # public DNS answer, verify TLS and reject redirects to other destinations.
    import http.client
    import socket
    import ssl
    host = urlsplit(origin).hostname
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        return False
    with socket.create_connection((addresses[0][4][0], 443), timeout=4) as raw:
        connection = http.client.HTTPSConnection(host, timeout=4)
        try:
            connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
            connection.request("GET", "/api/health", headers={"Skip-Zrok-Interstitial": "1", "skip_zrok_interstitial": "1", "X-DCC-Remote-Probe": nonce})
            response = connection.getresponse()
            return response.status == 200 and secrets.compare_digest(response.headers.get("X-DCC-Remote-Probe", ""), nonce)
        finally:
            connection.close()


class RemoteAccess:
    def __init__(self, app, state, client_factory=None, probe=public_probe):
        self.app = app
        self.state = state
        self.client_factory = client_factory or (lambda: docker.DockerClient(base_url="unix:///var/run/docker.sock", timeout=20))
        self.probe = probe
        self.available = False
        self.owner = hashlib.sha256(state.session_key.encode()).hexdigest()[:16]
        self.name = "dcc-remote-access-" + self.owner
        self.ingress = self.name + "-panel"
        self.egress = self.name + "-egress"
        self.lock = threading.RLock()
        self.intent = threading.Lock()
        self.epoch = 0
        self.route = None
        self.tunnel = "disabled"
        self.last_connection = None
        self.error = ""
        self.update = None

    def saved(self):
        rows = self.state.rows("SELECT data FROM settings WHERE user_id=?", (SETTINGS,))
        return self.state.decode_profile(rows[0]["data"]) if rows else {}

    def save(self, config):
        self.state.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (SETTINGS, self.state.encode_profile(config)))

    def owner_can_enable(self, owner):
        users = self.state.rows("SELECT role FROM users WHERE id=?", (owner,))
        return bool(users and users[0]["role"] == "admin" and self.state.mfa.enabled(owner))

    def blocked(self):
        if DIGEST in self.app.config.get("DCC_REMOTE_BLOCKED_DIGESTS", ()):
            return True
        path = self.state.directory / "dcc-remote-blocked-digests.txt"
        try:
            with path.open(encoding="ascii") as handle:
                content = handle.read(8193)
        except FileNotFoundError:
            return False
        except (OSError, UnicodeError):
            return True
        values = content.split()
        return len(content) > 8192 or DIGEST in values or any(not re.fullmatch(r"sha256:[a-f0-9]{64}", value) for value in values)

    def policy(self, owner):
        if not self.available:
            raise RemoteError("Remote access requires the local DCC Web Docker installation.")
        if self.blocked():
            raise RemoteError("This zrok image is blocked by the security policy.")
        if not self.owner_can_enable(owner):
            raise RemoteError("Enable 2FA for your administrator account before enabling remote access.")
        if not self.app.config["SESSION_COOKIE_HTTPONLY"] or self.app.config["SESSION_COOKIE_SAMESITE"] != "Strict":
            raise RemoteError("Secure DCC session settings are required.")

    def as_ingress(self, environ, start_response):
        environ["dcc.remote_ingress"] = True
        return self.app(environ, start_response)

    def guard(self):
        if not request.environ.get("dcc.remote_ingress"):
            return None
        route = self.route
        if not route or request.remote_addr != route["peer"] or request.host != route["host"]:
            abort(400, "Untrusted remote ingress")
        if self.blocked() or not self.owner_can_enable(route["owner"]):
            abort(503, "Remote access is blocked by the security policy")
        if (request.method == "GET" and request.path == "/api/health"
                and secrets.compare_digest(request.headers.get("X-DCC-Remote-Probe", ""), route["nonce"])):
            return "", 200, {"X-DCC-Remote-Probe": route["nonce"]}
        if (request.method == "GET" and request.path == "/api/health"
                and secrets.compare_digest(request.headers.get("X-DCC-Remote-Lease", ""), route["lease"])):
            return "", 200
        if not route["verified"]:
            abort(503, "Remote access is awaiting HTTPS verification")
        g.dcc_remote = True
        return None

    def container(self, client):
        try:
            container = client.containers.get(self.name)
        except NotFound:
            return None
        attrs = container.attrs
        if (attrs["Config"]["Labels"] or {}).get(LABEL) != self.owner:
            raise RemoteError("The managed container name is in use.")
        return container

    def validate_container(self, container):
        attrs = container.attrs
        host = attrs["HostConfig"]
        env = dict(value.split("=", 1) for value in attrs["Config"].get("Env", []) if "=" in value)
        if (attrs["Config"]["Image"] != IMAGE or attrs["Config"]["User"] != "2171:2171"
                or attrs["Config"]["Entrypoint"] != ["/bin/sh", "-c"] or attrs["Config"]["Cmd"] != [WAIT]
                or any(env.get(key) != value for key, value in ENVIRONMENT.items())
                or host.get("Privileged") or not host.get("ReadonlyRootfs") or attrs.get("Mounts")
                or set(host.get("CapDrop") or ()) != {"ALL"} or host.get("CapAdd")
                or host.get("PortBindings") or host.get("Devices") or host.get("DeviceRequests")
                or host.get("LogConfig", {}).get("Type") != "none"
                or host.get("RestartPolicy", {}).get("Name") not in {"no", ""}
                or host.get("SecurityOpt") not in (["no-new-privileges:true"], ["no-new-privileges"])
                or set(attrs["NetworkSettings"]["Networks"]) != {self.ingress, self.egress}):
            raise RemoteError("The installed tunnel does not match the isolated configuration.")

    def network(self, client, name, internal):
        try:
            net = client.networks.get(name)
        except NotFound:
            net = client.networks.create(name, driver="bridge", internal=internal, labels={LABEL: self.owner})
        if (net.attrs.get("Labels", {}).get(LABEL) != self.owner or net.attrs.get("Driver") != "bridge"
                or bool(net.attrs.get("Internal")) != internal):
            raise RemoteError("The managed network name is in use.")
        return net

    def install(self, client, panel):
        container = self.container(client)
        if container:
            self.validate_container(container)
            return
        try:
            client.images.get(IMAGE)
        except ImageNotFound:
            client.images.pull(IMAGE)
        ingress = self.network(client, self.ingress, True)
        egress = self.network(client, self.egress, False)
        ingress.reload()
        if panel.id not in (ingress.attrs.get("Containers") or {}):
            ingress.connect(panel, aliases=["dcc-remote-panel"])
        container = client.containers.create(
            IMAGE, [WAIT], name=self.name, entrypoint=["/bin/sh", "-c"], user="2171:2171",
            network=egress.name, environment=ENVIRONMENT,
            labels={LABEL: self.owner}, read_only=True, cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
            tmpfs={"/tmp": "rw,noexec,nosuid,nodev,size=32m,uid=2171,gid=2171,mode=0700"},
            log_config=docker.types.LogConfig(type="none"), pids_limit=64, mem_limit="256m",
            restart_policy={"Name": "no"},
        )
        try:
            ingress.connect(container)
        except DockerException:
            container.remove()
            raise

    def command(self, container, args, *, data=None, message="zrok rejected the operation."):
        # Send credentials and identity bytes through stdin, never Docker exec
        # arguments, environment metadata, or persistent files.
        try:
            proc = subprocess.run(
                ["docker", "--host", "unix:///var/run/docker.sock", "exec", "-i", container.id,
                 "timeout", "35", *args],
                input=data if data is not None else b"", capture_output=True, timeout=40, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise RemoteError("The zrok command did not complete.") from None
        if proc.returncode != 0:
            raise RemoteError(message)
        return proc.stdout

    def stop(self, container):
        self.route = None
        self.tunnel = "disabled"
        if container:
            container.reload()
            if container.attrs["State"]["Running"]:
                container.stop(timeout=12)

    def restore(self, container, config):
        self.stop(container)
        self.validate_container(container)
        container.start()
        if config.get("identity"):
            identity = self.state.vault.decrypt(config["identity"].encode())
            self.command(container, ["tar", "-xf", "-", "-C", "/tmp"], data=identity)

    def reservation(self, container, name):
        raw = self.command(container, ["zrok2", "list", "names", "--json", "-n", "public"],
                           message="The hosted zrok service could not list names.")
        values = json.loads(raw) or []
        return next((value for value in values if value.get("name") == name), None)

    def configure(self, container, data):
        config = self.saved()
        token = data.get("account_token", "")
        name = data.get("name") or config.get("name") or config.get("pending_name") or "dcc-" + secrets.token_hex(8)
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise RemoteError("Use 3–63 lowercase letters, numbers or internal hyphens for the public name.")
        if not isinstance(token, str) or (token and not TOKEN.fullmatch(token)):
            raise RemoteError("Enter a valid zrok account token.")
        if config.get("name") and config["name"] != name:
            raise RemoteError("Release the existing reservation before choosing a different name.")
        if not config.get("identity") and not token:
            raise RemoteError("A zrok account token is required.")
        if config.get("identity") and token:
            raise RemoteError("Remove the saved environment before entering a new account token.")
        try:
            self.restore(container, config)
            pending = config.get("pending_name")
            if pending and pending != name and self.reservation(container, pending):
                raise RemoteError("Complete or release the pending reservation before choosing a different name.")
            if token:
                self.command(container, ["/bin/sh", "-c", 'read -r token; exec zrok2 enable --headless "$token"'],
                             data=(token+"\n").encode(), message="zrok rejected the account token or the hosted service is unavailable.")
                identity = self.command(container, ["tar", "-cf", "-", "-C", "/tmp", ".zrok2"])
                if not 0 < len(identity) <= 512_000:
                    raise RemoteError("zrok returned an invalid environment.")
                config["identity"] = self.state.vault.encrypt(identity).decode()
                self.save(config)
            reservation = self.reservation(container, name)
            if reservation is None:
                config["pending_name"] = name
                self.save(config)
                self.command(container, ["zrok2", "create", "name", "-n", "public", name],
                             message="The name could not be reserved. It may already be in use.")
                reservation = self.reservation(container, name)
            elif name not in {config.get("name"), config.get("pending_name")}:
                raise RemoteError("The name already belongs to an existing reservation.")
            if not reservation or reservation.get("reserved") is not True:
                raise RemoteError("The hosted service did not return a reserved name.")
            config.pop("pending_name", None)
            self.save(dict(config, name=name, origin=name_origin(name, reservation)))
        finally:
            self.stop(container)

    def enable(self, container, owner, epoch):
        self.policy(owner)
        config = self.saved()
        if not config.get("origin") or not config.get("identity"):
            raise RemoteError("Configure a zrok environment and reserve a name first.")
        try:
            self.restore(container, config)
            reservation = self.reservation(container, config["name"])
            if not reservation or not reservation.get("reserved") or name_origin(config["name"], reservation) != config["origin"]:
                raise RemoteError("The saved public reservation is unavailable.")
            if reservation.get("shareToken"):
                raise RemoteError("The reserved name still has a share. Release it in the zrok console before enabling again.")
            container.reload()
            peer = container.attrs["NetworkSettings"]["Networks"][self.ingress]["IPAddress"]
            if not peer:
                raise RemoteError("The tunnel did not receive a private network address.")
            host = urlsplit(config["origin"]).hostname
            route = {"peer": peer, "host": host, "origin": config["origin"], "nonce": secrets.token_urlsafe(32),
                     "lease": secrets.token_urlsafe(32), "owner": owner, "verified": False}
            with self.intent:
                if epoch != self.epoch:
                    raise RemoteError("Public access was disabled during startup.")
                self.route = route
            self.tunnel = "connecting"
            self.command(container, ["/bin/sh", "-c", "umask 077; cat >/tmp/launch.new && mv /tmp/launch.new /tmp/launch"],
                         data=f"{config['name']} {host} {route['lease']}\n".encode())
        except Exception:
            self.stop(container)
            raise
        threading.Thread(target=self.monitor, args=(route,), name="dcc-remote-tunnel", daemon=True).start()

    def monitor(self, route):
        failures = 0
        while self.route is route:
            try:
                policy_ok = not self.blocked() and self.owner_can_enable(route["owner"])
            except Exception:
                policy_ok = False
            if not policy_ok:
                with self.lock:
                    if self.route is route:
                        try:
                            with closing(self.client_factory()) as client:
                                self.stop(self.container(client))
                        except (DockerException, RemoteError):
                            self.route = None
                        self.tunnel = "blocked"
                return
            try:
                verified = self.probe(route["origin"], route["nonce"])
            except Exception:
                verified = False
            with self.lock:
                if self.route is not route:
                    return
                route["verified"] = verified
                if verified:
                    failures = 0
                    self.tunnel, self.error = "active", ""
                    self.last_connection = time.time()
                else:
                    failures += 1
                    self.tunnel = "reconnecting" if self.last_connection else "connecting"
                    self.error = "The public HTTPS endpoint has not passed verification."
                    if failures >= 8:
                        try:
                            with closing(self.client_factory()) as client:
                                self.stop(self.container(client))
                        except (DockerException, RemoteError):
                            self.route = None
                        self.tunnel = "error"
                        return
            time.sleep(20 if verified else min(30, 2 ** failures))

    def uninstall(self, client, container, keep, provider_cleaned):
        config = self.saved()
        if not keep and provider_cleaned:
            self.save({})
        elif not keep and config.get("identity"):
            if self.blocked():
                raise RemoteError("Revoke the environment and release the name in the zrok console first.")
            try:
                self.restore(container, config)
                name = config.get("name") or config.get("pending_name")
                if name:
                    reservation = self.reservation(container, name)
                    if reservation and reservation.get("shareToken"):
                        raise RemoteError("The reserved name still has a share. Release it in the zrok console before removing it.")
                    if reservation:
                        self.command(container, ["zrok2", "delete", "name", "-n", "public", name])
                    config.pop("name", None)
                    config.pop("pending_name", None)
                    config.pop("origin", None)
                    self.save(config)
                self.command(container, ["zrok2", "disable"])
                self.save({})
            finally:
                self.stop(container)
        self.stop(container)
        if container:
            container.remove()
        for name in (self.ingress, self.egress):
            try:
                network = client.networks.get(name)
            except NotFound:
                continue
            if network.attrs.get("Labels", {}).get(LABEL) == self.owner:
                if name == self.ingress:
                    panel = local_container(client)
                    if panel.id in (network.attrs.get("Containers") or {}):
                        network.disconnect(panel)
                network.remove()

    def status(self):
        config = self.saved()
        status = {"module": "DCC Remote Access", "version": VERSION, "provider": "zrok",
                  "provider_version": ZROK_VERSION, "digest": DIGEST, "available": self.available,
                  "state": "not-installed", "container": "missing", "tunnel": self.tunnel,
                  "name": config.get("name"), "origin": config.get("origin"), "enrolled": bool(config.get("identity")),
                  "last_connection": self.last_connection, "error": self.error, "update": self.update,
                  "security": "blocked" if self.blocked() else "pinned"}
        if not self.available:
            return status
        try:
            with closing(self.client_factory()) as client:
                container = self.container(client)
                if container:
                    status["container"] = container.attrs["State"]["Status"]
                    self.validate_container(container)
                    status["state"] = ("blocked" if self.blocked() else
                                       self.tunnel if self.route or self.tunnel in {"blocked", "error"} else
                                       "disabled" if config.get("origin") else "configure")
                    if self.route and status["container"] != "running":
                        status.update(state="error", tunnel="error", error="The zrok process stopped. Check the reservation and account.")
        except (DockerException, RemoteError):
            status.update(state="error", error="Docker or the managed tunnel configuration is unavailable.")
        return status

    def check_update(self):
        raw = fetch_public("https://api.github.com/repos/openziti/zrok/releases/latest", limit=128_000)
        release = json.loads(raw).get("tag_name", "")
        if not re.fullmatch(r"v2\.\d+\.\d+", release):
            raise RemoteError("The hosted release metadata could not be verified.")
        latest = release[1:]
        self.update = {"latest": latest, "available": tuple(map(int, latest.split("."))) > tuple(map(int, ZROK_VERSION.split(".")))}
        return self.update

    def perform(self, action, data, owner, epoch):
        if action in {"disable", "uninstall"}:
            with self.intent:
                self.epoch += 1
                self.route = None
        with self.lock, closing(self.client_factory()) as client:
            container = self.container(client)
            if action == "install":
                self.install(client, local_container(client))
            elif action == "disable":
                self.stop(container)
            elif not container:
                raise RemoteError("Install DCC Remote Access first.")
            elif action == "uninstall":
                self.uninstall(client, container, data.get("keep_data") is not False, data.get("provider_cleaned") is True)
            elif action == "configure":
                if self.blocked():
                    raise RemoteError("This zrok image is blocked by the security policy.")
                if self.route:
                    raise RemoteError("Disable public access before changing the configuration.")
                self.configure(container, data)
            elif action in {"enable", "restart"}:
                if action == "enable" and self.route:
                    return {"accepted": True}
                self.enable(container, owner, epoch)
            self.state.audit(owner, "remote-access." + action, self.name, 200)
            return {"accepted": True}


def register_remote_access(app, state, body, profile, confirmed, reauthenticate, start_job, invalidate):
    remote = RemoteAccess(app, state)
    app.extensions["dcc_remote_access"] = remote

    @app.get("/api/admin/remote-access")
    def remote_status():
        admin()
        result = remote.status()
        result["mfa_ready"] = state.mfa.enabled(g.user["id"])
        result["can_manage"] = not g.get("dcc_remote")
        result["can_reauthenticate"] = trusted_https_request(app) or request.remote_addr in {"127.0.0.1", "::1"}
        return jsonify(result)

    @app.post("/api/admin/remote-access/<action>")
    def remote_action(action):
        admin()
        if g.get("dcc_remote"):
            abort(403, "Manage remote access from the local panel.")
        if action not in ACTIONS | {"check-update"}:
            abort(404)
        if not remote.available:
            abort(409, "Remote access requires the local DCC Web Docker installation.")
        if action == "check-update":
            return jsonify(remote.check_update())
        data = body()
        p = profile(data.get("profile"), "install") if action in {"install", "uninstall"} else {"id": "local"}
        if action in {"install", "uninstall"} and (p["kind"] != "local" or p.get("context")):
            abort(409, "Select the local Docker installation profile.")
        owner = g.user["id"]
        confirmed(data, "remote-access." + action, "workspace", "dcc-remote-access")
        if action in {"enable", "restart"}:
            remote.policy(owner)
        if action in {"configure", "enable", "restart", "uninstall"}:
            if not trusted_https_request(app) and request.remote_addr not in {"127.0.0.1", "::1"}:
                abort(403, "Open the local panel over HTTPS for this operation.")
            reauthenticate(data)
        epoch = remote.epoch
        if action == "disable":
            try:
                return jsonify(remote.perform(action, data, owner, epoch))
            except DockerException:
                abort(503, "Docker could not complete the managed tunnel operation.")
        def work():
            try:
                result = remote.perform(action, data, owner, epoch)
                invalidate(p["id"])
                return result
            except DockerException:
                raise RemoteError("Docker could not complete the managed tunnel operation.") from None
        return start_job(p, "remote-access." + action, work)

    return remote
