# DCC — audyt bezpieczeństwa i wydajności

## Stan prac i wznowienie

**18 listopada 2026, audyt lokalny zakończony.** Checkout `D:\CODEX\DCC\.codex-dcc-web-032`, gałąź `codex/dcc-security-performance`, baza `78fb6b4a84a532dbd02af02bc59e7140835a71a3` z `hattimon/DCC`. Osobny checkout chroni istniejące zmiany w katalogu nadrzędnym `D:\CODEX\DCC`.

- **Gotowe.** Poprawki Desktop, Web, MCP i Updatera, testy regresji, benchmark, konfiguracja CI i [instrukcja utrzymania](docs/SECURITY_MAINTENANCE.md). Zakończono zestawy Windows, testy Updatera i próbę uprawnień Desktop na Ubuntu oraz skany lokalne. Wyniki są poniżej.
- **Następny etap.** Rozpocząć od przeglądu gałęzi. Po zaakceptowaniu publikacji uruchomić `DCC checks` i kontrole kandydata. Testy uruchomienia obrazów na obu architekturach, pełne aktualizacje z zainstalowanych wersji i pomiar na Raspberry Pi wymagają odizolowanego runnera lub urządzenia testowego.
- **Wznowienie po przerwaniu sesji lub wyczerpaniu tokenów.** Uruchom `git status --short --branch` i `git log -1 --oneline` w podanym checkoutcie. Zacznij od pierwszego kroku bez wyniku. Porównaj zmiany z bazą podaną na górze. Uruchomione polecenia i katalogi tymczasowe mogą wygasnąć przy przerwaniu. Publikacja wymaga osobnej zgody.

## Zakres i potwierdzone ustalenia

Desktop to Python i PyQt, ze spakowanymi plikami PyInstaller oraz instalatorami NSIS i DEB. Web używa Flask, Waitress, SQLite, Jinja i JavaScript. MCP działa przez stdio oraz publiczny HTTPS z OAuth. Updater to osobna aplikacja Flask i Gunicorn korzystająca z Docker SDK i Compose. Sprawdzenie aplikacji odbyło się na danych syntetycznych, atrapach urządzeń, lokalnym loopback i publicznych obrazach pobieranych bez ich uruchamiania.

