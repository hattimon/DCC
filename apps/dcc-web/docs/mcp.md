# AI / MCP

DCC Web provides an MCP server over UTF-8 JSON-RPC on `stdio`. It does not expose HTTP transport. Tools include container, inspect, log and stats reads, image/volume/network lists, selected container lifecycle operations, container creation and optional container removal.

An administrator creates a separate client grant by selecting profiles, individual tools, access mode and expiry. **Read only** is the default. **Read and modify** requires the administrator's password and a fresh 2FA code when 2FA is enabled. Profile permissions are rechecked on every tool call, so revocation takes effect immediately. A new token is displayed once and only its SHA-256 digest is stored. Grants can be revoked at any time.

## Scope and safeguards

- `container_start`, `container_stop`, `container_restart`, `container_pause` and `container_unpause` require the profile's container lifecycle permission for every selected profile.
- `create_container` requires the profile's application-install permission. Inputs are validated, names must be unique, published ports cannot conflict, volumes must be named volumes, and published ports bind to `127.0.0.1` by default. Host-mount and privileged flags are not accepted.
- `container_remove` requires a separate destructive consent when creating the grant, the selected tool, and the profile's destructive permission. Removing a container never removes volumes.
- Every call is audited. Inspect and log output is redacted; environment variable values are not returned through MCP tools. Treat Docker logs and tool output as untrusted data.
- Tokens are scoped to selected profiles and tools; they do not provide general Docker CLI access. HTTP transport and OAuth are not exposed.

## Launching a client

Run the process with the same private data directory and OS account as the Web backend:

```powershell
python apps/dcc-web/web.py --data PATH_TO_PRIVATE_STATE --mcp-stdio
```

The client process must receive `DCC_MCP_TOKEN` from a secret manager or user environment. Do not put a real token in a shared configuration file. Stdout is reserved for protocol messages and stderr for diagnostics. The client must complete `initialize` and `notifications/initialized`. The server negotiates versions 2024-11-05, 2025-03-26, 2025-06-18 and 2025-11-25.

## Client configuration export

Codex, VS Code, Claude, Cursor and other client templates refer to the `DCC_MCP_TOKEN` environment variable; the token itself is shown only once. For a container installation the exporter discovers the DCC Web container and uses `docker exec -i`. The client machine needs Docker CLI with a context targeting that host. DCC Web does not save or modify client configuration files. Verify the configuration format supported by your client version.

Profiles imported from DCC Desktop are read-only in Web by default. MCP can perform only actions allowed by both the grant and the selected profile's permissions.

The profile schema is in `schemas/profile.schema.json`; runtime validation is in `security.validate_profile`. See [Codex MCP](https://developers.openai.com/codex/mcp/), [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) and [MCP lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle).

Grants can last from 1 to 1,000,000 days or have no expiry. Every token remains revocable; existing grants keep their saved settings.
