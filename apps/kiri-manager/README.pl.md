# DCC Kiri Manager 0.1.3 (kandydat do przeglądu)

**Wersja eksperymentalna**. Samodzielny panel WWW do zarządzania zasobami silników Kiri i Docker w repozytorium Docker Control Center (DCC). Kiri rozwija libracoder. Nazwy Kiri i Docker identyfikują oprogramowanie, z którym współpracuje panel.

![Ciemny przegląd DCC Kiri Manager z syntetycznymi danymi testowymi](site/assets/screenshots/dashboard-dark-pl.webp)

[English](README.md) · [Strona projektu](https://hattimon.github.io/DCC/kiri-manager/pl/) · [Wydanie GitHub](https://github.com/hattimon/DCC/releases/tag/kiri-manager-v0.1.2) · [Pakiet GHCR](https://github.com/hattimon/DCC/pkgs/container/dcc-kiri-manager) · [Wsparcie autora na Ko-fi](https://ko-fi.com/hattimon)

## Funkcje

- Automatyczne wykrywanie socketów udostępnionych przez administratora, weryfikacja tożsamości Kiri i odczytu zasobów oraz przycisk **Połącz**. Problemy są wyjaśnione ze wskazaniem następnego kroku.
- Odczyt kontenerów, obrazów, wolumenów, sieci i usług Compose. Szczegóły, ograniczony podgląd logów oraz próbki CPU, RAM, sieci i operacji blokowych dla wybranego kontenera.
- Uruchamianie, zatrzymywanie, restart, pauza, wznowienie i usuwanie zatrzymanych kontenerów z potwierdzeniem oraz zachowaniem wolumenów.
- Profile SSH z weryfikacją klucza hosta i szyfrowanym hasłem lub kluczem prywatnym.
- Kreator pierwszego uruchomienia oraz trwały zapis profili, języka, motywu i odświeżania. Panel można otworzyć przy niedostępnym silniku.
- Logowanie lokalnego administratora z możliwością unieważnienia sesji. Serwer uruchamia się jako UID/GID 10001.

## Instalacja i połączenie

**Opublikowana wersja: 0.1.2.** Kandydat 0.1.3 nie został wydany; przed testami przeczytaj [notatki](RELEASE_NOTES_0.1.3.md). Zainstaluj opublikowany panel w kategorii **DCC** w Sklepie DCC albo uruchom `docker compose up -d` z tego katalogu. Otwórz panel na hoście Docker. Przy pierwszym logowaniu użyj `admin` jako nazwy użytkownika i hasła. Przed wejściem do panelu ustaw własne hasło i w razie potrzeby zmień nazwę użytkownika. Konfiguracja i odzyskiwanie dostępu z terminala są w zwijanej sekcji na ekranie logowania. [Panel lokalny](http://127.0.0.1:8796) · [Instalacja i reset hasła](docs/installation.pl.md).

W DCC na Windows otwórz **Sklep → DCC Kiri Manager**. Aplikacja sprawdzi oficjalny potok Kiri i zaproponuje **Połącz** lub **Zainstaluj Kiri** (oficjalna instrukcja instalatora). Po połączeniu z potwierdzonym silnikiem instalacja panelu wymaga jawnej zgody administratora i udanego testu socketu wewnątrz tymczasowego kontenera Kiri. Niepowodzenie testu nie zmienia istniejącego panelu ani wolumenu `dcc_kiri_manager_data`. Panel WWW sam wykrywa wyłącznie sockety wcześniej udostępnione przez administratora; ręczny kreator aliasów jest opcją zaawansowaną. Pomocnik Debiana/Ubuntu nadal wymaga zgody na hoście.

Ten sam obraz może działać przez CLI zgodne z Kiri. Potok Windows służy **aplikacji DCC na Windows**; **kontener panelu WWW** potrzebuje dostępnego w tym samym środowisku socketu Unix. Montowanie między osobnymi środowiskami WSL/VM pozostaje niezweryfikowane. Szczegóły: [instalacja](docs/installation.pl.md) i [macierz zgodności](docs/compatibility.md).

## Dokumentacja

- [Audyt źródeł Kiri i macierz operacji](docs/kiri-audit.md)
- [Architektura i dane](docs/architecture.md)
- [API panelu](docs/api.md)
- [Bezpieczeństwo](docs/security.md)
- [Procedura wydania](docs/release.md)
- [Weryfikacja lokalna i w GitHub Actions](docs/verification.md)

Aby zaktualizować panel, pobierz zatwierdzoną wersję i odtwórz jego kontener z dotychczasowym wolumenem. Przed aktualizacją zrób kopię danych panelu. `docker compose down` usuwa kontener panelu z zachowaniem wolumenu. Instrukcja opisuje również cofnięcie wersji i instalację przez CLI.

Kod jest objęty [licencją MIT repozytorium DCC](../../LICENSE). Informacje o zależnościach i grafikach zawiera [wykaz licencji](docs/licenses.md). [Oficjalna strona Kiri](https://runkiri.com/).
