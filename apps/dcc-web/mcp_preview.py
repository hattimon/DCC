"""Profile-scoped MCP stdio server with explicit read and write grants."""
import hashlib
import ipaddress
from io import BytesIO
import json
import os
import re
from pathlib import Path, PurePosixPath
import secrets
import sys
import time
import threading
import base64
from urllib.parse import urlsplit

from flask import abort, g, jsonify, request, send_file

from engine import DockerBackend
from client_adapters import (
    CONFIG_PATHS, MANUAL_INSTRUCTIONS, agent_instructions, client_project_archive,
    codex_marketplace_archive, configuration_text, export_client, export_public_client, instruction_path,
)
from security import admin, redact
from host_terminal import HostTerminals
from mcp_host import SSHCommand, host_profile
import profile_facts

CLIENTS = ["OpenAI Codex", "Claude Desktop", "Claude Code", "Cursor", "Windsurf", "VS Code / GitHub Copilot", "Generic MCP"]
READ_TOOLS = {
    "host_info": "Read allowlisted Docker-engine OS, architecture and version facts; the SSH host OS may differ",
    "list_containers": "List containers in an authorized Docker profile",
    "inspect_container": "Inspect selected container metadata; commands, environment and secrets are omitted",
    "container_logs": "Read a bounded range of container logs",
    "container_stats": "Read current CPU, memory, network and I/O",
    "list_images": "List Docker images",
    "list_volumes": "List Docker volumes",
    "list_networks": "List Docker networks",
}
WRITE_TOOLS = {
    "container_start": "Start an authorized container",
    "container_stop": "Stop an authorized container",
    "container_restart": "Restart an authorized container",
    "container_pause": "Pause an authorized container",
    "container_unpause": "Resume an authorized container",
    "container_remove": "Remove an authorized container without deleting its volumes",
    "create_container": "Create a container with validated settings and named volumes only",
}
TERMINAL_TOOLS = {
    "host_exec": "Run a bounded command on an explicitly authorized SSH/Balena host; returns stdout, stderr and exit_code",
    "host_terminal_open": "Open an interactive PTY on an explicitly authorized SSH/Balena host",
    "host_terminal_read": "Read bounded base64 terminal output using its byte offset",
    "host_terminal_write": "Send base64 input to this MCP connection's authorized terminal",
    "host_terminal_resize": "Resize this MCP connection's authorized terminal",
    "host_terminal_close": "Close this MCP connection's authorized terminal",
}
TOOLS = {**READ_TOOLS, **WRITE_TOOLS, **TERMINAL_TOOLS}


# Docker ps/inspect can contain credentials in arbitrary fields (Command,
# Args, Entrypoint, labels, bind mount sources and health-check output). A
# name-based redactor cannot safely sanitize positional command arguments.
# Build the MCP response from a small allowlist instead of passing the raw
# Docker payload to redact(). This projection applies to every MCP transport.
_CONTAINER_LIST_FIELDS = (
    "ID", "Names", "Image", "State", "Status", "Ports", "Networks",
    "RestartPolicy", "CreatedAt", "RunningFor",
)

# Docker CLI resource and statistics JSON includes arbitrary extra keys. Some
# versions/plugins expose Labels, Mountpoint, custom metadata and other values
# that are not safe to send to MCP clients. Keep only UI-relevant scalar facts.
_MCP_DOCKER_ROW_FIELDS = {
    "container_stats": (
        "ID", "Container", "Name", "CPUPerc", "MemUsage", "MemPerc",
        "NetIO", "BlockIO", "PIDs",
    ),
    "list_images": ("Repository", "Tag", "ID", "Digest", "CreatedSince", "CreatedAt", "Size"),
    "list_volumes": ("Name", "Driver", "Scope"),
    "list_networks": ("Name", "ID", "Driver", "Scope", "IPv6", "Internal"),
}


def _mcp_fields(source, fields):
    if not isinstance(source, dict):
        return {}
    return {key: source[key] for key in fields
            if key in source and (source[key] is None or type(source[key]) in (str, int, float, bool))}


def _mcp_container_list(rows):
    if not isinstance(rows, list):
        raise ValueError("Invalid Docker container list")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Invalid Docker container entry")
    return [_mcp_fields(row, _CONTAINER_LIST_FIELDS) for row in rows]


def _mcp_docker_rows(tool, rows):
    """Project Docker CLI rows onto a bounded, transport-independent schema."""
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Invalid Docker resource or statistics list")
    fields = _MCP_DOCKER_ROW_FIELDS[tool]
    result = []
    for row in rows[:1000]:
        values = _mcp_fields(row, fields)
        result.append({key: value for key, value in values.items()
                       if not isinstance(value, str) or (len(value) <= 512
                       and all(char.isprintable() for char in value))})
    return result


