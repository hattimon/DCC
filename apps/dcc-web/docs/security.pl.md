# Model bezpieczeństwa

DCC Web zarządza Dockerem. Socket Docker, uprzywilejowany kontener, bind mount hosta lub plik Compose mogą dawać kontrolę nad hostem. Przeglądarka nie łączy się bezpośrednio z socketem. Uruchamiaj backend jako dedykowany użytkownik i ogranicz dostęp do zaufanych administratorów.

## Zaimplementowane zabezpieczenia

- Hasła są haszowane Scrypt; bootstrap Sklepu używa jednorazowego losowego hasła, a logowanie ma limity prób.
- Podpisane cookie jest rotowane, identyfikatory sesji są haszowane po stronie serwera, a sesja wygasa po 12 godzinach. Cookie jest HttpOnly/SameSite Strict. Konfiguracja HTTPS włącza Secure i HSTS.
- Zmiany wymagają CSRF i zgodnego Origin. Hosty mają allowlistę, CORS nie jest otwarty, serwer WebSocket nie jest uruchomiony.
- API sprawdza role i uprawnienia profilu. Profile są domyślnie read-only. Tokeny MCP są zakresowane, odwoływalne i przechowywane jako hashe.
- Potwierdzenia są jednorazowe, powiązane z operacją i celem oraz wygasają po 120 sekundach. Usunięcie wolumenu wymaga dodatkowej zgody; odinstalowanie i Compose down zachowują wolumeny.
- SSH sprawdza host key, TCP wymaga zweryfikowanego TLS, polecenia unikają host shell, a exec działa tylko wewnątrz kontenera.
- Fernet szyfruje sekrety. Windows chroni klucz DPAPI; Linux używa prywatnego pliku 0600. Chroń bazę, klucz, ACL i kopie.
- Odpowiedzi są escapowane; CSP jest restrykcyjne. Rozmiary, logi i historię ograniczono, a sekrety są redagowane. Audyt nie zapisuje treści żądań.
- Katalog zdalny pobiera wyłącznie HTTPS, sprawdza DNS i redirecty, odrzuca adresy prywatne, weryfikuje TLS i ogranicza dane.

## HTTPS i reverse proxy

Utrzymuj Waitress na 127.0.0.1:8789 i skonfiguruj zaufane reverse proxy TLS. Zachowaj Host i ustaw DCC_WEB_HTTPS=1, DCC_WEB_PUBLIC_ORIGIN=https://dcc.example.net oraz DCC_WEB_HOSTS=dcc.example.net. Zarządzane rozszerzenie Caddy obsługuje też opcjonalne lokalne HTTPS dla prywatnego adresu IP/nazwy: zachowuje HTTP i /data, wiąże port tylko z tym prywatnym/loopback adresem, skanuje porty 9443–9499 i przechowuje lokalne CA w trwałym wolumenie. Otwórz wybrany adres HTTPS, pobierz certyfikat publiczny CA i zaufaj mu na każdym urządzeniu klienckim; klucza podpisującego CA nie można pobrać. Lokalne TLS ustawia bezpieczne ciasteczka, ale nie wysyła HSTS, więc dotychczasowy HTTP pozostaje dostępny. Publiczne HTTPS jest osobną opcją wymagającą własnej domeny i osiągalnych portów 80/443. Nagłówki HTTPS z proxy są zaufane wyłącznie z tokenem danej instalacji, przechowywanym szyfrowanie z ustawieniami DCC Web; dowolne nagłówki proxy są odrzucane. Administratora do ręcznej instalacji publicznej utwórz lokalnie przez --init-admin. Obraz ze Sklepu tworzy losowe jednorazowe hasło przy pierwszym starcie i zapisuje je w logach kontenera. Ogranicz dostęp zaporą lub VPN. Nie ufaj wildcard CORS ani niezweryfikowanym nagłówkom proxy.

Przykładowa lokalizacja Nginx — certyfikaty i DNS konfiguruje administrator:

```
location / {
    proxy_pass http://127.0.0.1:8789;
    proxy_set_header Host dcc.example.net;
    proxy_set_header X-Forwarded-Proto https;
    client_max_body_size 2m;
}
```

## Zakres weryfikacji

Automatyczne testy obejmują logowanie, sesje, CSRF, role, szyfrowanie, potwierdzenia, polecenia, SSRF, katalog i MCP. Nie są certyfikacją pentestową. Transporty SSH/Balena/WSL są testowane mockami; nie wykonuje się destrukcyjnych operacji na infrastrukturze użytkownika. Redakcja nie rozpozna każdego sekretu aplikacji, więc nie wpisuj haseł w zwykłe logi.

MCP przekazuje klientowi metadane i logi jako niezaufane dane. Ta wersja nie ma narzędzi zapisu ani listenera HTTP. Dostęp administratora systemowego do katalogu danych omija granicę aplikacji. AI szyfruje sekrety, maskuje typowe pola, wymaga zgody dla sieci lokalnej, odrzuca redirecty i nigdy nie wykonuje wyniku modelu automatycznie.

## Pliki SSH

Zarządzanie plikami SSH jest dostępne administratorowi. Podgląd i audyt nie zawierają kluczy. Limity: 20 plików, 128 KiB na plik, 1 MiB łącznie. Obsługiwane są prywatne/publiczne klucze i known_hosts; ścieżki, urządzenia Windows, duplikaty i symlinki są odrzucane. Klucze prywatne są szyfrowane, pliki publiczne mają osobny ograniczony katalog, a zewnętrzne montowania są read-only.

Jednorazowe potwierdzenie wiąże się z hashami plików, katalogiem, zastępowaniem i konfiguracją zaznaczonych profili. Administrator hosta z kluczem głównym może odszyfrować pliki; chroń bazę i wolumen. Nie wgrywaj całego .ssh ani SSH config.

Docker CLI, Docker SDK i terminal hosta używają tych samych zaufanych known_hosts oraz Paramiko RejectPolicy. Brak pliku zatrzymuje połączenie. Panel nie dodaje automatycznie kluczy, nie uruchamia ssh-keyscan i nie zwiększa uprawnień.

Terminal hosta przez HTTP jest dozwolony tylko w przeglądarce na tym samym komputerze pod localhost/127.0.0.1/::1. Połączenie SSH z panelu do hosta pozostaje szyfrowane i sprawdza host key. Zdalne użycie panelu wymaga HTTPS.

Zobacz [przewodnik profili](profiles-security.md): kopie szyfrowane, usuwanie kluczy, 2FA, SMTP TLS i domeny.
