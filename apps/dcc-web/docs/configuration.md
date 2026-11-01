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
