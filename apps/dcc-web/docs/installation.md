# Install DCC Web 0.3.2

DCC Web runs on Windows, macOS and Debian-family Linux. Choose the Docker Compose installer or run the service directly with Python. The App Store installer in DCC Desktop remains available as well.

## Docker Compose installer (Windows, macOS, Linux)

Requirements: Docker Engine or Docker Desktop with Docker Compose v2, and Python 3.12 for the small port-scanning installer.

1. Download and extract [DCC-Web-0.3.2-source.zip](https://github.com/hattimon/DCC/releases/download/dcc-web-v0.3.2/DCC-Web-0.3.2-source.zip).
2. Open a terminal in the extracted `DCC-Web-0.3.2` directory.
3. Run the installer:

   ```powershell
   py -3.12 apps/dcc-web/install.py
   ```

   On macOS or Linux, run `python3 apps/dcc-web/install.py`.

Use a local Docker context (Docker Desktop or a local Docker Engine); the script rejects remote Docker endpoints because it publishes a localhost-only address. The installer checks published TCP host ports reported by Docker and tests local port availability. It uses `8789` when free; if that port is occupied, it scans `8790` through `8888`. The selected port is saved under the current user's application configuration. If a race claims the port while the container starts, the installer retries with another free port. It then pulls the published multi-architecture image, prompts you to create the first administrator, starts the service, and prints the exact URL to open.

The container listens on loopback only and keeps application data in the named `dcc_web_data` volume. The installer leaves an existing container named `dcc-web-standalone` untouched. Docker must be running and the current user must be allowed to use it. The container needs access to the Docker Engine socket so DCC Web can manage containers; socket access grants substantial control over that Docker host.

## Install from the DCC App Store

In DCC Desktop 1.3.11 or newer, open **App Store → DCC**, select **DCC Web**, and choose **Install**. DCC checks Docker-published and locally bindable ports, prefers 8789, and selects another free port when required. Open the address shown after installation. A fresh Store install creates the `admin` account with a strong random password; the installation result reveals it and the container logs retain a copy. Change the password after signing in. This route also supports installing to the currently selected Docker profile.

## Run natively with Python

This mode works on Windows, macOS and Linux and uses the Docker CLI/context configured for the current OS user. It requires Python 3.12 and Docker CLI access. Extract the source ZIP or clone the repository, then run from its root:

```powershell
py -3.12 -m venv .venv-dcc-web
.venv-dcc-web\Scripts\python.exe -m pip install -r apps/dcc-web/requirements.txt
.venv-dcc-web\Scripts\python.exe apps/dcc-web/web.py --host 127.0.0.1 --port 8789
```

On macOS or Linux, replace the commands with:

```bash
python3 -m venv .venv-dcc-web
.venv-dcc-web/bin/python -m pip install -r apps/dcc-web/requirements.txt
.venv-dcc-web/bin/python apps/dcc-web/web.py --host 127.0.0.1 --port 8789
```

For a native install, choose a free port yourself if 8789 is already in use. Open `http://127.0.0.1:8789` (or the port you selected), then create the administrator account. DCC Web stores its state in `~/.dcc-web` by default; use `--data PATH` to choose another directory.

## Access and security

The Compose installer is local-only by default. Containerized Web 0.3.2 includes optional DCC Remote Access with zrok. After updating the existing Web container through DCC Container Updater, reload the same panel address. Open **Settings → Administration and security → Panel access and HTTPS (TLS) → Remote Internet Access**. The tunnel starts disabled, and activation requires administrator MFA. The local Docker profile must have **Install applications** permission. [Remote Access setup](https://github.com/hattimon/DCC/blob/dcc-web-v0.3.2/apps/dcc-remote-access/README.md)

For optional local HTTPS, sign in and open **Settings → Administration and security → Local and public domains**. Enter the host's private IP (recommended) or a local DNS name, save it, then open **HTTPS access → Enable local HTTPS**. The managed Caddy extension keeps the current HTTP address and data volume, binds only to that private/loopback address, and picks a free host port from 9443–9499. Open the displayed HTTPS address once, download the local CA certificate and install/trust it on the client device. Public HTTPS remains a separate option requiring a domain and reachable ports 80/443.

---

# Instalacja DCC Web 0.3.2

DCC Web działa w systemach Windows, macOS i Linux z rodziny Debian. Wybierz instalator Docker Compose albo uruchom panel bezpośrednio przez Python. Aplikację można też instalować ze Sklepu DCC Desktop.

## Instalator Docker Compose (Windows, macOS, Linux)

Wymagania: Docker Engine lub Docker Desktop z Docker Compose v2 oraz Python 3.12 do skanowania portów.

1. Pobierz i rozpakuj [DCC-Web-0.3.2-source.zip](https://github.com/hattimon/DCC/releases/download/dcc-web-v0.3.2/DCC-Web-0.3.2-source.zip).
2. Otwórz terminal w rozpakowanym katalogu `DCC-Web-0.3.2`.
3. Uruchom instalator:

   ```powershell
   py -3.12 apps/dcc-web/install.py
   ```

   W macOS lub Linux uruchom `python3 apps/dcc-web/install.py`.

Wybierz lokalny kontekst Docker (Docker Desktop lub lokalny Docker Engine); skrypt odrzuca zdalne endpointy, bo wystawia adres dostępny tylko przez localhost. Instalator odczytuje opublikowane porty TCP kontenerów Dockera i sprawdza lokalną możliwość nasłuchu. Gdy port `8789` jest wolny, używa go; w przeciwnym razie skanuje zakres `8790–8888`. Wybrany port zapisuje w konfiguracji bieżącego użytkownika. Jeśli port zostanie zajęty podczas uruchamiania kontenera, instalator ponawia próbę z kolejnym wolnym portem. Następnie pobiera wieloarchitekturowy obraz, prosi o utworzenie pierwszego administratora, uruchamia panel i wyświetla dokładny adres.

Kontener nasłuchuje tylko lokalnie, a dane przechowuje w wolumenie `dcc_web_data`. Instalator nie modyfikuje istniejącego kontenera `dcc-web-standalone`. Docker musi działać, a bieżący użytkownik musi mieć do niego dostęp. Panel potrzebuje dostępu do socketu Docker Engine, aby zarządzać kontenerami; taki socket daje szeroką kontrolę nad hostem Dockera.

## Instalacja ze Sklepu DCC

W DCC Desktop 1.3.11 lub nowszym otwórz **Sklep aplikacji → DCC**, wybierz **DCC Web** i kliknij **Zainstaluj**. DCC sprawdza porty kontenerów oraz możliwość lokalnego nasłuchu, wybiera 8789 lub kolejny wolny port. Po instalacji otwórz wyświetlony adres. Ta metoda obsługuje również instalację na aktualnie wybranym profilu Docker.

## Natywne uruchomienie przez Python

Ten tryb działa w Windows, macOS i Linux oraz używa Docker CLI i kontekstu bieżącego użytkownika. Wymaga Python 3.12 i dostępu do Docker CLI. Rozpakuj archiwum źródłowe albo sklonuj repozytorium, a następnie uruchom polecenia z katalogu głównego:

```powershell
py -3.12 -m venv .venv-dcc-web
.venv-dcc-web\Scripts\python.exe -m pip install -r apps/dcc-web/requirements.txt
.venv-dcc-web\Scripts\python.exe apps/dcc-web/web.py --host 127.0.0.1 --port 8789
```

W macOS lub Linux użyj:

```bash
python3 -m venv .venv-dcc-web
.venv-dcc-web/bin/python -m pip install -r apps/dcc-web/requirements.txt
.venv-dcc-web/bin/python apps/dcc-web/web.py --host 127.0.0.1 --port 8789
```

Przy instalacji natywnej wybierz samodzielnie inny wolny port, jeśli 8789 jest zajęty. Otwórz `http://127.0.0.1:8789` (lub wybrany port) i utwórz konto administratora. Domyślne dane panelu są zapisywane w `~/.dcc-web`; parametr `--data PATH` pozwala wskazać inny katalog.

## Dostęp i bezpieczeństwo

Instalator Compose wystawia panel tylko lokalnie. Kontenerowa wersja 0.3.2 zawiera opcjonalny DCC Remote Access z zrok. Po aktualizacji istniejącego kontenera przez DCC Container Updater odśwież panel pod dotychczasowym adresem. Otwórz **Ustawienia → Administracja i bezpieczeństwo → Dostęp do panelu i HTTPS (TLS) → Zdalny dostęp przez Internet**. Tunel jest domyślnie wyłączony, a aktywacja wymaga MFA administratora. Lokalny profil Dockera musi mieć uprawnienie **Instalowanie aplikacji**. [Konfiguracja Remote Access](https://github.com/hattimon/DCC/blob/dcc-web-v0.3.2/apps/dcc-remote-access/README.pl.md)

Lokalne HTTPS włączysz w **Ustawienia → Administracja i bezpieczeństwo → Domena lokalna i publiczna**. Podaj prywatny adres IP hosta (zalecane) albo nazwę z lokalnego DNS, zapisz ustawienia i wybierz **Dostęp HTTPS → Włącz lokalne HTTPS**. Zarządzane rozszerzenie Caddy zachowuje obecny adres HTTP i wolumen danych, wiąże port tylko z tym prywatnym/loopback adresem oraz wybiera wolny port z zakresu 9443–9499. Otwórz wyświetlony adres HTTPS, pobierz lokalny certyfikat CA i zainstaluj/zaufaj mu na urządzeniu klienckim. Publiczne HTTPS jest osobną opcją wymagającą domeny oraz osiągalnych portów 80/443.
