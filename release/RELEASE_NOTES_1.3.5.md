# Docker Control Center v1.3.5

Docker Control Center 1.3.5 is the first public release after v1.1.1 that consolidates the large Windows, Linux, SSH, deployment-catalog, monitoring and AI-assistance work completed across the 1.2.x–1.3.x development builds.

## English

### Highlights

- **Windows + Linux desktop app** — Windows 10/11 support plus a native `.deb` package for Debian/Ubuntu/Linux Mint/MX Linux and other Debian-family systems.
- **Local Docker, WSL and remote hosts** — manage Docker Desktop, Docker inside WSL/WSL2, normal Linux Docker hosts and Balena OS devices over SSH.
- **Improved Docker Desktop stability** — local Docker connection handling was hardened for newer Docker Desktop versions on Windows 11.
- **Host recognition and health information** — better detection of Debian, Ubuntu, Balena OS, WSL and related Linux variants, with CPU/RAM information for connected hosts.
- **Container resource monitoring** — CPU and RAM usage for individual containers plus overall host/container load; CPU and RAM columns support three-state sorting (descending, ascending, neutral).
- **Container search** — live filtering while typing container names.
- **Project/network grouping** — containers can be grouped by project/Compose relationship or shared networks with collapsible groups. Each group header now has its own checkbox, so the whole group can be selected at once for bulk Start/Stop/Restart and other container actions.
- **More compact container table** — optimized WWW/link controls, narrower autostart column, movable column widths and better use of vertical space.
- **Persistent column layout** — manually adjusted column widths are saved and restored after restarting DCC; visible three-dot grips mark the draggable separators between columns.
- **Optional Magnet mode** — enabled by default; keeps the user-defined column proportions while automatically fitting the whole table to the current window width, including during live window resizing.
- **Improved port/link detection** — better detection and display of published addresses, IPs, web panels and exposed ports without clipping.
- **UI scaling** — `Ctrl + mouse wheel` zoom for the container area, improved resize behavior, scrollable dialogs, smaller minimum window size and full-screen/maximize support.
- **Opaque status area by default** — status text no longer blends with the background unless transparency is explicitly enabled.

### SSH profiles and remote-host workflow

- Added **SSH Agent** as an authentication mode.
- Added **Copy profile** for quickly cloning a connection profile and changing only selected fields such as IP/hostname.
- Added profile **Import / Export** both in the profiles dialog and the File menu.
- Imported profiles intentionally omit passwords/passphrases; key paths can be changed after moving a profile to another computer or OS.
- Added editable SSH key path on Windows and Linux.
- Improved direct SSH, tunnel and Balena command handling.
- Remote restart no longer reports a false error simply because the SSH session drops during reboot.
- After a requested host restart DCC performs non-blocking reconnect checks, shows restart/recovery status and refreshes containers when the host comes back.
- Automatic reconnect checks can be cancelled without freezing the main window.

### First-run setup and dependencies

