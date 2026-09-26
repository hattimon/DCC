# Docker Control Center v1.3.9

Docker Control Center 1.3.9 builds on the stable 1.3.8 updater and packaging flow, with a new theme-aware audio system plus the UI, Store, Repo Builder, icon and refresh improvements completed since 1.3.8.

## English

- Added case-insensitive search inside container logs with next/previous result navigation that survives log refreshes.
- Improved `Day` and `Light` theme readability and control surfaces.
- Repo Builder now shares the DCC theme/accent settings and supports Save / Save As workflows.
- Added the `New container` workflow improvements completed after 1.3.8.
- Improved Application Store sizing and compact layout behavior.
- Added and stabilized automatic container refresh with overlap protection.
- Expanded the neon accent palette and fixed neon animation/accent persistence.
- Added the final glass DCC icon and a consistent Windows/Linux icon pipeline, including the full Linux hicolor set.
- Added theme-aware procedural audio for `Night`, `Black`, `Dark`, `Light` and `Day`.
- The note button now enables/disables all DCC audio: ambient plus event sound effects.
- Reordered the compact controls to note -> transparency toggle -> transparency slider.
- Added event SFX for Docker start, stop, restart, pause/unpause, remove, container create/recreate/build success and errors.
- All DCC audio is generated procedurally by the repository tool; no external recordings or stock samples are required.
- Added package-aware audio resource resolution and validation for source and PyInstaller modes.
- Preserved the 1.3.8 Windows updater handoff: DCC finishes the download, exits Qt, the hidden helper waits for the DCC PID to disappear, waits an additional delay, then starts the installer.
- Preserved the NSIS safety changes: the installer does not terminate DCC and does not run installer-time `--self-check`.
- Added release/update tests for `1.3.8 -> 1.3.9` and deterministic Windows installer asset selection.

## Polski

- Dodano wyszukiwanie bez rozróżniania wielkości liter w logach kontenerów, nawigację następny/poprzedni wynik i zachowanie wyszukiwania po odświeżeniu logów.
- Poprawiono czytelność motywów `Day` i `Light` oraz ich powierzchnie kontrolek.
- Repo Builder korzysta ze wspólnych ustawień motywu/akcentu DCC i obsługuje Save / Save As.
- Uwzględniono poprawki workflow `New container` wykonane po 1.3.8.
- Poprawiono rozmiary i zwarty układ Application Store.
- Dodano i ustabilizowano automatyczne odświeżanie kontenerów z ochroną przed nakładaniem odświeżeń.
- Rozszerzono paletę neonowych akcentów oraz naprawiono zapamiętywanie animacji i akcentu.
- Dodano finalną szklaną ikonę DCC i spójny pipeline ikon Windows/Linux, w tym pełny zestaw hicolor dla Linuksa.
- Dodano proceduralne audio zależne od motywu dla `Night`, `Black`, `Dark`, `Light` i `Day`.
- Przycisk nutki włącza/wyłącza całe audio DCC: ambient i dźwięki zdarzeń.
- Zmieniono kolejność kompaktowych kontrolek na nutka -> przełącznik przezroczystości -> suwak przezroczystości.
- Dodano SFX dla operacji Docker: start, stop, restart, pauza/wznowienie, usunięcie oraz powodzenie/błąd tworzenia, odtwarzania i budowania kontenera.
- Wszystkie dźwięki DCC są generowane proceduralnie przez narzędzie z repozytorium; nie wymagają zewnętrznych nagrań ani stockowych sampli.
- Dodano resolver i walidację audio działające zarówno ze źródeł, jak i w trybie PyInstaller.
- Zachowano bezpieczny handoff updatera Windows z 1.3.8: DCC kończy pobieranie, zamyka Qt, ukryty helper czeka na zniknięcie PID DCC, odczekuje dodatkowo i dopiero uruchamia instalator.
- Zachowano poprawki NSIS: instalator nie kończy procesu DCC i nie uruchamia `--self-check` podczas instalacji.
- Dodano test ścieżki aktualizacji `1.3.8 -> 1.3.9` oraz jednoznacznego wyboru instalatora Windows.

## Packages / Pakiety

- `DockerControlCenter-Setup-1.3.9.exe`
- `DockerControlCenter_1.3.9_amd64.deb`
- `SHA256SUMS-1.3.9.txt`