| Waga | Ustalenie i dowód | Poprawka i weryfikacja |
|---|---|---|
| Wysoka | **Passphrase SSH w Desktop.** Atrapa Paramiko otrzymywała passphrase w argumencie hasła logowania. Paramiko może użyć tego pola w uwierzytelnianiu hasłem, jeśli klucz zawiedzie. [Referencja Paramiko](https://docs.paramiko.org/en/stable/api/client.html#paramiko.client.SSHClient.connect) | Passphrase służy do odszyfrowania klucza. Tryb hasła pozostaje osobnym przypadkiem. Test asercją sprawdza rzeczywiste argumenty wywołania. |
| Wysoka | **Podmiana klucza hosta SSH w Desktop.** Każde nowe połączenie akceptowało nieznany klucz, bo klient nie wczytywał poprzednich kluczy. | Desktop wczytuje OpenSSH `known_hosts` i zapamiętuje pierwszy klucz w prywatnym pliku. Test zapisuje klucz i sprawdza odrzucenie podmiany. Przy pierwszym połączeniu niezależnie zweryfikowany klucz można umieścić w OpenSSH `known_hosts`. |
| Wysoka | **Ponowna odpowiedź DNS dla połączenia AI w Web.** Test z atrapą resolvera pokazał, że po zatwierdzeniu adresu publicznego połączenie otwierało się na adresie link-local. Wymaga skonfigurowanego połączenia z odpowiednią nazwą DNS. | Gniazdo łączy się z wcześniej sprawdzonym adresem. Oryginalna nazwa służy nadal do Host i weryfikacji TLS. Test obejmuje zmianę DNS i odrzucenie zabronionego adresu. |
| Wysoka | **Poświadczenia w Web API.** Testowe hasło z URL bazy danych pojawiało się w odpowiedzi inspekcji kontenera mimo maskowania kluczy takich jak `PASSWORD`. | Wspólna funkcja maskuje dane logowania w URL. Test pokrywa inspekcję i podgląd Compose. Zanonimizowane pola i rozpoznane formaty są pokryte, a dowolne logi aplikacji nadal mogą zawierać sekrety w innych formatach. |
| Wysoka | **Nieaktualna zgoda MCP.** W lokalnym OAuth zatwierdzenie ekranu otwartego przed zmianą zakresu grantu kończyło się wydaniem kodu. | Podpisany stan formularza wiąże akceptację z wyświetloną rewizją. Po zmianie rewizji POST zwraca 403. Ponowne otwarcie ekranu i akceptacja aktualnego zakresu działają. |
| Wysoka | **Powtórzenie sesji Updatera.** Kopia ciasteczka nadal otwierała API po wylogowaniu oraz po zmianie hasła. | Istniejące logowanie wydaje odwoływalną sesję powiązaną z aktualnym hashem hasła. SQLite przechowuje skróty losowych identyfikatorów, maksymalnie 128 aktywnych sesji i do 8 godzin ważności. Testy sprawdzają odrzucenie starych ciasteczek oraz dalsze działanie bieżącej sesji po zmianie hasła. Po aktualizacji starsze ciasteczka wymagają ponownego logowania. |
| Średnia | **Prawa i zapis lokalnych sekretów.** Desktop na POSIX zapisywał zakodowaną zawartość zwykłym zapisem zależnym od `umask`. W Updaterze test z przygotowanym dowiązaniem twardym wykazał nadpisanie innego pliku przez zapis tymczasowy poświadczeń rejestru. | Desktop ogranicza istniejący plik i nowy zapis do `0600` na POSIX, odrzuca dowiązania symboliczne przy odczycie i zachowuje DPAPI w Windows. Updater zapisuje ustawienia i raporty przez atomową podmianę losowego prywatnego pliku. Test ponawia próbę nadpisania. POSIX Desktop przechowuje zawartość jako base64 i chroni ją prawami systemu plików. |
| Średnia | **Pobieranie aktualizacji Desktop.** Wspólna ścieżka tymczasowa była przewidywalna, a testowo zmieniona zawartość mogła zostać przekazana do instalatora. Warunkiem jest możliwość podmiany pliku albo odpowiedzi. | Pobranie trafia do nowego prywatnego katalogu. DCC sprawdza HTTPS także po przekierowaniu i porównuje SHA-256, gdy GitHub podaje skrót zasobu. Brak skrótu w starszym wydaniu nadal pozwala pobrać przez HTTPS. Test obejmuje odrzucenie zmienionej zawartości i porządkowanie niepełnego pobrania. |
| Regresja | **Koniec zadania Updatera przed zapisem raportu.** Test harmonogramu zarejestrował równoległe usuwanie danych testowych i zapis. Dodatkowa próba z zatrzymanym zapisem wykazała, że status był już `done`. | Status końcowy pojawia się po obsłużeniu raportu. Test czeka na rozpoczęcie zapisu i sprawdza moment udostępnienia wyniku. |
| Wysoka w zależnościach | **Web zawierał podatne `cryptography` 48.0.1.** Skan PyPI znalazł trzy osobne zgłoszenia w PKCS#7 i X.509. Wniosek dotyczy obecności wersji w projekcie. [GHSA-g6cj-pr64-35w5](https://github.com/pyca/cryptography/security/advisories/GHSA-g6cj-pr64-35w5), [GHSA-m2h6-j472-rp4c](https://github.com/pyca/cryptography/security/advisories/GHSA-m2h6-j472-rp4c), [GHSA-jwv3-5hgf-82ww](https://github.com/pyca/cryptography/security/advisories/GHSA-jwv3-5hgf-82ww) | Web używa 50.0.1, a Desktop ma dolną granicę 50.0.0. Uwzględniono również ustalenia dla `certifi`, Pillow w testach i `pip` w obrazach. Skan końcowych manifestów na Windows zakończył się powodzeniem. [Pillow 13](https://github.com/python-pillow/Pillow/releases/tag/13.0.0), [pip 26.3](https://pypi.org/project/pip/26.3/) |

Przegląd Web i testy objęły logowanie, wygaszanie sesji, CSRF, TOTP i kod odzyskiwania, role, odseparowanie profili, unieważnienie MCP i zgody narzędzi, wymaganie PKCE i HTTPS dla publicznego MCP, kontrolę Host i Origin, pliki SSH, walidację ścieżek i parametrów, izolację panelu proxy oraz ucieczkę tekstu w HTML. Web weryfikuje klucz hosta SSH i nie przyjmuje nieznanego klucza przy profilach wymagających jawnego `known_hosts`. Zdalny tryb Updatera nadal potrzebuje ochrony HTTPS i właściwych uprawnień do katalogu danych. Dostęp do gniazda Dockera daje szeroką kontrolę nad hostem. Polityki aplikacji i MCP ograniczają działania przez DCC, a izolacja kontenera zależy też od konfiguracji demona i hosta. [Zabezpieczenia dostępu do Dockera](https://docs.docker.com/engine/security/protect-access/)

## Obrazy i zależności systemowe

Grype 0.122.0 z bazą z 17 listopada 2026 sprawdził publiczne manifesty obu architektur. Poniżej liczby różnych identyfikatorów raportowanych przez skaner z dostępną poprawką. Alias GHSA i CVE może opisywać ten sam problem. Wynik oparty na nazwie i wersji komponentu wymaga sprawdzenia rewizji dystrybucji i tego, czy DCC używa podatnej funkcji.

| Publiczny obraz | Skompresowane warstwy AMD64 / ARM64 | Krytyczne / wysokie na każdej architekturze | Ustalenia |
|---|---:|---:|---|
| Web 0.3.4 | 130 805 482 B / 124 694 039 B | 1 / 10 | W obrazie nadal jest `cryptography` 48.0.1. Grype oznacza też bibliotekę Kerberos na podstawie numeru binarnego 1.20.1. Debian Bookworm przeniósł poprawkę CVE-2024-37371 do rewizji pakietu; tę pozycję trzeba porównać po pociągnięciu aktualnego obrazu i identyfikacji rewizji. [Debian Security Tracker](https://security-tracker.debian.org/tracker/CVE-2024-37371) |
| Container Updater 1.1.9 | 63 619 783 B / 62 778 270 B | 14 / 49 | Skan wskazał `curl` 8.14.1, OpenSSL i skompilowane zależności Docker Compose. `curl` w panelu służył do pobrania zweryfikowanego Compose podczas budowy. Został przeniesiony do osobnego etapu budowy. Adapter HTTP uruchamia `curl` w zatwierdzonym kontenerze docelowym, więc nadal zależy od narzędzi tego kontenera. Weryfikacja obrazu przed następnym wydaniem obejmuje brak `curl` i działanie Compose. Ocena OpenSSL wymaga pełnej rewizji Debiana, a zgłoszenie Go dotyczy obsługi HTTP/2 po stronie serwera. [Debian OpenSSL](https://security-tracker.debian.org/tracker/CVE-2026-63073), [GO-2026-6612](https://pkg.go.dev/vuln/GO-2026-6612) |
| zrok 2.0.9 | 174 813 270 B / 165 568 557 B | 6 / 119 | Krytyczne pozycje powtórzyły się w kandydacie 2.0.10 na obu architekturach. 2.0.10 zmienia format rejestru udostępnień i wymaga procedury wycofania. Wymiana wymaga obrazu z poprawkami i testu migracji na kopii stanu. [Informacje zrok 2.0.10](https://github.com/openziti/zrok/releases/tag/v2.0.10) |

Definicje obrazów DCC aktualizują `pip` w budowie, a GitHub Actions jawnie odświeża obrazy bazowe. Obrazy opublikowane pod powyższymi wersjami mają zawartość z chwili wydania. Różnica wielkości po zmianie Dockerfile i wynik ponownego skanu obrazu wymagają zbudowania kandydata. Pozostałe ustalenia w dostarczanych bibliotekach i gotowych programach wymagają zgodnych poprawek upstream oraz prób przed publikacją.

## Wyniki pomiaru monitoringu Web

Osiem równoległych kart, 48 kontenerów, 120 próbek historii i symulowane 120 ms opóźnienia Dockera. Pomiary na lokalnym Windowsie, na tych samych danych testowych. Skrypt `tools/benchmark_web_monitoring.py` nie potrzebuje działającego Dockera ani SSH.

| Metryka | Baza | Po poprawce |
|---|---:|---:|
| Wywołania Docker `stats` | 8 | 1 |
| Zapisy próbki | 8 | 1 |
| Łączna wielkość odpowiedzi | 10 014 537 B | 82 576 B |
| Czas do zakończenia wszystkich żądań | 1 377,3 ms | 240,1 ms |
| Czas CPU procesu | 1 265,6 ms | 109,4 ms |
| Szczyt alokacji Pythona | 16 253 539 B | 568 353 B |

Widok kontenerów pobiera bieżące statystyki bez historii. Równoczesne żądania o ten sam profil współdzielą pomiar i zapis, a żądania wykresów nadal mogą dostać historię. Oszczędność danych wyniosła 99,2%. Próbę można powtórzyć poleceniem `python tools/benchmark_web_monitoring.py --check`. Czas CPU i alokacje opisują próbę syntetyczną. Pomiar RSS, rozruchu i rzeczywistego ruchu SSH na Raspberry Pi wymaga osobnego urządzenia testowego.

## Weryfikacja

| Kontrola | Wynik |
|---|---|
| Windows | 172 testy, 1 pominięty test trybu POSIX. Test NSIS z nieistniejącym katalogiem rozpakowania PyInstaller przeszedł. NSIS zachowuje BOM i identyczną treść w obu plikach. |
| Ubuntu 22.04 | Cztery testy zabezpieczeń Desktop przeszły w WSL z Pythonem 3.10 i zależnościami aplikacji, w tym zmiana trybu pliku sekretów z `0644` na `0600`. Pełny zestaw testów używa Pillow 13, który wymaga co najmniej Pythona 3.11. Konfiguracja CI używa 3.12. |
| Instalator próbny | Wersja 1.3.12, 141 936 450 B, SHA-256 `12d2d7740a2b5b50881f50407e72b937b77d0c17f7a85222404ec147fd38357d`. Obie kontrolki `--self-check` przeszły. |
| Web / API / MCP | 227 testów, 2 pominięte testy agenta OpenSSH na Windows. Testy JavaScript oraz `--self-check` przeszły. Poprawność archiwum źródłowego 0.3.4 potwierdzona. |
| Updater | 254 testy na Windows, 20 pominiętych prób zależnych od platformy lub dostępnego narzędzia. Na Ubuntu 22.04 z Pythonem 3.10 i zweryfikowanym Compose 5.6.1 przeszły wszystkie 254. Przebiegi używały nieczynnego adresu demona i danych testowych. |
| Skan Python | `pip-audit 2.10.1 --strict` zakończył się kodem 0 dla rozwiązywania wszystkich trzech manifestów na Windows. |
| Sekrety i CI | Gitleaks nie zgłosił dopasowań po zawężeniu wyjątków do dokładnego hasła fixture oraz dwóch dopasowań w sprawdzonym pliku xterm. Kontrola SHA-256 jest częścią CI. Składnię workflow zweryfikowano za pomocą actionlint. |
| Wydania i produkcja | Próba NSIS uruchomiła nowy plik z nieistniejącym katalogiem rozpakowania PyInstaller. Pełna aktualizacja z zainstalowanej wersji oraz uruchomienie nowych obrazów z wolumenami pozostają w kontroli kandydata. Opublikowane obrazy sprawdzono w rejestrach, a konfiguracja produkcji nie była potrzebna do audytu. |

## Automatyzacja po akceptacji

Nowy workflow ogranicza PR do zmienionych komponentów i sprawdza koszt monitoringu. Cięższe kontrole migracji i instalatorów pozostały na etapie kandydata. Co tydzień GitHub Actions skanuje aktualne zależności, repozytorium i obrazy na obu platformach. Dependabot grupuje propozycje bezpieczeństwa. Zmiana zakresu uprawnień workflow pozostawia zapis w rejestrze wyłącznie zadaniom publikacji. Konfiguracja nie uruchamiała się jeszcze w GitHub Actions dla tej gałęzi. [Instrukcja uruchomienia i obsługi](docs/SECURITY_MAINTENANCE.md)