- Added a first-run wizard on Linux.
- **Fixed Linux Docker Desktop local mode**: DCC now follows `DOCKER_HOST` and the active Docker CLI context, including `desktop-linux` and user sockets such as `~/.docker/desktop/docker-cli.sock`, instead of always forcing `/var/run/docker.sock`.
- DCC now distinguishes Docker Desktop/rootless user sockets from the system Docker socket. Docker-group re-login/relaunch logic is only used when the selected endpoint actually requires `/var/run/docker.sock` access.
- Linux Docker setup now detects the real desktop account instead of blindly using `root`; it prefers the original `sudo`/PolicyKit user and uses that account for Docker-group configuration and Docker installation setup.
- DCC now detects Docker Desktop for Linux separately from Docker Engine. If Docker Desktop is installed but stopped, **Connect local**, the first-run wizard and **Configure -> Dependencies** show that state explicitly and offer **Start Docker Desktop**.
- If Docker Desktop for Linux is not installed, DCC offers the official Docker Desktop installation page while keeping **Install Docker Engine** as a separate choice.
- The existing **Start Docker Desktop when DCC starts** setting now works on Linux too. DCC starts the per-user `docker-desktop` service and polls the local Docker endpoint in the background until it becomes available, instead of immediately showing another connection error while Docker Desktop is still starting.
- If Docker is already installed but the current Linux user has no daemon access, the first-run wizard can now add that user to the `docker` group through the system PolicyKit password prompt; DCC never reads or stores the password.
- DCC can detect a missing Docker Engine and offer installation on supported Debian-family distributions.
- Added `Configure -> Dependencies` for Docker/Docker Desktop and OpenSSH/SSH Agent checks and later installation.
- `Configure -> Dependencies` also exposes Docker-group repair on Linux and distinguishes missing group membership from a session that still needs sign-out/sign-in or a stopped Docker service.
- Local-mode errors now provide a direct path to install/start Docker when it is unavailable.
- Windows installer performs packaged-runtime checks and verifies required integration components.
- Linux package declares the Qt/XCB/OpenSSH/PolicyKit runtime dependencies needed by the desktop app.

### Application updates and settings

- Automatic update checks are enabled by default and can be disabled.
- Update notifications can be disabled independently.
- Added manual **Check for updates**.
- Fixed a Linux Qt crash that could occur when switching the application language from the open language menu; menu reconstruction is now deferred until the triggering menu signal has finished.
- Fixed the remaining language-switch crash on Linux MX/Xfce. DCC no longer clears and rebuilds the Qt menu bar after a language action; existing menus and actions are translated in place after the popup closes, so the language changes without terminating the application.
- Docker-group setup now shows a clear confirmed state after a successful membership change. DCC distinguishes between "group configured, re-login required" and "group active, Docker daemon unavailable" instead of leaving only disabled action buttons.
- If the account is already configured in the `docker` group but the running DCC process has not inherited that group yet, **Connect local** now offers **Restart DCC with Docker access**. On Linux this relaunches DCC through `sg docker`, avoiding the raw `/var/run/docker.sock: Permission denied` error and normally avoiding a full desktop sign-out.
- Linux now uses Linux-specific application/help descriptions: local **Docker Engine**, remote SSH/Balena hosts and `docker ps` are described directly, without Windows Docker Desktop / WSL instructions in the Linux UI.
- Fixed overlapping group-header captions in the container table. Group titles are now rendered only once by the interactive header control, with corrected spacing after the group checkbox.
- The README **Download Latest Version** buttons now link directly to the current Windows installer and Linux `.deb` assets instead of opening the release/repository page first.
- **Fixed Linux self-update authorization** — after downloading the `.deb`, DCC now stays open while `pkexec/apt` waits for the system password, clearly tells the user that a password prompt is required, and closes only after the installation finishes successfully.
- Update prompt supports update now / remind later / cancel behavior.
- Added **Reset application settings** while preserving connection profiles.
- Added a separate **Factory reset** with an explicit warning explaining that profiles, saved credentials, LLM settings and local DCC data will be removed while Docker-host data remains untouched.

### Deployment catalog / app store

- Added an application-store style deployment catalog with categories, descriptions, icons, project links, documentation and GitHub/source links.
- The permanent primary catalog is now **`https://github.com/hattimon/DCC`**.
- The installable manifest is **`dcc-catalog.json`** in the repository root.
- DCC refreshes the catalog asynchronously at application startup and again when the deployment catalog is opened.
- Catalog data is cached locally so the store remains usable during temporary GitHub/network failures.
- Users can add/remove extra catalog repositories while the main DCC repository remains protected as the primary source.
- Added manual **Refresh catalogs**.
- Added Vane (formerly Perplexica) and a much larger set of self-hosted, AI, automation, monitoring, administration, storage and media applications.
- Catalog Docker presets use `--pull always`, so moving tags such as `latest`/`main` fetch a fresh image before deployment.
- Manual/local-image configurations do not force a pull, preserving private/local images.

