"""MCP client configuration exporters; they never persist or embed access tokens."""
import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


class ClientAdapter:
    def export(self, command, args):
        raise NotImplementedError


class JsonAdapter(ClientAdapter):
    def export(self, command, args):
        return {"format":"json","configuration":{"mcpServers":{"dcc":{"command":command,"args":args}}}}


class CodexAdapter(ClientAdapter):
    def export(self, command, args):
        # JSON strings/arrays are also valid TOML basic strings/arrays.
        text = '[mcp_servers.dcc]\ncommand = '+json.dumps(command, ensure_ascii=False)+'\nargs = '+json.dumps(args, ensure_ascii=False)+'\nenv_vars = ["DCC_MCP_TOKEN"]\n'
        return {"format":"toml","configuration":text}


class VSCodeAdapter(ClientAdapter):
    def export(self, command, args):
        return {"format":"json","configuration":{"servers":{"dcc":{"type":"stdio","command":command,"args":args,"env":{"DCC_MCP_TOKEN":"${input:dcc-token}"}}},"inputs":[{"id":"dcc-token","type":"promptString","description":"DCC MCP access token","password":True}]}}


def export_client(client, command, args):
    adapter = CodexAdapter() if client=="OpenAI Codex" else VSCodeAdapter() if client=="VS Code / GitHub Copilot" else JsonAdapter()
    return dict(adapter.export(command,args),client=client,notice="Preview template. Set DCC_MCP_TOKEN in the client process environment or secret manager; never paste the token into a shared file. Desktop clients may require an OS launcher that inherits that environment. No external AI client has been exercised in this local test run.")


def _zip_files(files):
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    buffer.seek(0)
    return buffer


def codex_project_archive(configuration):
    return _zip_files({".codex/config.toml": configuration})


def codex_marketplace_archive(command, args):
    """Package a local marketplace using Codex's compatibility manifest for env_vars."""
    manifest = {
        "name": "dcc-web",
        "version": "0.1.0",
        "description": "Scoped Docker access through DCC Web MCP.",
        "mcpServers": "./.mcp.json",
        "interface": {"displayName": "DCC Web MCP"},
    }
    marketplace = {
        "name": "dcc-web-local",
        "interface": {"displayName": "DCC Web"},
        "plugins": [{
            "name": manifest["name"],
            "source": {"source": "local", "path": "./plugins/dcc-web"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        }],
    }
    mcp = {"mcpServers": {"dcc": {
        "command": command,
        "args": args,
        "env_vars": ["DCC_MCP_TOKEN"],
    }}}
    return _zip_files({
        ".agents/plugins/marketplace.json": json.dumps(marketplace, indent=2),
        "plugins/dcc-web/.codex-plugin/plugin.json": json.dumps(manifest, indent=2),
        "plugins/dcc-web/.mcp.json": json.dumps(mcp, indent=2),
    })
