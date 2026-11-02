# DCC Web 0.1.5

## English

- Host terminal sessions now work when DCC Web is opened over HTTP on the same computer (`localhost`, `127.0.0.1` or `::1`). Remote SSH remains encrypted and host-key verified. Access from another device still requires HTTPS.
- Added Polish formatted documentation; the documentation language follows the selected panel language.
- Collapsed the SSH keys and trusted hosts section by default and added SSH-agent setup guidance.
- The Container Updater image workflow now publishes moving image tags only when its application version changes, avoiding false update notifications after unrelated source edits.

## Polski

- Terminal hosta działa teraz, gdy DCC Web jest otwarty przez HTTP na tym samym komputerze (`localhost`, `127.0.0.1` lub `::1`). Zdalne SSH pozostaje szyfrowane i weryfikuje klucz hosta. Dostęp z innego urządzenia nadal wymaga HTTPS.
- Dodano sformatowaną dokumentację po polsku; język dokumentacji odpowiada językowi wybranemu w panelu.
- Sekcja kluczy SSH i zaufanych hostów jest domyślnie zwinięta. Dodano odnośnik do instrukcji konfiguracji agenta SSH.
- Workflow obrazu Container Updater publikuje ruchome tagi tylko po zmianie wersji aplikacji, ograniczając fałszywe powiadomienia o aktualizacji po niezwiązanych zmianach kodu.
