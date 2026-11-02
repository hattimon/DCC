# DCC Web 0.1.1

[Polski](README.pl.md) · [English](README.md) · [Repozytorium GitHub](https://github.com/hattimon/DCC)

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

Pobierz [pakiet źródłowy DCC Web](https://github.com/hattimon/DCC/releases/download/v1.3.11/DCC-Web-0.1.1-source.zip), rozpakuj go i uruchom instalator z katalogu `DCC-Web-0.1.1`. Wybierz lokalny kontekst Docker; instalator nie obsługuje zdalnych endpointów, bo wystawia panel wyłącznie na localhost:

```powershell
py -3.12 apps/dcc-web/install.py
```

Na macOS i Linux użyj `python3 apps/dcc-web/install.py`. Potrzebne są Docker Engine/Desktop i Docker Compose v2. Instalator odczytuje opublikowane porty działających kontenerów oraz sprawdza możliwość lokalnego nasłuchu. Najpierw wybiera port 8789, a gdy jest zajęty, skanuje zakres 8790–8888. Wybrany port zapisuje w konfiguracji użytkownika. Jeśli inny proces zajmie port podczas uruchamiania, instalator ponawia próbę z kolejnym wolnym portem. Konto administratora tworzysz interaktywnie. Panel jest wystawiany tylko lokalnie, a instalator wyświetla końcowy adres. Istniejący kontener `dcc-web-standalone` pozostawia bez zmian.

Możesz też uruchomić panel natywnie przez Python 3.12: utwórz środowisko wirtualne, zainstaluj `apps/dcc-web/requirements.txt` i uruchom `apps/dcc-web/web.py`. W tym wariancie panel korzysta z Docker CLI i kontekstu skonfigurowanego dla bieżącego użytkownika.

## Bezpieczeństwo

Dostęp do `/var/run/docker.sock` daje panelowi administracyjną kontrolę nad hostem. Proces serwera działa jako UID 10001; kontener odczytuje grupę socketu i zachowuje tylko możliwości potrzebne do obniżenia uprawnień. Ogranicz dostęp HTTP do zaufanej sieci. Przed udostępnieniem panelu poza LAN skonfiguruj HTTPS, VPN lub zaufany reverse proxy.

## Dokumentacja i kod

[Instalacja](docs/installation.md) · [Bezpieczeństwo](docs/security.md) · [Profile](docs/configuration.md) · [Sklep](docs/catalogs.md) · [Funkcje i ograniczenia](docs/feature-matrix.md)

Kod źródłowy: [hattimon/DCC](https://github.com/hattimon/DCC/tree/dcc-web-v0.1.1/apps/dcc-web).
