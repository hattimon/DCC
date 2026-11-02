# Configuration and profiles

State is kept in the directory selected by `--data` / `DCC_WEB_DATA`. SQLite stores users, hashed sessions, encrypted profiles and credentials, catalogs, per-user preferences, audit, short-lived confirmations and monitoring samples. It never edits Desktop's profile store or keyring.

| Profile kind | Backend |
|---|---|
| local | Docker CLI and optional named CLI context |
| tcp | Docker API endpoint with verified TLS and CA/client certificate paths |
| ssh | Docker CLI through SSH with `RejectPolicy` for unknown host keys |
| balena | Balena CLI through verified SSH |
| wsl | `wsl.exe --distribution NAME --exec docker` on Windows |
| tunnel | Existing explicit tunnel terminating on localhost; no arbitrary tunnel command execution |

SSH/WSL operations run in their target environment. Compose files and bind mount paths must exist there. Compose YAML import currently writes to the backend and requires a local/TLS profile; discovered remote projects remain manageable when their Compose CLI is available. Source builds require a separately reviewed GitHub repository and explicit confirmation. GitHub/source builds are not automatic catalog side effects.

Profile permissions start with `read`. Separate capabilities are `containers.write`, `exec`, `images.write`, `volumes.write`, `networks.write`, `compose.write`, `install`, `update`, `destructive`. User roles impose a second limit: viewer reads, operator reads/lifecycle/exec, admin may use enabled profile capabilities. Administrators can restrict profiles to comma-separated user IDs from Settings → users. An empty restriction permits all authenticated users, subject to role/capability checks. A partial API profile edit preserves existing restrictions and credentials.

Import accepts encrypted Web backups and legacy Desktop profile lists. A plaintext Desktop export imports connection metadata without passwords and can match keys already uploaded to the vault by filename. Every Web export is encrypted with a separate password and can optionally include saved credentials and managed keys. Browser forms never repopulate stored secrets. Leaving a credential field empty keeps the encrypted previous value. See the [import and export guide](profiles-security.md).

| Environment | Meaning |
|---|---|
| `DCC_WEB_DATA` | Private persistent state directory |
| `DCC_WEB_MASTER_KEY` | Optional Fernet key supplied securely instead of generated key storage |
| `DCC_WEB_HTTPS=1` | Secure cookie and HSTS for explicit HTTPS proxy deployment |
| `DCC_WEB_PUBLIC_ORIGIN` | Exact browser origin, e.g. `https://dcc.example.net` |
| `DCC_WEB_HOSTS` | Comma-separated permitted HTTP hostnames |
| `DCC_WEB_PYTHON` | Windows launcher interpreter |
| `DCC_MCP_TOKEN` | One-time issued MCP grant token, supplied through the client environment |

Restart the service after environment changes. `--host` defaults to localhost. Non-loopback binding requires `--allow-lan` and a previously created administrator. No proxy header is trusted automatically.

The interface defaults to English. The header and Settings language selectors save EN/PL per user; login remembers the last browser choice. Existing saved Polish preferences are retained. Optional `panel_host` overrides the host used in published-panel links. `cli` may explicitly select docker, balena or balena-engine for SSH/Balena hosts.

Verified SSH profiles can use the reused safe UpdateService through Docker SDK HTTP over SSH dial-stdio. It uses the same encrypted password/key and RejectPolicy, without embedding secrets in URLs. Localhost tunnels are also supported. WSL direct recreation requires a reachable TLS profile or host Compose/Updater; no untested WSL HTTP bridge is simulated.


## Shared SSH files and Desktop profile imports

A Desktop path such as `C:/Users/name/.ssh/id_ed25519` describes the Desktop computer. It does not copy the key into a Linux container. Plaintext Desktop imports cannot transfer secrets; the optional filename match selects a managed key already uploaded to Web. Unmatched paths remain available for deliberate configuration.

In **Profiles → Shared SSH files**, the default managed directory is `<DCC_WEB_DATA>/ssh` (`/data/ssh` in the published container, persisted in `dcc_web_data`). Administrators can upload selected private/public SSH keys and a trusted `known_hosts` from the browser. The first dialog validates files and previews names, sizes and host key fingerprints; a separate explicit confirmation permits storage. Replacing existing files requires a separate opt-in. Upload only over HTTPS or a trusted loopback connection. Prefer a dedicated, passphrase-protected key; enter its passphrase individually in the profile.

