# Desktop / Web audit and acceptance matrix

Audit source: Desktop `DockerControlCenter.py` dialogs, MainWindow actions, Docker/SSH/WSL adapters, store, `RepoBuilder.py`, packaging and existing regression tests. Desktop retains all those implementations. Web implements the operational browser equivalents below; it is not claimed to have full native application parity.

| Desktop function | Web implementation / limit | Evidence |
|---|---|---|
| Local Docker / CLI contexts | Profile connection, info, read-only default | API + CLI mock + real local read check |
| Verified remote TCP | TLS profile with CA/client paths | Validation/command construction tests; no external host supplied |
| SSH / Balena OS | Verified SSH, quoted Docker/Balena arguments | Transport mocks; external host acceptance pending |
| Docker Desktop / WSL | Local CLI or named WSL distro | Argument tests; WSL target acceptance pending |
| Profile create/edit/delete/import/export | Encrypted secrets, user/capability restrictions, legacy metadata import | API tests + browser form |
| Desktop hidden tunnel command | Connect to already established localhost tunnel | Arbitrary tunnel creation intentionally not executed by Web |
| Container list/status/health/search | List with panel links, published ports and inspect state/health/mounts/env/image | API + browser + 1000 synthetic rows |
| Start/stop/restart/pause/unpause/remove | Confirmed single/bulk actions; no forced volume removal | API and browser mock lifecycle |
| Restart policy/autostart | Confirmed on/off actions | Transport action map / API |
| Container details and diagnostic inspection | Redacted full Docker inspect, connection errors | API + browser |
| Exec terminal | Bounded non-interactive container command/output | API construction; no interactive PTY/WebSocket terminal |
| Edit container startup | Env/command/user/workdir/ports/restart recreation via existing updater | Local/TLS/verified SSH/tunnel; delegation + upstream safety tests; SSH requires manual host acceptance |
| Additional mount/port recreation | Ports editable; mounts retained during recreation or managed through Compose | Advanced mount/network editing remains through Compose |
| Logs | Periodic live refresh, tail/search/download/error highlighting | API + real browser |
| CPU/RAM/network/I/O | Live stats/table and bounded historical CPU/RAM charts | API + browser; samples collected while clients request them |
| Images | List/search/inspect/pull/tag/remove | API + browser; save/load archive UI pending |
| Volumes | List/search/inspect/create/delete with irreversible consent and attachment check | API + browser; backup/restore UI pending |
| Networks | List/search/inspect/create bridge/remove | API + browser; advanced network wizard pending |
| Compose | Discover/import/validate/ps/up/pull/stop/restart/logs/down; multiple files | API + browser; remote imports require host file provisioning |
| Store installation/manual container | Catalog renders without Docker round trips; installed-app scan is asynchronous; install/uninstall show progress; uninstall retains volumes | API canonical presets, background-scan and job tests + browser mock install |
| Store categories | All → Installed → bold DCC → AI, multiple memberships, Balena OS | Shared helper/Desktop/Web tests |
| Additional catalogs | GitHub/HTTPS/file, enable/delete/validate/cache/fallback/hourly/manual refresh | API + browser source manager |
| Container updates | Existing safe UpdateService with confirmed check/apply | Local/TLS/verified SSH/tunnel API; WSL uses TLS or host Updater/Compose; Balena requires its CLI dial-stdio support |
| Desktop updater EXE/DEB | Desktop retains handoff/pkexec/apt-get; Web independently versioned | 1.3.11 release/update regression and isolated package checks |
| Theme/audio settings | Five native Web themes, live previews, local audio, user preferences | API + browser playback/screenshots |
| Desktop PL/EN interface | Preserved; full Web EN (default) and PL with per-user persistence | API, browser and authored-fragment translation tests |
| Desktop AI command generator/provider settings | Web has OpenAI Responses, compatible endpoint and Ollama proposal adapters | Explicit generation only; encrypted keys, no automatic execution; provider tests mocked |
| MCP profiles/client grants | Scoped stdio read and write tools, reauthentication for write grants, per-profile permission checks, expiry/revoke/audit | Unit/stdin lifecycle tests; external client sessions pending |
| Repo Builder native editor | Existing Desktop executable included in builds | Web catalog import/manage works; native editor stays Desktop |
| OS dependencies / Docker installation / host reboot / host terminal | Existing Desktop paths preserved | Native Web can open its local shell; containerized Web manages its local Docker Engine by socket and reaches the same host shell through an explicitly configured, verified SSH profile. Web does not perform OS installation or host reboot. |
| Tray, pin/taskbar identity, native shortcuts, full screen/transparency/tutorial | Native Desktop features preserved | Existing Desktop UI/installer regressions |
| Browser security/user audit | New auth/CSRF/RBAC/vault/confirmation/audit | Dedicated Web security tests |

All actions exposed in Web are backed by API operations; unavailable adapter operations return an explicit error instead of reporting success. Transport mocks validate command construction, not the availability of a customer's remote engine. Destructive browser tests use only the synthetic fixture. See the local acceptance report for actual counts, measured performance, artifact hashes and upgrade-test boundaries.
