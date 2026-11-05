# DCC Web 0.2.8

When enabling zrok from the local panel, administrators can allow DCC Container Updater 1.1.4 or newer to pause and resume the tunnel during compatible Web updates. Both Web images must support the handoff. The first upgrade from an older Web version uses the manual steps shown next to the blocker. [Release notes](https://github.com/hattimon/DCC/releases/tag/dcc-web-v0.2.8)

[English](README.md) · [Polski](README.pl.md) · [GitHub repository](https://github.com/hattimon/DCC)

DCC Web is the browser workspace in Docker Control Center. It is independently versioned and complements the Windows and Linux desktop application. The DCC App Store entry opens this page from its **Website** button. Install DCC Web from the **DCC** category in Desktop 1.3.11 or newer.

Web 0.2.4 fixes DCC Remote Access installation with custom local Docker profile IDs and restores its visibility in the **DCC** App Store category. Web 0.2.3 introduced optional DCC Remote Access for Docker installations. After updating the existing container through DCC Container Updater, open **Settings → Administration and security → Panel access and HTTPS (TLS) → Remote Internet Access**. [Remote Access setup](../dcc-remote-access/README.md)

Web 0.2.4 also exports agent instructions and project ZIPs for all seven MCP clients. [MCP setup and export](docs/mcp.md#export-configuration-and-agent-instructions)

Web 0.2.5 fixes a **Profile not found** error when checking the result of Remote Access configuration, activation or restart.

Web 0.2.6 accepts hosted zrok reservations on `shares.zrok.io` and lets you resume a pending reservation with the saved environment.

Web 0.2.7 uses BalenaOS's SSH port 22222 by default and migrates existing Balena profiles that still use the old default port 22. SSH errors now identify common causes such as host reachability, authentication and trusted host keys. It also moves legacy DCC Remote Access panel networks into a collision-checked subnet pool so the isolated network cannot capture routes to remote profiles. The tunnel sidecar stops during migration and must be enabled again after the update. [Profile setup](docs/configuration.md)

Web 0.2.2 adds pausable MCP grants, profile selection by name or host address, manual container refresh, and configurable change-aware polling. Web 0.2.1 displays profile IDs below profile names, in Overview → Host details, and beside the selected host address on the Containers page. Older Desktop clients can use **Administration** after refreshing the official catalog; Container Updater remains under **Updates**. Web 0.1.8 adds optional, managed local HTTPS while retaining the current HTTP endpoint and persistent data. Web 0.2.0 fixes the recovery SMTP settings dialog so administrators can configure mail. The 0.1.4 release fixed duplicate versions in the Web store, including stale caches retained from earlier images. See [catalog compatibility](docs/catalogs.md#older-desktop-clients) for the limitation of already published Desktop binaries with a bundled older Web entry.

The implementation uses Flask, Waitress, SQLite, native ES modules and CSS. It shares `dcc_catalog.py` and the canonical `dcc-catalog.json` with Desktop and delegates safe container recreation to DCC Container Updater.

When installed from the DCC App Store, a fresh container creates the `admin` account with a strong random password. The installation result shows the credentials; the password is also written once to the container logs. Change it after signing in. The standalone local installer still lets you create the administrator interactively.

## Start on Windows

From the repository root, using the prepared acceptance environment:

```powershell
.\apps\dcc-web\start.ps1
```

Open [DCC Web](http://127.0.0.1:8789). Create the initial administrator locally with a password of at least 12 characters. There is no production default password. The initial Docker profile allows reading only. Enable individual write capabilities in Profiles when needed.

For a fresh checkout, create a Python 3.12 environment and install `apps/dcc-web/requirements.txt`. Set `DCC_WEB_PYTHON` to its Python executable, or run `python apps/dcc-web/web.py` directly. Docker CLI must be available to the backend; Compose operations additionally require Docker Compose v2.

## Install on Windows, macOS or Linux

Download the [DCC Web source package](https://github.com/hattimon/DCC/releases/download/dcc-web-v0.2.8/DCC-Web-0.2.8-source.zip), extract it, and run the bundled installer from the extracted `DCC-Web-0.2.8` directory:

```powershell
py -3.12 apps/dcc-web/install.py
```

On macOS or Linux, use `python3 apps/dcc-web/install.py`. The installer requires Docker Engine/Desktop and Docker Compose v2, and a local Docker context. It checks published TCP ports from running Docker containers and attempts a local bind before selecting a port. It prefers 8789, then scans 8790–8888; the chosen port is saved in the per-user configuration directory. If another process claims the port during startup, it retries on the next free port. The installer creates the initial administrator interactively, starts DCC Web on loopback only, and prints the final URL. It does not overwrite or remove an existing `dcc-web-standalone` container.

For a native Python installation without a container, use Python 3.12, create a virtual environment, install `apps/dcc-web/requirements.txt`, and run `apps/dcc-web/web.py`. This mode uses the Docker CLI and context configured for the current OS user.

## What works

- Local, Docker context, verified TLS, SSH, Balena and Windows WSL profiles; encrypted credentials and profile/user permissions.
- Container lifecycle, project/network/flat grouping and group selection, a sticky bulk toolbar, inspect, exec, configuration recreation, polling logs/download and resource history.
- Separate host-terminal windows and tabs using verified SSH, Windows ConPTY, Linux PTY and WSL; per-profile host.exec permission, 16 sessions by default with a configurable limit.
- Images, volumes, networks, Compose projects and explicit import/validation of Compose YAML.
- Shared App Store: additional GitHub/HTTPS/file catalogs, validation, refresh, cache, fallback, installation previews and volume-preserving uninstall.
- Five themes, live appearance preview, per-user settings and three local audio packs, enabled by default.
- Unique panel endpoints with copy buttons, full image-reference copying, visible ports, direct bulk controls and grouped container actions.
- Installation phases, bounded redacted logs, copy/download and explicitly revealed encrypted startup access details.
- OpenAI, compatible endpoints and Ollama assistants for configuration proposals, previews and port conflict resolution.
- Authentication, CSRF, strict cookies, RBAC, confirmations, bounded jobs, audit and scoped read/write MCP stdio tools.

See the [feature matrix](docs/feature-matrix.md) for adapter restrictions and desktop-specific functions. In particular, direct update/recreation uses local, TLS, verified SSH or explicit localhost-tunnel API profiles; WSL can use TLS or host Compose/Updater. The complete interface supports English (default) and Polish, with saved per-user selection. No external AI client has been certified. Streamable HTTP and MCP write tools are explicitly granted and scoped to profile permissions.

## Structure

```text
web.py                 application factory, API and CLI
engine.py              Docker CLI/SSH/WSL transports and jobs
state.py               SQLite state and encrypted credentials
security.py            authentication, authorization, validation, redaction
catalogs.py             compatible catalogs and deployment preview
mcp_preview.py         scoped, revocable stdio server with read and write grants
client_adapters.py     Codex TOML, VS Code JSON and mcpServers JSON exports
templates/             login, workspace, information page
static/                native JS views, five CSS themes, local audio
docs/                  installation, security, matrix and acceptance instructions
tests/                 isolated API tests and real browser QA fixture
Dockerfile             independent non-root Web image
compose.yaml           explicit localhost deployment example
start.ps1, start.sh     local launchers
```

## Documentation

[Installation](docs/installation.md) · [Configuration](docs/configuration.md) · [Security](docs/security.md) · [Catalogs](docs/catalogs.md) · [AI assistant](docs/ai.md) · [MCP](docs/mcp.md) · [Themes/audio](docs/themes-audio.md) · [Tests](docs/testing.md)

The running application serves an information page at `/about` and formatted documents at `/docs/<name>`. Catalog/media references are resolved inside this repository. The published image supports Linux amd64 and arm64.

## Preview status

See [CURRENT_STATUS.md](CURRENT_STATUS.md) for verified features and remaining work. Do not treat planned features as shipped functionality.

Project repository: [hattimon/DCC](https://github.com/hattimon/DCC).


## Shared SSH keys for imported profiles

In **Profiles**, upload selected SSH files to the managed private directory, then use checkboxes to apply it only to chosen SSH/Balena profiles. Individual paths remain available. Trusted `known_hosts`, host verification and profile permissions remain required. See [configuration](docs/configuration.md#shared-ssh-files-and-desktop-profile-imports) and [security](docs/security.md#ssh-file-storage) for storage, external read-only mounts, confirmations and bulk removal behavior.

## 0.1.7 — optional local HTTPS

- Configure an optional private IP or local DNS name from **Settings → Administration and security → Local and public domains**.
- Install the managed Caddy extension to get a local HTTPS URL. It binds to the selected private/loopback host IP and automatically scans Docker-published ports from 9443 to 9499.
- The existing HTTP port and the DCC Web data volume remain unchanged. If a host port is taken after the scan, setup retries another candidate and restores the previous proxy on failure.
- Open the HTTPS URL once so Caddy issues its local certificate, then download `DCC-Web-local-root-CA.crt` from **Settings → HTTPS access** and trust it on the client device. The CA private key remains in the extension's persistent volume.
- Public HTTPS remains optional and separate; it needs a public domain and reachable ports 80/443.

## 0.1.6 — host terminal and localized documentation

- Host terminal access works from a loopback HTTP panel. Remote SSH remains encrypted and host-key verified; other devices still require HTTPS.
- Documentation follows the selected Polish or English language, and SSH agent setup guidance is linked from profile settings.
- The SSH key and trusted-host section is collapsed by default.

## 0.1.4 — profiles and security / profile i bezpieczeństwo

[Wizard, encrypted keys/backups, 2FA, verified email recovery, read-only mounts and domains / instrukcja](docs/profiles-security.md).
