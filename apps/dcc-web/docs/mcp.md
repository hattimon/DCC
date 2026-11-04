# AI / MCP

DCC Web provides an MCP server over UTF-8 JSON-RPC on `stdio`. It does not expose HTTP transport. Tools include container, inspect, log and stats reads, image/volume/network lists, selected container lifecycle operations, container creation and optional container removal.

An administrator creates a separate client grant by selecting profiles, individual tools, access mode and expiry. **Read only** is the default. **Read and modify** requires the administrator's password and a fresh 2FA code when 2FA is enabled. Profile permissions are rechecked on every tool call, so revocation takes effect immediately. A new token is displayed once and only its SHA-256 digest is stored. Grants can be paused and resumed. Revoking a grant, pausing/resuming it, or removing a revoked grant from the list requires an explicit checkbox confirmation. Removing it from the list preserves the audit record.

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

In **AI / MCP → Export**, choose a Codex download.

- **Project package (ZIP).** Extract it at the root of the trusted project to add `.codex/config.toml`. If the file already exists, merge the `dcc` section from the TOML download into it. For project-only access, remove any existing global `dcc` entry from `~/.codex/config.toml`. Start a new chat in the project.
- **TOML.** Merge the `dcc` section into `~/.codex/config.toml` or the trusted project's `.codex/config.toml`.
- **Codex plugin (ZIP).** Extract it into a separate directory, run `codex plugin marketplace add .` there, and install **DCC Web MCP** from the **DCC Web** source in the plugin directory.

If the export uses `docker exec`, select the context that runs the DCC Web container. MCP tools accept a profile ID, exact profile name, or host/IP address in the `profile` argument. The server lists the profiles included in the grant and resolves selectors only within that allowlist. If a name or address is ambiguous, use a unique name or ID. DCC Web connects using the address stored in the profile.

### Set the Codex token

Codex CLI and Desktop use the same MCP configuration. Open a terminal at the root of the project containing the extracted configuration and follow the steps for your system.

#### Windows

**One CLI session in PowerShell**

1. Open a new PowerShell window at the project root and paste the block below.
2. Paste the token when prompted and press Enter. Codex CLI starts with the variable.
3. Close the PowerShell window when you finish.

```powershell
$dccToken = Read-Host 'Paste the DCC token' -AsSecureString
$env:DCC_MCP_TOKEN = [System.Net.NetworkCredential]::new('', $dccToken).Password
$dccToken.Dispose()
codex
```

**Keep the token across restarts for CLI and Desktop**

1. Open **Edit environment variables for your account** from the Start menu.
2. Under **User variables**, select **New**. Enter `DCC_MCP_TOKEN` as the name and paste the token as the value.
3. Save the changes. Open a new PowerShell window or fully quit and reopen Codex Desktop.

**Encrypted storage for CLI**

Set up the local `SecretStore` vault using [Microsoft's instructions](https://learn.microsoft.com/en-us/powershell/utility-modules/secretmanagement/get-started/using-secretstore). Store the token once. Then load it into the environment when starting Codex from the project directory in a new PowerShell window.

```powershell
# Store once
Set-Secret -Vault SecretStore -Name dcc-mcp -Secret (Read-Host 'Paste the DCC token' -AsSecureString)

# Run from the project when starting Codex
& {
    $env:DCC_MCP_TOKEN = Get-Secret -Vault SecretStore -Name dcc-mcp -AsPlainText -ErrorAction Stop
    codex
}
```

#### macOS

1. Open **Terminal** and go to the project root.
2. Run the command below, then paste the token when prompted and press Enter.
3. Codex CLI starts in that project. The value leaves the session environment when you exit the CLI.

```sh
zsh -c 'printf "%s" "Paste the DCC token: " >&2; IFS= read -rs DCC_MCP_TOKEN && printf "\n" && export DCC_MCP_TOKEN && exec codex'
```

**Store the token in Keychain**

Run the first command once and paste the token when prompted. Run the second command from the project directory to start Codex on later visits. macOS may ask for permission to read the item from Keychain.

```sh
security add-generic-password -a "$USER" -s dcc-mcp -T "" -w
(dcc_token=$(security find-generic-password -a "$USER" -s dcc-mcp -w) && [ -n "$dcc_token" ] && DCC_MCP_TOKEN="$dcc_token" codex)
```

#### Linux

1. Open a terminal and go to the project root.
2. Run the command below, then paste the token when prompted and press Enter.
3. Codex CLI starts in that project. The value leaves the session environment when you exit the CLI.

```sh
bash -c 'IFS= read -rsp "Paste the DCC token: " DCC_MCP_TOKEN && printf "\n" && export DCC_MCP_TOKEN && exec codex'
```

**Store the token in Secret Service**

In a session with a running Secret Service provider such as GNOME Keyring, use `secret-tool` from libsecret. The first command prompts for the token and stores it. Run the second command from the project directory to start Codex with the token. On a host without Secret Service, use the Bash prompt above.

```sh
secret-tool store --label='DCC MCP' service dcc-mcp account "$USER"
(dcc_token=$(secret-tool lookup service dcc-mcp account "$USER") && [ -n "$dcc_token" ] && DCC_MCP_TOKEN="$dcc_token" codex)
```

#### Keep the token between launches

The project MCP configuration stays on disk. The token remains valid until it expires or you revoke it in DCC Web. The one-session examples prompt for the value on each launch. If your projects use separate tokens, replace `dcc-mcp` with a distinct name in the store and lookup commands for each project. The program launching Codex CLI or Desktop must supply the value as `DCC_MCP_TOKEN`. A variable set in a terminal is inherited by processes launched from that terminal.

When adding a custom STDIO server in Codex, you can set `DCC_MCP_TOKEN` as the environment variable key and paste the token as the value. Codex stores the value in plain text in its configuration. If the launch environment already provides the value, enter only `DCC_MCP_TOKEN` in the environment variable allowlist. The Codex downloads use the allowlist.

Keep the token outside the project directory. A `.env` file stores plain text and requires a launcher that loads the value into the environment before starting Codex. An agent with project file access can read an ignored `.env` file. An `AGENTS.md` note can name the `dcc` MCP server and the profile ID. After starting Codex, use `/mcp` to check the connection.

Any chat with access to the MCP server can use the grant's selected profiles and tools. A trusted project's configuration can scope the server to that project. Use **Revoke access** in DCC Web to block subsequent calls with the token.

Profiles imported from DCC Desktop are read-only in Web by default. MCP can perform only actions allowed by both the grant and the selected profile's permissions.

The profile schema is in `schemas/profile.schema.json`; runtime validation is in `security.validate_profile`. See [Codex MCP](https://developers.openai.com/codex/mcp/), [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) and [MCP lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle).

Grants can last from 1 to 1,000,000 days or have no expiry. Every token remains revocable; existing grants keep their saved settings.
