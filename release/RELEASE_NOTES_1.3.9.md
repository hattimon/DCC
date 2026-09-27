# Docker Control Center v1.3.9

DCC 1.3.9 finalizes the UI, theme, audio, icon, refresh and packaging work built on top of the stable 1.3.8 updater flow.

## English

- Fixed the Windows 1.3.8 update handoff: v1.3.9 recognizes the legacy staged updater helper, installs silently and relaunches DCC. The current updater verifies the installed version and reports failures; DCC taskbar pin icons refresh in place.
- Added case-insensitive search to Logs; the query remains in place when logs are refreshed.
- Added configurable container auto-refresh with saved on/off state and a 5, 10, 15, 30 or 60 second interval. Refreshes do not overlap an active container refresh.
- New Container opens in Store mode and can switch to a manual Docker command; editing an existing container keeps its real configuration while the catalog refreshes.
- Adjusted Store sizing so category navigation and cards fit normal and compact desktop widths without horizontal scrolling.
- Expanded the neon palette with muted colors and custom accents. Neon animation preserves the selected hue, and Theme Settings can enable glow independently from animation.
- Fixed the global checkbox visibility regression with an explicit checked mark while retaining native Qt click and signal behavior.
- Replaced dialog-level deferred callbacks with owned, cleaned-up timers and stopped recurring UI timers during shutdown, addressing the reported `0xC0000409` stability issue.
- Added visible accent grips at container-table resize boundaries while keeping sorting and interactive resizing.
- Fixed shortcut AppUserModelID assignment on Windows PowerShell and made failures log a warning while installation continues; corrected Polish installer text encoding.
- Fixed one-file PyInstaller child-process context so external programs do not retain the temporary `_MEI` directory.
- Kept the Theme Settings introduction on one line with clear spacing before the first section.
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
- Added separate final icons and Windows metadata for DCC and Repo Builder, stable AppUserModelIDs and non-destructive shell icon refresh. Windows and Linux icon assets are generated from `assets/dcc_icon.png`.
- Searchable Windows Start Menu entries are `DCC - Docker Control Center`, `DCC Repo Builder` and `Uninstall DCC`.
- Manual NSIS install detects a running DCC and requests a graceful close with user confirmation; no forced `taskkill /F` path is used.
- Preserved the updater handoff: wait for the DCC PID to exit, wait an additional 1200 ms, run the installer and relaunch DCC after a successful update. Update discovery from 1.3.8 selects `DockerControlCenter-Setup-1.3.9.exe`.
- Linux packaging includes both desktop entries, both icon sets and all audio assets.

## Polski

- Naprawiono aktualizację Windows ze starszego updatera 1.3.8: instalator 1.3.9 rozpoznaje stary plik pomocniczy, instaluje aktualizację po cichu i ponownie uruchamia DCC. Aktualny updater sprawdza zainstalowaną wersję i zgłasza błąd; ikony przypiętych skrótów DCC są odświeżane bez usuwania przypięć.
- Dodano niewrażliwe na wielkość liter wyszukiwanie w Logs; wpisane zapytanie pozostaje po odświeżeniu logów.
- Dodano konfigurowalne auto-odświeżanie kontenerów z zapamiętaniem stanu i interwałem 5, 10, 15, 30 lub 60 sekund. Odświeżanie nie uruchamia się ponownie, gdy poprzednie nadal trwa.
- New Container otwiera się domyślnie w Store i pozwala przełączyć się na ręczną komendę Docker; edycja istniejącego kontenera zachowuje jego konfigurację podczas odświeżania katalogu.
- Dopasowano rozmiary Store tak, aby nawigacja kategorii i karty mieściły się na typowych i węższych ekranach bez poziomego przewijania.
- Rozszerzono paletę neonu o stonowane kolory i własne akcenty. Animacja zachowuje wybrany odcień, a Theme Settings pozwala niezależnie włączyć poświatę i jej animację.
- Naprawiono widoczność zaznaczenia we wszystkich checkboxach, zachowując natywne kliknięcia i sygnały Qt.
- Zastąpiono odroczone callbacki dialogów własnymi timerami z kontrolowanym sprzątaniem i zatrzymywaniem cyklicznych timerów przy zamykaniu, rozwiązując zgłoszony problem stabilności `0xC0000409`.
- Dodano widoczne uchwyty akcentu przy granicach zmiany szerokości kolumn tabeli kontenerów, zachowując sortowanie i ręczną zmianę rozmiaru.
- Naprawiono przypisywanie AppUserModelID skrótom w Windows PowerShell; błąd zapisuje ostrzeżenie, ale nie przerywa instalacji. Poprawiono kodowanie polskich tekstów instalatora.
- Naprawiono katalog roboczy i środowisko procesów potomnych PyInstaller one-file, aby nie blokowały usuwania tymczasowego katalogu `_MEI`.
- Ustawiono wiersz wprowadzający Theme Settings w jednej linii i dodano odstęp przed pierwszą sekcją.
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
- Dodano osobne finalne ikony i metadane Windows dla DCC i Repo Buildera, stabilne AppUserModelID oraz niedestrukcyjne odświeżanie ikon powłoki. Zasoby ikon Windows i Linux są generowane z `assets/dcc_icon.png`.
- Wyszukiwalne skróty Windows Start Menu: `DCC - Docker Control Center`, `DCC Repo Builder` i `Uninstall DCC`.
- Manualny instalator NSIS wykrywa uruchomione DCC i prosi o jego łagodne zamknięcie z potwierdzeniem użytkownika; nie używa wymuszonego `taskkill /F`.
- Zachowano handoff updatera: oczekiwanie na zakończenie PID DCC, dodatkowe 1200 ms, uruchomienie instalatora i relaunch DCC po udanej aktualizacji. Aktualizacja z 1.3.8 wybiera `DockerControlCenter-Setup-1.3.9.exe`.
- Pakiet Linux zawiera oba wpisy desktop, oba zestawy ikon i komplet audio.

## Packages / Pakiety

- `DockerControlCenter-Setup-1.3.9.exe`
- `DockerControlCenter_1.3.9_amd64.deb`
- `SHA256SUMS-1.3.9.txt`
