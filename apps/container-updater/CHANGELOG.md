# DCC Container Updater 1.1.9

Cinema Hub started with Docker Compose on Windows shows an update action in its container row. The local PowerShell procedure verifies an isolated copy of the existing SQLite database before deployment. The updater recognizes the pinned version on later scans.

Cinema Hub uruchomiony przez Docker Compose na Windows pokazuje akcję aktualizacji przy kontenerze. Procedura PowerShell sprawdza kopię SQLite w izolowanym kontenerze przed wdrożeniem. Przy kolejnych skanach aktualizator rozpoznaje przypiętą wersję.

Linux amd64 / arm64 · `ghcr.io/hattimon/dcc-container-updater:1.1.9` · `latest`

# DCC Container Updater 1.1.8

During compatible DCC Web updates, the updater transfers saved tunnel recovery consent even when zrok is already stopped. After the replacement becomes healthy it can recover consent from a verified older Web container before removing the backup.

Podczas zgodnej aktualizacji DCC Web Updater przenosi zapisaną zgodę na wznowienie także wtedy, gdy tunel zrok jest już zatrzymany. Po sprawdzeniu nowego kontenera może przenieść zgodę ze zweryfikowanej starszej instalacji Web przed usunięciem kopii.

Linux amd64 / arm64 · `ghcr.io/hattimon/dcc-container-updater:1.1.8` · `latest`

# DCC Container Updater 1.1.7

When the old container uses its image's default command or entrypoint, the replacement now uses the target image's defaults. Explicit runtime overrides remain intact. This fixes updates where an image removed or renamed its default startup script, including Cinema Hub 1.3.5 to 1.3.15. The updater also waits through Docker's `restarting` state and includes bounded, sanitized startup logs if rollback is still needed. Existing data mounts remain attached to the replacement and are never deleted during rollback.

Jeśli stary kontener używa domyślnej komendy lub punktu wejścia obrazu, nowy dostaje ustawienia domyślne nowego obrazu. Ręczne nadpisania są zachowane. Naprawia to aktualizacje, w których obraz zmienił skrypt startowy, w tym Cinema Hub 1.3.5 do 1.3.15. Updater czeka też na zakończenie stanu `restarting` i przy dalszej awarii pokazuje ograniczone, oczyszczone logi startowe. Podłączone wolumeny z danymi pozostają dołączone i nie są usuwane podczas wycofania.

Linux amd64 / arm64 · `ghcr.io/hattimon/dcc-container-updater:1.1.7` · `latest`

# DCC Container Updater 1.1.6

When an update fails and the previous container is restored, the result now includes a short, sanitized description of the underlying Docker error. Common credentials and authorization headers are redacted.

Jeśli aktualizacja się nie powiedzie, a poprzedni kontener zostanie przywrócony, wynik pokaże krótki, oczyszczony opis błędu Docker. Typowe hasła, tokeny i nagłówki autoryzacji są ukrywane.

Linux amd64 / arm64 · `ghcr.io/hattimon/dcc-container-updater:1.1.6` · `latest`

# DCC Container Updater 1.1.5

Docker Desktop can briefly return 404 when the updater inspects a container immediately after Docker created it. The updater now retries that bounded lookup and, if the ID never becomes visible, removes only the replacement created by that update before restoring the previous container. This prevents a transient inspect race from leaving a name conflict or blocking rollback.

Docker Desktop może przez chwilę zwracać 404 przy odczycie kontenera bezpośrednio po jego utworzeniu. Updater ponawia ograniczoną liczbę prób; jeśli identyfikator nadal nie jest widoczny, usuwa wyłącznie kontener utworzony w tej aktualizacji, a potem przywraca poprzedni kontener. Chwilowy błąd odczytu nie powinien już blokować wycofania ani pozostawiać konfliktu nazwy.

Linux amd64 / arm64 · `ghcr.io/hattimon/dcc-container-updater:1.1.5` · `latest`

# DCC Container Updater 1.1.4

