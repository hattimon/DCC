# DCC Web 0.3.2

Wersja 0.3.2 zachowuje oryginalne adresy paneli kontenerów i otwiera je przez chronioną sesję DCC przy wejściu publicznym. Dodaje izolację, cookies usług oraz obsługę formularzy, modułów JS i połączeń SSE/WebSocket. [Konfiguracja, bezpieczeństwo i ograniczenia](docs/panels.pl.md).

Monitoring sortuje CPU, RAM, RAM %, sieć, dysk I/O i liczbę procesów tak jak zakładka Kontenery: malejąco → rosnąco → kolejność domyślna. Sieć i dysk są porządkowane według sumy obu wyświetlanych kierunków.

Wersja 0.3.0 ponawia połączenie po awarii Internetu/DNS/zrok i odtwarza nieoczekiwanie zatrzymany tunel. Przy lokalnym włączaniu dostępu zaznacz **Wznawiaj tunel po restarcie DCC Web lub komputera**, aby zapisać zgodę na wznowienie. Osobno zaznacz zgodę dla Updatera, aby objąć aktualizacje obrazu. Wyłączenie dostępu anuluje wznowienie; publiczny panel pozostaje zamknięty do ponownej weryfikacji HTTPS.

Przy włączaniu zrok z lokalnego panelu administrator może zezwolić DCC Container Updaterowi 1.1.4 lub nowszemu na zatrzymanie i wznowienie tunelu podczas zgodnych aktualizacji Web. Oba obrazy DCC Web muszą obsługiwać przekazanie zgody. Przy pierwszej aktualizacji ze starszego Web wykonaj kroki wskazane obok blokady. [Opis wydania](https://github.com/hattimon/DCC/releases/tag/dcc-web-v0.3.2)

Wersja 0.2.7 ustawia dla profili BalenaOS standardowy port SSH 22222 i migruje profile ze starym domyślnym portem 22. Błędy SSH wskazują teraz typowe przyczyny, np. brak łączności, błąd uwierzytelniania lub weryfikacji klucza hosta. Przenosi też starszą sieć panelu DCC Remote Access do sprawdzonej puli podsieci, aby izolowana sieć nie przejmowała tras do zdalnych profili. Podczas migracji sidecar tunelu zostaje zatrzymany i po aktualizacji trzeba go ponownie włączyć. [Konfiguracja profili](docs/configuration.pl.md)

Wersja 0.2.6 obsługuje rezerwacje w domenie `shares.zrok.io` i pozwala dokończyć oczekującą rezerwację z zapisanym środowiskiem.

Wersja 0.2.5 naprawia błąd **Profile not found** podczas sprawdzania wyniku konfiguracji, włączania lub restartu Remote Access.

Wersja 0.2.4 naprawia instalację DCC Remote Access dla lokalnych profili Dockera z niestandardowym ID i przywraca moduł w kategorii **DCC** Sklepu aplikacji. Wersja 0.2.3 wprowadziła opcjonalny DCC Remote Access w instalacji Docker. Po aktualizacji istniejącego kontenera przez DCC Container Updater otwórz **Ustawienia → Administracja i bezpieczeństwo → Dostęp do panelu i HTTPS (TLS) → Zdalny dostęp przez Internet**. [Konfiguracja Remote Access](../dcc-remote-access/README.pl.md)

Wersja 0.2.2 dodaje pauzowanie grantów MCP, wybór profilu po nazwie lub adresie hosta, ręczne odświeżanie kontenerów oraz konfigurowalne sprawdzanie zmian. Wersja 0.2.1 pokazuje ID profilu pod jego nazwą, w sekcji „Szczegóły hosta” na ekranie „Przegląd” oraz obok adresu hosta na stronie „Kontenery”. Wersja 0.1.8 dodała opcjonalne lokalne HTTPS przez zarządzane rozszerzenie Caddy. Panel zachowuje dotychczasowy adres HTTP i dane; dla prywatnego IP/nazwy wybiera wolny port HTTPS z zakresu 9443–9499. Pobierz certyfikat lokalnego CA i zaufaj mu na urządzeniu klienckim. Publiczne HTTPS pozostaje osobną opcją wymagającą własnej domeny i portów 80/443. Wersja 0.2.0 naprawia otwieranie konfiguracji SMTP poczty odzyskiwania. Wersja 0.1.6 umożliwia otwieranie terminala hosta przez HTTP na tym samym komputerze, dodaje polską dokumentację i domyślnie zwija sekcję kluczy SSH. Wersja 0.1.4 naprawiła duplikaty sklepu. Starsze DCC Desktop po odświeżeniu katalogu znajdą Web w **Administracji**, a Updater w **Aktualizacjach**. Zmiana wersji Web nie wymaga nowego EXE/DEB.

[Polski](README.pl.md) · [English](README.md) · [Repozytorium GitHub](https://github.com/hattimon/DCC)

Wersja 0.2.4 dodaje eksport instrukcji agentów i paczek projektowych ZIP dla siedmiu klientów MCP. [Konfiguracja i eksport MCP](docs/mcp.pl.md#eksport-konfiguracji-i-instrukcji-agenta)

DCC Web to przeglądarkowy panel Docker Control Center, rozwijany jako osobny moduł obok aplikacji desktopowej na Windows i Linux. W Sklepie DCC pozycja znajduje się w kategoriach **DCC**, **Administracja** i **WWW**. Przycisk **Strona** prowadzi do tej prezentacji.

## Funkcje

- Zarządzanie kontenerami, obrazami, wolumenami, sieciami i projektami Compose.
- Lokalne i zdalne profile Docker, role użytkowników oraz szyfrowane dane profili.
- Terminal hosta w osobnym oknie i kartach: Windows, WSL, Linux PTY i zweryfikowane SSH.
- Sklep aplikacji DCC ze wspólnym katalogiem, wyszukiwaniem i podglądem instalacji.
- Interfejs po polsku i angielsku; wybór języka jest zapamiętywany.
- Lokalne efekty dźwiękowe włączone domyślnie, z regulacją głośności i możliwością wyłączenia.
- Widoczne porty i odnośniki do paneli, operacje na wielu kontenerach i postęp instalacji.

## Instalacja

Zaktualizuj DCC Desktop do wersji 1.3.11 lub nowszej, otwórz **Sklep aplikacji**, wybierz kategorię **DCC** i zainstaluj **DCC Web**. Panel używa trwałego wolumenu `dcc_web_data` i portu hosta wybranego przez DCC (domyślnie 8789).

Przy instalacji ze Sklepu DCC świeży kontener tworzy konto `admin` z silnym, losowym hasłem. Dane logowania pojawią się w wyniku instalacji, a hasło zostanie jednorazowo zapisane w logach kontenera. Zmień je po zalogowaniu. Instalator samodzielny nadal pozwala interaktywnie utworzyć administratora.

### Instalacja na Windows, macOS lub Linux

Pobierz [pakiet źródłowy DCC Web](https://github.com/hattimon/DCC/releases/download/dcc-web-v0.3.2/DCC-Web-0.3.2-source.zip), rozpakuj go i uruchom instalator z katalogu `DCC-Web-0.3.2`. Wybierz lokalny kontekst Docker; instalator nie obsługuje zdalnych endpointów, bo wystawia panel wyłącznie na localhost:

```powershell
py -3.12 apps/dcc-web/install.py
```

Na macOS i Linux użyj `python3 apps/dcc-web/install.py`. Potrzebne są Docker Engine/Desktop i Docker Compose v2. Instalator odczytuje opublikowane porty działających kontenerów oraz sprawdza możliwość lokalnego nasłuchu. Najpierw wybiera port 8789, a gdy jest zajęty, skanuje zakres 8790–8888. Wybrany port zapisuje w konfiguracji użytkownika. Jeśli inny proces zajmie port podczas uruchamiania, instalator ponawia próbę z kolejnym wolnym portem. Konto administratora tworzysz interaktywnie. Panel jest wystawiany tylko lokalnie, a instalator wyświetla końcowy adres. Istniejący kontener `dcc-web-standalone` pozostawia bez zmian.

Możesz też uruchomić panel natywnie przez Python 3.12: utwórz środowisko wirtualne, zainstaluj `apps/dcc-web/requirements.txt` i uruchom `apps/dcc-web/web.py`. W tym wariancie panel korzysta z Docker CLI i kontekstu skonfigurowanego dla bieżącego użytkownika.

## Bezpieczeństwo

Dostęp do `/var/run/docker.sock` daje panelowi administracyjną kontrolę nad hostem. Proces serwera działa jako UID 10001; kontener odczytuje grupę socketu i zachowuje tylko możliwości potrzebne do obniżenia uprawnień. Ogranicz dostęp HTTP do zaufanej sieci. Przed udostępnieniem panelu poza LAN skonfiguruj HTTPS, VPN lub zaufany reverse proxy.

## Dokumentacja i kod

[Instalacja](docs/installation.md) · [Bezpieczeństwo](docs/security.md) · [Profile](docs/configuration.md) · [Sklep](docs/catalogs.md) · [Funkcje i ograniczenia](docs/feature-matrix.md)

Kod źródłowy: [hattimon/DCC](https://github.com/hattimon/DCC/tree/dcc-web-v0.3.2/apps/dcc-web).


## Klucze SSH po imporcie profili

Ścieżka `C:/Users/.../.ssh/id_ed25519` z aplikacji desktopowej nie istnieje wewnątrz kontenera Linux. W zakładce **Profile → Wspólne pliki SSH** administrator może wybrać pliki na swoim komputerze i wgrać je do prywatnego folderu (domyślnie `/data/ssh` w trwałym wolumenie). Po podglądzie i potwierdzeniu zaznacz wybrane profile SSH/Balena checkboxami i wybierz **Użyj wspólnego folderu**. Pozostałe profile zachowają indywidualne ścieżki. Zaufany `known_hosts` jest wymagany; passphrase klucza wpisz osobno w profilu.

Można też wskazać istniejący folder serwera, zamontowany w kontenerze tylko do odczytu. Panel pokazuje ścieżkę i instrukcję kopiowania. Przeglądarka nie otworzy folderu serwera w lokalnym Eksploratorze; wybór plików otwiera lokalne okno systemowe. Klucze przechowuje wolumen, więc administrator hosta może je odczytać — zalecany jest osobny klucz z passphrase i połączenie HTTPS. Weryfikacja hosta SSH pozostaje włączona.

Zaznaczanie wszystkich profili pozwala również usunąć je zbiorczo po świadomym potwierdzeniu. Kontenery, wolumeny i pliki SSH pozostają zachowane, a terminale usuwanych profili są zamykane. Szczegóły: [konfiguracja](docs/configuration.md#shared-ssh-files-and-desktop-profile-imports) i [bezpieczeństwo](docs/security.md#ssh-file-storage).

## 0.1.4 — profiles and security / profile i bezpieczeństwo

[Wizard, encrypted keys/backups, 2FA, verified email recovery, read-only mounts and domains / instrukcja](docs/profiles-security.md).