Select profiles using the row checkboxes or **Select all**, then choose **Use shared directory**. The preview lists changed SSH/Balena profiles and skipped connection types. An imported Windows path becomes its basename, e.g. `/data/ssh/id_ed25519`; unselected profiles, permissions, user restrictions and encrypted credentials stay unchanged. A profile may select **Individual path** to override the shared directory. Empty key paths retain password/agent authentication while using shared host verification.

A different shared directory must already exist and be accessible on the DCC Web server. For containers, mount a narrow folder read-only, e.g. `--mount type=bind,source=/host/dcc-ssh,target=/run/dcc-ssh,readonly`, then set `/run/dcc-ssh`. The panel never uploads into external directories or makes arbitrary server-side copies. Directory changes affect only opted-in profiles and do not move/delete files. A browser cannot open a server directory in your local Explorer; the upload dialog opens the local file picker, and **How to copy files** provides explicit Docker/PowerShell commands for the default container directory.

**Delete selected profiles** can remove all selected connection profiles after a preview and confirmation. It removes their encrypted connection credentials and closes their active host terminals. It retains Docker containers, volumes, and shared SSH files; use Delete selected files in the panel to remove stored keys. Removing a profile is not revocation of the key on the remote host.


## SSH agent

Web 0.1.4 recognizes private/public keys by content, independent of extension (including no extension, `.pem` and `.key`). Profiles lists their type and whether a passphrase is required. Upload accepts selected files or proposes recognized files from a folder selected in the browser. SSH config and unrelated files are excluded; only checked files are uploaded after confirmation. Trusted `known_hosts` is still required. Encrypted PKCS8 keys are decrypted in memory when their separately stored passphrase is supplied.

When importing Windows Desktop profiles, check **Match keys already uploaded to the shared directory** to map an existing private key with exactly the same basename to `/data/ssh`. Unmatched paths stay visible for manual selection; they do not magically become container paths. Passwords/passphrases are not taken from the exported JSON. Default permissions remain read-only. In each SSH/Balena profile, select Automatic, Profile key/password, or SSH agent when the Web process can access an agent with loaded identities. The agent choice is hidden otherwise.

**SSH agent** uses identities already unlocked on the Web server. It ignores the imported local key path and does not store the agent passphrase in the profile. The Profiles page reports whether the server can access loaded identities. The socket must be explicitly made accessible to the non-root Web UID 10001; mounting it does not grant missing Unix filesystem permissions. Agent access permits authentication with identities loaded in that agent, so use a dedicated agent with only the intended keys. No agent is forwarded to remote hosts.

For native Linux Docker Engine, load the key with `ssh-add` on the host, then extend the existing Web service with a reviewed Compose override:

```yaml
services:
  dcc-web:
    environment:
      SSH_AUTH_SOCK: /run/dcc-agent.sock
    volumes:
      - type: bind
        source: ${SSH_AUTH_SOCK:?Set the host SSH_AUTH_SOCK}
        target: /run/dcc-agent.sock
        read_only: true
```

The entrypoint retains non-root UID 10001 and adds the mounted socket group when Docker socket access is enabled. A socket limited to mode 0600 and owned by a different UID still needs a dedicated agent/socket with access granted to UID 10001 or its group; do not make the socket world-writable. Existing ports, data volume and other service options must be retained when recreating the container.

Docker Desktop documents `/run/host-services/ssh-auth.sock` forwarding for **Mac and Linux**: [Docker SSH agent forwarding](https://docs.docker.com/desktop/features/networking/networking-how-tos/#ssh-agent-forwarding). Windows OpenSSH's named pipe is not directly mountable as a Unix socket in a Linux container. On Windows, use an explicitly configured trusted bridge to a Unix agent socket in WSL/Linux (verify socket access from the container), or upload the encrypted key and enter its passphrase in the profile. The native Python Web server on Windows can use the local OpenSSH/Pageant agent supported by [Paramiko](https://docs.paramiko.org/en/stable/api/client.html). No bridge or host service is installed automatically.

## Connection wizard and account security

Web 0.1.4 adds a three-step connection wizard, encrypted configuration/key storage, selected key deletion, encrypted backups, optional TOTP 2FA and verified email recovery. See the [complete profile and security guide](profiles-security.md), including read-only host folder mounting and separate local/public domain settings.
