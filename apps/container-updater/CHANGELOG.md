# DCC Container Updater 1.1.7

When Docker reports a replacement as `restarting`, the updater now waits through the configured startup window before deciding to roll back. If startup still fails, the error includes bounded, sanitized container state and recent startup logs captured before cleanup, so the cause is visible while the previous container is restored.

Gdy Docker zgłasza stan `restarting`, updater czeka przez skonfigurowany czas startu, zanim wycofa aktualizację. Jeśli kontener nadal nie wstanie, komunikat zawiera ograniczone i oczyszczone informacje o stanie oraz końcowe logi startowe pobrane przed usunięciem nieudanego kontenera. Poprzedni kontener jest przywracany.

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
