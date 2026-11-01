# DCC Web 0.1.0 — local acceptance candidate

DCC Web is an independently versioned browser interface for Docker Control Center. This candidate is local only: no image, release or deployment has been published. Desktop remains version 1.3.11 and retains its Qt interface and updater.

The implementation uses Flask, Waitress, SQLite, native ES modules and CSS. This follows the existing Container Updater stack and avoids adding a frontend framework or a JavaScript build pipeline. It shares `dcc_catalog.py` and the canonical `dcc-catalog.json` with Desktop, and delegates safe container recreation to the existing Container Updater service without modifying that module.

## Start on Windows

From the repository root, using the prepared acceptance environment:

```powershell
.\apps\dcc-web\start.ps1
```

Open [DCC Web](http://127.0.0.1:8789). Create the initial administrator locally with a password of at least 12 characters. There is no production default password. The initial Docker profile allows reading only. Enable individual write capabilities in Profiles when needed.

For a fresh checkout, create a Python 3.12 environment and install `apps/dcc-web/requirements.txt`. Set `DCC_WEB_PYTHON` to its Python executable, or run `python apps/dcc-web/web.py` directly. Docker CLI must be available to the backend; Compose operations additionally require Docker Compose v2.

## What works

- Local, Docker context, verified TLS, SSH, Balena and Windows WSL profiles; encrypted credentials and profile/user permissions.
- Container lifecycle, bulk operations, inspect, bounded exec, configuration recreation, live polling logs/download and resource history.
- Images, volumes, networks, Compose projects and explicit import/validation of Compose YAML.
- Shared App Store: additional GitHub/HTTPS/file catalogs, validation, refresh, cache, fallback, installation previews and volume-preserving uninstall.
- Five themes, live appearance preview, per-user settings and three local audio packs, disabled initially.
- Clickable panel endpoints, visible ports, direct bulk controls and grouped container actions.
- OpenAI, compatible endpoints and Ollama assistants for configuration proposals, previews and port conflict resolution.
- Authentication, CSRF, strict cookies, RBAC, confirmations, bounded jobs, audit and a read-only MCP stdio Preview.

See the [feature matrix](docs/feature-matrix.md) for adapter restrictions and desktop-specific functions. In particular, direct update/recreation uses local, TLS, verified SSH or explicit localhost-tunnel API profiles; WSL can use TLS or host Compose/Updater. The complete interface supports English (default) and Polish, with saved per-user selection. No external AI client has been certified. Streamable HTTP and MCP writes are planned and disabled.

## Structure

```text
web.py                 application factory, API and CLI
engine.py              Docker CLI/SSH/WSL transports and jobs
state.py               SQLite state and encrypted credentials
security.py            authentication, authorization, validation, redaction
catalogs.py             compatible catalogs and deployment preview
mcp_preview.py         scoped, revocable read-only stdio server
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

The running application serves an information page at `/about` and these documents at `/docs/<name>`. Catalog/media references are resolved inside this repository. DCC Web is intentionally not inserted into the 67-entry official catalog while its image is unpublished.