def _mcp_container_inspect(row):
    if not isinstance(row, dict):
        raise ValueError("Invalid Docker inspection result")
    result = _mcp_fields(row, ("Id", "Name", "Created", "RestartCount"))
    config = _mcp_fields(row.get("Config"), ("Image", "User"))
    if config:
        result["Config"] = config
    state = row.get("State")
    if isinstance(state, dict):
        visible = _mcp_fields(state, (
            "Status", "Running", "Paused", "Restarting", "OOMKilled", "Dead",
            "Pid", "ExitCode", "StartedAt", "FinishedAt",
        ))
        health = _mcp_fields(state.get("Health"), ("Status", "FailingStreak"))
        if health:
            visible["Health"] = health  # Never include Health.Log.Output.
        result["State"] = visible
    host = row.get("HostConfig")
    if isinstance(host, dict):
        visible = _mcp_fields(host, ("NetworkMode", "Memory", "NanoCpus", "PidsLimit"))
        policy = _mcp_fields(host.get("RestartPolicy"), ("Name", "MaximumRetryCount"))
        if policy:
            visible["RestartPolicy"] = policy
        result["HostConfig"] = visible
    mounts = row.get("Mounts")
    if isinstance(mounts, list):
        # Source, Driver options and propagation metadata can expose secrets.
        result["Mounts"] = [_mcp_fields(item, ("Type", "Name", "Destination", "RW"))
                            for item in mounts[:128] if isinstance(item, dict)]
    networks = row.get("NetworkSettings")
    if isinstance(networks, dict) and isinstance(networks.get("Networks"), dict):
        result["NetworkNames"] = [name for name in networks["Networks"]
                                  if isinstance(name, str) and re.fullmatch(r"[a-zA-Z0-9_.-]{1,128}", name)][:128]
    return result
MUTATING_TOOLS = set(WRITE_TOOLS) | set(TERMINAL_TOOLS)
ACTION_TOOLS = {
    "container_start": ("start", {"containers.write"}),
    "container_stop": ("stop", {"containers.write"}),
    "container_restart": ("restart", {"containers.write"}),
    "container_pause": ("pause", {"containers.write"}),
    "container_unpause": ("unpause", {"containers.write"}),
    "container_remove": ("remove", {"containers.write", "destructive"}),
}

_dimensions = {"cols": {"type": "integer", "minimum": 20, "maximum": 300},
               "rows": {"type": "integer", "minimum": 5, "maximum": 120}}
_terminal_schemas = {}
_terminal_schemas["host_exec"] = {"required": ["profile", "command"], "properties": {
    "command": {"type": "string", "minLength": 1, "maxLength": 8192},
    "timeout": {"type": "integer", "minimum": 1, "maximum": 300}}}
_terminal_schemas["host_terminal_open"] = {"required": ["profile"], "properties": _dimensions}
for _name in ("host_terminal_read", "host_terminal_write", "host_terminal_resize", "host_terminal_close"):
    _terminal_schemas[_name] = {"required": ["profile", "terminal"], "properties": {"terminal": {"type": "string"}}}
_terminal_schemas["host_terminal_read"]["properties"].update({"offset": {"type": "integer", "minimum": 0}})
_terminal_schemas["host_terminal_write"]["properties"].update({"data": {"type": "string", "description": "Base64-encoded UTF-8 keystrokes; at most 16 KiB decoded"}})
_terminal_schemas["host_terminal_write"]["required"].append("data")
_terminal_schemas["host_terminal_resize"]["properties"].update(_dimensions)
READ_SCHEMAS = {
    "host_info": {"required": ["profile"]},
    "list_containers": {"required": ["profile"]},
    "inspect_container": {"required": ["profile", "container"], "properties": {"container": {"type": "string"}}},
    "container_logs": {"required": ["profile", "container"], "properties": {"container": {"type": "string"}, "tail": {"type": "integer", "minimum": 1, "maximum": 2000}}},
    "container_stats": {"required": ["profile"]},
    "list_images": {"required": ["profile"]},
    "list_volumes": {"required": ["profile"]},
    "list_networks": {"required": ["profile"]},
}
for _name in ACTION_TOOLS:
    READ_SCHEMAS[_name] = {"required": ["profile", "container"], "properties": {"container": {"type": "string"}}}
READ_SCHEMAS["create_container"] = {
    "required": ["profile", "name", "image"],
    "properties": {
        "name": {"type": "string", "minLength": 1, "maxLength": 128},
        "image": {"type": "string", "minLength": 1, "maxLength": 255},
        "ports": {"type": "array", "maxItems": 32, "items": {"type": "object", "properties": {
            "host_port": {"type": "integer", "minimum": 1, "maximum": 65535},
            "container_port": {"type": "integer", "minimum": 1, "maximum": 65535},
            "protocol": {"type": "string", "enum": ["tcp", "udp"]},
            "host_ip": {"type": "string"}}, "required": ["host_port", "container_port"], "additionalProperties": False}},
        "environment": {"type": "object", "maxProperties": 100, "additionalProperties": {"type": "string"}},
        "volumes": {"type": "array", "maxItems": 32, "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "container_path": {"type": "string"}}, "required": ["name", "container_path"], "additionalProperties": False}},
        "command": {"type": "array", "maxItems": 128, "items": {"type": "string", "maxLength": 1024}},
        "restart": {"type": "string", "enum": ["no", "always", "unless-stopped", "on-failure"]},
    },
}


READ_SCHEMAS.update(_terminal_schemas)


def required_capabilities(name):
    if name in TERMINAL_TOOLS:
        return {"read", "host.exec"}
    if name in ACTION_TOOLS:
        return {"read", *ACTION_TOOLS[name][1]}
    if name == "create_container":
        return {"read", "install"}
    return {"read"}


def _container_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,200}", value):
        raise ValueError("Invalid container identifier")
    return value


def _address_alias(value):
    text = value.strip().casefold()
    try:
        return ipaddress.ip_address(text.removeprefix("[").removesuffix("]")).compressed, None
    except ValueError:
        pass
    try:
        parsed = urlsplit(text if "://" in text else "//" + text)
        host = parsed.hostname
        if host and not any(character.isspace() for character in host):
            if ":" in host:
                host = ipaddress.ip_address(host).compressed
            return host, parsed.port
    except ValueError:
        pass
    return None


