"""Profile-scoped MCP stdio server with explicit read and write grants."""
import hashlib
import ipaddress
import json
import os
import re
from pathlib import Path
import secrets
import sys
import time

from flask import abort, g, jsonify, request

from engine import DockerBackend
from client_adapters import export_client
from security import admin, redact

CLIENTS = ["OpenAI Codex", "Claude Desktop", "Claude Code", "Cursor", "Windsurf", "VS Code / GitHub Copilot", "Generic MCP"]
READ_TOOLS = {
    "list_containers": "List containers in an authorized Docker profile",
    "inspect_container": "Inspect a container, with secret values redacted",
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
TOOLS = {**READ_TOOLS, **WRITE_TOOLS}
ACTION_TOOLS = {
    "container_start": ("start", {"containers.write"}),
    "container_stop": ("stop", {"containers.write"}),
    "container_restart": ("restart", {"containers.write"}),
    "container_pause": ("pause", {"containers.write"}),
    "container_unpause": ("unpause", {"containers.write"}),
    "container_remove": ("remove", {"containers.write", "destructive"}),
}
READ_SCHEMAS = {
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


def required_capabilities(name):
    if name in ACTION_TOOLS:
        return {"read", *ACTION_TOOLS[name][1]}
    if name == "create_container":
        return {"read", "install"}
    return {"read"}


def _container_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,200}", value):
        raise ValueError("Invalid container identifier")
    return value


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
    def __init__(self, state, token, backend_factory=DockerBackend):
        self.state, self.digest, self.factory = state, hashlib.sha256(token.encode()).hexdigest(), backend_factory
        self.negotiated = False
        self.initialized = False

    def grant(self):
        rows = self.state.rows("SELECT * FROM grants WHERE token=? AND revoked=0", (self.digest,))
        if not rows:
            raise PermissionError("MCP access is invalid or revoked")
        value = json.loads(rows[0]["data"])
        if value.get("expires") is not None and value["expires"] < time.time():
            raise PermissionError("MCP access has expired")
        return value

    def call(self, name, arguments):
        grant = self.grant()
        profile_id = arguments.get("profile") if isinstance(arguments, dict) else None
        status = 200
        try:
            if name not in TOOLS or name not in grant.get("tools", []) or profile_id not in grant.get("profiles", []):
                raise PermissionError("Tool or profile is outside this grant")
            if name in WRITE_TOOLS and grant.get("mode", "read") != "write":
                raise PermissionError("Write tools require a write-enabled grant")
            if name == "container_remove" and not grant.get("allow_destructive", False):
                raise PermissionError("Container removal requires explicit destructive authorization")
            profile = self.state.profile(profile_id, private=True)
            required = required_capabilities(name)
            if not required.issubset(set(profile.get("permissions", ["read"]))):
                raise PermissionError("Profile permission was revoked")
            engine = self.factory(profile)
            if name == "list_containers":
                result = engine.containers()
            elif name == "inspect_container":
                result = engine.inspect(_container_id(arguments.get("container")))
            elif name == "container_logs":
                target = _container_id(arguments.get("container"))
                result = engine.logs(target, max(1, min(int(arguments.get("tail", 200)), 2000)))
            elif name == "container_stats":
                result = engine.stats()
            elif name in {"list_images", "list_volumes", "list_networks"}:
                result = engine.resources(name.removeprefix("list_"))
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
            mode = self.grant().get("mode", "read")
            result = {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "dcc-web", "version": "0.1.7"},
                      "instructions": ("Read-only tools are enabled." if mode == "read" else "Only explicitly granted tools and profiles are enabled. Every operation is checked against the current profile permissions. Container removal does not delete volumes.") + " Use stdio transport; HTTP transport is not exposed."}
            self.negotiated = True
        elif method == "ping":
            result = {}
        elif not self.initialized:
            return {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32002, "message": "Complete initialize and notifications/initialized first"}}
        elif method == "tools/list":
            grant = self.grant()
            result = {"tools": []}
            for name in grant.get("tools", []):
                if name not in TOOLS or name in WRITE_TOOLS and grant.get("mode", "read") != "write":
                    continue
                definition = READ_SCHEMAS[name]
                properties = {"profile": {"type": "string"}, **definition.get("properties", {})}
                write = name in WRITE_TOOLS
                result["tools"].append({"name": name, "description": TOOLS[name],
                    "inputSchema": {"type": "object", "properties": properties, "required": definition["required"], "additionalProperties": False},
                    "annotations": {"readOnlyHint": not write, "destructiveHint": name == "container_remove", "openWorldHint": name == "create_container"}})
        elif method == "tools/call":
            result = self.call(params.get("name"), params.get("arguments", {}))
        else:
            return {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "Method is not implemented"}}
        return {"jsonrpc": "2.0", "id": message["id"], "result": result}


