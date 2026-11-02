// Only authored UI strings/template fragments are translated. Interpolated Docker data is preserved.
let language='EN';
const pairs=`
Postęp instalacji|Installation progress
Instalacja trwa…|Installation in progress…
Sprawdzanie konfiguracji|Checking configuration
Pobieranie obrazu|Pulling image
Tworzenie kontenera|Creating container
Uruchamianie i kontrola stanu|Starting and checking health
Odczyt logów i danych dostępowych|Reading logs and access details
Instalacja zakończona|Installation completed
Instalacja nie powiodła się|Installation failed
Kopiuj logi|Copy logs
Pobierz logi|Download logs
Pokaż dane dostępowe|Show access details
Wykryj dane dostępowe|Detect access details
Dane dostępowe wykryte w logach|Access details detected in logs
Nie wykryto gotowych danych logowania. Utwórz konto w aplikacji przy pierwszym uruchomieniu.|No ready-made credentials were detected. Create an account in the application on first launch.
Zamknięcie okna nie przerywa instalacji. Postęp można ponownie otworzyć w sklepie.|Closing this window does not cancel installation. Reopen progress from the store.
Kontener został utworzony. Sprawdź jego panel i stan uruchomienia.|The container was created. Check its panel and startup status.
Brak zapisanej instalacji|No saved installation
Kliknij, aby skopiować pełną ścieżkę obrazu|Click to copy the full image reference
Zaznacz grupę|Select group
Grupuj|Group by
Projekty|Projects
Projekt|Project
Lista płaska|Flat list
Samodzielne kontenery|Standalone containers
Bez sieci|No network
kontenerów|containers
uruchomionych|running
Zaznacz jeden kontener|Select one container
Brak uprawnienia profilu|Profile permission required
Włącz zarządzanie kontenerami|Enable container management
Profil zezwala na odczyt, ale zarządzanie kontenerami jest wyłączone.|This profile allows reading, but container management is disabled.
Profil zezwala na odczyt, ale zarządzanie kontenerami jest wyłączone. Możesz włączyć start, stop, restart, pauzę i edycję konfiguracji dla tego profilu.|This profile allows reading, but container management is disabled. You can enable start, stop, restart, pause and configuration editing for this profile.
Poproś administratora o uprawnienie containers.write.|Ask an administrator to enable containers.write.
Niektóre operacje nie powiodły się.|Some operations failed.
Wynik operacji zbiorczej|Bulk operation results
Infrastruktura hosta Docker|Docker host infrastructure
Odczytywanie infrastruktury…|Reading infrastructure…
Nie udało się odczytać infrastruktury hosta Docker.|Could not read Docker host infrastructure.
Aktywny profil|Active profile
Język|Language
Dokumentacja|Documentation
Wyloguj|Sign out
Twoje profile. Twoje dane.|Your profiles. Your data.
Sklep|Store
Terminal hosta|Host terminal
Maksymalna liczba sesji terminala|Maximum terminal sessions
Sprawdzaj aktualizacje panelu przy odświeżaniu|Check panel updates on refresh
Nowa zakładka|New tab
Zamknij zakładkę|Close tab
Połącz|Connect
Rozłącz|Disconnect
Kopiuj|Copy
Otwórz kolejne okno|Open another window
Włącz terminal dla tego profilu|Enable terminal for this profile
Połączenie z hostem…|Connecting to host…
Sesja terminala zakończona.|Terminal session ended.
Wpisywane polecenia działają na wybranym hoście.|Commands run on the selected host.
Terminal wymaga osobnego uprawnienia host.exec.|Terminal requires the separate host.exec permission.
Terminal|Terminal
Wszystkie|All
Zainstalowane|Installed
Zainstalowana|Installed
Niezainstalowana|Not installed
Przegląd|Overview
Kontenery|Containers
Kontener|Container
Uruchomione|Running
Uruchomiony|Running
Zatrzymane|Stopped
Zatrzymany|Stopped
Wstrzymane|Paused
Wstrzymany|Paused
Utworzony|Created
Zdrowy|Healthy
Nieznany|Unknown
Sukces|Success
Błąd|Error
Logi|Logs
Monitoring|Monitoring
Obrazy|Images
Obrazy Docker|Docker images
Wolumeny|Volumes
Sieć hosta|Host network
Sieci|Networks
Sieć|Network
Sklep aplikacji|App Store
Profile|Profiles
Profile połączeń|Connection profiles
Dziennik operacji|Audit log
Asystent AI|AI assistant
Asystent konfiguracji AI|AI configuration assistant
Ustawienia|Settings
Motywy|Themes
Nazwa|Name
Stan|State
Obraz|Image
CPU|CPU
Pamięć|Memory
Akcje|Actions
Porty / panele|Ports / panels
Porty|Ports
Dostępny port|Available port
Brak zmian konfiguracji|No configuration changes
Polityka restartu|Restart policy
Montowania i pozostałe ustawienia są zachowywane. Zmiana obrazu jest osobną operacją aktualizacji.|Mounts and other settings are retained. Image updates are a separate operation.
Porty — [IP:]HOST:CONTAINER/tcp lub /udp, po jednym na linię|Ports — [IP:]HOST:CONTAINER/tcp or /udp, one per line
Polecenie silnika (docker / balena / balena-engine, opcjonalnie)|Engine CLI (docker / balena / balena-engine, optional)
Port hosta|Host port
Port kontenera|Container port
Nowy kontener|New container
Uruchom|Start
Zatrzymaj|Stop
Pauza|Pause
Wznów|Resume
Więcej operacji|More actions
Operacje zaznaczonych|Selected actions
Zaznacz wszystkie|Select all
Zaznacz|Select
zaznaczonych|selected
Zaznaczone:|Selected:
Zaznacz kontenery|Select containers
Cykl życia|Lifecycle
Cykl życia kontenerów|Container lifecycle
Konfiguracja|Configuration
Diagnostyka|Diagnostics
Odnośniki i dane|Links and data
Aktualizacje i usuwanie|Updates and removal
Operacje kontenera|Container actions
Operacja|Operation
Operacje|Actions
Edytuj|Edit
Edytuj konfigurację startu|Edit startup configuration
Włącz autostart|Enable autostart
Wyłącz autostart|Disable autostart
Polecenie w kontenerze|Run command in container
Polecenie wewnątrz kontenera|Command inside container
Szczegóły|Details
Szczegóły konfiguracji|Configuration details
Szczegóły i konfiguracja|Details and configuration
Szczegóły zasobu|Resource details
Adresy paneli / porty|Panel addresses / ports
Kopiuj adres panelu|Copy panel address
Kopiuj szczegóły|Copy details
Kopiuj porty|Copy ports
Kopiuj sieci|Copy networks
Kopiuj dane|Copy data
Zaznacz i skopiuj|Select and copy
Skopiowano do schowka|Copied to clipboard
Sprawdź aktualizację obrazu|Check image update
Aktualizuj bezpiecznie obraz|Safely update image
Usuń kontener — zachowaj wolumeny|Remove container — retain volumes
Usuń kontenery|Remove containers
Usuń|Remove
Wynik aktualizacji|Update result
Wynik polecenia|Command output
Komenda|Command
Konfiguracja startu kontenera|Container startup configuration
Nowa komenda (opcjonalnie)|New command (optional)
Użytkownik kontenera (opcjonalnie)|Container user (optional)
Katalog roboczy (opcjonalnie)|Working directory (optional)
Zmienne do zmiany — pozostałe zostaną zachowane|Environment changes — other values are retained
Wymagana postać KEY=value|Use KEY=value format
Adresy HTTP/HTTPS są wyznaczane z opublikowanych portów TCP. Usługi inne niż WWW mogą nie obsługiwać przeglądarki.|HTTP/HTTPS addresses are inferred from published TCP ports. Non-web services may not open in a browser.
Operacje wymagają odpowiednich uprawnień profilu. Wolumeny nie są automatycznie usuwane.|Actions require profile permissions. Volumes are not removed automatically.
Sekrety środowiska są maskowane. Porty, montowania, healthcheck i konfiguracja pochodzą z Docker inspect.|Environment secrets are masked. Ports, mounts, health checks and configuration come from Docker inspect.
Polecenie działa wewnątrz wybranego kontenera. Docker socket lub uprzywilejowany kontener może zapewniać dostęp do hosta.|The command runs inside the selected container. A Docker socket or privileged container may provide host access.
Kontener zostanie odtworzony z zachowaniem konfiguracji i montowań przez istniejący bezpieczny updater DCC. Usługi Compose i sam Updater wymagają ich własnej ścieżki aktualizacji.|The existing DCC updater recreates the container while preserving configuration and mounts. Compose services and the Updater itself require their own update path.
Odtwórz kontener z nową konfiguracją. Montowania i pozostałe ustawienia zostaną zachowane.|Recreate the container with the new configuration. Mounts and other settings are retained.
Pełna kontrola cyklu życia — z zachowaniem danych.|Container lifecycle control while retaining persistent data.
Szukaj kontenera|Search containers
Szukaj nazwy lub obrazu…|Search name or image…
Filtr stanu|State filter
Wszystkie stany|All states
Twoje środowisko Docker w jednym miejscu|Your Docker environment in one place
Wszystkie w tym profilu|All in this profile
zatrzymanych|stopped
rdzeni hosta|host cores
Użycie kontenerów|Container usage
kontenerów w profilu|containers in this profile
kontenerów. Dane w wolumenach pozostaną zachowane.|containers. Volume data is retained.
kontenerów|containers
Zobacz wszystkie →|View all →
Ostatnie operacje|Recent actions
Dziennik →|Audit log →
Użycie zasobów|Resource usage
Bieżąca historia|Recorded history
Brak pomiaru|No measurement
Historia użycia CPU|CPU history
Historia użycia pamięci|Memory history
Pamięć (MiB)|Memory (MiB)
Szczegóły hosta|Host details
Architektura|Architecture
Architektury|Architectures
Sterownik|Driver
Wersja Engine|Engine version
Pamięć hosta|Host memory
Czas|Time
Wynik|Result
Logi i diagnostyka|Logs and diagnostics
Bieżący strumień zdarzeń z wybranego kontenera.|Current events from the selected container.
Automatyczne odświeżanie, wyszukiwanie i pobieranie logów.|Automatic refresh, search and log downloads.
Brak kontenerów w tym profilu.|No containers in this profile.
Szukaj w logach|Search logs
Szukaj w logach…|Search logs…
Liczba linii|Line count
Na żywo|Live
Pobierz .log|Download .log
Wyjście kontenera|Container output
Ładowanie logów…|Loading logs…
Ładowanie…|Loading…
linii|lines
CPU, pamięć, sieć i I/O. Historia obejmuje zebrane pomiary tego profilu.|CPU, memory, network and I/O. History contains measurements collected for this profile.
CPU kontenerów (%)|Container CPU (%)
Aktualne zasoby|Current resources
pomiarów|measurements
Dysk I/O|Disk I/O
Procesy|Processes
Wcześniej|Earlier
Teraz|Now
Wykres pojawi się po zebraniu co najmniej dwóch pomiarów|A chart appears after at least two measurements
Lokalne obrazy, tagi i pobieranie z rejestrów.|Local images, tags and registry downloads.
Repozytorium|Repository
Identyfikator|Identifier
Utworzony|Created
Rozmiar|Size
Pobierz obraz|Pull image
Obraz, np. alpine:3.22|Image, e.g. alpine:3.22
Szukaj zasobu…|Search resources…
Szukaj zasobu|Search resources
Nowy tag obrazu|New image tag
Docelowy tag|Destination tag
Nowy wolumen|New volume
Nazwa wolumenu|Volume name
Zakres|Scope
Nowa sieć|New network
Nazwa sieci bridge|Bridge network name
Połączenia kontenerów i szczegóły sieci Docker.|Container connectivity and Docker network details.
Trwałe dane kontenerów. Usuwanie wymaga dodatkowego potwierdzenia.|Persistent container data. Deletion requires additional confirmation.
Trwałe dane tego wolumenu zostaną bezpowrotnie usunięte. Wolumen używany przez kontener nie może być usunięty.|This volume's persistent data will be permanently deleted. Attached volumes cannot be removed.
Wybrany zasób zostanie usunięty. Wykorzystywane zasoby mogą blokować tę operację.|The selected resource will be removed. Resources in use can block this operation.
Przygotuj projekt Compose|Prepare Compose project
Projekty wykryte na wybranym hoście Docker.|Projects detected on the selected Docker host.
Up i Pull mogą zmienić obrazy usług. Down nie usuwa wolumenów. Konfiguracja i logi są dostępne bez uruchamiania projektu.|Up and Pull may change service images. Down retains volumes. Configuration and logs are available without starting the project.
Projekt|Project
Pliki konfiguracji|Configuration files
Zarządzaj →|Manage →
Nazwa projektu|Project name
Plik Compose YAML|Compose YAML file
Plik zostanie zapisany i zweryfikowany przez docker compose config. Uruchomienie projektu jest osobną, potwierdzaną operacją. Ścieżki montowań muszą być dostępne na wybranym hoście Docker.|The file is saved and validated by docker compose config. Starting the project requires separate confirmation. Mount paths must exist on the selected Docker host.
Zapisz i zweryfikuj dostarczony plik Compose.|Save and validate the supplied Compose file.
Projekt zweryfikowany|Project validated
Zapisany plik:|Saved file:
Uruchom ten zapisany projekt poleceniem Docker Compose albo wybierz go z listy przygotowanych projektów.|Start this saved project with Docker Compose or select it from the prepared project list.
Status usług|Service status
Sprawdź konfigurację|Check configuration
Logi projektu|Project logs
Uruchom / zastosuj konfigurację|Start / apply configuration
Pobierz obrazy|Pull images
Zatrzymaj i usuń kontenery projektu|Stop and remove project containers
Wynik Compose|Compose result
w wybranym projekcie. Wolumeny nie będą automatycznie usuwane.|in the selected project. Volumes are retained.
Operacje panelu i klientów MCP — bez zapisywania sekretów.|Panel and MCP client actions, without recording secrets.
Użytkownik|User
Cel|Target
Jeden katalog dla DCC Desktop i Web. Wybierz, sprawdź, zainstaluj.|One catalog for DCC Desktop and Web. Choose, review, install.
Katalogi|Catalogs
Odśwież katalogi|Refresh catalogs
Szukaj obrazu, opisu lub nazwy…|Search image, description or name…
Szukaj aplikacji|Search applications
aplikacji|applications
aktywnych źródeł|active sources
Wybierz aplikację|Choose an application
Przejrzyj katalog lub zmień filtr.|Browse the catalog or change the filter.
Zainstalowana na tym hoście|Installed on this host
Odinstaluj|Uninstall
Zainstaluj|Install
Najważniejsze funkcje|Key features
Obraz Docker|Docker image
Dowolna|Any
Porty host → kontener|Host → container ports
Nie wymaga|Not required
Silniki|Engines
RAM minimum|Minimum RAM
Nie podano|Not specified
Dane trwałe|Persistent data
Wolumeny / montowania — sprawdź konfigurację|Volumes / mounts — review configuration
Według konfiguracji|According to configuration
Ta aplikacja korzysta z Docker socket i może uzyskać uprawnienia administratora hosta.|This application uses a Docker socket and can gain host administrator access.
Ważne uwagi i wymagania|Important notes and requirements
Zbuduj obraz ze źródeł|Build image from source
Dokumentacja|Documentation
Strona|Website
Katalog jest dostępny z lokalnego cache. Nie udało się potwierdzić stanu instalacji — sprawdź połączenie Docker.|The cached catalog is available. Installation state could not be verified; check the Docker connection.
Brak aplikacji dla wybranego filtra.|No applications match this filter.
Sprawdzanie katalogów…|Checking catalogs…
Katalogi odświeżone. Niedostępne źródła korzystają z cache.|Catalogs refreshed. Unavailable sources use cached data.
Instalowanie jest wyłączone w tym profilu|Installation is disabled for this profile
Profil ma domyślnie tylko odczyt. Instalacja wymaga osobnej zgody administratora w Profile / Uprawnienia. To ograniczenie uprawnień, a nie kontenera testowego.|Profiles are read-only by default. An administrator must enable installation in Profiles / Permissions. This is a permission restriction, not a test-container restriction.
Otwórz uprawnienia profilu|Open profile permissions
Zezwól na instalowanie w tym profilu|Allow installation on this profile
Nazwa kontenera|Container name
Automatycznie wybierz dostępny port przy konflikcie|Automatically choose an available port on conflict
Zmienne środowiskowe — jedna KEY=value na linię|Environment variables — one KEY=value per line
Opcje kontenera — montowania, sieć, limity i restart|Container options — mounts, network, limits and restart
Sprawdź porty i trwałe dane. Docker socket daje dostęp administratora hosta. Instalacja wymaga osobnego potwierdzenia.|Review ports and persistent data. Docker socket access grants host administration. Installation requires separate confirmation.
Wybrany port nie koliduje z opublikowanymi portami Docker.|The selected port does not conflict with published Docker ports.
Każda zmienna wymaga postaci KEY=value|Each variable must use KEY=value format
Podgląd instalacji|Installation preview
Akceptuję dostęp do Docker socket i uprawnienia administratora hosta.|I accept Docker socket access and host administration privileges.
Sprawdziłem montowania i sposób przechowywania danych trwałych.|I reviewed mounts and persistent data storage.
Akceptuję dodatkowe uprawnienia, urządzenia lub capabilities kontenera.|I accept additional container privileges, devices or capabilities.
Zapewniłem wymagane usługi zależne.|I provided the required dependent services.
Instalacja rozpocznie się dopiero po potwierdzeniu. Wolumeny nie są automatycznie usuwane.|Installation starts only after confirmation. Volumes are not removed automatically.
Aplikacja została zainstalowana|Application installed
Główny katalog DCC jest stałym źródłem. Błędne odświeżenie nie usuwa ostatniej poprawnej zawartości.|The main DCC catalog is permanent. Failed refreshes retain the last valid contents.
Oficjalny katalog DCC|Official DCC catalog
wpisów|entries
Kopia dołączona do aplikacji|Bundled catalog copy
Zawartość|Contents
STAŁE ŹRÓDŁO|PERMANENT SOURCE
Aktywne|Enabled
Repozytorium GitHub lub bezpośredni adres HTTPS do JSON|GitHub repository or direct HTTPS JSON URL
Lub wybierz lokalny plik JSON|Or choose a local JSON file
Katalogi aplikacji|Application catalogs
Sprawdź i dodaj|Validate and add
Podaj adres katalogu albo wybierz plik JSON|Enter a catalog URL or choose a JSON file
Katalog został sprawdzony i dodany|Catalog validated and added
Lokalny Docker, WSL, SSH, Balena i zdalny Docker przez TLS.|Local Docker, WSL, SSH, Balena and remote Docker over TLS.
Importuj|Import
Eksportuj|Export
Nowy profil|New profile
Nowe profile są domyślnie tylko do odczytu. Sekrety połączeń są szyfrowane. Eksport nie zawiera haseł, tokenów ani kluczy prywatnych.|New profiles are read-only by default. Connection secrets are encrypted. Exports exclude passwords, tokens and private keys.
Profil|Profile
Połączenie|Connection
Dostęp|Access
Aktywny|Active
Sprawdź|Test
Edytuj profil|Edit profile
Usuń zapisany profil połączenia. Zasoby Docker pozostaną zachowane.|Remove the saved connection profile. Docker resources are retained.
Import profili|Import profiles
JSON eksportu Desktop lub Web|Desktop or Web export JSON
Import dotyczy konfiguracji połączeń. Hasła i klucze nie są importowane w jawnym JSON. Dane źródłowe nie są modyfikowane.|Import transfers connection metadata. Passwords and keys are not imported as plaintext JSON. Source data is unchanged.
Nazwa profilu|Profile name
Typ połączenia|Connection type
Lokalny Docker / Docker Desktop|Local Docker / Docker Desktop
Balena OS przez SSH|Balena OS over SSH
Zdalny Docker z TLS|Remote Docker with TLS
Istniejący tunel na localhost|Existing localhost tunnel
Kontekst Docker CLI (opcjonalnie)|Docker CLI context (optional)
Dystrybucja WSL|WSL distribution
Adres paneli / IP hosta (opcjonalnie)|Panel hostname / host IP (optional)
Host SSH / Balena|SSH / Balena host
Użytkownik SSH|SSH username
Ścieżka klucza SSH|SSH key path
Endpoint Docker, np. tcp://server:2376|Docker endpoint, e.g. tcp://server:2376
Hasło SSH — puste zachowuje obecne|SSH password — leave blank to retain
Passphrase klucza — puste zachowuje obecną|Key passphrase — leave blank to retain
Ścieżka CA TLS|TLS CA path
Ścieżka certyfikatu klienta TLS|TLS client certificate path
Ścieżka klucza klienta TLS|TLS client key path
Identyfikatory użytkowników, oddzielone przecinkami — puste: wszyscy|User IDs, comma-separated — blank allows all users
Uprawnienia profilu|Profile permissions
Odczyt|Read
Polecenia w kontenerach|Container exec
Zarządzanie obrazami|Manage images
Tworzenie wolumenów|Create volumes
Tworzenie sieci|Create networks
Operacje Compose|Compose actions
Instalowanie aplikacji|Install applications
Aktualizacje|Updates
Operacje destrukcyjne|Destructive actions
Dostęp do Docker może dawać kontrolę nad hostem. Włączaj tylko potrzebne operacje. SSH wymaga zweryfikowanego wpisu known_hosts; TCP używa TLS, chyba że jest to świadomie wybrany lokalny tunel.|Docker access can grant host control. Enable only required operations. SSH requires a verified known_hosts entry; TCP uses TLS except for an explicitly configured localhost tunnel.
Zapisz profil|Save profile
Profil został zapisany|Profile saved
Wygląd, dźwięki i bezpieczeństwo Twojej przestrzeni.|Appearance, sounds and workspace security.
Theme Settings|Theme Settings
Wybierz charakter przestrzeni. Podgląd działa od razu; zapis zatwierdza ustawienia.|Preview your workspace appearance instantly, then save to keep the changes.
Kolor akcentowy|Accent color
Intensywność akcentów|Accent intensity
Gęstość interfejsu|Interface density
Komfortowa|Comfortable
Kompaktowa|Compact
Język katalogu i nawigacji|Interface language
Język interfejsu|Interface language
Efekty wizualne|Visual effects
Subtelne przejścia|Subtle transitions
Dźwięki|Sounds
Krótkie, lokalne efekty. Dźwięk uruchamia się po interakcji i może być całkowicie wyłączony.|Short local effects. Sound starts after interaction and can be disabled completely.
Włącz dźwięki|Enable sounds
Głośność Master|Master volume
Głośność efektów|Effects volume
Głośność powiadomień|Notification volume
Styl dźwięków|Sound style
Soft — delikatny|Soft — gentle
Clear — czytelny|Clear — distinct
Warm — ciepły|Warm — mellow
Odsłuchaj efekt|Play test sound
Odświeżanie|Refresh
Interwał odświeżania (sekundy)|Refresh interval (seconds)
Odświeżanie zatrzymuje się na ukrytej karcie i podczas edycji formularzy. Katalogi mają osobne odświeżanie i cache.|Refresh pauses in hidden tabs and while editing forms. Catalogs have separate refresh and cache.
Przywróć domyślne|Reset defaults
Anuluj podgląd|Cancel preview
Zapisz ustawienia|Save settings
Ustawienia zapisane|Settings saved
Konto i zabezpieczenia|Account and security
Zmień hasło|Change password
Zarządzaj użytkownikami|Manage users
Hasła są hashowane scrypt. Sesja: HttpOnly, SameSite Strict i ochrona CSRF. Administrator przypisuje uprawnienia w profilach.|Passwords use scrypt. Sessions use HttpOnly, SameSite Strict and CSRF protection. Administrators assign profile permissions.
Włącz dźwięki, aby uruchomić odsłuch|Enable sounds to play a sample
Obecne hasło|Current password
Nowe hasło — co najmniej 12 znaków|New password — at least 12 characters
Użytkownicy|Users
Rola|Role
Nazwa nowego użytkownika|New username
Hasło — minimum 12 znaków|Password — at least 12 characters
Viewer — odczyt|Viewer — read only
Operator — kontenery i exec|Operator — containers and exec
Dodaj użytkownika|Add user
Użytkownik został dodany|User added
Profile i narzędzia dla klientów MCP — jawnie ograniczony Preview.|Profiles and tools for MCP clients — explicitly limited Preview.
Nowy dostęp|New grant
Klienci|Clients
Granice dostępu|Access boundaries
Przydzielone dostępy|Access grants
Nazwa / klient|Name / client
Ważny do|Expires
Eksport|Export
Odbierz dostęp|Revoke access
Nowy dostęp MCP|New MCP grant
Nazwa dostępu|Grant name
Klient|Client
Ważność w dniach|Validity in days
Bez limitu czasowego|No expiry
Narzędzia tylko do odczytu|Read-only tools
Utwórz dostęp|Create grant
Token — pokazany tylko raz|Token — shown once
Zapisz token w menedżerze sekretów klienta. Nie będzie można ponownie go odczytać.|Save the token in your client's secret manager. It cannot be retrieved again.
Eksport konfiguracji jest dostępny w tabeli; zamiast tokenu zawiera bezpieczny znacznik środowiska.|Configuration export is available in the table and contains no token value.
Konfiguracja MCP stdio|MCP stdio configuration
Dostęp odebrany|Access revoked
Działa read-only stdio: kontenery, inspekcja, logi, monitoring, obrazy, wolumeny i sieci. Operacje zapisu i Streamable HTTP nie są udostępniane w tym Preview.|Read-only stdio supports containers, inspect, logs, monitoring, images, volumes and networks. Writes and Streamable HTTP are unavailable in this Preview.
Konfiguracja pozostaje niezależna od dostawcy AI. Eksport używa standardowego procesu MCP, a token trafia do środowiska klienta lub menedżera sekretów.|Configuration is provider-neutral. Export starts a standard MCP process; the token comes from the client environment or secret manager.
Tylko wybrane profile i narzędzia. Odczyt jako domyślny zakres, termin ważności, dziennik i możliwość natychmiastowego odebrania dostępu.|Only selected profiles and tools are accessible. Read-only scope, optional expiry, audit and immediate revocation.
Lokalny lub zewnętrzny model do tworzenia i poprawiania konfiguracji Docker.|Use a local or external model to create and improve Docker configurations.
AI proponuje konfigurację. Instalacja pozostaje osobną operacją z kontrolą portów, uprawnień i potwierdzeniem.|AI proposes configuration. Installation remains a separate operation with port validation, permissions and confirmation.
Połączenie AI|AI connection
Dostawca|Provider
Adres bazowy API|API base URL
Model|Model
Klucz API — puste zachowuje obecny|API key — leave blank to retain
Klucz API (opcjonalny dla serwera lokalnego)|API key (optional for a local server)
Zezwól na świadomie wskazany serwer lokalny / LAN|Allow the explicitly configured local / LAN server
Włącz asystenta AI|Enable AI assistant
Klucz jest szyfrowany po stronie backendu i nie jest zwracany w konfiguracji ani eksportach. Serwer modelu musi być już uruchomiony; DCC nie uruchamia modeli automatycznie.|The backend encrypts the key and excludes it from configuration and exports. The model server must already be running; DCC does not start models automatically.
Zapisz połączenie AI|Save AI connection
Pobierz listę modeli|Fetch model list
Przygotuj kontener|Prepare a container
Obecna komenda Docker (opcjonalnie)|Current Docker command (optional)
Obraz Docker (opcjonalnie)|Docker image (optional)
Co chcesz uruchomić lub poprawić?|What would you like to run or improve?
Opisz aplikację, porty, dane trwałe i wymagania…|Describe the application, ports, persistent data and requirements…
Dołącz architekturę, RAM i zajęte porty hosta|Include host architecture, RAM and occupied ports
Żądanie trafia do skonfigurowanego dostawcy AI. Dostawca może naliczać opłaty. Propozycja nie jest wykonywana automatycznie.|The request is sent to the configured AI provider, which may charge for usage. Proposals are never executed automatically.
Wygeneruj / popraw z AI|Generate / improve with AI
Ustawienia AI ↗|AI settings ↗
Zastosuj propozycję do formularza|Apply proposal to form
Propozycja AI została zastosowana do formularza. Sprawdź konfigurację przed instalacją.|AI proposal applied to the form. Review the configuration before installation.
Połączenie AI zostało zapisane|AI connection saved
OpenAI-compatible — lokalny lub zewnętrzny endpoint|OpenAI-compatible — local or external endpoint
Brak danych do wyświetlenia|No data to display
Zapisz|Save
Zamknij|Close
Anuluj|Cancel
Dalej|Next
Potwierdź operację|Confirm operation
Sprawdź i potwierdź|Review and confirm
Potwierdzam|Confirm
Rozumiem skutki tej operacji i potwierdzam jej wykonanie.|I understand the consequences and confirm this operation.
Operacja w toku…|Operation in progress…
Operacja zakończona|Operation completed
Operacja na zaznaczonych kontenerach|Action on selected containers
Operacja nadal trwa. Sprawdź stan Dockera przed ponowieniem.|The operation is still running. Check Docker before retrying.
Sesja wygasła|Session expired
Nieprawidłowa odpowiedź serwera|Invalid server response
Nie udało się wykonać operacji|The operation could not be completed
Połączono|Connected
Połączono ·|Connected ·
Połączono z|Connected to
Brak połączenia Docker|Docker disconnected
Odświeżono|Refreshed
Odśwież|Refresh
Wymagane sprawdzenie profilu|Check the connection profile
Sprawdź profil połączenia i uprawnienia.|Check the connection profile and permissions.
Jak kontynuować|How to continue
Upewnij się, że Docker działa, a proces DCC Web ma do niego dostęp. Nowe profile mają tylko odczyt; operacje zapisu włącza administrator w profilu.|Ensure Docker is running and accessible to DCC Web. New profiles are read-only; an administrator enables write operations.
Sprawdź profile|Check profiles
Spróbuj ponownie|Try again
Aktywny profil|Active profile
Wyloguj|Sign out
Twoje profile. Twoje dane.|Your profiles. Your data.
Konfiguracja:|Configuration:
Zmieniono zajęte porty:|Occupied ports changed:
Dodaj tag:|Add tag:
Uruchom polecenie:|Run command:
Zatrzymaj i usuń kontenery aplikacji|Stop and remove application containers
Wolumeny i montowane katalogi pozostaną zachowane; dane tylko w warstwie kontenera mogą zostać utracone.|Volumes and mounted directories are retained; data only in the container writable layer can be lost.
Potwierdzasz przegląd repozytorium|You confirm review of the repository
Docker zbuduje obraz; kod źródłowy nie będzie wykonywany bezpośrednio na hoście.|Docker builds the image; source code is not executed directly on the host.
`;
const messages=Object.fromEntries(pairs.trim().split('\n').map(line=>line.split('|')));
const reverse=Object.fromEntries(Object.entries(messages).filter(([a,b])=>a!==b).map(([a,b])=>[b,a]));
const errorPL={
'Installation is disabled for this profile. Enable Install applications in Profiles / Permissions. Only an administrator can change this setting.':'Instalowanie jest wyłączone w tym profilu. Administrator musi włączyć Instalowanie aplikacji w Profile / Uprawnienia.',
'Configure and enable the AI connection first':'Najpierw skonfiguruj i włącz połączenie AI.',
'Another operation is already running for this profile':'W tym profilu trwa już inna operacja. Poczekaj na jej zakończenie.',
'Use the image update action to change the existing container image':'Do zmiany obrazu istniejącego kontenera użyj osobnej operacji aktualizacji.',
'Invalid AI credential':'Nieprawidłowy format klucza API.',
'Enable installation or container management for this profile to use the AI assistant':'Włącz instalowanie lub zarządzanie kontenerami w uprawnieniach tego profilu, aby korzystać z AI.',
'Local HTTP endpoints require explicit local-network consent':'Lokalny endpoint HTTP wymaga zaznaczenia zgody na połączenie z siecią lokalną.',
'Specify the AI model name':'Podaj nazwę modelu AI.',
'AI did not return a valid configuration proposal':'AI nie zwróciło poprawnej propozycji konfiguracji.',
'AI provider is unavailable or returned invalid JSON':'Dostawca AI jest niedostępny lub zwrócił niepoprawny JSON.',
'A fresh explicit confirmation is required':'Wymagane jest nowe, jawne potwierdzenie.',
'Administrator permission required':'Wymagane są uprawnienia administratora.',
'Profile access denied':'Brak dostępu do profilu.',
'Login required':'Wymagane jest logowanie.',
'Invalid CSRF token':'Nieprawidłowy token CSRF. Odśwież stronę.',
'Docker is unavailable or the operation timed out. Check the selected profile.':'Docker jest niedostępny lub przekroczono limit czasu. Sprawdź wybrany profil.',
'Docker access denied; check this profile\'s host permissions':'Brak dostępu do Docker. Sprawdź uprawnienia na hoście tego profilu.',
'Docker rejected the operation. Check the profile and resource state.':'Docker odrzucił operację. Sprawdź profil i stan zasobu.',
'Operation failed; review the selected profile, configuration and Docker state':'Operacja nie powiodła się. Sprawdź profil, konfigurację i stan Docker.'
};
const escape=value=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
const keys=Object.keys(messages).filter(key=>messages[key]!==key).sort((a,b)=>b.length-a.length);
const pattern=new RegExp('(?<![\\p{L}\\p{N}_])(?:'+keys.map(escape).join('|')+')(?![\\p{L}\\p{N}_])','gu');
export function setLanguage(value){language=value==='PL'?'PL':'EN';if(typeof document!=='undefined')document.documentElement.lang=language.toLowerCase();}
export function getLanguage(){return language;}
export function t(value){const text=String(value??''),trim=text.trim();if(language==='PL'&&text.startsWith('Terminal session limit ('))return 'Osiągnięto limit sesji terminala '+text.match(/\(\d+\)/)?.[0]+'. Zamknij nieużywaną sesję albo zmień limit w Ustawieniach.';if(language==='PL'&&text==='Close an existing terminal before opening another one')return 'Osiągnięto limit aktywnych sesji terminala. Wliczane są sesje ze wszystkich kart i okien.';if(language==='PL'&&text.startsWith('This profile does not permit the operation: '))return 'Profil nie zezwala na tę operację: '+text.slice(42)+'. Sprawdź uprawnienia profilu.';if(language==='PL')return errorPL[text]||(text==='Theme Settings'?'Ustawienia motywu':text);if(messages[trim])return text.replace(trim,messages[trim]);return text;}
export function literal(value){return language==='EN'?String(value).replace(pattern,key=>messages[key]):String(value).replace('Theme Settings','Ustawienia motywu');}
export function html(parts,...values){return parts.map((part,index)=>literal(part)+(index<values.length?String(values[index]??''):'')).join('');}
