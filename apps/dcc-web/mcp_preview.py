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
from urllib.parse import urlsplit

from flask import abort, g, jsonify, request, send_file

from engine import DockerBackend
from client_adapters import (
    CONFIG_PATHS, MANUAL_INSTRUCTIONS, agent_instructions, client_project_archive,
    codex_marketplace_archive, configuration_text, export_client, instruction_path,
)
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
    def __init__(self, state, token, backend_factory=DockerBackend):
        self.state, self.digest, self.factory = state, hashlib.sha256(token.encode()).hexdigest(), backend_factory
        self.negotiated = False
        self.initialized = False

    def grant(self):
        rows = self.state.rows("SELECT * FROM grants WHERE token=?", (self.digest,))
        if not rows:
            raise PermissionError("MCP access is invalid or revoked")
        if rows[0]["revoked"]:
            raise PermissionError("MCP access is invalid or revoked")
        value = json.loads(rows[0]["data"])
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
            grant=self.grant()
            mode = grant.get("mode", "read")
            choices=self.profile_choices(grant)
            selector_help=("Select a granted connection profile by its exact name or host/IP address; the profile ID also works when names or addresses are ambiguous. Granted profiles: "+", ".join(choices)+". ") if choices else "Select a granted connection profile by name, host/IP address, or profile ID. "
            result = {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "dcc-web", "version": "0.2.6"},
                      "instructions": selector_help+("Read-only tools are enabled." if mode == "read" else "Only explicitly granted tools and profiles are enabled. Every operation is checked against the current profile permissions. Container removal does not delete volumes.") + " Use stdio transport; HTTP transport is not exposed."}
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
                properties = {"profile": {"type": "string", "description": "Exact granted profile name or host/IP address; profile ID is also accepted."}, **definition.get("properties", {})}
                write = name in WRITE_TOOLS
                result["tools"].append({"name": name, "description": TOOLS[name],
                    "inputSchema": {"type": "object", "properties": properties, "required": definition["required"], "additionalProperties": False},
                    "annotations": {"readOnlyHint": not write, "destructiveHint": name == "container_remove", "openWorldHint": name == "create_container"}})
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
            return jsonify(clients=CLIENTS, tools=TOOLS, read_tools=READ_TOOLS, write_tools=WRITE_TOOLS,
                           grants=grants_list, transports={"stdio": "scoped read/write", "streamable_http": "disabled"})
        data = request.get_json() or {}
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
        except (TypeError, ValueError, OverflowError):
            abort(400, "Validity must be a positive number of days")
        if not unlimited and not 1 <= days <= 1_000_000:
            abort(400, "Validity must be between 1 and 1000000 days, or select No expiry")
        token = secrets.token_urlsafe(40)
        ident = secrets.token_hex(12)
        metadata = {"name": str(data.get("name", "MCP client"))[:80], "client": client, "profiles": profiles,
                    "tools": tools, "mode": mode, "allow_destructive": allow_destructive,
                    "permissions": ["read", "write"] if mode == "write" else ["read"], "created": time.time(),
                    "expires": None if unlimited else time.time() + 86400 * days}
        with state.connect() as db:
            db.execute("INSERT INTO grants(id,token,data) VALUES(?,?,?)", (ident, hashlib.sha256(token.encode()).hexdigest(), json.dumps(metadata)))
            state.write_audit(db, g.user["id"], "mcp.grant.create", ident, 201)
        return jsonify(id=ident, token=token, notice="Shown once. Store this token in the client's environment, not its configuration file."), 201

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
                "tools": [name for name in tools if required_capabilities(name) <= permissions],
            })
        return agent_instructions(grant_id, metadata, profiles, TOOLS, variant)

    def export_launcher():
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
        return command, args

    def send_bundle(grant_id, metadata, variant, config, filename):
        instructions = render_grant(grant_id, metadata, variant)
        bundle = client_project_archive(metadata["client"], config["configuration"], instructions, variant)
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
        command, args = export_launcher()
        if download == "plugin":
            return send_file(codex_marketplace_archive(command, args), mimetype="application/zip",
                             as_attachment=True, download_name="dcc-web-codex.zip")
        config = export_client(client, command, args)
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
        return jsonify(**config, path=CONFIG_PATHS[client])

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
        config = export_client(metadata["client"], *export_launcher())
        suffix = "-chatgpt-web" if variant == "chatgpt-web" else ""
        return send_bundle(grant_id, metadata, variant, config, f"dcc-mcp-project{suffix}.zip")


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
