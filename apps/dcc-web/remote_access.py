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
from host_setup import SETTINGS_ID as DOMAINS_SETTINGS_ID, local_container
from security import admin, trusted_https_request

VERSION = "0.1.0"
ZROK_VERSION = "2.0.9"
DIGEST = "sha256:00c5b65bbb5b7c045c1d23d35ab392f2edd43633ee8513c7a858899993f41d8f"
IMAGE = f"docker.io/openziti/zrok2:{ZROK_VERSION}@{DIGEST}"
LABEL = "io.dcc.remote-access"
SETTINGS = "__dcc_remote_access__"
UPDATE_TICKET = "__dcc_remote_update__"
UPDATE_CONTROL_LABEL = "io.dcc.web.remote-maintenance"
UPDATE_TICKET_SECONDS = 600
PORT = 8791
PANEL_NETWORK_POOL = ipaddress.ip_network("198.18.0.0/15")
PANEL_NETWORK_PREFIX = 28
NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{1,61})[a-z0-9]")
TOKEN = re.compile(r"[A-Za-z0-9]{8,128}")
HOSTED_ZONES = ("share.zrok.io", "shares.zrok.io")
ENVIRONMENT = {"HOME": "/tmp", "ZROK2_API_ENDPOINT": "https://api-v2.zrok.io",
               "GODEBUG": "http2client=0,http2server=0"}
PROFILE_ACTIONS = frozenset({"install", "uninstall"})
WORKSPACE_JOB_ACTIONS = frozenset({"configure", "enable", "restart"})
ACTIONS = PROFILE_ACTIONS | WORKSPACE_JOB_ACTIONS | {"disable"}
WAIT = (Path(__file__).resolve().parents[1] / "dcc-remote-access" / "supervise.sh").read_text(encoding="utf-8")


class RemoteError(ValueError):
    """A message safe to display without showing zrok's raw output."""