### Automated catalog maintenance

- Added scheduled GitHub Actions maintenance for existing catalog applications.
- Existing GitHub-backed apps can track upstream release/tag metadata.
- The app card can display the latest known upstream release.
- Added automated discovery of popular self-hosted/container repositories.
- Newly discovered projects are written only to `catalog/candidates.json` and proposed for review; they are **not** automatically made installable.
- This keeps automated discovery separate from trusted deployment commands and avoids publishing unsafe mounts/privileges without review.

### Manual deployment and Edit start

- Added a real **Manual configuration** mode for new containers.
- A new container no longer forces the first store preset (previously Agent Zero) to be selected.
- Users can type the image, name, host/container ports, additional parameters, command or a complete `docker run` command manually.
- Fixed `Configure -> Edit start` so the header identifies the actual selected container rather than showing a catalog preset.
- Background catalog refresh can no longer overwrite the edited container with the first catalog item.
- Existing container configuration reconstruction was expanded to preserve more real runtime settings:
  - restart policy
  - environment variables
  - bind mounts and named volumes
  - published ports
  - user and working directory
  - network mode
  - privileged/read-only/auto-remove flags
  - added/dropped capabilities
  - DNS and extra hosts
  - devices
  - CPU and memory limits
  - shared memory size
  - tmpfs mounts
  - labels
  - entrypoint and command
- Named Docker volumes remain named volumes instead of being reconstructed as `/var/lib/docker/volumes/...` bind mounts.

### Safer deployment and automatic repair

- Improved deterministic port-conflict detection against currently running containers.
- DCC can propose safe port/name corrections before deployment.
- Deployment runs through a progress window with clear **Success / Failure** state and localized messages.
- Failed deployments can be diagnosed and retried while preserving unrelated configuration.
- Optional AI-assisted repair can analyze a failed `docker run` command and propose a corrected command using current host/container/port context.
- Risky options such as privileged mode, host networking, devices, Docker socket mounts or host-root mounts remain visible and require explicit confirmation.

### AI / LLM providers

The LLM configuration now supports:

- Local Ollama
- OpenAI
- Anthropic Claude
- Google Gemini
- Groq
- Mistral AI
- OpenRouter
- DeepSeek
- xAI / Grok

Model lists can be detected/refreshed where supported, and provider credentials remain in the local secret store rather than the public repository.

### Screenshots

