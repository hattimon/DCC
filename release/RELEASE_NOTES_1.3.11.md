# Docker Control Center v1.3.11

## English
- Bold DCC category directly after Installed and before AI; apps may belong to several categories.
- DCC Container Updater remains in Updates and also appears in DCC. Compact application header.
- Independent DCC Web workspace, shared catalog semantics, themes, audio and MCP preparation.
- Local DCC Web sound effects are enabled by default and can be disabled in settings.
- DCC Web 0.1.1 is installable from the DCC, Administration and WWW App Store categories. The Website button opens its formatted GitHub product page.
- A fresh DCC Web Store install now starts with a one-time random administrator password shown in the installation result and container logs; it is stored only as a password hash.
- The DCC Web image supports Linux amd64 and arm64. The web process drops to UID 10001 and receives the Docker socket group.
- DCC Web help pages render Markdown as formatted, escaped HTML without adding a runtime dependency.
- Container filters and bulk actions share one row; the search field contracts on narrow screens.
- Added a cross-platform DCC Web installer that scans Docker and local TCP ports, then selects a free port when 8789 is busy.
- Retained the Windows graceful updater handoff/restart and Linux pkexec/apt installation flow.
- Reissued the Linux DEB with the missing `libpulse0` runtime dependency and the portable `pkexec` dependency name. CI builds on Ubuntu 22.04, upgrades and launches under X11, and verifies a clean install on Debian 13 (the current MX Linux base).

## Polski
- Pogrubiona kategoria DCC za Zainstalowane i przed AI; wiele kategorii jednej aplikacji.
- DCC Container Updater pozostaje w Aktualizacje i jest dostępny także w DCC. Zwarty nagłówek.
- Niezależny DCC Web, wspólna logika katalogu, motywy, audio i przygotowanie MCP.
- Lokalne efekty dźwiękowe DCC Web są domyślnie włączone i można je wyłączyć w ustawieniach.
- DCC Web 0.1.1 można zainstalować z kategorii DCC, Administracja i WWW. Przycisk Strona otwiera sformatowaną prezentację na GitHubie.
- Nowa instalacja DCC Web tworzy losowe hasło administratora wyświetlane w wyniku instalacji i logach; w bazie przechowywany jest wyłącznie hash.
- Obraz DCC Web obsługuje Linux amd64 i arm64; proces panelu działa jako UID 10001 i otrzymuje grupę socketu Docker.
- Dokumentacja DCC Web wyświetla formatowany, bezpiecznie escapowany Markdown bez nowych zależności.
- Filtry i operacje na kontenerach mieszczą się w jednym wierszu; wyszukiwarka zwęża się na małym ekranie.
- Zachowany handoff i restart Windows oraz instalacja przez pkexec/apt na Linux.
- Ponownie udostępniono DEB z zależnościami `libpulse0` i `pkexec`, zgodnymi z aktualnym Debianem/MX. CI buduje pakiet na Ubuntu 22.04, sprawdza aktualizację i start X11 oraz czystą instalację w Debianie 13.
- Dodano wieloplatformowy instalator DCC Web, który skanuje używane porty kontenerów i wybiera wolny port, gdy domyślny 8789 jest zajęty.

## Downloads / Pobieranie
- DockerControlCenter-Setup-1.3.11.exe
- DockerControlCenter_1.3.11_amd64.deb
- SHA256SUMS-1.3.11.txt
- DCC-Web-0.1.1-source.zip

The existing updater discovers this release through GitHub's latest-release API and selects the platform installer by asset name. The v1.3.11 Linux assets are rebuilt with corrected runtime dependencies; release tag and version remain unchanged.

## DCC Web 0.1.1

Independent Flask/Waitress module with native browser UI, encrypted Docker profiles, role/profile permissions, confirmed container/resource/Compose operations, logs, monitoring and the shared multi-source store. Five themes and three short local sound packs; provider-neutral read-only MCP stdio Preview with revocable grants and client configuration exporters.

Niezależny moduł Flask/Waitress: profile Docker z szyfrowanymi sekretami, uprawnienia, potwierdzane operacje, logi, monitoring i wspólny sklep. Pięć motywów, trzy lokalne pakiety audio oraz MCP stdio Preview tylko do odczytu.

Known limits / ograniczenia: container recreation/updates support local/TLS/verified SSH and localhost tunnel API profiles; WSL uses TLS or host Compose/Updater. Interactive PTY and native OS dependency installation remain Desktop-specific. Web now has complete EN/PL, panel links and ports, bulk controls, grouped actions, AI proposal adapters and 2000-day/no-expiry MCP grants. AI providers and remote SSH API mutations require manual acceptance with the chosen host/model. MCP HTTP/write tools are disabled; external AI clients and interactive polkit/installer UI still require manual acceptance. See `apps/dcc-web/docs/feature-matrix.md` and the local acceptance report for evidence and exact limits.
