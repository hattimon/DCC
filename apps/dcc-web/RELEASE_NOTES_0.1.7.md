# DCC Web 0.1.7

## English

- Added optional local HTTPS managed from Settings by a dedicated Caddy extension. It supports a private IP address or local DNS name, binds only to the selected private/loopback host address and scans Docker-published ports from 9443 to 9499.
- Kept the existing HTTP port and persistent `/data` volume unchanged. If Docker reports a host-port conflict after scanning, provisioning tries the next candidate; on failure, the previous HTTPS proxy is restored.
- Added authenticated proxy handling for Secure session cookies and the HTTPS-aware terminal, CSRF and Origin checks. Local HTTPS does not enable HSTS, so the existing HTTP endpoint remains usable.
- Added administrator-only download of the public local CA certificate. Open the local HTTPS URL once before downloading, then trust the CA on each client device. The CA private key remains in Caddy's persistent volume.
- Kept public HTTPS optional and separate; it still requires a public domain and reachable ports 80/443.
- Clarified local-host terminal access: a containerized Web profile manages its colocated Docker Engine through the socket, while a terminal on that server uses a separately authorized, host-key-verified SSH profile. Native host installs can open their own local shell.
- The App Store catalog loads independently from Docker. Installed-app scans and installation/removal run asynchronously and report progress, so a slow remote host does not block browsing.
- Added scoped MCP read/write grants, per-tool and per-profile checks, reauthentication for write access, optional destructive-operation consent and stdio-only transport.
- Added CPU and RAM sorting and an inline address beside the Containers title. Local profiles show the panel address used by the browser; SSH profiles show their configured SSH destination.
- Added an administrator SMTP test-send action and one-click select-all in profile permission setup; EN/PL selection remains saved.

## Polski

- Dodano opcjonalne lokalne HTTPS zarządzane z Ustawień przez osobne rozszerzenie Caddy. Obsługuje prywatny adres IP lub nazwę z lokalnego DNS, wiąże HTTPS tylko z wybranym prywatnym/loopback adresem hosta i skanuje porty Docker od 9443 do 9499.
- Zachowano dotychczasowy port HTTP i trwały wolumen `/data`. Jeśli Docker zgłosi zajęty port po skanowaniu, konfiguracja próbuje następnego; przy błędzie przywraca poprzednie rozszerzenie HTTPS.
- Dodano uwierzytelnioną obsługę proxy dla bezpiecznych ciasteczek sesji oraz kontroli HTTPS, terminala, CSRF i Origin. Lokalne HTTPS nie włącza HSTS, więc dotychczasowy adres HTTP nadal działa.
- Administrator może pobrać publiczny certyfikat lokalnego CA. Najpierw otwórz lokalny adres HTTPS, a potem zaufaj certyfikatowi na każdym urządzeniu klienckim. Prywatny klucz CA pozostaje w trwałym wolumenie Caddy.
- Publiczne HTTPS pozostaje opcjonalne i oddzielne; wymaga domeny publicznej oraz osiągalnych portów 80/443.
- Doprecyzowano terminal lokalnego hosta: kontenerowy Web zarządza lokalnym Docker Engine przez socket, a terminal tego serwera wymaga osobnego profilu SSH z weryfikacją klucza hosta i uprawnieniem. Natywna instalacja może otworzyć własną powłokę lokalną.
- Katalog sklepu ładuje się niezależnie od Dockera. Odczyt zainstalowanych aplikacji oraz instalacja i usuwanie działają asynchronicznie i pokazują postęp, więc wolny host zdalny nie blokuje przeglądania.
- Dodano zakresowane uprawnienia MCP do odczytu i zapisu, kontrolę narzędzi i profili, ponowne uwierzytelnienie zapisu, osobną zgodę na operacje destrukcyjne i wyłącznie transport stdio.
- Dodano sortowanie według CPU i pamięci oraz adres obok nagłówka Kontenery. Profil lokalny pokazuje adres panelu użyty przez przeglądarkę, a SSH — skonfigurowany host SSH.
- Dodano testową wysyłkę SMTP dla administratora i przycisk zaznaczenia wszystkich uprawnień w kreatorze profilu; wybór EN/PL jest zapamiętywany.

## Verification

The GitHub release workflow runs the DCC Web Python suite, catalog identity and maintenance tests, frontend checks, image build, socket-permission smoke test and source archive packaging before publishing the multi-architecture image and refreshing the official catalog.
