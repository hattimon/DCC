# Docker Control Center v1.3.9

DCC 1.3.9 finalizes the UI, theme, audio, icon, refresh and packaging work built on top of the stable 1.3.8 updater flow.

## English

- Improved Application Store readability in `Light` and `Day`, including readable Categories and theme-derived surfaces without hard-coded dark backgrounds.
- Completed `Light` / `Day` palettes in Repo Builder and prevented PyInstaller `_MEI...` extraction paths from being shown or persisted as a normal catalog location.
- Container refresh now preserves vertical and horizontal scroll, current selection and expanded groups.
- Column Magnet is enabled by default with a visible checkmark; table dividers use vertical `⋮` resize grips without fake data columns.
- `View -> Theme -> SETTINGS` is the first theme-menu item, followed by a separator and the visual themes.
- Added Theme Settings for visual theme, neon/accent, audio enabled, independent sound style, Master volume, Theme intro volume and Effects volume, with Save/Cancel rollback behavior.
- Replaced continuous ambient playback with short one-shot intros. Intro plays on app start, visual-theme change when audio follows the theme, audio-profile change and audio OFF -> ON, then playback returns to silence.
- Sound style is independent from the visual theme and supports `Auto`, `Night`, `Black`, `Dark`, `Light` and `Day`.
- Default audio levels are Master 100%, Theme intro 35% and Effects 65%; legacy `ambient_volume` is migrated to `intro_volume` when needed.
- Added five distinct procedural sound profiles: Night rock/metal guitar-like, Black electronic/neon/glass, Dark sci-fi, Light fresh/clean and Day mystical/fog/harbor.
- Added 65 locally generated WAV assets: 13 required one-shot files for each of five profiles, with no downloaded samples or external recordings.
- Container audio uses a baseline first snapshot, real stopped/running transitions, restart-request/restart-complete pairing, host reconnect sound and deduplication to avoid refresh spam.
- Added separate final icons and Windows metadata for DCC and Repo Builder, stable AppUserModelIDs and non-destructive shell icon refresh.
- Windows Start Menu entries are `DCC - Docker Control Center`, `DCC Repo Builder` and `Uninstall DCC`.
- Manual NSIS install detects a running DCC and requests a graceful close with user confirmation; no forced `taskkill /F` path is used.
- Preserved the updater handoff: wait for the DCC PID to exit, wait an additional 1200 ms, run the installer and relaunch DCC after a successful update.
- Linux packaging includes both desktop entries, both icon sets and all audio assets.

## Polski

- Poprawiono czytelność Application Store w motywach `Light` i `Day`, w tym Kategorie/Categories i powierzchnie wynikające z palety motywu bez wymuszonych ciemnych teł.
- Dokończono jasne palety Repo Buildera oraz zabezpieczenie przed pokazywaniem lub zapisywaniem tymczasowej ścieżki PyInstaller `_MEI...` jako normalnej lokalizacji katalogu.
- Odświeżanie kontenerów zachowuje pionowy i poziomy scroll, zaznaczenie oraz rozwinięte grupy.
- Magnes kolumn jest domyślnie włączony i ma czytelny checkmark; separatory nagłówków używają pionowych uchwytów `⋮` bez sztucznych kolumn danych.
- `Widok -> Motyw -> USTAWIENIA` jest pierwszą pozycją menu motywu, nad separatorem i listą motywów.
- Dodano Theme Settings dla motywu wizualnego, neonu/akcentu, włączenia audio, niezależnego stylu dźwięku oraz głośności Master, intro i efektów z obsługą Save/Cancel rollback.
- Usunięto ciągły ambient loop. Audio używa krótkiego one-shot intro przy starcie aplikacji, zmianie motywu gdy profil jest Auto, zmianie profilu audio oraz przejściu audio OFF -> ON, po czym następuje cisza.
- Styl audio jest niezależny od motywu wizualnego i obsługuje `Auto`, `Night`, `Black`, `Dark`, `Light` oraz `Day`.
- Domyślne poziomy głośności: Master 100%, Theme intro 35%, Effects 65%; stare `ambient_volume` jest migrowane do `intro_volume` gdy potrzeba.
- Dodano pięć odrębnych proceduralnych profili: Night rock/metal, Black electronic/neon/glass, Dark sci-fi, Light fresh/clean i Day mystical/fog/harbor.
- Finalny pakiet zawiera 65 lokalnie generowanych plików WAV: 13 wymaganych one-shotów dla każdego z pięciu profili, bez zewnętrznych sampli i nagrań.
- Logika audio kontenerów używa pierwszego snapshotu jako baseline, reaguje tylko na rzeczywiste przejścia stopped/running, paruje restart requested/completed, obsługuje host_connected i deduplikuje eventy.
- Dodano osobne finalne ikony i metadane Windows dla DCC i Repo Buildera, stabilne AppUserModelID oraz niedestrukcyjne odświeżanie ikon powłoki.
- Skróty Start Menu: `DCC - Docker Control Center`, `DCC Repo Builder` i `Uninstall DCC`.
- Manualny instalator NSIS wykrywa uruchomione DCC i prosi o jego łagodne zamknięcie z potwierdzeniem użytkownika; nie używa wymuszonego `taskkill /F`.
- Zachowano handoff updatera: oczekiwanie na zakończenie PID DCC, dodatkowe 1200 ms, uruchomienie instalatora i relaunch DCC po udanej aktualizacji.
- Pakiet Linux zawiera oba wpisy desktop, oba zestawy ikon i komplet audio.

## Packages / Pakiety

- `DockerControlCenter-Setup-1.3.9.exe`
- `DockerControlCenter_1.3.9_amd64.deb`
- `SHA256SUMS-1.3.9.txt`
