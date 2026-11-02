# DCC Web 0.1.3

## PL

- Web: rozpoznawanie kluczy SSH po zawartości, wybór plików z folderu, jawne dopasowanie kluczy przy imporcie Windows i wybór agenta SSH.
- Web: kolumna autostartu z polityki restartu Docker oraz Deep Ocean jako domyślny motyw nowych kont.

- Jeden wpis aktualnej wersji aplikacji w sklepie Web, niezaleĹĽnie od liczby kategorii i starszych wpisĂłw w pamiÄ™ci katalogĂłw.
- Starszy katalog lub import nie zastÄ™puje nowszej wersji z tagiem liczbowym. Zachowane sÄ… osobne warianty instalacji i repozytoria aplikacji.
- DCC Web jest dostÄ™pny takĹĽe w starszych klientach w kategorii Administracja; Updater pozostaje w Aktualizacjach. Format katalogu pozostaje zgodny ze schematem 1.
- Katalog jest sprawdzany pod kÄ…tem duplikatĂłw. Automatyzacja Ĺ›ledzi wydania Web oddzielnie od Desktop i potwierdza dostÄ™pnoĹ›Ä‡ obrazĂłw amd64/arm64 przed zmianÄ… wpisu.
- Zmiana dotyczy kontenera Web. Nie opublikowano nowych instalatorĂłw EXE/DEB. Starsze pliki Desktop z zaszytym wpisem Web mogÄ… nadal pokazywaÄ‡ wĹ‚asny stary wpis; katalog JSON nie ma mechanizmu jego usuniÄ™cia z tych klientĂłw.

## EN

- Web: SSH key detection by content, folder file selection, opt-in Windows import key matching and explicit SSH agent authentication.
- Web: restart-policy autostart column and Deep Ocean as the initial default theme.

- One current application entry in the Web store across categories, including databases retaining older catalog entries.
- Older numeric image versions from caches or imports cannot downgrade a newer entry. Distinct installation variants and repositories are retained.
- Legacy clients find Web under Administration and Updater under Updates; catalog schema 1 remains supported.
- Duplicate definitions fail catalog validation. Maintenance tracks Web releases separately from Desktop and verifies amd64/arm64 images before advancing the catalog.
- Independent Web container update; the same desktop fix is included in the separate v1.3.12 EXE/DEB release. Previously published Desktop binaries containing an old bundled Web entry may still display it because their JSON schema has no removal instruction.