def _profile_addresses(profile):
    addresses = set()
    for key in ("host", "endpoint", "panel_host"):
        value = profile.get(key)
        if not isinstance(value,str) or not value.strip():
            continue
        address = _address_alias(value)
        if address:
            host, port = address
            addresses.add((host, None))
            port = profile.get("port", port) if key == "host" else port
            if port is not None:
                try:
                    addresses.add((host, int(port)))
                except (ValueError, TypeError):
                    pass
    return addresses


def _create_args(arguments, engine):
    name, image = arguments.get("name"), arguments.get("image")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name):
        raise ValueError("Invalid container name")
    if not isinstance(image, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:@+-]{0,254}", image):
        raise ValueError("Invalid Docker image reference")

    entries = engine.containers()
    if any(name in str(value.get("Names", "")).split(",") for value in entries):
        raise ValueError("Container name already exists")
    args = ["run", "--detach", "--name", name]
    restart = arguments.get("restart", "unless-stopped")
    if restart not in {"no", "always", "unless-stopped", "on-failure"}:
        raise ValueError("Unsupported restart policy")
    args += ["--restart", restart]

    ports = arguments.get("ports", [])
    if not isinstance(ports, list) or len(ports) > 32:
        raise ValueError("Invalid port mappings")
    occupied = set()
    for entry in entries:
        for published in re.finditer(r":(\d+)->\d+/(tcp|udp)", str(entry.get("Ports", ""))):
            occupied.add((int(published.group(1)), published.group(2)))
    requested = set()
    for item in ports:
        if not isinstance(item, dict):
            raise ValueError("Invalid port mapping")
        host_port, container_port = item.get("host_port"), item.get("container_port")
        protocol = item.get("protocol", "tcp")
        host_ip = item.get("host_ip", "127.0.0.1")
        if type(host_port) is not int or type(container_port) is not int or not 1 <= host_port <= 65535 or not 1 <= container_port <= 65535 or protocol not in {"tcp", "udp"}:
            raise ValueError("Invalid port mapping")
        try:
            host_address = ipaddress.IPv4Address(host_ip)
        except (ipaddress.AddressValueError, TypeError):
            raise ValueError("Use an IPv4 address for a published host port") from None
        if not host_address.is_loopback:
            raise ValueError("MCP-created containers may publish ports only on the local loopback interface")
        host_ip = str(host_address)
        key = (host_port, protocol)
        if key in requested or key in occupied:
            raise ValueError(f"Host port {host_port}/{protocol} is already in use")
        requested.add(key)
        args += ["--publish", f"{host_ip}:{host_port}:{container_port}/{protocol}"]

    environment = arguments.get("environment", {})
    if not isinstance(environment, dict) or len(environment) > 100:
        raise ValueError("Invalid environment variables")
    for key, value in environment.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or not isinstance(value, str) or len(value) > 4096 or "\0" in value:
            raise ValueError("Invalid environment variable")
        args += ["--env", key + "=" + value]

    volumes = arguments.get("volumes", [])
    if not isinstance(volumes, list) or len(volumes) > 32:
        raise ValueError("Invalid volume mappings")
    names = set()
    for item in volumes:
        if not isinstance(item, dict):
            raise ValueError("Invalid volume mapping")
        volume, path = item.get("name"), item.get("container_path")
        if not isinstance(volume, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", volume) or volume in names:
            raise ValueError("Only uniquely named Docker volumes are supported")
        if not isinstance(path, str) or not path.startswith("/") or "\0" in path or ".." in path.split("/") or ":" in path:
            raise ValueError("Volume destination must be a safe absolute container path")
        names.add(volume)
        args += ["--volume", f"{volume}:{path}"]

    command = arguments.get("command", [])
    if not isinstance(command, list) or len(command) > 128 or not all(isinstance(v, str) and len(v) <= 1024 and "\0" not in v for v in command):
        raise ValueError("Container command must be a bounded array of strings")
    args += [image, *command]
    return args, name, image


class MCPService:
    def __init__(self, state, token, backend_factory=None, terminal_factory=None, command_factory=SSHCommand):
        if backend_factory is None:
            backend_factory = DockerBackend
        self.state, self.digest, self.factory = state, hashlib.sha256(token.encode()).hexdigest(), backend_factory
        self.negotiated = False
        self.initialized = False
        self.terminals = HostTerminals(terminal_factory)
        self.command_factory = command_factory
        self.connection_id = secrets.token_urlsafe(24)
        self.stopped = threading.Event()
        self.watcher = None

    def close(self):
        self.stopped.set()
        self.terminals.close_all()

    def authorize_host(self, name, profile_id, revision=None):
        grant = self.grant()
        if (grant.get("mode") != "write" or name not in grant.get("tools", [])
                or grant.get("allow_host_terminal") is not True
                or profile_id not in grant.get("profiles", [])
                or profile_id not in grant.get("terminal_profiles", [])
                or revision is not None and revision != grant.get("revision")):
            raise PermissionError("Host tool or device is outside this grant")
        profile = self.state.profile(profile_id)
        if not required_capabilities(name) <= set(profile.get("permissions", ["read"])):
            raise PermissionError("Profile host permission was revoked")
        host_profile(profile)

    def host_available(self, name, profile_id):
        try:
            self.authorize_host(name, profile_id)
            return True
        except (PermissionError, ValueError):
            return False

    def _watch_terminals(self):
        while not self.stopped.wait(.5):
            with self.terminals.lock:
                for value in list(self.terminals.sessions.values()):
                    try:
                        self.authorize_host("host_terminal_open", value.profile, value.revision)
                    except Exception:
                        self.terminals.close(value.id, self.digest, self.connection_id)

    @staticmethod
    def integer(arguments, key, default, minimum, maximum):
        value = arguments.get(key, default)
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError("Invalid " + key)
        return value

    def host_call(self, name, arguments, profile, grant):
        profile_id, revision = profile["id"], grant.get("revision")
        authorize = lambda: self.authorize_host(name, profile_id, revision)
        authorize()
        if name == "host_exec":
            command = arguments.get("command")
            if not isinstance(command, str) or not command.strip() or len(command) > 8192 or "\x00" in command:
                raise ValueError("Provide a host command of at most 8192 characters")
            timeout = self.integer(arguments, "timeout", 30, 1, 300)
            runner = self.command_factory(profile)
            try:
                result = runner.run(command, timeout, authorize)
                authorize()
                return result
            finally:
                runner.close()
        if name in {"host_terminal_open", "host_terminal_resize"}:
            cols = self.integer(arguments, "cols", 120, 20, 300)
            rows = self.integer(arguments, "rows", 32, 5, 120)
        if name == "host_terminal_open":
            value = self.terminals.open(profile, self.digest, self.connection_id, cols, rows, limit=8)
            value.revision = revision
            try:
                authorize()
            except Exception:
                self.terminals.close(value.id, self.digest, self.connection_id)
                raise
            if not self.watcher or not self.watcher.is_alive():
                self.watcher = threading.Thread(target=self._watch_terminals, name="dcc-mcp-revocation", daemon=True)
                self.watcher.start()
            return {"terminal": value.id, "profile": profile_id, "encoding": "base64", "offset": 0}
        terminal = arguments.get("terminal")
        if not isinstance(terminal, str) or len(terminal) > 100:
            raise ValueError("Invalid terminal session")
        value = self.terminals.get(terminal, self.digest, self.connection_id)
        if value.profile != profile_id or value.revision != revision:
            raise PermissionError("Terminal belongs to another device or grant revision")
        if name == "host_terminal_read":
            return value.output(self.integer(arguments, "offset", 0, 0, 2**63-1), max_bytes=65536)
        if name == "host_terminal_write":
            data = arguments.get("data")
            if not isinstance(data, str) or len(data) > 21848:
                raise ValueError("Terminal input must be base64 with at most 16 KiB decoded")
            try:
                raw = base64.b64decode(data, validate=True)
            except ValueError:
                raise ValueError("Invalid base64 terminal input") from None
            if not 1 <= len(raw) <= 16384:
                raise ValueError("Terminal input must contain 1 to 16384 bytes")
            authorize()
            value.connection.write(raw)
        elif name == "host_terminal_resize":
            value.connection.resize(cols, rows)
        elif name == "host_terminal_close":
            self.terminals.close(value.id, self.digest, self.connection_id)
        value.touched = time.monotonic()
        return {"ok": True}

    def grant(self):
        rows = self.state.rows("SELECT * FROM grants WHERE token=?", (self.digest,))
        if not rows:
            raise PermissionError("MCP access is invalid or revoked")
        if rows[0]["revoked"]:
            raise PermissionError("MCP access is invalid or revoked")
        value = json.loads(rows[0]["data"])
        if getattr(self, "public_check", None) and (value.get("allow_public") is not True or not self.public_check()):
            raise PermissionError("A current public MCP session approved with 2FA is required")
        if value.get("expires") is not None and value["expires"] <= time.time():
            raise PermissionError("MCP access has expired")
        if rows[0]["paused"]:
            raise PermissionError("MCP access is paused")
        return value

    def resolve_profile(self, selector, grant):
        if not isinstance(selector,str) or not selector.strip():
            raise ValueError("Provide a granted profile name, host address, or profile ID")
        selector = selector.strip()
        selected = selector.casefold()
        address = _address_alias(selector)
        profile_ids = dict.fromkeys(grant.get("profiles", []))
        if selector in profile_ids:
            return selector
        matches = []
        for profile_id in profile_ids:
            try:
                profile=self.state.profile(profile_id)
            except ValueError:
                continue
            names = {str(profile.get(key) or "").strip().casefold() for key in ("name", "distro", "context")}
            if selected in names or address in _profile_addresses(profile):
                matches.append(profile_id)
        if len(matches)==1:
            return matches[0]
        if len(matches)>1:
            raise ValueError("This profile name or address matches multiple granted profiles; use a unique name or profile ID")
        raise PermissionError("No granted profile matches this name or host address")

    def profile_choices(self, grant):
        choices=[]
        for profile_id in grant.get("profiles",[]):
            try:
                profile=self.state.profile(profile_id)
            except ValueError:
                continue
            name=str(profile.get("name") or profile_id)
            address=profile.get("host") or profile.get("endpoint") or profile.get("distro") or profile.get("context")
            if profile.get("host") and profile.get("port") and str(profile["port"]) != "22":
                host = profile["host"]
                address = f"[{host}]:{profile['port']}" if ":" in host and not host.startswith("[") else f"{host}:{profile['port']}"
            choices.append(name+(f" ({address})" if address else ""))
        return choices

    def call(self, name, arguments):
        grant = self.grant()
        profile_id = arguments.get("profile") if isinstance(arguments, dict) else None
        status = 200
        try:
            if name not in TOOLS or name not in grant.get("tools", []):
                raise PermissionError("Tool or profile is outside this grant")
            profile_id=self.resolve_profile(profile_id,grant)
            if name in MUTATING_TOOLS and grant.get("mode", "read") != "write":
                raise PermissionError("Write tools require a write-enabled grant")
            if name == "container_remove" and not grant.get("allow_destructive", False):
                raise PermissionError("Container removal requires explicit destructive authorization")
            profile = self.state.profile(profile_id, private=True)
            required = required_capabilities(name)
            if not required.issubset(set(profile.get("permissions", ["read"]))):
                raise PermissionError("Profile permission was revoked")
            engine = self.factory(profile) if name not in TERMINAL_TOOLS else None
            if name in TERMINAL_TOOLS:
                result = self.host_call(name, arguments, profile, grant)
            elif name == "host_info":
                result = profile_facts.remember(self.state, profile, engine.info())
            elif name == "list_containers":
                result = _mcp_container_list(engine.containers())
            elif name == "inspect_container":
                result = _mcp_container_inspect(engine.inspect(_container_id(arguments.get("container"))))
            elif name == "container_logs":
                target = _container_id(arguments.get("container"))
                result = engine.logs(target, max(1, min(int(arguments.get("tail", 200)), 2000)))
            elif name == "container_stats":
                result = _mcp_docker_rows(name, engine.stats())
            elif name in {"list_images", "list_volumes", "list_networks"}:
                result = _mcp_docker_rows(name, engine.resources(name.removeprefix("list_")))
            elif name in ACTION_TOOLS:
                target = _container_id(arguments.get("container"))
                action = ACTION_TOOLS[name][0]
                engine.action(target, action)
                result = {"container": target, "operation": action, "ok": True, "volumes_deleted": False}
            else:
                args, container_name, image = _create_args(arguments, engine)
                created_id = engine.run(args, timeout=600).strip()
                result = {"container": container_name, "image": image, "id": created_id[:128], "ok": True}
            self.state.audit("mcp:" + str(grant.get("name", "client")), name, profile_id, 200)
            return {"content": [{"type": "text", "text": json.dumps(redact(result), ensure_ascii=False)}], "isError": False}
        except PermissionError:
            status = 403
            raise
        except Exception:
            status = 400
            raise
        finally:
            if status != 200:
                self.state.audit("mcp:" + str(grant.get("name", "client")), name if isinstance(name, str) else "invalid", str(profile_id or "invalid"), status)

    def handle(self, message):
        method = message.get("method")
        if "id" not in message:
            if method == "notifications/initialized" and self.negotiated:
                self.grant()
                self.initialized = True
            return None
        self.grant()
        params = message.get("params", {})
        if method == "initialize":
            if self.negotiated:
                raise ValueError("Already initialized")
            version = params.get("protocolVersion")
            if version not in {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}:
                version = "2025-11-25"
            grant=self.grant()
            mode = grant.get("mode", "read")
            choices=self.profile_choices(grant)
            selector_help=("Select a granted connection profile by its exact name or host/IP address; the profile ID also works when names or addresses are ambiguous. Granted profiles: "+", ".join(choices)+". ") if choices else "Select a granted connection profile by name, host/IP address, or profile ID. "
            result = {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "dcc-web", "version": Path(__file__).with_name("VERSION").read_text().strip()},
                      "instructions": "Manage granted devices ONLY through DCC MCP. If access or a tool is unavailable, report it; do not bypass via system SSH/Docker CLI, DCC Desktop or browser terminals. Host tools require explicit device consent and run as the profile's SSH account. " + selector_help+("Read-only tools are enabled." if mode == "read" else "Only explicitly granted tools and profiles are enabled. Every operation is checked against the current profile permissions. Container removal does not delete volumes.") + " Reconnect MCP after grant edits. Local stdio is supported. Public HTTPS Streamable HTTP requires explicit administrator enablement, a public grant, OAuth PKCE and fresh 2FA approval."}
            self.negotiated = True
        elif method == "ping":
            result = {}
        elif not self.initialized:
            return {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32002, "message": "Complete initialize and notifications/initialized first"}}
        elif method == "tools/list":
            grant = self.grant()
            result = {"tools": []}
            for name in grant.get("tools", []):
                if name not in TOOLS or name in MUTATING_TOOLS and grant.get("mode", "read") != "write":
                    continue
                if name in TERMINAL_TOOLS and not any(
                        self.host_available(name, ident) for ident in grant.get("terminal_profiles", [])):
                    continue
                definition = READ_SCHEMAS[name]
                properties = {"profile": {"type": "string", "description": "Exact granted profile name or host/IP address; profile ID is also accepted."}, **definition.get("properties", {})}
                write = name in MUTATING_TOOLS
                result["tools"].append({"name": name, "description": TOOLS[name],
                    "inputSchema": {"type": "object", "properties": properties, "required": definition["required"], "additionalProperties": False},
                    "annotations": {"readOnlyHint": not write, "destructiveHint": name == "container_remove" or name in TERMINAL_TOOLS, "openWorldHint": name == "create_container" or name in TERMINAL_TOOLS}})
        elif method == "tools/call":
            result = self.call(params.get("name"), params.get("arguments", {}))
        else:
            return {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "Method is not implemented"}}
        return {"jsonrpc": "2.0", "id": message["id"], "result": result}


