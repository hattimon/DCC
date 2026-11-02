# Docker Control Center 1.3.12

## PL

- Web: rozpoznawanie kluczy SSH po zawartości, wybór plików z folderu, jawne dopasowanie kluczy przy imporcie Windows i wybór agenta SSH.
- Web: kolumna autostartu z polityki restartu Docker oraz Deep Ocean jako domyślny motyw nowych kont.

- Sklep wyświetla jeden aktualny wpis danej aplikacji niezależnie od kategorii. Nowy tag obrazu zastępuje poprzednią wersję z katalogu wbudowanego, pamięci lub dodatkowego repozytorium.
- Starsze tagi liczbowe nie zastępują nowszych. Zachowane są osobne, jawnie nazwane warianty instalacji i aplikacje z innych repozytoriów obrazów.
- Walidacja katalogu i automatyzacja blokują powielone definicje wersji. Oficjalne wydania DCC Web są śledzone oddzielnie od Desktop, po sprawdzeniu obrazów amd64/arm64.
- DCC Web 0.1.3 zawiera tę samą poprawkę sklepu. Starsze DCC mogą nadal instalować Web z Administracji, a Container Updater z Aktualizacji. Format katalogu pozostaje zgodny ze schematem 1.
- Zachowano instalator NSIS, przekazanie aktualizacji w Windows, nazwy pakietów, skrypty i zależności DEB. Aktualizacja zachowuje profile i ustawienia. Linux jest budowany na Ubuntu 22.04 w celu zachowania zgodności z rodziną Debian/Ubuntu/MX Linux.

## EN

- Web: SSH key detection by content, folder file selection, opt-in Windows import key matching and explicit SSH agent authentication.
- Web: restart-policy autostart column and Deep Ocean as the initial default theme.

- The store displays one current entry per application across categories. A newer image tag replaces older bundled, cached or repository entries.
- Older numeric tags cannot downgrade newer entries. Explicit installation variants and unrelated image repositories remain separate.
- Catalog validation and maintenance reject duplicate version definitions. Web releases are tracked separately from Desktop and require published amd64/arm64 images.
- DCC Web 0.1.3 includes the same store fix. Legacy Desktop clients retain Administration for Web and Updates for Container Updater; catalog schema 1 remains supported.
- Existing NSIS installer, Windows update handoff, package names, Debian scripts and dependencies are retained. Upgrades preserve profiles/settings. Linux builds use Ubuntu 22.04 for Debian/Ubuntu/MX compatibility.

## Downloads

- `DockerControlCenter-Setup-1.3.12.exe`
- `DockerControlCenter_1.3.12_amd64.deb`
- `SHA256SUMS-1.3.12.txt`

Existing releases can detect v1.3.12 through the normal application updater. A client that has not yet installed the fix may continue to display its bundled older Web entry beside the current catalog entry.
