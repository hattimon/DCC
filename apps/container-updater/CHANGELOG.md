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