![Main window](https://raw.githubusercontent.com/hattimon/DCC/main/images/release-1.3.5/01-main-window.png)

![Manual container configuration](https://raw.githubusercontent.com/hattimon/DCC/main/images/release-1.3.5/02-manual-container-configuration.png)

![Edit existing container](https://raw.githubusercontent.com/hattimon/DCC/main/images/release-1.3.5/03-edit-existing-container.png)

![Catalog repositories](https://raw.githubusercontent.com/hattimon/DCC/main/images/release-1.3.5/04-catalog-repositories.png)

![Connection profiles](https://raw.githubusercontent.com/hattimon/DCC/main/images/release-1.3.5/05-connection-profiles.png)

![Dependencies](https://raw.githubusercontent.com/hattimon/DCC/main/images/release-1.3.5/06-dependencies.png)

![LLM providers](https://raw.githubusercontent.com/hattimon/DCC/main/images/release-1.3.5/07-llm-providers.png)

### Downloads

- **Windows installer:** `DockerControlCenter-Setup.exe`
- **Windows portable:** `DockerControlCenter-Portable.zip`
- **Debian / Ubuntu / MX Linux:** `DockerControlCenter_1.3.5_amd64.deb`
- **Catalog manifest:** `dcc-catalog.json`
- **Checksums:** `SHA256SUMS-1.3.5.txt`
- GitHub also provides automatic source-code ZIP and TAR archives for the tag.

---

## Polski

### Najważniejsze zmiany

- **Windows + Linux** — obsługa Windows 10/11 oraz natywny pakiet `.deb` dla Debian/Ubuntu/Linux Mint/MX Linux i innych systemów bazujących na Debianie.
- **Docker lokalny, WSL i hosty zdalne** — obsługa Docker Desktop, Dockera w WSL/WSL2, zwykłych hostów Linux oraz urządzeń Balena OS przez SSH.
- **Stabilniejsze połączenie z Docker Desktop** — poprawiono obsługę lokalnego Dockera z nowszym Docker Desktop na Windows 11.
- **Lepsze rozpoznawanie hosta** — Debian, Ubuntu, Balena OS, WSL i pokrewne systemy oraz informacje CPU/RAM hosta.
- **Monitoring zasobów kontenerów** — CPU i RAM dla każdego kontenera oraz ogólne obciążenie; kolumny CPU/RAM mają sortowanie malejąco, rosnąco i tryb neutralny.
- **Wyszukiwarka kontenerów** — filtrowanie listy już podczas wpisywania nazwy.
- **Grupowanie projektów i sieci** — kontenery mogą być grupowane wg projektu/Compose lub wspólnych sieci z rozwijanymi grupami. Każda belka grupy ma teraz własny checkbox, który zaznacza wszystkie kontenery w grupie do zbiorczych akcji Start/Stop/Restart i pozostałych operacji.
- **Bardziej kompaktowa tabela** — zoptymalizowane WWW/linki, węższy autostart, przesuwane szerokości kolumn i więcej miejsca na listę kontenerów.
- **Zapamiętywanie szerokości kolumn** — ręcznie ustawione szerokości są zapisywane i odtwarzane po ponownym uruchomieniu DCC; trzy pionowe kropki pokazują miejsca, w których można złapać separator kolumn.
- **Opcjonalny tryb Magnes** — domyślnie włączony; zachowuje ręcznie ustawione proporcje kolumn i automatycznie dopasowuje całą tabelę do szerokości okna podczas jego rozciągania lub zwężania.
- **Lepsze wykrywanie IP/portów/paneli WWW** — poprawione adresy wystawionych usług i brak ucinania portów.
- **Skalowanie UI** — `Ctrl + scroll` zmienia skalę obszaru kontenerów; poprawiono minimalny rozmiar okna, paski przewijania i pełny ekran/maksymalizację.
- **Nieprzezroczysty status domyślnie** — tekst statusu nie zlewa się z tłem, dopóki użytkownik sam nie włączy przezroczystości.

### Profile SSH i hosty zdalne

- Dodano logowanie przez **Agenta SSH**.
- Dodano **Kopiuj profil**, aby szybko zmienić np. tylko IP/host.
- Dodano **Import / Eksport profili** w oknie profili i w menu Plik.
- Eksport/import celowo nie przenosi haseł ani haseł do kluczy; po przeniesieniu profilu można wskazać nową ścieżkę klucza.
- Ścieżka klucza SSH jest edytowalna na Windows i Linux.
- Poprawiono Direct SSH, tunele TCP oraz komendy Balena.
- Restart hosta nie zgłasza już fałszywego błędu tylko dlatego, że SSH znika w trakcie restartu.
- Po restarcie DCC nie blokuje okna: w tle sprawdza odzyskanie połączenia, pokazuje stan restartu i automatycznie odświeża kontenery po powrocie hosta.
- Automatyczne próby odzyskania połączenia można anulować.

### Pierwsze uruchomienie i zależności

- Dodano kreator pierwszego uruchomienia na Linux.
- **Poprawiono lokalny Docker Desktop na Linuxie**: DCC korzysta teraz z `DOCKER_HOST` i aktywnego kontekstu Docker CLI, w tym `desktop-linux` oraz socketów użytkownika takich jak `~/.docker/desktop/docker-cli.sock`, zamiast zawsze wymuszać `/var/run/docker.sock`.
- DCC rozróżnia socket Docker Desktop/rootless od systemowego socketu Dockera. Logika grupy `docker` i ponownego uruchomienia sesji jest stosowana tylko wtedy, gdy wybrany endpoint rzeczywiście wymaga dostępu do `/var/run/docker.sock`.
- Konfiguracja Dockera na Linuxie wykrywa teraz rzeczywiste konto użytkownika pulpitu zamiast bezwarunkowo używać `root`; preferowany jest pierwotny użytkownik `sudo`/PolicyKit i to konto jest dodawane do grupy `docker`.
- DCC rozpoznaje teraz Docker Desktop dla Linux osobno od Docker Engine. Gdy Docker Desktop jest zainstalowany, ale wyłączony, **Połącz lokalnie**, kreator pierwszego uruchomienia i **Konfiguruj -> Zależności** pokazują ten stan i proponują **Uruchom Docker Desktop**.
- Gdy Docker Desktop dla Linux nie jest zainstalowany, DCC proponuje otwarcie oficjalnej strony instalacyjnej Docker Desktop, a **Zainstaluj Docker Engine** pozostaje osobną opcją.
- Ustawienie **Uruchamiaj Docker Desktop przy starcie DCC** działa teraz również na Linuxie. DCC uruchamia usługę użytkownika `docker-desktop` i w tle ponawia sprawdzanie lokalnego Dockera aż do uzyskania połączenia, zamiast od razu pokazywać kolejny błąd podczas startu Docker Desktop.
- Jeżeli Docker jest już zainstalowany, ale bieżący użytkownik Linux nie ma dostępu do demona, kreator może teraz dodać go do grupy `docker` przez systemowe okno PolicyKit. DCC nie odczytuje ani nie zapisuje hasła.
- DCC wykrywa brak Dockera i może zaproponować instalację Docker Engine na wspieranych systemach Debian-family.
- Dodano `Konfiguruj -> Zależności` do sprawdzania/instalacji Docker/Docker Desktop i OpenSSH/Agenta SSH.
- W `Konfiguruj -> Zależności` dodano również naprawę członkostwa w grupie Docker oraz rozróżnienie braku grupy od sesji wymagającej ponownego logowania albo niedziałającej usługi Docker.
- Przy braku lokalnego Dockera komunikat prowadzi bezpośrednio do instalacji/uruchomienia.
- Instalator Windows wykonuje test spakowanego runtime.
- Pakiet Linux deklaruje wymagane zależności Qt/XCB/OpenSSH/PolicyKit.

### Aktualizacje i ustawienia

- Automatyczne sprawdzanie aktualizacji jest domyślnie włączone i można je wyłączyć.
- Powiadomienia o aktualizacjach można wyłączyć osobno.
- Dodano ręczne **Sprawdź aktualizacje**.
- Poprawiono błąd Qt na Linuxie, który mógł zamknąć aplikację podczas zmiany języka z otwartego menu; przebudowa menu odbywa się teraz dopiero po zakończeniu obsługi kliknięcia.
- Usunięto pozostały crash przy zmianie języka na Linux MX/Xfce. DCC nie kasuje już i nie buduje od nowa paska menu Qt po wyborze języka; istniejące menu i akcje są tłumaczone w miejscu po zamknięciu popupu, dzięki czemu język zmienia się bez zamykania aplikacji.
- Konfiguracja grupy docker pokazuje teraz jednoznaczny stan potwierdzony po poprawnym dodaniu użytkownika. DCC rozróżnia stan „grupa skonfigurowana, wymagane ponowne logowanie” od „grupa aktywna, demon Docker niedostępny”, zamiast pozostawiać tylko nieaktywne przyciski.
- Jeżeli konto jest już dodane do grupy `docker`, ale uruchomiony proces DCC nie odziedziczył jeszcze tej grupy, **Połącz lokalnie** proponuje teraz **Uruchom DCC ponownie z dostępem do Docker**. Na Linux DCC uruchamia się ponownie przez `sg docker`, zamiast pokazywać surowy błąd `/var/run/docker.sock: Permission denied`; zwykle nie wymaga to pełnego wylogowania z pulpitu.
- Linux używa teraz własnych opisów aplikacji i pomocy: lokalny **Docker Engine**, zdalne hosty SSH/Balena i test `docker ps` są opisane bez instrukcji dotyczących Windows Docker Desktop / WSL.
- Poprawiono nachodzące na siebie nagłówki grup w tabeli kontenerów. Tytuł grupy jest teraz renderowany tylko raz przez interaktywny nagłówek, z poprawionym odstępem za checkboxem grupy.
- Przyciski **Download Latest Version** w README prowadzą teraz bezpośrednio do aktualnego instalatora Windows i pakietu Linux `.deb`, zamiast najpierw otwierać stronę release/repozytorium.
- **Poprawiono autoupdate na Linuxie** — po pobraniu `.deb` DCC pozostaje uruchomiony, gdy `pkexec/apt` czeka na systemowe hasło, jasno informuje o konieczności jego wpisania i zamyka się dopiero po poprawnym zakończeniu instalacji.
- Okno aktualizacji obsługuje aktualizację teraz / przypomnij później / anuluj.
- Dodano **Reset ustawień aplikacji** bez usuwania profili połączeń.
- Dodano osobny **Reset do ustawień fabrycznych** z ostrzeżeniem, które dokładnie opisuje usuwane profile, dane logowania, konfigurację LLM i dane DCC. Dane Dockera na hostach nie są usuwane.

### Katalog wdrożeń / sklep aplikacji

- Dodano katalog aplikacji w stylu sklepu: kategorie, opisy, ikonki, link do projektu, dokumentacji i GitHuba/źródła.
- Stałym głównym repozytorium katalogu jest **`https://github.com/hattimon/DCC`**.
- Instalowalny manifest znajduje się w **`dcc-catalog.json`** w katalogu głównym repo.
- DCC odświeża katalog w tle przy starcie aplikacji oraz ponownie po wejściu do katalogu wdrożeń.
- Katalog jest cache'owany lokalnie, więc działa również przy chwilowej niedostępności GitHuba/sieci.
- Można dodawać i usuwać dodatkowe repozytoria katalogów; głównego repo DCC nie można przypadkowo usunąć.
- Dodano ręczne **Odśwież katalogi**.
- Dodano Vane (dawniej Perplexica) i znacznie większy zestaw aplikacji self-hosted, AI, automatyzacji, monitoringu, administracji, storage i media.
- Presety katalogu dla Dockera używają `--pull always`, dzięki czemu tagi `latest`/`main` pobierają świeży obraz przed wdrożeniem.
- Tryb ręczny i lokalne/prywatne obrazy nie wymuszają pobierania.

### Automatyczne utrzymywanie katalogu

- Dodano cykliczny GitHub Actions do sprawdzania istniejących aplikacji katalogu.
- Wpisy GitHub mogą otrzymywać informacje o najnowszym release/tagu upstream.
- Karta aplikacji może pokazywać najnowszą znaną wersję upstream.
- Dodano automatyczne wyszukiwanie popularnych projektów self-hosted/kontenerowych.
- Nowo znalezione projekty trafiają wyłącznie do `catalog/candidates.json` do przeglądu i **nie są automatycznie publikowane jako instalowalne**.
- Dzięki temu automat nie publikuje bez kontroli komend z ryzykownymi mountami/uprawnieniami.

### Ręczna instalacja i Edytuj start

- Dodano prawdziwy tryb **Konfiguracja ręczna**.
- Nowy kontener nie ma już automatycznie wybranego pierwszego presetu (wcześniej Agent Zero).
- Można ręcznie wpisać obraz, nazwę, port hosta/kontenera, dodatkowe parametry, komendę lub pełny `docker run`.
- Poprawiono `Konfiguruj -> Edytuj start`: nagłówek pokazuje faktycznie edytowany kontener.
- Odświeżenie katalogu w tle nie może już nadpisać formularza pierwszym presetem.
- Rozszerzono odtwarzanie prawdziwej konfiguracji istniejącego kontenera o:
  - restart policy
  - zmienne środowiskowe
  - bind mounty i named volumes
  - porty
  - user/workdir
  - network mode
  - privileged/read-only/auto-remove
  - capabilities
  - DNS/extra hosts
  - devices
  - limity CPU/RAM
  - shm-size
  - tmpfs
  - labels
  - entrypoint i command
- Nazwane wolumeny Dockera pozostają named volumes, zamiast zmieniać się w bind mount `/var/lib/docker/volumes/...`.

### Bezpieczniejsze wdrażanie i automatyczna naprawa

- Rozbudowano deterministyczne wykrywanie konfliktów portów z aktualnymi kontenerami.
- DCC może zaproponować bezpieczne korekty portu/nazwy przed instalacją.
- Wdrożenie ma czytelne okno postępu i jednoznaczny stan **Sukces / Błąd**, zgodny z językiem aplikacji.
- Nieudane wdrożenie może zostać przeanalizowane i ponowione bez utraty niezwiązanej konfiguracji.
- Opcjonalna naprawa AI analizuje błąd `docker run` razem z aktualnym kontekstem hosta, portów i kontenerów i proponuje poprawioną komendę.
- Ryzykowne opcje, np. privileged, host networking, devices, Docker socket czy mount katalogu root, nadal wymagają jawnego potwierdzenia.

### AI / dostawcy LLM

Konfiguracja LLM obsługuje teraz:

- lokalną Ollama
- OpenAI
- Anthropic Claude
- Google Gemini
- Groq
- Mistral AI
- OpenRouter
- DeepSeek
- xAI / Grok

Lista modeli może być wykrywana/odświeżana tam, gdzie dostawca to wspiera, a klucze pozostają w lokalnym magazynie sekretów i nie trafiają do publicznego repozytorium.

### Zrzuty ekranu

![Główne okno](https://raw.githubusercontent.com/hattimon/DCC/main/images/release-1.3.5/01-main-window.png)

![Ręczna konfiguracja kontenera](https://raw.githubusercontent.com/hattimon/DCC/main/images/release-1.3.5/02-manual-container-configuration.png)

![Edycja istniejącego kontenera](https://raw.githubusercontent.com/hattimon/DCC/main/images/release-1.3.5/03-edit-existing-container.png)

![Repozytoria katalogów](https://raw.githubusercontent.com/hattimon/DCC/main/images/release-1.3.5/04-catalog-repositories.png)

![Profile połączeń](https://raw.githubusercontent.com/hattimon/DCC/main/images/release-1.3.5/05-connection-profiles.png)

![Zależności](https://raw.githubusercontent.com/hattimon/DCC/main/images/release-1.3.5/06-dependencies.png)

![Dostawcy LLM](https://raw.githubusercontent.com/hattimon/DCC/main/images/release-1.3.5/07-llm-providers.png)

### Pliki do pobrania

- **Windows instalator:** `DockerControlCenter-Setup.exe`
- **Windows portable:** `DockerControlCenter-Portable.zip`
- **Debian / Ubuntu / MX Linux:** `DockerControlCenter_1.3.5_amd64.deb`
- **Manifest katalogu aplikacji:** `dcc-catalog.json`
- **Sumy kontrolne:** `SHA256SUMS-1.3.5.txt`
- GitHub automatycznie udostępnia również archiwa ZIP/TAR kodu źródłowego dla tagu.

## Validation / Walidacja

- Windows packaged runtime `--self-check`: **OK**
- Linux packaged runtime `--self-check`: **OK**
- Automated Python regression tests: **34/34 passed**
- Installed local Windows version after update: **1.3.5**
