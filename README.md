# Docker Control Center

[Jump to Polish / Przejdź do polskiej wersji](#polski)

![Windows](https://img.shields.io/badge/Windows-11%20%2F%2010-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/UI-PyQt6-41CD52?logo=qt&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Local%20%7C%20WSL%20%7C%20SSH-2496ED?logo=docker&logoColor=white)
![Languages](https://img.shields.io/badge/Languages-EN%20%7C%20PL-F7DF1E?logo=googletranslate&logoColor=black)
[![XERJ Corpus Hub contributor](https://hub.xerj.org/contributors/hattimon/badge.svg)](https://hub.xerj.org/contributors/hattimon)

A cross-platform desktop control panel for managing Docker on Windows and Debian-family Linux, locally, through WSL/WSL2, and on remote hosts over SSH or Balena OS.

### Download Latest Version — 1.3.12

[![Windows EXE](https://img.shields.io/badge/Windows-EXE-blue)](https://github.com/hattimon/DCC/releases/download/v1.3.12/DockerControlCenter-Setup-1.3.12.exe)
[![Linux DEB](https://img.shields.io/badge/Linux-DEB-orange)](https://github.com/hattimon/DCC/releases/download/v1.3.12/DockerControlCenter_1.3.12_amd64.deb)
[![DCC Web v0.1.6](https://img.shields.io/badge/DCC%20Web-v0.1.6-20bfc8?logo=docker&logoColor=white)](apps/dcc-web/docs/installation.md)

DCC Web can be installed on Windows, macOS and Debian-family Linux with Docker Compose or run directly with Python. Its installer checks Docker-published ports and local port availability, uses 8789 when free, and chooses another available port when necessary. See the [installation guide](apps/dcc-web/docs/installation.md).

## What's New in v1.3.12

### EN
- One current App Store entry per application across all categories, including after catalog refresh or import.
- Older cached numeric versions cannot replace newer entries; catalog validation rejects duplicate definitions.
- DCC Web 0.1.4 ships the same store fix. Legacy catalogs retain Administration for Web and Updates for Updater.
- Existing Windows installer update handoff and Debian-family package upgrade mechanisms are retained.

### PL
- Jeden aktualny wpis aplikacji w sklepie we wszystkich jej kategoriach, również po odświeżeniu i imporcie katalogu.
- Starsze wersje z pamięci katalogu nie zastępują nowszych; walidacja odrzuca powielone definicje.
- DCC Web 0.1.4 zawiera tę samą poprawkę. Starsze klienty nadal widzą Web w Administracji i Updater w Aktualizacjach.
- Zachowano dotychczasowy mechanizm aktualizacji instalatorem Windows i pakietem DEB.

## What's New in v1.3.11

### EN
- Added the bold DCC Store category and multiple categories per app; Container Updater remains in Updates.
- Added DCC Web 0.1.1 as an installable multi-architecture App Store app with a rendered GitHub product page.
- Fixed fresh DCC Web App Store startup with a one-time random administrator password surfaced in the installation result.
- Added a cross-platform DCC Web installer and documented automatic port selection to avoid conflicts with existing containers.
- Preserved the Windows installer handoff and Linux package updater while publishing versioned EXE and DEB assets.
- Improved DCC Web container controls, host terminals, installation progress and formatted in-panel documentation.
- Fixed the Windows infrastructure terminal and improved Store contrast and refresh cleanup.
- Reissued the Linux DEB with the missing `libpulse0` runtime dependency and verified desktop-entry startup under X11.

### PL
- Dodano pogrubioną kategorię DCC i możliwość przypisywania aplikacjom wielu kategorii. Container Updater nadal należy do Aktualizacji.
- Dodano DCC Web 0.1.1 jako instalowalną aplikację sklepu dla architektur amd64 i arm64 oraz sformatowaną stronę projektu na GitHubie.
- Naprawiono pierwsze uruchomienie DCC Web ze sklepu. Losowe hasło administratora jest wyświetlane po instalacji.
- Dodano instalator DCC Web dla wielu systemów. Skanuje porty kontenerów i wybiera wolny port, gdy 8789 jest zajęty.
- Zachowano przekazywanie aktualizacji do instalatora Windows i instalację pakietu Linux. Wydanie zawiera wersjonowane pliki EXE i DEB.
- Uzupełniono sterowanie kontenerami, terminale hostów, postęp instalacji i formatowaną dokumentację DCC Web.
- Naprawiono terminal infrastruktury Windows i poprawiono kontrast sklepu oraz porządkowanie po odświeżaniu.
- Ponownie udostępniono pakiet DEB z brakującą zależnością `libpulse0`; sprawdzono uruchamianie wpisu pulpitu w X11.

### DCC Web

[DCC Web product page / strona projektu](apps/dcc-web/README.md) · [Installation guide / instrukcja instalacji](apps/dcc-web/docs/installation.md) · [Polski opis](apps/dcc-web/README.pl.md) · [Repository](https://github.com/hattimon/DCC)

## What's New in v1.3.9

### EN
- Added theme-aware procedural ambient audio and Docker operation SFX for all five themes.
- The note button now controls all DCC audio and sits before transparency controls.
- Improved logs search, Day/Light themes, Store sizing, container auto-refresh and Repo Builder Save/Save As.
- Preserved the safe Windows updater handoff and the cross-platform icon pipeline.

![Docker Control Center v1.3.5 - English overview](images/release-1.3.5/09-v1.3.5-overview-en.png)

### PL
- Dodano generowany dźwięk tła zależny od motywu oraz dźwięki operacji Dockera dla wszystkich pięciu motywów.
- Przycisk dźwięku steruje dźwiękami DCC i znajduje się przed kontrolkami przezroczystości.
- Poprawiono wyszukiwanie logów, motywy Day i Light, rozmiary sklepu, automatyczne odświeżanie kontenerów oraz funkcje Save i Save As w Repo Builderze.
- Zachowano bezpieczne przekazywanie aktualizacji do instalatora Windows i wspólny proces obsługi ikon w Windows i Linux.

![Docker Control Center v1.3.5 - polskie podsumowanie](images/release-1.3.5/08-v1.3.5-overview-pl.png)

## English

### What it does
- Manage local Docker containers from one desktop app.
- Connect to WSL / WSL2 Docker environments.
- Connect to remote Docker hosts over SSH or Balena OS (auto-detected).
- Browse container logs, inspect containers, open web links, and manage autostart.
- Create and modify container run commands with presets and AI-assisted editing.
- Switch between `Light`, `Dark`, and `Black` themes with background artwork support.

### Screenshots
Screenshots below use the English UI.

`Main view - local containers`

![Main view - local containers](images/image.png)

`Remote view - SSH-connected containers`

![Remote view - SSH-connected containers](images/image1.png)

`New container wizard`

![New container wizard](images/image2.png)

`AI assistant`

![AI assistant](images/image3.png)

`New remote profile`

![New remote profile](images/image4.png)

### Distribution
- `Installer`: installs for the current Windows user.
- `Portable`: standalone EXE package with no Python requirement.

### SSH key + passphrase
1. Open `Connection profiles` and add/edit a profile.
2. Set `SSH authentication` to `SSH key + passphrase`.
3. Choose the key file and enter the passphrase.
4. Optional: enable ssh-agent in Windows (see the in-app guide).

### Privacy and security
- User settings are stored per Windows user in `%APPDATA%\DockerControlCenter`.
- API keys and SSH passwords are not stored in the repository.
- Secrets are protected per user with Windows DPAPI.
- The public repository excludes personal profiles, secrets, build folders, and local environment files.

### Included features
- Local Docker management
- WSL / WSL2 integration helpers
- SSH profiles with key, passphrase, or password auth
- Balena OS auto-detection (`balena ps` / `balena run`)
- Curated catalog of 50+ popular images, including lightweight Raspberry Pi options
- AI assistant for `docker run` command editing
- Per-theme custom backgrounds
- Music toggle and futuristic desktop UI
- Context actions, logs, inspect, and link opening

### Example user data files
- `docker_connection_profiles.example.json`
- `%APPDATA%\DockerControlCenter\docker_connection_profiles.json`
- `%APPDATA%\DockerControlCenter\docker_control_center_secrets.json`

---

## Polski

### Co robi aplikacja
- Zarządza lokalnymi kontenerami Docker z jednego okna.
- Łączy się z Dockerem w WSL / WSL2.
- Łączy się ze zdalnymi hostami Docker przez SSH lub Balena OS (automatyczne wykrywanie).
- Wyświetla logi, inspect i linki WWW oraz pozwala ustawić autostart kontenerów.
- Umożliwia tworzenie i edytowanie komend `docker run` z presetami i wsparciem AI.
- Pozwala przełączać motywy `Light`, `Dark` i `Black` oraz korzystać z tapet graficznych.

### Zrzuty ekranu
Poniższe zrzuty przedstawiają interfejs w języku angielskim.

`Widok główny – lokalne kontenery`

![Widok główny – lokalne kontenery](images/image.png)

`Widok zdalny – kontenery przez SSH`

![Widok zdalny – kontenery przez SSH](images/image1.png)

`Kreator nowego kontenera`

![Kreator nowego kontenera](images/image2.png)

`Asystent AI`

![Asystent AI](images/image3.png)

`Dodawanie nowego profilu zdalnego`

![Dodawanie nowego profilu zdalnego](images/image4.png)

### Dystrybucja
- `Installer`: instaluje aplikację dla bieżącego użytkownika Windows.
- `Portable`: samodzielna wersja EXE bez potrzeby instalowania Pythona.

### Klucz SSH + hasło do klucza
1. Otwórz `Profile połączeń` i dodaj lub edytuj profil.
2. Ustaw `Autoryzacja SSH` na `Klucz + hasło do klucza`.
3. Wybierz plik klucza i wpisz hasło.
4. Opcjonalnie włącz ssh-agent w Windows (instrukcja jest dostępna w aplikacji).

### Prywatność i bezpieczeństwo
- Ustawienia użytkownika są przechowywane osobno dla każdego konta Windows w `%APPDATA%\DockerControlCenter`.
- Klucze API i hasła SSH nie są przechowywane w repozytorium.
- Sekrety są chronione za pomocą Windows DPAPI dla konkretnego użytkownika.
- Publiczne repozytorium nie zawiera prywatnych profili, sekretów, plików kompilacji ani lokalnych plików środowiska.

### Najważniejsze funkcje
- Zarządzanie lokalnym Dockerem
- Wsparcie dla WSL / WSL2
- Profile SSH z uwierzytelnianiem kluczem, hasłem do klucza lub hasłem
- Automatyczne wykrywanie Balena OS (`balena ps` / `balena run`)
- Katalog ponad 40 popularnych obrazów, w tym lekkie opcje dla Raspberry Pi
- Asystent AI do edycji komend `docker run`
- Różne tła dla motywów
- Muzyka w tle i futurystyczny interfejs
- Menu kontekstowe, logi, inspect i otwieranie linków

### Przykładowe pliki danych
- `docker_connection_profiles.example.json`
- `%APPDATA%\DockerControlCenter\docker_connection_profiles.json`
- `%APPDATA%\DockerControlCenter\docker_control_center_secrets.json`

## Repository contents
- `docker-menager.ps` - main application source
- `DockerControlCenter.nsi` - NSIS installer script
- `backgrounds/` - theme background artwork
- `images/` - README screenshots
- `icon.ico` / `icon.png` - application icons
- `assets/audio/` - procedural theme ambient and Docker operation sound effects


## Support the project / Wesprzyj projekt

If DCC is useful to you, you can support its continued development on Ko-fi.

Jeżeli DCC jest dla Ciebie przydatny, możesz wesprzeć dalszy rozwój projektu na Ko-fi.

[https://ko-fi.com/hattimon](https://ko-fi.com/hattimon)

## License

DCC is licensed under the MIT License. See [LICENSE](LICENSE).

Projekt DCC jest udostępniany na licencji MIT.

Third-party assets are covered by their respective licenses or ownership terms. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Materiały podmiotów trzecich podlegają ich własnym licencjom lub prawom właścicieli.

## DCC Web

DCC Web is the browser-based counterpart to DCC Desktop and runs as a separate service. See the [product overview](apps/dcc-web/README.md) and the [GitHub repository](https://github.com/hattimon/DCC).

DCC Web provides container management, profiles, logs, monitoring, Compose and the shared App Store, along with themes, local audio, English and Polish, clickable panel links, an AI configuration assistant and a read-only MCP Preview. See the [installation guide](apps/dcc-web/docs/installation.md) and [feature matrix](apps/dcc-web/docs/feature-matrix.md) for setup and adapter limitations. Its Docker image is published in GHCR and listed in the App Store catalog.
