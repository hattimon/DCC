# Testing and acceptance

## Container panel gateway (0.3.2)

`python -m unittest discover -s apps/dcc-web/tests -p test_panel_proxy.py -v` exercises HTTP, SSE and WebSocket with temporary DCC state. It first tries real loopback fixtures; if the Windows execution environment blocks loopback connections, it uses an in-memory socket fixture. Passing the in-memory suite proves gateway behavior but does not prove a real Docker or zrok connection. These tests never connect to user Docker profiles.

`python -m unittest discover -s apps/dcc-web/tests -p test_panel_transport.py -v` checks the isolated helper command, its resource limits and byte relay with a simulated child process. To validate the real helper image and its container network namespace, a separately authorized Docker engine with working socket permissions is required.

For repeatable browser verification, run `panel_browser_fixture.py --updater` and `panel_browser_fixture.py` from `apps/dcc-web/tests` in separate processes with the Web dependencies installed. The fixtures use ports 18878/18879 and temporary data under `output/playwright`. Run `playwright-cli -s=dcc-panel open about:blank` then `playwright-cli -s=dcc-panel run-code --filename apps/dcc-web/tests/panel_browser_smoke.js` from the repository root. This checks service assets, API, forms, multipart upload, service/DCC cookie separation, live text messages, ES-module cycles/dynamic imports, Updater login/report navigation and clearing an open panel after logout. Stop only those test processes afterward.

The separate backend tests cover binary WebSocket messages, idle revocation, expiry, new MFA requirements, permission changes, redirect/path manipulation, scoped cookies and bounded resources. The browser Updater uses its real UI with a synthetic Docker service; it does not update containers. Live SSH forwarding, public TLS/domain/IP, zrok and installed-image upgrades require separate infrastructure validation. [Panel trust model and limits](panels.md).


Backend, repository root:

```powershell
python -m unittest discover -s apps/dcc-web/tests -p test_web.py -v
python apps/dcc-web/web.py --self-check
git diff --check
```

Tests use temporary state and an explicit FakeBackend factory. The production application never selects it. `tests/review_server.py` adds a localhost-only QA scaling route and a clearly labelled fixture profile; this is a separate test entry point excluded from the production image.

Browser QA (Python Playwright and an installed Chromium required):

```powershell
python apps/dcc-web/tests/review_server.py --port 8790 --data PATH_TO_QA_ONLY_DATA
python apps/dcc-web/tests/browser_smoke.py --url http://127.0.0.1:8790 --out PATH_TO_SCREENSHOTS
```

The fixture contains synthetic credentials documented in its source; they do not exist in the production setup. Tests exercise login, search, confirmations, mock stop/install, both Updater category filters, logs, monitoring, resource/Compose/MCP views, profile dialogs, five themes, real local audio playback, desktop/tablet/phone layouts and 1000 synthetic rows. Browser-plugin tooling was unavailable in the acceptance environment, so locally installed Python Playwright/Chromium was used. Strict CSP is retained; tests do not enable unsafe-eval.

Desktop uses the full existing `tests/` suite with an isolated APPDATA/QSettings path and Qt offscreen fonts. Windows native installer restart tests require NSIS and the built EXE. Pillow is a test-only dependency declared in root `requirements-test.txt`. Linux updater unit cases cover success, authorization wait, cancellation and error behavior. Package-install smoke tests use disposable environments with synthetic profile/configuration files.

Acceptance must distinguish mocked operations, actual package installation and interactive GUI behavior. Headless tests do not prove an actual Linux polkit password prompt, Windows installer UI, signed installer reputation, every remote host adapter or every external MCP client. The local acceptance report and logs record executed checks and remaining limits; do not interpret planned checks as passing results.

Before publication, manually exercise the chosen OS upgrade from 1.3.10, confirm profiles/settings, test the required SSH/WSL/Balena host and any client-specific MCP configuration. No test may remove user containers, volumes or overwrite an existing installation.

Extended operator acceptance: `python apps/dcc-web/tests/browser_extended.py --out PATH` against the synthetic server on 8790. It checks panel new tabs, bulk operations, grouped menu/copy, image action clipping, editable ports/restart, AI proposals, 2000-day/no-expiry grants, all English view captions and EN/PL persistence. `node apps/dcc-web/tests/frontend_unit.mjs` verifies that translations affect authored UI fragments while preserving interpolated Docker data.
