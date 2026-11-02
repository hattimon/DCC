# DCC Web 0.1.6

## English

- Host terminal sessions now work when DCC Web is opened over HTTP on the same computer (`localhost`, `127.0.0.1` or `::1`). Remote SSH remains encrypted and host-key verified. Access from another device still requires HTTPS.
- Added Polish formatted documentation; the documentation language follows the selected panel language.
- Collapsed the SSH keys and trusted hosts section by default and added SSH-agent setup guidance.
- Container MCP exports now use the verified DCC Web container through Docker CLI and forward the token by environment variable, preserving the non-root process and grant restrictions.
- Host-folder mount confirmations tolerate Docker returning unchanged mount entries in a different order; actual configuration changes still require a new confirmation.
- The Container Updater image workflow now publishes moving image tags only when its application version changes, avoiding false update notifications after unrelated source edits.

- Corrected the documentation regression test to verify both languages and valid internal anchors. Added terminal transport checks for loopback URLs behind Docker port forwarding, HTTPS enforcement, CSRF and profile permissions.

## Polski

- Terminal hosta działa teraz, gdy DCC Web jest otwarty przez HTTP na tym samym komputerze (`localhost`, `127.0.0.1` lub `::1`). Zdalne SSH pozostaje szyfrowane i weryfikuje klucz hosta. Dostęp z innego urządzenia nadal wymaga HTTPS.
- Dodano sformatowaną dokumentację po polsku; język dokumentacji odpowiada językowi wybranemu w panelu.
- Sekcja kluczy SSH i zaufanych hostów jest domyślnie zwinięta. Dodano odnośnik do instrukcji konfiguracji agenta SSH.
- Eksport MCP z kontenera używa rozpoznanego kontenera DCC Web przez Docker CLI i przekazuje token zmienną środowiskową, zachowując proces bez uprawnień roota oraz zakres nadanego dostępu.
- Potwierdzenie podłączenia folderu hosta jest odporne na zmianę kolejności tych samych montowań w odpowiedzi Docker. Rzeczywista zmiana konfiguracji nadal wymaga nowego potwierdzenia.
- Workflow obrazu Container Updater publikuje ruchome tagi tylko po zmianie wersji aplikacji, ograniczając fałszywe powiadomienia o aktualizacji po niezwiązanych zmianach kodu.

- Poprawiono test dokumentacji, aby sprawdzał oba języki i działające kotwice. Dodano testy terminala przez Docker bridge, wymagania HTTPS, CSRF i uprawnień profilu.

## Validation / Weryfikacja

- Windows: 108 Web tests, OK with two platform skips. Linux: all 108 Web tests passed.
- Catalog and Desktop store regression: all 54 tests passed. Source packaging and Desktop release compatibility checks: all 9 tests passed.
- Real Docker upgrade from Web 0.1.2 preserved profile configuration, encrypted credentials/keys and settings. MCP stdio initialization, tool restrictions and revocation passed through the exported Docker command. Read-only host-folder recreation passed; restart count remained zero.
- Sprawdzono aktualizację rzeczywistego kontenera z 0.1.2, zachowanie danych, szyfrowanie, unikalność wpisu sklepu, MCP i odtworzenie kontenera z folderem tylko do odczytu. Testy używają wyłącznie jednorazowych danych syntetycznych.
