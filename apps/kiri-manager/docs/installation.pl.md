# Instalacja

Panel używa portu 8796/tcp. Domyślne mapowania udostępniają go na adresie loopback hosta. Własny wolumen `dcc_kiri_manager_data` utrzymuje ustawienia, a healthcheck sprawdza działanie procesu. Po zatwierdzeniu wydania obraz będzie dostępny w GHCR.

## Docker i Sklep DCC

W katalogu modułu na wybranym hoście Docker:

```sh
docker compose up -d
docker compose exec panel python -m backend.admin
```

Otwórz http://127.0.0.1:8796/ na tym hoście. Zmienna `KIRI_PANEL_HOST_PORT` pozwala wybrać inny port. Utwórz hasło administratora o długości co najmniej 14 znaków. Instalacja przez CLI:

```sh
docker run -d --name dcc-kiri-manager --restart unless-stopped \
  -p 127.0.0.1:8796:8796 --volume dcc_kiri_manager_data:/data \
  --read-only --tmpfs /tmp:size=8m,mode=1777 --cap-drop ALL \
  --security-opt no-new-privileges:true --memory 192m --pids-limit 40 \
  ghcr.io/hattimon/dcc-kiri-manager:0.1.0
docker exec -it dcc-kiri-manager python -m backend.admin
```

Po publikacji wpisu wybierz **DCC → DCC Kiri Manager** i sprawdź mapowanie portu w podglądzie. Przycisk **Website / Strona** prowadzi do wizytówki produktu. Panel otwórz pod jego adresem loopback na hoście Docker. Użyj rzeczywistej nazwy kontenera w poleceniu konfiguracji hasła. Panel można otworzyć bez podłączenia silnika. Kreator wskaże odpowiedni instalator Kiri.

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
  ghcr.io/hattimon/dcc-kiri-manager:0.1.0
docker --host "unix://$socket" exec -it dcc-kiri-manager python -m backend.admin
```

Raspberry Pi 4/5 wymaga systemu 64-bitowego, obrazu arm64 i zgodnego jądra z systemd/cgroups. Dostępność pakietu upstream dla Linux ARM64 nie jest potwierdzeniem działania na Raspberry Pi. Oba modele mają status **NOT VERIFIED**. [Macierz zgodności](compatibility.md).

## Windows 10/11 AMD64, WSL2

Użyj [oficjalnego instalatora Kiri](https://docs.runkiri.com/windows/). Wybierz Kiri Linux dla izolacji lub Ubuntu dla pracy z typowym terminalem Linux. Wybór localhost upraszcza dostęp do panelu. `docker --context kiri version` potwierdza, jaki silnik obsługuje polecenia. Potok `npipe:////./pipe/kiri` jest interfejsem dla klientów Windows.

- **Docker Desktop** może uruchomić panel w trybie konfiguracji. Kontener Linux w tym środowisku nie ma połączenia z potokiem Windows ani socketem w osobnej dystrybucji WSL.
- **Uruchomienie w Kiri** używa `docker --context kiri` z portem, wolumenem i opcjami z wariantu CLI. Połączenie wymaga dostępu do `/var/lib/kiri-daemon/.kiri/run/docker.sock` wewnątrz dystrybucji Kiri. Montowanie i prawa pozostają **NOT VERIFIED**. Sprawdź je na środowisku testowym przed zastosowaniem ustawień z Linuxa.

## macOS Intel i Apple Silicon

Zainstaluj pakiet Kiri odpowiedni dla procesora na macOS 14 lub nowszym. Docker Desktop oraz Kiri mogą uruchomić panel konfiguracyjny przez właściwy kontekst CLI. Kontenery Linux działają wewnątrz VM. Socket hosta `$HOME/.kiri/run/docker.sock` jest dostępny dla procesów macOS. Połączenie OCI między tymi środowiskami pozostaje poza zakresem wersji. [Instalacja Kiri](https://docs.runkiri.com/install/) · [Architektura](https://docs.runkiri.com/how-it-works/).

Eksperymentalna opcja zaawansowana to lokalny proces Python 3.12 z zależnościami modułu w środowisku wirtualnym. Skonfiguruj `KIRI_SOCKETS` jako JSON z bezwzględną ścieżką do socketu, np. `{"mac":"/Users/alex/.kiri/run/docker.sock"}`. Polecenia `python -m backend.admin` i `python -m backend` uruchamiają konto i panel na loopback.

## Problemy i aktualizacja

- **Brak aliasów:** zamontuj dedykowany socket tam, gdzie ten wariant jest dostępny, i skonfiguruj `KIRI_SOCKETS`.
- **Odmowa dostępu lub natychmiastowe rozłączenie:** sprawdź, czy UID procesu panelu jest upoważniony w Kiri. Konfiguracja montowania wymaga także numerycznej grupy socketu.
- **Błąd tożsamości:** sprawdź kontekst CLI, wersję upstream i ścieżkę endpointu. Panel weryfikuje identyfikatory Kiri przed odczytem.
- **Timeout:** zweryfikuj gotowość silnika oraz aktualny plik socketu. Pomiar warstw obrazów może przekroczyć limit czasu panelu.
- **Aktualizacja:** wykonaj spójną kopię bazy z dedykowanego wolumenu lub zrób ją przy zatrzymanym panelu. Odtwórz tylko panel z zatwierdzonym obrazem i zachowaj wolumen.
- **Cofnięcie wersji:** jeśli poprzedni obraz nie obsługuje schematu bazy, przywróć spójną kopię danych panelu przeznaczoną dla tej wersji.
- **Odinstalowanie:** `docker compose down` usuwa panel z zachowaniem jego wolumenu. Zachowaj `dcc_kiri_manager_data`, jeśli chcesz wrócić do tych profili.
