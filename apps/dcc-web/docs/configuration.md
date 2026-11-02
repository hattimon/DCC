# Configuration and profiles

State is kept in the directory selected by `--data` / `DCC_WEB_DATA`. SQLite stores users, hashed sessions, encrypted credential blobs, public profile metadata, catalogs, per-user preferences, audit, short-lived confirmations and monitoring samples. It never edits Desktop's profile store or keyring.

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

Import accepts exported Web profiles and legacy Desktop profile lists. It imports connection metadata only; enter credentials separately. Export excludes passwords, passphrases and TLS secrets. Browser forms never repopulate stored secrets. Leaving a credential field empty keeps the encrypted previous value.

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

A Desktop path such as `C:/Users/name/.ssh/id_ed25519` describes the Desktop computer. It does not copy the key into a Linux container. Import keeps legacy paths unchanged and never transfers private key material or plaintext credentials.

In **Profiles → Shared SSH files**, the default managed directory is `<DCC_WEB_DATA>/ssh` (`/data/ssh` in the published container, persisted in `dcc_web_data`). Administrators can upload selected private/public SSH keys and a trusted `known_hosts` from the browser. The first dialog validates files and previews names, sizes and host key fingerprints; a separate explicit confirmation permits storage. Replacing existing files requires a separate opt-in. Upload only over HTTPS or a trusted loopback connection. Prefer a dedicated, passphrase-protected key; enter its passphrase individually in the profile.

Select profiles using the row checkboxes or **Select all**, then choose **Use shared directory**. The preview lists changed SSH/Balena profiles and skipped connection types. An imported Windows path becomes its basename, e.g. `/data/ssh/id_ed25519`; unselected profiles, permissions, user restrictions and encrypted credentials stay unchanged. A profile may select **Individual path** to override the shared directory. Empty key paths retain password/agent authentication while using shared host verification.

A different shared directory must already exist and be accessible on the DCC Web server. For containers, mount a narrow folder read-only, e.g. `--mount type=bind,source=/host/dcc-ssh,target=/run/dcc-ssh,readonly`, then set `/run/dcc-ssh`. The panel never uploads into external directories or makes arbitrary server-side copies. Directory changes affect only opted-in profiles and do not move/delete files. A browser cannot open a server directory in your local Explorer; the upload dialog opens the local file picker, and **How to copy files** provides explicit Docker/PowerShell commands for the default container directory.

**Delete selected profiles** can remove all selected connection profiles after a preview and confirmation. It removes their encrypted connection credentials and closes their active host terminals. It retains Docker containers, volumes, and shared SSH files; remove files deliberately on the server if you wish to revoke that stored identity. Removing a profile is not revocation of the key on the remote host.
