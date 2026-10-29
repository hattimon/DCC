# DCC Container Updater 1.1.1

Fix scheduled updates incorrectly blocked by the updater's read-only directory views and system monitors' read-only views of the host filesystem. Real shared-data consumers, writable mounts, explicit data mounts, named volumes, explicit dependencies and Compose safeguards remain protected. Scheduled and manual updates use the same saved registry credentials, independently of browser login.

Naprawiono fałszywą blokadę aktualizacji z harmonogramu wywołaną przez podgląd katalogów tylko do odczytu w panelu aktualizacji i monitorze systemu. Zachowano ochronę rzeczywistych zależności i współdzielonych danych. Harmonogram korzysta z tych samych zapisanych danych rejestrów co aktualizacja ręczna, także po wylogowaniu z panelu.

# DCC Container Updater 1.1.0

Check a single container from its table row, or use **Check selected…** to check several containers. Existing update checkboxes and **Update selected** keep their original behavior. Unselected scan results are preserved; newly discovered containers can be selected before a full scan.

Sprawdzanie jednego kontenera przyciskiem w wierszu lub kilku przez **Sprawdź wybrane…**. Dotychczasowe checkboxy aktualizacji i **Aktualizuj zaznaczone** działają jak wcześniej. Wyniki pozostałych kontenerów zostają zachowane; nowe kontenery można sprawdzić bez pełnego skanowania.

The image is published for Linux AMD64 and ARM64 as `ghcr.io/hattimon/dcc-container-updater:1.1.0` and `latest`. The installed panel detects the new image through its existing self-update check and requests confirmation before restarting. Settings and mounted data are retained.

[Setup and update instructions](https://github.com/hattimon/DCC/tree/main/apps/container-updater#readme)
