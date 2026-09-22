# Docker Control Center

[Jump to Polish / Przejdz do polskiej wersji](#polski)

![Windows](https://img.shields.io/badge/Windows-11%20%2F%2010-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/UI-PyQt6-41CD52?logo=qt&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Local%20%7C%20WSL%20%7C%20SSH-2496ED?logo=docker&logoColor=white)
![Languages](https://img.shields.io/badge/Languages-EN%20%7C%20PL-F7DF1E?logo=googletranslate&logoColor=black)

A cross-platform desktop control panel for managing Docker on Windows and Debian-family Linux, locally, through WSL/WSL2, and on remote hosts over SSH or Balena OS.

### Download Latest Version
[![Windows EXE](https://img.shields.io/badge/Windows-EXE-blue)](https://github.com/hattimon/DCC/releases/latest/download/DockerControlCenter-Setup.exe)
[![Linux DEB](https://img.shields.io/badge/Linux-DEB-orange)](https://github.com/hattimon/DCC/releases/latest/download/DockerControlCenter_1.3.8_amd64.deb)

## What's New in v1.3.8

### EN
- Fixed SmartWAN artwork and description overlap in the application catalog.
- Kept search, the application counter, manual configuration and online refresh in one compact row.
- Added `Day` and `Night` themes with dedicated background artwork and readable menus.
- Made every category button visible without scrolling or clipped labels, with extra space below the last row.
- Increased application-card height so two-line descriptions remain fully visible.
- Expanded the application store and added the DCC Repo Builder workflow.

`Day theme - main application`

![DCC v1.3.8 Day theme - English main window](images/release-1.3.8/main-day-en.png)

`Night theme - SmartWAN in the application store`

![DCC v1.3.8 Night theme - English SmartWAN store](images/release-1.3.8/store-smartwan-night-en.png)

`Day theme - Repo Builder`

![DCC v1.3.8 Day theme - English Repo Builder](images/release-1.3.8/repo-builder-day-en.png)

### PL
- Poprawiono nakładanie grafiki SmartWAN i opisu w katalogu aplikacji.
- Pole wyszukiwania, licznik aplikacji, konfiguracja ręczna i odświeżanie online mieszczą się w jednym wierszu.
- Dodano motywy `Day` i `Noc` z osobnymi tłami oraz czytelnymi menu.
- Wszystkie przyciski kategorii są widoczne bez przewijania i uciętych nazw, z dodatkowym miejscem pod ostatnim rzędem.
- Zwiększono wysokość kart aplikacji, aby dwuwierszowe opisy były w pełni widoczne.
- Rozbudowano sklep aplikacji i dodano workflow DCC Repo Builder.

`Motyw Day - aplikacja główna`

![DCC v1.3.8 motyw Day - główne okno PL](images/release-1.3.8/main-day-pl.png)

`Motyw Noc - SmartWAN w sklepie aplikacji`

![DCC v1.3.8 motyw Noc - sklep SmartWAN PL](images/release-1.3.8/store-smartwan-night-pl.png)

`Motyw Day - Repo Builder`

![DCC v1.3.8 motyw Day - Repo Builder PL](images/release-1.3.8/repo-builder-day-pl.png)

## English

### What it does
- Manage local Docker containers from one desktop app.
- Connect to WSL / WSL2 Docker environments.
- Connect to remote Docker hosts over SSH or Balena OS (auto-detected).
- Browse container logs, inspect containers, open web links, and manage autostart.
- Create and modify container run commands with presets and AI-assisted editing.
- Switch between `Day`, `Light`, `Dark`, `Black`, and `Night` themes with background artwork support.

### Screenshots
The v1.3.8 screenshots show both new themes using the English UI.

`Main application - Day`

![Main application - Day](images/release-1.3.8/main-day-en.png)

`Main application - Night`

![Main application - Night](images/release-1.3.8/main-night-en.png)

`Application store / SmartWAN - Day`

![Application store SmartWAN - Day](images/release-1.3.8/store-smartwan-day-en.png)

`Application store / SmartWAN - Night`

![Application store SmartWAN - Night](images/release-1.3.8/store-smartwan-night-en.png)

`Repo Builder - Day`

![Repo Builder - Day](images/release-1.3.8/repo-builder-day-en.png)

`Repo Builder - Night`

![Repo Builder - Night](images/release-1.3.8/repo-builder-night-en.png)

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
- Zarzadza lokalnymi kontenerami Docker z jednego okna.
- Laczy sie z Dockerem w WSL / WSL2.
- Laczy sie ze zdalnymi hostami Docker przez SSH lub Balena OS (auto-wykrywanie).
- Pokazuje logi, inspect, linki WWW i pozwala ustawic autostart kontenerow.
- Umozliwia tworzenie i edycje komend `docker run` z presetami oraz wsparciem AI.
- Pozwala przelaczac motywy `Day`, `Light`, `Dark`, `Black` i `Night` oraz korzystac z tapet graficznych.

### Zrzuty ekranu
Poniższe zrzuty pokazują oba nowe motywy w polskim interfejsie.

`Aplikacja główna - Day`

![Aplikacja główna - Day](images/release-1.3.8/main-day-pl.png)

`Aplikacja główna - Noc`

![Aplikacja główna - Noc](images/release-1.3.8/main-night-pl.png)

`Sklep aplikacji / SmartWAN - Day`

![Sklep aplikacji SmartWAN - Day](images/release-1.3.8/store-smartwan-day-pl.png)

`Sklep aplikacji / SmartWAN - Noc`

![Sklep aplikacji SmartWAN - Noc](images/release-1.3.8/store-smartwan-night-pl.png)

`Repo Builder - Day`

![Repo Builder - Day](images/release-1.3.8/repo-builder-day-pl.png)

`Repo Builder - Noc`

![Repo Builder - Noc](images/release-1.3.8/repo-builder-night-pl.png)

### Dystrybucja
- `Installer`: instaluje aplikacje dla aktualnego uzytkownika Windows.
- `Portable`: samodzielna wersja EXE bez potrzeby instalacji Pythona.

### Klucz SSH + haslo do klucza
1. Otworz `Profile polaczen` i dodaj/edytuj profil.
2. Ustaw `Autoryzacja SSH` na `Klucz + haslo do klucza`.
3. Wybierz plik klucza i wpisz haslo.
4. Opcjonalnie: wlacz ssh-agent w Windows (instrukcja w aplikacji).

### Prywatnosc i bezpieczenstwo
- Ustawienia uzytkownika sa trzymane per konto Windows w `%APPDATA%\DockerControlCenter`.
- Klucze API i hasla SSH nie sa przechowywane w repozytorium.
- Sekrety sa zabezpieczane przez Windows DPAPI dla konkretnego uzytkownika.
- Publiczne repo nie zawiera prywatnych profili, sekretow, buildow ani lokalnego srodowiska.

### Najwazniejsze funkcje
- Zarzadzanie lokalnym Dockerem
- Wsparcie dla WSL / WSL2
- Profile SSH z kluczem, haslem do klucza lub haslem
- Auto-wykrywanie Balena OS (`balena ps` / `balena run`)
- Katalog 40+ popularnych obrazow, w tym lekkie opcje pod Raspberry Pi
- Asystent AI do edycji komend `docker run`
- Rozne tla dla motywow
- Muzyka w tle i futurystyczny interfejs
- Menu kontekstowe, logi, inspect i otwieranie linkow

### Przykladowe pliki danych
- `docker_connection_profiles.example.json`
- `%APPDATA%\DockerControlCenter\docker_connection_profiles.json`
- `%APPDATA%\DockerControlCenter\docker_control_center_secrets.json`

## Repository contents
- `docker-menager.ps` - main application source
- `DockerControlCenter.nsi` - NSIS installer script
- `backgrounds/` - theme background artwork
- `images/` - README screenshots
- `icon.ico` / `icon.png` - application icons
- `bg.mp3` - optional in-app background music

