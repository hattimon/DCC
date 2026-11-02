# Konfiguracja i profile

Panel zapisuje stan w katalogu --data lub DCC_WEB_DATA. Baza SQLite przechowuje użytkowników, sesje, zaszyfrowane sekrety, profile, katalogi, preferencje, audyt i próbki monitoringu. Nie zmienia magazynu profili ani pęku kluczy DCC Desktop.

| Profil | Sposób połączenia |
|---|---|
| local | Docker CLI i opcjonalny kontekst |
| tcp | API Docker z TLS oraz CA/certyfikatem klienta |
| ssh | Docker CLI przez weryfikowane SSH |
| balena | Balena CLI przez weryfikowane SSH |
| wsl | wsl.exe z wybraną dystrybucją |
| tunnel | Istniejący tunel do localhost; panel nie uruchamia dowolnych poleceń tunelu |

SSH/WSL wykonują operacje w środowisku docelowym. Pliki Compose i ścieżki montowań muszą być dostępne tam. Import Compose zapisuje pliki po stronie backendu. Profile mają domyślnie tylko odczyt; osobno można zezwolić na cykl życia, exec, obrazy, wolumeny, sieci, Compose, instalację, aktualizacje i operacje destrukcyjne. Rola użytkownika dodatkowo ogranicza dostęp. Puste ograniczenie użytkowników oznacza wszystkich zalogowanych, nadal zgodnie z rolą i prawami.

Import przyjmuje profile Web i starsze eksporty Desktop. Przenosi metadane, nie hasła. Sekrety wpisuje się osobno, a puste pola zachowują poprzednią zaszyfrowaną wartość. Eksport pomija hasła, passphrase i TLS.

| Zmienna | Znaczenie |
|---|---|
| DCC_WEB_DATA | Prywatny katalog danych |
| DCC_WEB_MASTER_KEY | Opcjonalny klucz Fernet dostarczony bezpiecznie |
| DCC_WEB_HTTPS=1 | Bezpieczne cookies i HSTS dla HTTPS |
| DCC_WEB_PUBLIC_ORIGIN | Dokładny publiczny origin HTTPS |
| DCC_WEB_HOSTS | Dozwolone nazwy hostów |
| DCC_WEB_PYTHON | Interpreter w Windows |
| DCC_MCP_TOKEN | Token zgody MCP przekazany środowiskiem |

Po zmianie zmiennych uruchom usługę ponownie. Domyślnie panel słucha na localhost. Dostęp sieciowy wymaga --allow-lan i istniejącego administratora. Nagłówki proxy nie są domyślnie zaufane. Interfejs jest domyślnie EN; wybór EN/PL zapisuje się dla użytkownika i steruje także językiem dokumentacji.

## Wspólne klucze i import Desktop

Ścieżka C:/Users/nazwa/.ssh/id_ed25519 opisuje komputer Desktop i nie jest automatycznie dostępna w kontenerze Linux. W Profile → Klucze i zaufane hosty można bezpiecznie przesłać wybrane klucze i known_hosts. Prywatne klucze są szyfrowane. Po imporcie Desktop zaznacz dopasowanie już wgranych kluczy po nazwie. Niezaznaczone profile pozostają bez zmian; profile mogą też mieć ścieżkę indywidualną.

Katalog zarządzany to /data/ssh w kontenerze. Alternatywny katalog musi już istnieć na hoście. Montuj go tylko do odczytu. Panel nie kopiuje automatycznie plików po ścieżce podanej przez użytkownika. Szczegółowy import, usuwanie i montowanie opisuje [przewodnik profili i bezpieczeństwa](profiles-security.md).

## SSH Agent

Agent SSH działa tylko wtedy, gdy proces serwera DCC Web widzi działający socket agenta i ma prawo z niego korzystać. Gdy kontener nie widzi agenta lub agent nie ma załadowanych kluczy, opcja nie jest dostępna w kreatorze profilu. Link do tej instrukcji pozostaje widoczny w panelu.

Na natywnym Linux Docker Engine załaduj wybrany klucz na hoście poleceniem ssh-add, a socket SSH_AUTH_SOCK zamontuj do istniejącej usługi DCC Web jako /run/dcc-agent.sock w Compose override. Zachowaj UID 10001 i nadaj socketowi dostęp temu UID/grupie. Nie ustawiaj socketu jako zapisywalnego dla wszystkich. Po zmianie odtwórz usługę z zachowaniem portów, wolumenu i pozostałych opcji.

Docker Desktop ma przekazywanie /run/host-services/ssh-auth.sock opisane dla macOS i Linux w [dokumentacji Docker](https://docs.docker.com/desktop/features/networking/networking-how-tos/#ssh-agent-forwarding). Potok Windows OpenSSH nie jest gniazdem Unix i nie można go bezpośrednio podmontować do Linuxowego kontenera. Dla Windows skonfiguruj zaufany most WSL/Unix i sprawdź dostęp socketu z kontenera albo wgraj zaszyfrowany klucz i podaj passphrase w profilu. [Natywny serwer Python](https://docs.paramiko.org/en/stable/api/client.html) może użyć obsługiwanego lokalnego agenta. Panel nie instaluje mostu ani agenta automatycznie.

Nie przekazuj agenta dalej do hosta SSH. Agent pozwala używać wszystkich załadowanych kluczy, dlatego zalecany jest dedykowany agent z ograniczonym zestawem tożsamości. Szczegóły: [oficjalna instrukcja Docker](https://docs.docker.com/desktop/features/networking/networking-how-tos/#ssh-agent-forwarding).

## Pozostałe funkcje

Aktualizator używa bezpiecznej usługi UpdateService, zachowuje szyfrowane dane i weryfikuje klucze hostów. Ustawienia pozwalają włączyć opcjonalne TOTP 2FA, odzyskiwanie przez zweryfikowany email z TLS SMTP i osobne domeny lokalne/publiczne. Zobacz [model bezpieczeństwa](security.md).