def register_mcp(app, state, profile_lookup, reauthenticate, confirmed):
    @app.route("/api/mcp/grants", methods=["GET", "POST"])
    def grants():
        admin()
        if request.method == "GET":
            grants_list = []
            for row in state.rows("SELECT id,data,revoked,paused FROM grants"):
                metadata = json.loads(row["data"])
                metadata.setdefault("mode", "read")
                metadata.setdefault("allow_destructive", False)
                grants_list.append(dict(id=row["id"], revoked=bool(row["revoked"]), paused=bool(row["paused"]), **metadata))
            return jsonify(clients=CLIENTS, tools=TOOLS, read_tools=READ_TOOLS, write_tools=WRITE_TOOLS, terminal_tools=TERMINAL_TOOLS,
                           grants=grants_list, transports={"stdio": "scoped read/write", "streamable_http": "optional HTTPS with OAuth/PKCE and fresh DCC 2FA"})
        return save_grant(request.get_json() or {})

    def save_grant(data, existing=None):
        if not isinstance(data, dict):
            abort(400)
        mode = data.get("mode", "read")
        if mode not in ("read", "write"):
            abort(400, "Choose read-only or read/write access")
        profiles = data.get("profiles", [])
        tools = data.get("tools", list(READ_TOOLS))
        client = data.get("client", "Generic MCP")
        if (client not in CLIENTS or not isinstance(profiles, list) or not 1 <= len(profiles) <= 100
                or not all(isinstance(profile, str) and profile for profile in profiles)
                or len(set(profiles)) != len(profiles) or not isinstance(tools, list) or not tools
                or not all(isinstance(tool, str) for tool in tools)
                or len(set(tools)) != len(tools) or set(tools) - set(TOOLS)):
            abort(400, "Choose existing profiles and available tools")
        if mode == "read" and set(tools) - set(READ_TOOLS):
            abort(400, "Read-only grants cannot include write tools")
        selected_writes = set(tools) & MUTATING_TOOLS
        if mode == "write" and not selected_writes:
            abort(400, "Select at least one write tool")
        allow_destructive = data.get("allow_destructive") is True
        if "container_remove" in selected_writes and not allow_destructive:
            abort(400, "Container removal requires explicit destructive authorization")
        allow_host = data.get("allow_host_terminal") is True
        terminal_profiles = data.get("terminal_profiles", [])
        if (not isinstance(terminal_profiles, list) or not all(isinstance(p, str) for p in terminal_profiles)
                or len(set(terminal_profiles)) != len(terminal_profiles) or set(terminal_profiles) - set(profiles)
                or bool(set(tools) & set(TERMINAL_TOOLS)) != allow_host
                or bool(terminal_profiles) != allow_host):
            abort(400, "Select terminal devices within this grant and explicitly allow terminal access")
        for profile_id in profiles:
            profile = profile_lookup(profile_id)
            permissions = set(profile.get("permissions", ["read"]))
            if any(not required_capabilities(tool).issubset(permissions) for tool in tools if tool not in TERMINAL_TOOLS):
                abort(400, "The profile does not have the permission required by the selected tool")
            if profile_id in terminal_profiles:
                if not {"read", "host.exec"} <= permissions or profile.get("kind") not in {"ssh", "balena"}:
                    abort(400, "Terminal devices require SSH or Balena profiles with host.exec permission")
        allow_public = data.get("allow_public") is True
        if allow_public and not state.mfa.enabled(g.user['id']):
            abort(400, "Enable account 2FA before granting public MCP access")
        if mode == "write" or existing or allow_public:
            reauthenticate(data)
        unlimited = data.get("unlimited") is True
        try:
            days = int(data.get("days", 30))
        except (TypeError, ValueError, OverflowError):
            abort(400, "Validity must be a positive number of days")
        if not unlimited and not 1 <= days <= 1_000_000:
            abort(400, "Validity must be between 1 and 1000000 days, or select No expiry")
        token = secrets.token_urlsafe(40) if not existing else None
        ident = existing["id"] if existing else secrets.token_hex(12)
        previous = json.loads(existing["data"]) if existing else {}
        public_minutes = data.get('public_session_minutes',previous.get('public_session_minutes',30))
        if type(public_minutes) is not int or public_minutes not in (15,30,60):
            abort(400, "Public session duration must be 15, 30 or 60 minutes")
        expires = None if unlimited else time.time() + 86400 * days
        if existing and data.get("renew_expiry") is not True:
            expires = previous.get("expires")
        metadata = {"name": str(data.get("name", "MCP client"))[:80], "client": client, "profiles": profiles,
                    "tools": tools, "mode": mode, "allow_destructive": allow_destructive,
                    "allow_host_terminal": allow_host, "terminal_profiles": terminal_profiles,
                    "allow_public": allow_public,
                    "public_owner": previous.get('public_owner') or g.user['id'] if allow_public else None,
                    "public_session_minutes": public_minutes,
                    "revision": secrets.token_hex(12),
                    "permissions": ["read", "write"] if mode == "write" else ["read"], "created": previous.get("created", time.time()),
                    "expires": expires}
        with state.connect() as db:
            if existing:
                # Compare metadata to avoid overwriting a concurrent administrator's edit.
                cursor = db.execute("UPDATE grants SET data=? WHERE id=? AND data=? AND revoked=0",
                                    (json.dumps(metadata), ident, existing["data"]))
                if cursor.rowcount != 1:
                    abort(409, "This grant changed or was revoked. Reload it before editing.")
            else:
                db.execute("INSERT INTO grants(id,token,data) VALUES(?,?,?)", (ident, hashlib.sha256(token.encode()).hexdigest(), json.dumps(metadata)))
            state.write_audit(db, g.user["id"], "mcp.grant.edit" if existing else "mcp.grant.create", ident, 200 if existing else 201)
        if existing:
            return jsonify(id=ident, token_preserved=True, notice="The existing token is unchanged. Reconnect MCP and refresh the exported instructions; open terminals were closed.")
        return jsonify(id=ident, token=token, notice="Shown once. Store this token in the client's environment, not its configuration file."), 201

    @app.put("/api/mcp/grants/<grant_id>")
    def edit_grant(grant_id):
        admin()
        rows = state.rows("SELECT * FROM grants WHERE id=?", (grant_id,))
        if not rows:
            abort(404)
        if rows[0]["revoked"]:
            abort(409, "A revoked token cannot be restored; create a new grant")
        return save_grant(request.get_json() or {}, rows[0])

    def grant_transition(grant_id,action,sql):
        admin()
        data=request.get_json() or {}
        confirmed(data,"mcp.grant."+action,"workspace",grant_id)
        with state.connect() as db:
            if db.execute(sql, (grant_id,)).rowcount != 1:
                if not db.execute("SELECT 1 FROM grants WHERE id=?", (grant_id,)).fetchone():
                    abort(404)
                abort(409, "This grant has already been revoked")
            state.write_audit(db, g.user["id"], "mcp.grant." + action, grant_id, 200)
            if action in {'pause','revoke'}:
                db.execute("UPDATE mcp_oauth_sessions SET revoked=1 WHERE json_extract(data,'$.grant')=?",(grant_id,))
        return jsonify(ok=True)

    @app.post("/api/mcp/grants/<grant_id>/pause")
    def pause_grant(grant_id):
        return grant_transition(grant_id,"pause","UPDATE grants SET paused=1 WHERE id=? AND revoked=0")

    @app.post("/api/mcp/grants/<grant_id>/resume")
    def resume_grant(grant_id):
        return grant_transition(grant_id,"resume","UPDATE grants SET paused=0 WHERE id=? AND revoked=0")

    @app.delete("/api/mcp/grants/<grant_id>")
    def revoke(grant_id):
        return grant_transition(grant_id,"revoke","UPDATE grants SET revoked=1 WHERE id=? AND revoked=0")

    @app.delete("/api/mcp/grants/<grant_id>/history")
    def delete_grant_history(grant_id):
        admin()
        data=request.get_json() or {}
        confirmed(data,"mcp.grant.delete-history","workspace",grant_id)
        with state.connect() as db:
            cursor=db.execute("DELETE FROM grants WHERE id=? AND revoked=1",(grant_id,))
            if cursor.rowcount!=1:
                exists=db.execute("SELECT revoked FROM grants WHERE id=?",(grant_id,)).fetchone()
                if not exists:
                    abort(404)
                abort(409,"Only revoked grants can be removed from history")
            state.write_audit(db, g.user["id"], "mcp.grant.history.deleted", grant_id, 200)
        return jsonify(ok=True)

    def export_grant(grant_id):
        admin()
        rows = state.rows("SELECT data,paused FROM grants WHERE id=? AND revoked=0", (grant_id,))
        if not rows:
            abort(404)
        metadata = json.loads(rows[0]["data"])
        expires = metadata.get("expires")
        if rows[0]["paused"] or (expires is not None and expires <= time.time()):
            abort(409, "This MCP grant is paused or expired.")
        return metadata

    def export_variant(metadata):
        variant = request.args.get("variant", "standard")
        try:
            instruction_path(metadata["client"], variant)
        except ValueError as error:
            abort(400, str(error))
        return variant

    def render_grant(grant_id, metadata, variant):
        transport = export_transport(grant_id, metadata)
        tools = [
            name for name in metadata.get("tools", [])
            if name in TOOLS and (name in READ_TOOLS or metadata.get("mode") == "write")
            and (name != "container_remove" or metadata.get("allow_destructive") is True)
        ]
        profiles = []
        for profile_id in dict.fromkeys(metadata.get("profiles", [])):
            try:
                profile = state.profile(profile_id)
            except ValueError:
                continue
            permissions = set(profile.get("permissions", ["read"]))
            if "read" not in permissions:
                continue
            # Include hostname/IP aliases only, excluding endpoint userinfo, paths and queries.
            addresses = sorted(host for host, port in _profile_addresses(profile) if port is None)
            profiles.append({
                "id": profile_id,
                "name": profile.get("name") or profile_id,
                "addresses": addresses,
                "tools": [name for name in tools if required_capabilities(name) <= permissions
                          and (name not in TERMINAL_TOOLS or metadata.get("allow_host_terminal") is True
                               and profile_id in metadata.get("terminal_profiles", []) and profile.get("kind") in {"ssh", "balena"})],
                "environment": profile_facts.snapshot(state, profile),
            })
        return agent_instructions(grant_id, dict(metadata,export_transport=transport), profiles, TOOLS, variant)

    def export_transport(grant_id, metadata):
        transport = request.args.get('transport','stdio')
        if transport not in {'stdio','https'}: abort(400)
        if transport == 'https':
            public = app.extensions['dcc_mcp_http']
            if not public.enabled(): abort(409,'Enable optional public MCP in AI / MCP settings first')
            try: public.oauth.grant(grant_id)
            except PermissionError: abort(409,'Allow public MCP sessions on this grant with its owner account 2FA')
            if metadata['client'] != 'OpenAI Codex': abort(400,'Public MCP export currently supports OpenAI Codex; choose stdio for this client')
        return transport

    def export_configuration(grant_id, metadata):
        transport = export_transport(grant_id, metadata)
        if transport == 'https':
            return dict(export_public_client(metadata['client'],app.extensions['dcc_mcp_http'].saved()['origin']+'/mcp/'+grant_id),platform=export_platform())
        command,args = export_launcher()
        return dict(export_client(metadata['client'],command,args),launcher='docker' if command=='docker' else 'native',transport='stdio',platform=export_platform())

    def export_platform():
        platform = request.args.get("platform", "auto")
        if platform not in {"auto", "windows", "linux", "macos"}:
            abort(400, "Choose Windows, Linux or macOS for the MCP client")
        return platform

    def export_launcher():
        platform = export_platform()
        args = [str(Path(__file__).with_name("web.py")), "--data", str(state.directory), "--mcp-stdio"]
        command = sys.executable
        if os.environ.get("DCC_WEB_CONTAINER_NAME"):
            import docker
            from host_setup import local_container
            client = docker.from_env(timeout=10)
            try:
                container = local_container(client)
                command = "docker"
                args = ["exec", "-i", "--env", "DCC_MCP_TOKEN", container.name,
                        "/usr/local/bin/dcc-web-entrypoint", sys.executable, *args]
            finally:
                client.close()
        elif platform not in {"auto", "windows" if os.name == "nt" else "macos" if sys.platform == "darwin" else "linux"}:
            abort(400, "This native stdio export requires the server OS and paths. Use a container export for another client platform.")
        return command, args

    def send_bundle(grant_id, metadata, variant, config, filename):
        instructions = render_grant(grant_id, metadata, variant)
        bundle = client_project_archive(metadata["client"], config["configuration"], instructions, variant,
                                        export_platform(), config.get("launcher") == "docker", config.get('transport','stdio'))
        state.audit(g.user["id"], "mcp:bundle-download", grant_id, 200)
        return send_file(bundle, mimetype="application/zip", as_attachment=True, download_name=filename)

    @app.get("/api/mcp/config/<grant_id>")
    def export(grant_id):
        metadata = export_grant(grant_id)
        client = metadata["client"]
        download = request.args.get("download")
        if download not in (None, "config", "1", "plugin", "project"):
            abort(400)
        if download in ("plugin", "project") and client != "OpenAI Codex":
            abort(404)
        variant = export_variant(metadata) if download == "project" else None
        if download == "plugin":
            if export_transport(grant_id,metadata) != 'stdio': abort(400,'Use the project ZIP for public HTTPS access')
            command,args = export_launcher()
            return send_file(codex_marketplace_archive(command, args), mimetype="application/zip",
                             as_attachment=True, download_name="dcc-web-codex.zip")
        config = export_configuration(grant_id,metadata)
        if download == "project":
            return send_bundle(grant_id, metadata, variant, config, "dcc-mcp-project.zip")
        if download in ("config", "1"):
            is_toml = config["format"] == "toml"
            content = configuration_text(config["configuration"])
            filename = (PurePosixPath(CONFIG_PATHS[client]).name if download == "1"
                        else f'dcc-mcp.{config["format"]}')
            return send_file(BytesIO(content.encode("utf-8")),
                             mimetype="application/toml" if is_toml else "application/json",
                             as_attachment=True, download_name=filename)
        return jsonify(**config, path=CONFIG_PATHS[client], public_enabled=app.extensions['dcc_mcp_http'].enabled(), grant_public=metadata.get('allow_public') is True)

    @app.get("/api/mcp/instructions/<grant_id>")
    def export_instructions(grant_id):
        metadata = export_grant(grant_id)
        variant = export_variant(metadata)
        client = metadata["client"]
        download = request.args.get("download")
        if download not in (None, "1"):
            abort(400)
        filename = instruction_path(client, variant, standalone=True)
        content = render_grant(grant_id, metadata, variant)
        if download:
            state.audit(g.user["id"], "mcp:instructions-download", grant_id, 200)
            return send_file(BytesIO(content.encode("utf-8")), mimetype="text/markdown",
                             as_attachment=True, download_name=filename)
        return jsonify(content=content, filename=filename, path=instruction_path(client, variant),
                       automatic=client not in MANUAL_INSTRUCTIONS)

    @app.get("/api/mcp/bundle/<grant_id>")
    def export_bundle(grant_id):
        metadata = export_grant(grant_id)
        variant = export_variant(metadata)
        config = export_configuration(grant_id,metadata)
        suffix = "-chatgpt-web" if variant == "chatgpt-web" else ""
        return send_bundle(grant_id, metadata, variant, config, f"dcc-mcp-project{suffix}.zip")


def stdio(state, input_stream=None, output_stream=None):
    service = MCPService(state, os.environ.get("DCC_MCP_TOKEN", ""))
    input_stream, output_stream = input_stream or sys.stdin, output_stream or sys.stdout
    for stream in (input_stream, output_stream):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        _stdio_messages(service, input_stream, output_stream)
    finally:
        service.close()


def _stdio_messages(service, input_stream, output_stream):
    while True:
        line = input_stream.readline(1_000_001)
        if not line:
            break
        message = {}
        try:
            if len(line) > 1_000_000:
                raise ValueError("Request too large")
            message = json.loads(line)
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                raise ValueError("Invalid JSON-RPC request")
            response = service.handle(message)
        except PermissionError:
            response = {"jsonrpc": "2.0", "id": message.get("id") if isinstance(message, dict) else None, "error": {"code": -32001, "message": "MCP access denied"}}
        except Exception:
            response = {"jsonrpc": "2.0", "id": message.get("id") if isinstance(message, dict) else None, "error": {"code": -32602, "message": "Invalid request or unavailable DCC resource; check the granted profile in DCC Web"}}
        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
            output_stream.flush()
