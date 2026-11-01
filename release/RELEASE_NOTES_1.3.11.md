# Docker Control Center v1.3.11 — local review candidate

## English
- Bold DCC category directly after Installed and before AI; apps may belong to several categories.
- DCC Container Updater remains in Updates and also appears in DCC. Compact application header.
- Independent DCC Web workspace, shared catalog semantics, themes, audio and MCP preparation.
- Retained the Windows graceful updater handoff/restart and Linux pkexec/apt installation flow.

## Polski
- Pogrubiona kategoria DCC za Zainstalowane i przed AI; wiele kategorii jednej aplikacji.
- DCC Container Updater pozostaje w Aktualizacje i jest dostępny także w DCC. Zwarty nagłówek.
- Niezależny DCC Web, wspólna logika katalogu, motywy, audio i przygotowanie MCP.
- Zachowany handoff i restart Windows oraz instalacja przez pkexec/apt na Linux.

## Downloads / Pobieranie
- DockerControlCenter-Setup-1.3.11.exe
- DockerControlCenter_1.3.11_amd64.deb
- SHA256SUMS-1.3.11.txt

Local artifacts only. Not published / Wyłącznie artefakty lokalne. Bez publikacji.

## DCC Web 0.1.0 acceptance scope / zakres akceptacji

Independent Flask/Waitress module with native browser UI, encrypted Docker profiles, role/profile permissions, confirmed container/resource/Compose operations, logs, monitoring and the shared multi-source store. Five themes and three short local sound packs; provider-neutral read-only MCP stdio Preview with revocable grants and client configuration exporters.

Niezależny moduł Flask/Waitress: profile Docker z szyfrowanymi sekretami, uprawnienia, potwierdzane operacje, logi, monitoring i wspólny sklep. Pięć motywów, trzy lokalne pakiety audio oraz MCP stdio Preview tylko do odczytu.

Known limits / ograniczenia: container recreation/updates support local/TLS/verified SSH and localhost tunnel API profiles; WSL uses TLS or host Compose/Updater. Interactive PTY and native OS dependency installation remain Desktop-specific. Web now has complete EN/PL, panel links and ports, bulk controls, grouped actions, AI proposal adapters and 2000-day/no-expiry MCP grants. AI providers and remote SSH API mutations require manual acceptance with the chosen host/model. MCP HTTP/write tools are disabled; external AI clients and interactive polkit/installer UI still require manual acceptance. See `apps/dcc-web/docs/feature-matrix.md` and the local acceptance report for evidence and exact limits.