def register_mcp(app, state, profile_lookup, reauthenticate):
    @app.route("/api/mcp/grants", methods=["GET", "POST"])
    def grants():
        admin()
        if request.method == "GET":
            grants_list = []
            for row in state.rows("SELECT id,data,revoked FROM grants"):
                metadata = json.loads(row["data"])
                metadata.setdefault("mode", "read")
                metadata.setdefault("allow_destructive", False)
                grants_list.append(dict(id=row["id"], revoked=bool(row["revoked"]), **metadata))
            return jsonify(clients=CLIENTS, tools=TOOLS, read_tools=READ_TOOLS, write_tools=WRITE_TOOLS,
                           grants=grants_list, transports={"stdio": "scoped read/write", "streamable_http": "disabled"})
        data = request.get_json() or {}
        mode = data.get("mode", "read")
        if mode not in {"read", "write"}:
            abort(400, "Choose read-only or read/write access")
        profiles = data.get("profiles", [])
        tools = data.get("tools", list(READ_TOOLS))
        client = data.get("client", "Generic MCP")
        if client not in CLIENTS or not isinstance(profiles, list) or not profiles or len(profiles) > 100 or len(set(profiles)) != len(profiles) or not isinstance(tools, list) or not tools or len(set(tools)) != len(tools) or set(tools) - set(TOOLS):
            abort(400, "Choose existing profiles and available tools")
        if mode == "read" and set(tools) - set(READ_TOOLS):
            abort(400, "Read-only grants cannot include write tools")
        selected_writes = set(tools) & set(WRITE_TOOLS)
        if mode == "write" and not selected_writes:
            abort(400, "Select at least one write tool")
        allow_destructive = data.get("allow_destructive") is True
        if "container_remove" in selected_writes and not allow_destructive:
            abort(400, "Container removal requires explicit destructive authorization")
        for profile_id in profiles:
            profile = profile_lookup(profile_id)
            permissions = set(profile.get("permissions", ["read"]))
            if any(not required_capabilities(tool).issubset(permissions) for tool in tools):
                abort(400, "The profile does not have the permission required by the selected tool")
        if mode == "write":
            reauthenticate(data)
        unlimited = data.get("unlimited") is True
        try:
            days = int(data.get("days", 30))
        except (TypeError, ValueError):
            abort(400, "Validity must be a positive number of days")
        if not unlimited and not 1 <= days <= 1_000_000:
            abort(400, "Validity must be between 1 and 1000000 days, or select No expiry")
        token = secrets.token_urlsafe(40)
        ident = secrets.token_hex(12)
        metadata = {"name": str(data.get("name", "MCP client"))[:80], "client": client, "profiles": profiles,
                    "tools": tools, "mode": mode, "allow_destructive": allow_destructive,
                    "permissions": ["read", "write"] if mode == "write" else ["read"], "created": time.time(),
                    "expires": None if unlimited else time.time() + 86400 * days}
        state.execute("INSERT INTO grants(id,token,data) VALUES(?,?,?)", (ident, hashlib.sha256(token.encode()).hexdigest(), json.dumps(metadata)))
        return jsonify(id=ident, token=token, notice="Shown once. Store this token in the client's environment, not its configuration file."), 201

    @app.delete("/api/mcp/grants/<grant_id>")
    def revoke(grant_id):
        admin()
        state.execute("UPDATE grants SET revoked=1 WHERE id=?", (grant_id,))
        return jsonify(ok=True)

    @app.get("/api/mcp/config/<grant_id>")
    def export(grant_id):
        admin()
        rows = state.rows("SELECT data FROM grants WHERE id=? AND revoked=0", (grant_id,))
        if not rows:
            abort(404)
        metadata = json.loads(rows[0]["data"])
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
        return jsonify(export_client(metadata["client"], command, args))


def stdio(state, input_stream=None, output_stream=None):
    service = MCPService(state, os.environ.get("DCC_MCP_TOKEN", ""))
    input_stream, output_stream = input_stream or sys.stdin, output_stream or sys.stdout
    for stream in (input_stream, output_stream):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
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
            response = {"jsonrpc": "2.0", "id": message.get("id") if isinstance(message, dict) else None, "error": {"code": -32602, "message": "Invalid request or unavailable Docker resource"}}
        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
            output_stream.flush()