def name_origin(name, reservation):
    zone = reservation.get("namespaceName")
    if (not isinstance(name, str) or not NAME.fullmatch(name)
            or reservation.get("namespaceToken") != "public" or zone not in HOSTED_ZONES):
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
        self.network_error = ""
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

    def validate_container(self, container, allow_missing_ingress=False):
        attrs = container.attrs
        host = attrs["HostConfig"]
        env = dict(value.split("=", 1) for value in attrs["Config"].get("Env", []) if "=" in value)
        attached = frozenset(attrs["NetworkSettings"]["Networks"])
        allowed_networks = {frozenset({self.ingress, self.egress})}
        if allow_missing_ingress:
            allowed_networks.add(frozenset({self.egress}))
        if (attrs["Config"]["Image"] != IMAGE or attrs["Config"]["User"] != "2171:2171"
                or attrs["Config"]["Entrypoint"] != ["/bin/sh", "-c"] or attrs["Config"]["Cmd"] != [WAIT]
                or any(env.get(key) != value for key, value in ENVIRONMENT.items())
                or host.get("Privileged") or not host.get("ReadonlyRootfs") or attrs.get("Mounts")
                or set(host.get("CapDrop") or ()) != {"ALL"} or host.get("CapAdd")
                or host.get("PortBindings") or host.get("Devices") or host.get("DeviceRequests")
                or host.get("LogConfig", {}).get("Type") != "none"
                or host.get("RestartPolicy", {}).get("Name") not in {"no", ""}
                or host.get("SecurityOpt") not in (["no-new-privileges:true"], ["no-new-privileges"])
                or attached not in allowed_networks):
            raise RemoteError("The installed tunnel does not match the isolated configuration.")

    def _profile_addresses(self):
        values = set()
        profiles = self.state.profiles()
        for profile in profiles:
            for value in (profile.get("host"), profile.get("endpoint")):
                if not isinstance(value, str) or not value.strip():
                    continue
                try:
                    parsed = urlsplit(value if "://" in value else "//" + value)
                    address = ipaddress.ip_address(parsed.hostname or "")
                except ValueError:
                    continue
                if address.version == 4:
                    values.add(address)
        try:
            rows = self.state.rows("SELECT data FROM settings WHERE user_id=?", (DOMAINS_SETTINGS_ID,))
            if rows:
                local = self.state.decode_profile(rows[0]["data"]).get("local", "")
                address = ipaddress.ip_address(str(local).strip("[]"))
                if address.version == 4:
                    values.add(address)
        except (KeyError, TypeError, ValueError):
            pass
        return values

    def panel_network_subnet(self, client, exclude_name=None):
        """Pick an isolated subnet outside common LANs and every configured Docker network."""
        occupied = []
        for network in client.networks.list():
            if getattr(network, "name", None) == exclude_name:
                continue
            attrs = network.attrs or {}
            for config in (attrs.get("IPAM") or {}).get("Config") or []:
                try:
                    occupied.append(ipaddress.ip_network(config["Subnet"], strict=False))
                except (KeyError, TypeError, ValueError):
                    continue
        hosts = self._profile_addresses()
        candidates = tuple(PANEL_NETWORK_POOL.subnets(new_prefix=PANEL_NETWORK_PREFIX))
        start = int(self.owner[:8], 16) % len(candidates)
        for offset in range(len(candidates)):
            candidate = candidates[(start + offset) % len(candidates)]
            if any(candidate.overlaps(value) for value in occupied):
                continue
            if any(address in candidate for address in hosts):
                continue
            return str(candidate)
        raise RemoteError("No non-overlapping subnet is available for the isolated Remote Access network.")

    def _create_network(self, client, name, internal, subnet=None):
        options = {}
        if internal:
            subnet = subnet or self.panel_network_subnet(client, exclude_name=name)
            options["ipam"] = docker.types.IPAMConfig(
                pool_configs=[docker.types.IPAMPool(subnet=subnet)]
            )
        return client.networks.create(name, driver="bridge", internal=internal,
                                      labels={LABEL: self.owner}, **options)

    def network(self, client, name, internal):
        try:
            net = client.networks.get(name)
        except NotFound:
            net = self._create_network(client, name, internal)
        if (net.attrs.get("Labels", {}).get(LABEL) != self.owner or net.attrs.get("Driver") != "bridge"
                or bool(net.attrs.get("Internal")) != internal):
            raise RemoteError("The managed network name is in use.")
        return net

    def repair_panel_network(self, client=None, panel=None):
        """Move a conflicting isolated ingress network off remote-profile LAN routes."""
        if client is None:
            with closing(self.client_factory()) as active_client:
                return self.repair_panel_network(active_client, panel=panel)
        try:
            network = client.networks.get(self.ingress)
        except NotFound:
            network = None
        container = self.container(client)
        if network is None and container is None:
            return False
        panel = panel or local_container(client)
        if container:
            container.reload()
            # A previous process may have stopped after detaching the sidecar
            # but before reconnecting it. Allow that safe, egress-only state so
            # the idempotent repair below can finish on the next startup.
            self.validate_container(container, allow_missing_ingress=True)
        if network is None:
            network = self.network(client, self.ingress, True)
            network.connect(panel, aliases=["dcc-remote-panel"])
            if container:
                network.connect(container)
            self.network_error = ""
            return True

        network.reload()
        attrs = network.attrs
        if (attrs.get("Labels", {}).get(LABEL) != self.owner or attrs.get("Driver") != "bridge"
                or not attrs.get("Internal")):
            raise RemoteError("The managed panel network cannot be safely repaired.")
        configs = (attrs.get("IPAM") or {}).get("Config") or []
        subnets = []
        for config in configs:
            try:
                subnets.append(ipaddress.ip_network(config["Subnet"], strict=False))
            except (KeyError, TypeError, ValueError):
                continue
        conflicts = any(address in subnet for address in self._profile_addresses() for subnet in subnets)
        # Older Docker installations chose the subnet automatically, which can
        # claim a home-LAN route even when no remote profile is saved yet. New
        # managed networks always live in our collision-checked pool.
        conflicts = (conflicts or len(subnets) != 1
                     or not subnets[0].subnet_of(PANEL_NETWORK_POOL))
        members = attrs.get("Containers") or {}
        expected = {panel.id}
        if container:
            expected.add(container.id)
        unexpected = set(members) - expected
        if unexpected:
            raise RemoteError("The managed panel network contains an unexpected container and was left unchanged.")
        attached = set(members)
        needs_connect = panel.id not in attached or (container and container.id not in attached)
        if not conflicts and not needs_connect:
            self.network_error = ""
            return False

        if container:
            container.reload()
            if container.attrs.get("State", {}).get("Running"):
                container.stop(timeout=12)
        old_subnet = str(subnets[0]) if subnets else None
        try:
            for value in (panel, container):
                if value and value.id in attached:
                    network.disconnect(value, force=True)
            if conflicts:
                network.remove()
                network = self.network(client, self.ingress, True)
            network.connect(panel, aliases=["dcc-remote-panel"])
            if container:
                network.connect(container)
        except Exception:
            # Restore the old network if migration fails, so the panel stays reachable.
            try:
                try:
                    restored = client.networks.get(self.ingress)
                except NotFound:
                    restored = self._create_network(client, self.ingress, True, subnet=old_subnet)
                restored.reload()
                restored_members = restored.attrs.get("Containers") or {}
                if panel.id not in restored_members:
                    restored.connect(panel, aliases=["dcc-remote-panel"])
                if container and container.id not in restored_members:
                    restored.connect(container)
            except Exception:
                pass
            self.network_error = "The isolated panel network could not be repaired. Remote Access remains unavailable until it is fixed."
            raise
        self.network_error = ""
        return True

    def install(self, client, panel):
        self.repair_panel_network(client, panel=panel)
        container = self.container(client)
        if container:
            container.reload()
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

    def enable(self, container, owner, epoch, *, resume_after_update=False):
        self.policy(owner)
        config = self.saved()
        if not config.get("origin") or not config.get("identity"):
            raise RemoteError("Configure a zrok environment and reserve a name first.")
        try:
            self.restore(container, config)
            attempts = 4 if resume_after_update else 1
            for attempt in range(attempts):
                reservation = self.reservation(container, config["name"])
                if not reservation or not reservation.get("reserved") or name_origin(config["name"], reservation) != config["origin"]:
                    raise RemoteError("The saved public reservation is unavailable.")
                if not reservation.get("shareToken"):
                    break
                if attempt == attempts - 1:
                    raise RemoteError("The reserved name still has a share. Release it in the zrok console before enabling again.")
                if epoch != self.epoch:
                    raise RemoteError("Public access was disabled during startup.")
                time.sleep(3)
            container.reload()
            peer = container.attrs["NetworkSettings"]["Networks"][self.ingress]["IPAddress"]
            if not peer:
                raise RemoteError("The tunnel did not receive a private network address.")
            host = urlsplit(config["origin"]).hostname
            route = {"peer": peer, "host": host, "origin": config["origin"], "nonce": secrets.token_urlsafe(32),
                     "lease": secrets.token_urlsafe(32), "owner": owner, "verified": False,
                     "resume_after_update": resume_after_update}
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

    def update_pause_allowed(self):
        route = self.route
        return bool(self.available and route and route["verified"] and route.get("resume_after_update")
                    and not self.network_error and not self.blocked() and self.owner_can_enable(route["owner"]))

    def maintenance(self, args):
        if args == ["status"]:
            return self.update_pause_allowed()
        if len(args) not in {2, 3} or not re.fullmatch(r"[0-9a-f]{64}", args[1]):
            return False
        action, nonce = args[:2]
        proof = hashlib.sha256(nonce.encode()).hexdigest()
        with self.lock, closing(self.client_factory()) as client:
            panel = local_container(client)
            if action == "pause" and len(args) == 3 and re.fullmatch(r"sha256:[0-9a-f]{64}", args[2]):
                return self.pause_for_update(client, panel, proof, args[2])
            if action == "resume" and len(args) == 2:
                return self.resume_after_update(client, panel, proof)
        return False

    def pause_for_update(self, client, panel, proof, target_image):
        image = client.images.get(target_image)
        if (image.attrs.get("Config", {}).get("Labels") or {}).get(UPDATE_CONTROL_LABEL) != "1":
            return False
        if not any(ref.startswith(("ghcr.io/hattimon/dcc-web:", "ghcr.io/hattimon/dcc-web@"))
                   for ref in (image.attrs.get("RepoTags") or []) + (image.attrs.get("RepoDigests") or [])):
            return False
        sidecar = self.container(client)
        if not sidecar:
            return False
        sidecar.reload()
        self.validate_container(sidecar)
        with self.intent:
            if not self.update_pause_allowed() or not sidecar.attrs["State"]["Running"]:
                return False
            owner = self.route["owner"]
            ticket = dict(proof=proof, owner=owner, panel=panel.id, target=target_image,
                          expires=time.time() + UPDATE_TICKET_SECONDS)
            self.state.execute("INSERT OR REPLACE INTO settings VALUES(?,?)",
                               (UPDATE_TICKET, self.state.encode_profile(ticket)))
            self.epoch += 1
            self.route = None
        self.stop(sidecar)
        self.state.audit(owner, "remote-access.update-pause", self.name, 200)
        return True

    def resume_after_update(self, client, panel, proof):
        rows = self.state.rows("SELECT data FROM settings WHERE user_id=?", (UPDATE_TICKET,))
        if not rows or self.route or self.network_error:
            return False
        saved = rows[0]["data"]
        ticket = self.state.decode_profile(saved)
        if time.time() >= ticket["expires"]:
            self.state.execute("DELETE FROM settings WHERE user_id=? AND data=?", (UPDATE_TICKET, saved))
            return False
        if (not secrets.compare_digest(proof, ticket["proof"])
                or (panel.id != ticket["panel"] and panel.attrs.get("Image") != ticket["target"])):
            return False
        self.policy(ticket["owner"])
        sidecar = self.container(client)
        if not sidecar or not self.state.execute("DELETE FROM settings WHERE user_id=? AND data=?", (UPDATE_TICKET, saved)):
            return False
        owner, epoch = ticket["owner"], self.epoch
        self.tunnel, self.error = "connecting", ""

        def restore():
            with self.lock:
                if self.epoch != epoch or self.route:
                    return
                try:
                    self.enable(sidecar, owner, epoch, resume_after_update=True)
                    self.state.audit(owner, "remote-access.update-resume", self.name, 200)
                except Exception:
                    if self.epoch == epoch:
                        self.tunnel = "error"
                        self.error = "Could not resume the tunnel after updating. Enable access from the local panel."
                    self.state.audit(owner, "remote-access.update-resume", self.name, 503)

        threading.Thread(target=restore, name="dcc-remote-update-resume", daemon=True).start()
        return True

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
                  "name": config.get("name"), "pending_name": config.get("pending_name"),
                  "origin": config.get("origin"), "enrolled": bool(config.get("identity")),
                  "last_connection": self.last_connection, "error": self.error, "update": self.update,
                  "security": "blocked" if self.blocked() else "pinned",
                  "update_resume_allowed": self.update_pause_allowed()}
        if self.network_error:
            status.update(state="error", tunnel="disabled", error=self.network_error)
            return status
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
            if action != "install":
                self.state.execute("DELETE FROM settings WHERE user_id=?", (UPDATE_TICKET,))
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
                self.enable(container, owner, epoch, resume_after_update=data.get("resume_after_update") is True)
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
        profile_action = action in PROFILE_ACTIONS
        p = profile(data.get("profile"), "install") if profile_action else {"id": "workspace"}
        if profile_action and (p["kind"] != "local" or p.get("context")):
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
                if profile_action:
                    invalidate(p["id"])
                return result
            except DockerException:
                raise RemoteError("Docker could not complete the managed tunnel operation.") from None
        return start_job(p, "remote-access." + action, work)

    return remote
