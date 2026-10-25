# DCC Container Updater 1.1.0

Check a single container from its table row, or use **Check selected…** to check several containers. Existing update checkboxes and **Update selected** keep their original behavior. Unselected scan results are preserved; newly discovered containers can be selected before a full scan.

Sprawdzanie jednego kontenera przyciskiem w wierszu lub kilku przez **Sprawdź wybrane…**. Dotychczasowe checkboxy aktualizacji i **Aktualizuj zaznaczone** działają jak wcześniej. Wyniki pozostałych kontenerów zostają zachowane; nowe kontenery można sprawdzić bez pełnego skanowania.

The image is published for Linux AMD64 and ARM64 as `ghcr.io/hattimon/dcc-container-updater:1.1.0` and `latest`. The installed panel detects the new image through its existing self-update check and requests confirmation before restarting. Settings and mounted data are retained.

[Setup and update instructions](https://github.com/hattimon/DCC/tree/main/apps/container-updater#readme)
