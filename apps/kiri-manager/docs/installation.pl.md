# Instalacja

Panel używa portu 8796/tcp. Domyślne mapowania udostępniają go na adresie loopback hosta. Własny wolumen `dcc_kiri_manager_data` utrzymuje ustawienia, a healthcheck sprawdza działanie procesu. Po zatwierdzeniu wydania obraz będzie dostępny w GHCR.

## Zalecany przepływ automatyczny (DCC Windows i panel)

Otwórz **Sklep DCC → DCC Kiri Manager**. Aplikacja Windows bezpośrednio sprawdza `npipe:////./pipe/kiri`, potwierdza tożsamość silnika przez `/version` i odczyt listy kontenerów. Następnie pokazuje **Połącz**. Gdy brak potoku i instalacji użytkownika, pokazuje **Zainstaluj Kiri** prowadzące do [oficjalnego instalatora Windows](https://docs.runkiri.com/windows/). Odmowa uprawnień i błędna tożsamość silnika mają osobne komunikaty. Użytkownik nie wpisuje aliasów ani komend.

Po połączeniu otwórz ponownie wpis w Sklepie, aby zainstalować panel. DCC żąda zgody administratora na dostęp do API silnika, pobiera zatwierdzony obraz i uruchamia tymczasowy kontener w Kiri. Testuje rzeczywisty socket WSL, tożsamość Kiri i odczyt zasobów jako UID 10001. Dopiero poprawny test pozwala utworzyć panel z wolumenem `dcc_kiri_manager_data:/data`. Następnie DCC sprawdza z Windows odpowiedź `http://127.0.0.1:8796/healthz`, jej nagłówek identyfikujący panel i format JSON. Jeśli port nie jest osiągalny z Windows, nowy kontener zostaje usunięty bez usuwania wolumenu. Należy sprawdzić przekierowanie portu WSL i konflikt portu 8796. Nieudany test pozostawia istniejące instalacje bez zmian. Kontener Docker Desktop nie widzi automatycznie potoku Windows ani socketu innej dystrybucji WSL. Test pełnej instalacji panelu w rzeczywistym Windows/WSL pozostaje **NOT VERIFIED**.

Panel WWW automatycznie wyświetla **Połącz**, gdy administrator udostępnił dostępny i zweryfikowany socket Kiri. W innym przypadku pokazuje przyczynę blokady i instrukcję konfiguracji. Alias i terminal są opcjonalne w sekcji **Zaawansowana konfiguracja ręczna**. Przeglądarka nie instaluje silnika na hoście ani nie montuje socketu do już uruchomionego kontenera.

## Docker i Sklep DCC

W katalogu modułu na wybranym hoście Docker:

```sh
docker compose up -d
```

Otwórz http://127.0.0.1:8796/ na tym hoście. Zmienna `KIRI_PANEL_HOST_PORT` pozwala wybrać inny port. W Sklepie DCC wybierz **DCC → DCC Kiri Manager** i skorzystaj z adresu lokalnego podanego przy instalacji. Przycisk **Website / Strona** prowadzi do wizytówki projektu.

### Pierwsze logowanie

Jeśli na wolumenie nie utworzono dotąd konta, zaloguj się lokalnie jako `admin` z hasłem `admin`. Te dane startowe znajdziesz też w logu uruchomienia panelu. Zanim wejdziesz do panelu, ustaw własne hasło od 14 do 128 znaków. W tym samym formularzu możesz zmienić nazwę użytkownika. Aktualizacja z zachowaniem wolumenu zachowuje także istniejące konto i ustawienia.

### Instalacja przez CLI

```sh
docker run -d --name dcc-kiri-manager --restart unless-stopped \
  -p 127.0.0.1:8796:8796 --volume dcc_kiri_manager_data:/data \
  --read-only --tmpfs /tmp:size=8m,mode=1777 --cap-drop ALL \
  --security-opt no-new-privileges:true --memory 192m --pids-limit 40 \
  ghcr.io/hattimon/dcc-kiri-manager:0.1.3
```

## Konfiguracja i reset z terminala

Rozwiń pomoc na ekranie logowania, aby zobaczyć polecenia do wykonania na hoście. Jeśli zapomnisz hasła, użyj polecenia dla swojego środowiska i rzeczywistej nazwy kontenera panelu.

```sh
# Docker
docker exec -it dcc-kiri-manager python -m backend.admin --reset

# Kiri z kontekstem kiri
docker --context kiri exec -it dcc-kiri-manager python -m backend.admin --reset

# Kiri na natywnym Linuxie
docker --host unix:///run/kiri/docker.sock exec -it dcc-kiri-manager python -m backend.admin --reset

# Natywny Python, w katalogu panelu z tą samą zmienną KIRI_PANEL_DATA
python -m backend.admin --reset
```

Wpisz i potwierdź nowe hasło w terminalu. Reset wylogowuje aktywne sesje i zachowuje nazwę użytkownika, profile oraz ustawienia. Aby zmienić nazwę, dodaj `--username operator`. Do pierwszej konfiguracji konta użyj polecenia kończącego się na `python -m backend.admin`. Wariant terminalowy służy też do utworzenia konta przed udostępnieniem panelu przez skonfigurowane proxy HTTPS.

## Linux (Ubuntu, Debian, Raspberry Pi)

Dla natywnego Debiana lub Ubuntu z systemd i procesorem amd64 albo arm64 kreator udostępnia plik `setup-kiri-linux.sh`. Plan można odczytać bez podwyższonych uprawnień. Uruchomienie z `--apply` weryfikuje SHA-256 pakietu upstream, instaluje Kiri Lite w przypadku braku pakietu Kiri, uruchamia usługę i sprawdza dedykowany socket. Potwierdź operację na hoście. [Oficjalne pakiety Kiri](https://docs.runkiri.com/linux/).

```sh
bash setup-kiri-linux.sh --plan
bash setup-kiri-linux.sh --apply
```

### Nadaj dostęp panelowi na natywnym Linuxie

Kiri 0.2.2 sprawdza UID procesu w bazie kont hosta oraz uprawnienia pliku socketu. Przed uruchomieniem obu wariantów kontenerowych upoważnij dedykowane konto bez logowania o UID `10001`. Wariant zakłada bezpośrednie mapowanie UID kontenera na hosta. Skrypt zatrzyma się, jeśli identyfikator lub nazwa konta jest już zajęta przez innego użytkownika. [Kod kontroli UID w Kiri](https://github.com/libracoder/kiri/blob/v0.2.2/crates/kiri/src/daemon/access.rs).

```sh
bash setup-kiri-linux.sh --plan --grant-panel-access
bash setup-kiri-linux.sh --apply --grant-panel-access
```

Jawna opcja nadaje dostęp kontu `dcc-kiri-panel` przez `kiri host-access`. Członkostwo w grupie `kiri` daje uprawnienia na poziomie silnika. Aby cofnąć dostęp, usuń to konto z grupy `kiri` na hoście. Przy mapowaniu przestrzeni użytkowników sprawdź rzeczywisty UID procesu widoczny dla hosta.

Panel w Dockerze na tym samym hoście może użyć osobnej konfiguracji montowania jednego socketu:

```sh
export KIRI_SOCKET_PATH=/run/kiri/docker.sock
export KIRI_SOCKET_GID="$(stat -c %g "$KIRI_SOCKET_PATH")"
docker compose -f compose.yaml -f compose.kiri-socket.yaml config
docker compose -f compose.yaml -f compose.kiri-socket.yaml up -d
```

Wybierz alias `local` i przetestuj połączenie w kreatorze. Montowanie zachowuje uprawnienia API silnika. Jeżeli panel zainstalowano ze Sklepu DCC, operator może odtworzyć wyłącznie ten panel z tym samym wolumenem i zweryfikowanymi opcjami socketu. Zmiana montowania wymaga odtworzenia kontenera. Po wymianie pliku socketu przez Kiri sprawdź usługę i w razie potrzeby odtwórz sam panel.

### Bezpośrednio w Kiri

Użyj CLI zgodnego z Dockerem i wskaż dedykowany socket Kiri. Ustawienia panelu przeszły testy z Kiri Lite 0.2.2 na Ubuntu 24.04.5 LTS na amd64 i arm64. [Wyniki integracji](verification.md#integracja-na-github-actions).

```sh
socket=/run/kiri/docker.sock
gid="$(stat -c %g "$socket")"
docker --host "unix://$socket" version
docker --host "unix://$socket" run -d --name dcc-kiri-manager \
  -p 127.0.0.1:8796:8796 --volume dcc_kiri_manager_data:/data \
  --mount "type=bind,src=$socket,dst=/run/dcc-kiri/engine.sock,readonly" \
  --group-add "$gid" -e 'KIRI_SOCKETS={"local":"/run/dcc-kiri/engine.sock"}' \
  --cap-drop ALL --security-opt no-new-privileges:true --read-only \
  --tmpfs /tmp:size=8m,mode=1777 --restart unless-stopped \
  ghcr.io/hattimon/dcc-kiri-manager:0.1.3
```

Raspberry Pi 4/5 wymaga systemu 64-bitowego, obrazu arm64 i zgodnego jądra z systemd/cgroups. Dostępność pakietu upstream dla Linux ARM64 nie jest potwierdzeniem działania na Raspberry Pi. Oba modele mają status **NOT VERIFIED**. [Macierz zgodności](compatibility.md).

## Windows 10/11 AMD64, WSL2

Użyj [oficjalnego instalatora Kiri](https://docs.runkiri.com/windows/). Wybierz Kiri Linux dla izolacji lub Ubuntu dla pracy z typowym terminalem Linux. Wybór localhost upraszcza dostęp do panelu. `docker --context kiri version` potwierdza, jaki silnik obsługuje polecenia. Potok `npipe:////./pipe/kiri` jest interfejsem dla klientów Windows.

Według dokumentacji Kiri daemon WSL nasłuchuje na `/var/lib/kiri-daemon/.kiri/run/docker.sock`. DCC próbuje zamontować tę ścieżkę **wyłącznie w kontenerze tego samego silnika Kiri** i uruchamia test uprawnień panelu. Nie jest to obsługa montowania socketów między WSL i Docker Desktop. Nieudany test oznacza konieczność sprawdzenia dostępu w WSL przez administratora. DCC samodzielnie nie zmienia właściciela ani uprawnień socketu ani nie nadpisuje panelu. Instalator Kiri i konfiguracja WSL mogą wymagać zatwierdzenia uprawnień administratora Windows.

- **Docker Desktop** może uruchomić panel w trybie konfiguracji. Kontener Linux w tym środowisku nie ma połączenia z potokiem Windows ani socketem w osobnej dystrybucji WSL.
- **Uruchomienie w Kiri** używa `docker --context kiri` z portem, wolumenem i opcjami z wariantu CLI. Połączenie wymaga dostępu do `/var/lib/kiri-daemon/.kiri/run/docker.sock` wewnątrz dystrybucji Kiri. Montowanie i prawa pozostają **NOT VERIFIED**. Sprawdź je na środowisku testowym przed zastosowaniem ustawień z Linuxa.

## macOS Intel i Apple Silicon

Zainstaluj pakiet Kiri odpowiedni dla procesora na macOS 14 lub nowszym. Docker Desktop oraz Kiri mogą uruchomić panel konfiguracyjny przez właściwy kontekst CLI. Kontenery Linux działają wewnątrz VM. Socket hosta `$HOME/.kiri/run/docker.sock` jest dostępny dla procesów macOS. Połączenie OCI między tymi środowiskami pozostaje poza zakresem wersji. [Instalacja Kiri](https://docs.runkiri.com/install/) · [Architektura](https://docs.runkiri.com/how-it-works/).

Eksperymentalna opcja zaawansowana to lokalny proces Python 3.12 z zależnościami modułu w środowisku wirtualnym. Skonfiguruj `KIRI_SOCKETS` jako JSON z bezwzględną ścieżką do socketu, np. `{"mac":"/Users/alex/.kiri/run/docker.sock"}`. Uruchom `python -m backend` i otwórz lokalny adres, aby skonfigurować konto.

## Problemy i aktualizacja

- **Brak aliasów:** zamontuj dedykowany socket tam, gdzie ten wariant jest dostępny, i skonfiguruj `KIRI_SOCKETS`.
- **Odmowa dostępu lub natychmiastowe rozłączenie:** sprawdź, czy UID procesu panelu jest upoważniony w Kiri. Konfiguracja montowania wymaga także numerycznej grupy socketu.
- **Błąd tożsamości:** sprawdź kontekst CLI, wersję upstream i ścieżkę endpointu. Panel weryfikuje identyfikatory Kiri przed odczytem.
- **Timeout:** zweryfikuj gotowość silnika oraz aktualny plik socketu. Pomiar warstw obrazów może przekroczyć limit czasu panelu.
- **Aktualizacja:** wykonaj spójną kopię bazy z dedykowanego wolumenu lub zrób ją przy zatrzymanym panelu. Odtwórz tylko panel z zatwierdzonym obrazem i zachowaj wolumen.
- **Cofnięcie wersji:** jeśli poprzedni obraz nie obsługuje schematu bazy, przywróć spójną kopię danych panelu przeznaczoną dla tej wersji.
- **Odinstalowanie:** `docker compose down` usuwa panel z zachowaniem jego wolumenu. Zachowaj `dcc_kiri_manager_data`, jeśli chcesz wrócić do tych profili.

## Kandydat 0.1.3 i SSH

Domyślny Compose i Sklep nadal wskazują opublikowane 0.1.2. Lokalny plik `compose.candidate.yaml` buduje obraz `dcc-kiri-manager:0.1.3-review` ze źródeł. Używaj go po jawnej zgodzie na właściwym hoście, z osobnym wolumenem testowym i portem. Dotychczasowy UID/GID socketu pozostaje bez zmian. W Połączenia → Nowy profil SSH wybierz oczekiwany silnik, host/port/użytkownika, wklej zweryfikowany niehaszowany wpis known_hosts i podaj hasło albo klucz prywatny. Zdalne Docker CLI musi już wskazywać właściwy silnik, a konto mieć jego uprawnienia. Przetestuj przed zapisaniem i aktywacją. Zmiana celu wymaga ponownego podania sekretu. Zrób prywatną kopię bazy i master-key. Schemat 3 nie działa z 0.1.2: do rollbacku zatrzymaj panel i przywróć kopię schematu 2 sprzed migracji; późniejsze zmiany nie zostaną przeniesione.

Po zgodzie na izolowany przegląd użyj osobnego pliku (opcjonalnie dodaj nakładkę socketu): `docker compose -f compose.candidate.yaml up --build -d`. Projekt, kontener, wolumen danych i port 18796 na loopback są odrębne od opublikowanego panelu. Nie łącz tego pliku z produkcyjnym compose.yaml. Migracja produkcyjna wymaga osobnego planu.
