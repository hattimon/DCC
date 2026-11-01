"""MCP client configuration exporters; they never persist or embed access tokens."""
import json


class ClientAdapter:
    def export(self, command, args):
        raise NotImplementedError


class JsonAdapter(ClientAdapter):
    def export(self, command, args):
        return {"format":"json","configuration":{"mcpServers":{"dcc":{"command":command,"args":args}}}}


class CodexAdapter(ClientAdapter):
    def export(self, command, args):
        # JSON strings/arrays are also valid TOML basic strings/arrays.
        text = '[mcp_servers.dcc]\ncommand = '+json.dumps(command)+'\nargs = '+json.dumps(args)+'\nenv_vars = ["DCC_MCP_TOKEN"]\n'
        return {"format":"toml","configuration":text}


class VSCodeAdapter(ClientAdapter):
    def export(self, command, args):
        return {"format":"json","configuration":{"servers":{"dcc":{"type":"stdio","command":command,"args":args,"env":{"DCC_MCP_TOKEN":"${input:dcc-token}"}}},"inputs":[{"id":"dcc-token","type":"promptString","description":"DCC MCP access token","password":True}]}}


def export_client(client, command, args):
    adapter = CodexAdapter() if client=="OpenAI Codex" else VSCodeAdapter() if client=="VS Code / GitHub Copilot" else JsonAdapter()
    return dict(adapter.export(command,args),client=client,notice="Preview template. Set DCC_MCP_TOKEN in the client process environment or secret manager; never paste the token into a shared file. Desktop clients may require an OS launcher that inherits that environment. No external AI client has been exercised in this local test run.")
