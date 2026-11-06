# Docker Control Center

[Jump to Polish / Przejdź do polskiej wersji](#polski)

![Windows](https://img.shields.io/badge/Windows-11%20%2F%2010-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/UI-PyQt6-41CD52?logo=qt&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Local%20%7C%20WSL%20%7C%20SSH-2496ED?logo=docker&logoColor=white)
![Languages](https://img.shields.io/badge/Languages-EN%20%7C%20PL-F7DF1E?logo=googletranslate&logoColor=black)
[![XERJ Corpus Hub contributor](https://hub.xerj.org/contributors/hattimon/badge.svg)](https://hub.xerj.org/contributors/hattimon)

A cross-platform desktop control panel for managing Docker on Windows and Debian-family Linux, locally, through WSL/WSL2, and on remote hosts over SSH or Balena OS.

### Download Latest Version

[![Windows EXE v1.3.12](https://img.shields.io/badge/Windows-EXE%20v1.3.12-blue)](https://github.com/hattimon/DCC/releases/download/v1.3.12/DockerControlCenter-Setup-1.3.12.exe)
[![Linux DEB v1.3.12](https://img.shields.io/badge/Linux-DEB%20v1.3.12-orange)](https://github.com/hattimon/DCC/releases/download/v1.3.12/DockerControlCenter_1.3.12_amd64.deb)
[![DCC Web v0.3.1](https://img.shields.io/badge/DCC%20Web-v0.3.1-20bfc8?logo=docker&logoColor=white)](https://github.com/hattimon/DCC/releases/download/dcc-web-v0.3.1/DCC-Web-0.3.1-source.zip)

DCC Web: Windows, macOS, Linux · Docker Compose.

[Install DCC Web (EN)](https://github.com/hattimon/DCC/blob/dcc-web-v0.3.1/apps/dcc-web/docs/installation.md) · [Instalacja DCC Web (PL)](https://github.com/hattimon/DCC/blob/dcc-web-v0.3.1/apps/dcc-web/docs/installation.pl.md)

Release notes / Opisy wydań: [DCC Desktop 1.3.12](https://github.com/hattimon/DCC/releases/tag/v1.3.12) · [DCC Web 0.3.1](https://github.com/hattimon/DCC/releases/tag/dcc-web-v0.3.1) · [DCC Container Updater 1.1.5](https://github.com/hattimon/DCC/releases/tag/updater-v1.1.5) · [All releases / Wszystkie wydania](https://github.com/hattimon/DCC/releases)

### Automatic DCC Web updates / Automatyczne aktualizacje DCC Web

Install **DCC Container Updater** from **App Store → DCC** in DCC Desktop or DCC Web. For supported Docker installations, enable automatic updates for your DCC Web container in the Updater panel.

Zainstaluj **DCC Container Updater** przez **Sklep aplikacji → DCC** w DCC Desktop lub DCC Web. W obsługiwanej instalacji kontenerowej włącz automatyczne aktualizacje kontenera DCC Web w panelu Updatera.

DCC Web 0.2.8 or newer and Updater 1.1.5 can preserve the configured public zrok domain across a compatible Web update. When the administrator has enabled tunnel resumption, Updater pauses the tunnel during container replacement and resumes it after the new Web container passes its health check. You do not need to turn off or remove the public domain manually. For the first upgrade from Web older than 0.2.8, follow the compatibility instructions shown by Updater.

DCC Web 0.2.8 lub nowszy i Updater 1.1.5 mogą zachować skonfigurowaną publiczną domenę zrok podczas zgodnej aktualizacji Web. Jeśli administrator włączył wznawianie tunelu, Updater automatycznie wstrzymuje tunel na czas podmiany kontenera i wznawia go po pozytywnym teście zdrowia nowego kontenera Web. Nie trzeba ręcznie wyłączać dostępu publicznego ani usuwać domeny. Przy pierwszej aktualizacji z Web starszego niż 0.2.8 wykonaj instrukcje zgodności wyświetlone przez Updater.

[DCC Container Updater](apps/container-updater/README.md) · [Installation guide / Instrukcja instalacji](apps/container-updater/README.md#install)

### DCC Desktop — overview / widok aplikacji

![Docker Control Center v1.3.5 - English overview](images/release-1.3.5/09-v1.3.5-overview-en.png)

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

DCC Web **0.3.1** preserves original container-panel addresses and opens them through a session-protected gateway on public ingress. It adds isolated service cookies, forms, ES modules, SSE and WebSocket bridging. / Wersja **0.3.1** zachowuje oryginalne adresy paneli kontenerów i otwiera je przez bramę chronioną sesją DCC. Dodaje izolację cookies usług oraz obsługę formularzy, modułów ES, SSE i WebSocket. [Release / Wydanie 0.3.1](https://github.com/hattimon/DCC/releases/tag/dcc-web-v0.3.1)

Monitoring in **0.3.0** supports descending → ascending → default sorting for CPU, RAM, RAM %, network, disk I/O and processes. / Monitoring w **0.3.0** obsługuje sortowanie malejące → rosnące → domyślne dla CPU, RAM, RAM %, sieci, dysku I/O i procesów.

DCC Web **0.3.0** keeps reconnecting after Internet outages and adds optional tunnel recovery after a Web/computer restart. Enable both restart recovery and Updater handoff in the local Remote Internet Access dialog to cover both cases. / DCC Web **0.3.0** ponawia połączenie po przerwie w Internecie i dodaje opcjonalne wznowienie tunelu po restarcie panelu/komputera. Zaznacz obie zgody na wznowienie w lokalnych ustawieniach zdalnego dostępu. [Release / Wydanie 0.3.0](https://github.com/hattimon/DCC/releases/tag/dcc-web-v0.3.0)

DCC Web is the browser-based counterpart to DCC Desktop and runs as a separate service. See the [product overview](https://github.com/hattimon/DCC/blob/dcc-web-v0.3.1/apps/dcc-web/README.md) and the [GitHub repository](https://github.com/hattimon/DCC).

DCC Web provides container management, profiles with visible profile IDs, logs, monitoring, Compose and the shared App Store, along with themes, local audio, English and Polish, clickable panel links, an AI configuration assistant and scoped MCP tools for authorized read and write operations. Its Docker image is published in GHCR and listed in the App Store catalog. [Installation guide](https://github.com/hattimon/DCC/blob/dcc-web-v0.3.1/apps/dcc-web/docs/installation.md) · [Feature matrix](https://github.com/hattimon/DCC/blob/dcc-web-v0.3.1/apps/dcc-web/docs/feature-matrix.md)

DCC Web 0.2.4 adds grant-scoped agent instructions and project ZIPs for seven MCP clients, including an optional ChatGPT Web variant for Codex. [MCP guide (EN)](https://github.com/hattimon/DCC/blob/dcc-web-v0.3.1/apps/dcc-web/docs/mcp.md) · [Instrukcja MCP (PL)](https://github.com/hattimon/DCC/blob/dcc-web-v0.3.1/apps/dcc-web/docs/mcp.pl.md)

DCC Web 0.2.6 accepts hosted zrok reservations on `shares.zrok.io` and can resume a pending reservation using the saved environment. After updating through DCC Container Updater, open **Settings → Administration and security → Panel access and HTTPS (TLS) → Remote Internet Access** to finish setup.

DCC Web 0.2.7 defaults BalenaOS profiles to SSH port 22222 and migrates existing profiles that still use the former default port 22. SSH connection failures now report actionable causes such as DNS, timeout, refused connection, authentication, host-key verification or unreadable saved credentials. It also migrates legacy DCC Remote Access panel networks into a collision-checked subnet pool so the isolated network cannot capture routes to remote profiles; re-enable the tunnel after updating.

DCC Web 0.2.5 fixes the **Profile not found** error when checking the result of Remote Access configuration, activation or restart. Public access starts disabled. [Remote Access (EN)](https://github.com/hattimon/DCC/blob/dcc-web-v0.3.0/apps/dcc-remote-access/README.md) · [Zdalny dostęp (PL)](https://github.com/hattimon/DCC/blob/dcc-web-v0.3.0/apps/dcc-remote-access/README.pl.md)