Updater pauses and resumes the active zrok tunnel during compatible DCC Web updates after local administrator opt-in. It waits for the replacement or restored panel to become healthy before requesting tunnel resumption. The blocker now shows the manual procedure for older Web versions and installations without consent.

Updater zatrzymuje i wznawia aktywny tunel zrok podczas zgodnych aktualizacji DCC Web po zgodzie administratora w lokalnym panelu. Czeka na gotowość nowego lub przywróconego panelu przed wznowieniem. Komunikat blokady opisuje teraz procedurę ręczną dla starszych wersji Web i instalacji bez zgody.

Linux amd64 / arm64 · `ghcr.io/hattimon/dcc-container-updater:1.1.4` · `latest`

# DCC Container Updater 1.1.3

Update DCC Web with both managed Caddy HTTPS and a stopped Remote Access tunnel. Replacement and rollback preserve both Docker networks and their aliases. Turn off the tunnel from DCC Web before updating.

Aktualizacja DCC Web obsługuje zarządzane HTTPS Caddy oraz zatrzymany tunel Remote Access. Podmiana i wycofanie zachowują obie sieci Docker i ich aliasy. Przed aktualizacją wyłącz tunel w DCC Web.

# DCC Container Updater 1.1.2

Safely update the official DCC Web container when its optional managed HTTPS Caddy proxy uses a dedicated Docker network. The updater recognizes only the DCC-created Web/Caddy pair, preserves the `dcc-web-upstream` alias during replacement and reconnects the previous container on rollback. Unrecognized custom networks and additional network peers remain blocked.

Bezpieczna aktualizacja oficjalnego kontenera DCC Web z opcjonalnym zarządzanym proxy HTTPS Caddy i dedykowaną siecią Docker. Aktualizator rozpoznaje wyłącznie parę Web/Caddy utworzoną przez DCC, zachowuje alias `dcc-web-upstream` podczas podmiany i ponownie podłącza poprzedni kontener przy wycofaniu. Nieznane sieci niestandardowe i dodatkowe kontenery w sieci nadal blokują aktualizację.

The image is published for Linux AMD64 and ARM64 as `ghcr.io/hattimon/dcc-container-updater:1.1.2` and `latest`. The installed panel detects the new image through its existing self-update check and requests confirmation before restarting. Settings and mounted data are retained.

# DCC Container Updater 1.1.1

Fix scheduled updates incorrectly blocked by the updater's read-only directory views and system monitors' read-only views of the host filesystem. Real shared-data consumers, writable mounts, explicit data mounts, named volumes, explicit dependencies and Compose safeguards remain protected. Scheduled and manual updates use the same saved registry credentials, independently of browser login.

Naprawiono fałszywą blokadę aktualizacji z harmonogramu wywołaną przez podgląd katalogów tylko do odczytu w panelu aktualizacji i monitorze systemu. Zachowano ochronę rzeczywistych zależności i współdzielonych danych. Harmonogram korzysta z tych samych zapisanych danych rejestrów co aktualizacja ręczna, także po wylogowaniu z panelu.

# DCC Container Updater 1.1.0

Check a single container from its table row, or use **Check selected…** to check several containers. Existing update checkboxes and **Update selected** keep their original behavior. Unselected scan results are preserved; newly discovered containers can be selected before a full scan.

Sprawdzanie jednego kontenera przyciskiem w wierszu lub kilku przez **Sprawdź wybrane…**. Dotychczasowe checkboxy aktualizacji i **Aktualizuj zaznaczone** działają jak wcześniej. Wyniki pozostałych kontenerów zostają zachowane; nowe kontenery można sprawdzić bez pełnego skanowania.

The image is published for Linux AMD64 and ARM64 as `ghcr.io/hattimon/dcc-container-updater:1.1.0` and `latest`. The installed panel detects the new image through its existing self-update check and requests confirmation before restarting. Settings and mounted data are retained.

[Setup and update instructions](https://github.com/hattimon/DCC/tree/main/apps/container-updater#readme)
