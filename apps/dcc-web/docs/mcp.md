# AI / MCP Preview

The server is provider-neutral. Implemented transport: UTF-8, newline-delimited JSON-RPC over stdio. Implemented tools: `list_containers`, `inspect_container`, `container_logs`, `container_stats`, `list_images`, `list_volumes`, `list_networks`. All are read-only. Streamable HTTP, OAuth, write tools and destructive MCP operations are planned and disabled. There is no hidden HTTP MCP endpoint.

Administrators create a named grant in AI / MCP, choose existing profile IDs and tools, choose a client and expiry (including 2000 days) or No expiry, then copy the token shown once. Only its SHA-256 digest is stored. Revocation applies to the next request. The grant still requires profile read permission and cannot cross its profile/tool scope. Calls are audited and output is redacted. Treat Docker log contents as untrusted data.

Start with the same private data directory and OS account as the Web backend:

```powershell
# Obtain the value from your secret manager; do not commit it.
python apps/dcc-web/web.py --data PATH_TO_PRIVATE_STATE --mcp-stdio
```

The launching process must supply `DCC_MCP_TOKEN`. Stdout contains protocol responses only. Stderr is available for diagnostics. The client must complete `initialize` and `notifications/initialized` before calling tools. The server negotiates the supported 2024-11-05/2025-03-26/2025-06-18/2025-11-25 versions and declares only tools capability.

## Client adapters

`ClientAdapter.export(command,args)` is the provider-independent interface. Native installations export the real Python executable, server path and private state path. Container installations identify the running DCC Web container through Docker and export `docker exec -i --env DCC_MCP_TOKEN ...`. The container entrypoint runs the MCP process as UID 10001 with the Docker socket group. The configuration contains the token variable name only; supply its value through the client process environment or a supported secret input. Docker CLI must be installed on the client's computer and use the Docker context hosting this container. No client files are modified automatically.

Codex example (replace paths; the token is inherited from the process environment):

```toml
[mcp_servers.dcc]
command = "python"
args = ["/path/to/DCC/apps/dcc-web/web.py", "--data", "/private/dcc-state", "--mcp-stdio"]
env_vars = ["DCC_MCP_TOKEN"]
```

Claude Desktop / Claude Code / Cursor / Windsurf / generic JSON template:

```json
{"mcpServers":{"dcc":{"command":"python","args":["/path/to/DCC/apps/dcc-web/web.py","--data","/private/dcc-state","--mcp-stdio"]}}}
```

These clients must inherit `DCC_MCP_TOKEN` from a dedicated OS launcher/environment or use their supported secret injection mechanism. Do not put a real token into shared JSON. The exporter provides a template rather than silently editing existing client files. Verify the configuration location and environment behavior for the installed client version.

VS Code export uses `servers.dcc` with `type: stdio` and a password `promptString` input referenced as `${input:dcc-token}`. No token value is exported. External Codex/Claude/Cursor/Windsurf/Copilot sessions have not been run in this acceptance test. Export serialization, lifecycle, grants and tool dispatch are covered by isolated tests; external client certification remains future work.

## Profile schema and permissions

Connection schema: `schema_version:1`, a `profiles` array, each with `name`, `kind`, transport-specific fields, optional `users` and `permissions`. See [configuration](configuration.md). Secrets are encrypted independently, excluded from that schema/export. The Web capability vocabulary already separates read/lifecycle/install/update/destructive operations. This MCP version deliberately offers only the read subset. Future write adapters must enforce the same scope and an interactive confirmation mechanism, rather than granting unrestricted Docker access.

The public export schema is provided in `schemas/profile.schema.json`. Runtime validation remains in `security.validate_profile`; no JSON Schema runtime dependency is required.

Primary references for the implemented protocol/configuration formats: [MCP lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle), [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), [official Codex MCP configuration](https://developers.openai.com/codex/mcp/), [VS Code MCP configuration](https://code.visualstudio.com/docs/agents/reference/mcp-configuration), [Claude Code MCP](https://code.claude.com/docs/en/mcp). Client configuration formats can evolve independently of this Preview.

Grants support 2000 days and other positive day counts (up to 1000000), or an explicit No expiry checkbox. No-expiry grants store `expires:null`; they remain immediately revocable and subject to profile/tool restrictions. Existing finite grants are unchanged.
