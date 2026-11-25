# DCC Kiri Manager 0.1.1

**Wersja eksperymentalna**. Samodzielny panel WWW do odczytu zasobów silnika Kiri w repozytorium Docker Control Center (DCC). Kiri rozwija libracoder. Nazwy Kiri i Docker identyfikują oprogramowanie, z którym współpracuje panel.

![Ciemny przegląd DCC Kiri Manager z syntetycznymi danymi testowymi](site/assets/screenshots/dashboard-dark-pl.webp)

[English](README.md) · [Strona projektu](https://hattimon.github.io/DCC/kiri-manager/pl/) · [Wydanie GitHub](https://github.com/hattimon/DCC/releases/tag/kiri-manager-v0.1.1) · [Pakiet GHCR](https://github.com/hattimon/DCC/pkgs/container/dcc-kiri-manager) · [Wsparcie autora na Ko-fi](https://ko-fi.com/hattimon)

## Funkcje

- Rozpoznawanie tożsamości Kiri i negocjacja wersji API na jawnie skonfigurowanym sockecie Unix.
- Odczyt kontenerów, obrazów, wolumenów, sieci i usług Compose. Szczegóły, ograniczony podgląd logów oraz próbki CPU, RAM, sieci i operacji blokowych dla wybranego kontenera.
- Kreator pierwszego uruchomienia oraz trwały zapis profili, języka, motywu i odświeżania. Panel można otworzyć przy niedostępnym silniku.
- Logowanie lokalnego administratora z możliwością unieważnienia sesji. Serwer uruchamia się jako UID/GID 10001.

## Instalacja i połączenie

Zainstaluj panel w kategorii **DCC** w Sklepie DCC albo uruchom `docker compose up -d` z tego katalogu. Otwórz panel na hoście Docker. Przy pierwszym logowaniu użyj `admin` jako nazwy użytkownika i hasła. Przed wejściem do panelu ustaw własne hasło i w razie potrzeby zmień nazwę użytkownika. Konfiguracja i odzyskiwanie dostępu z terminala są w zwijanej sekcji na ekranie logowania. [Panel lokalny](http://127.0.0.1:8796) · [Instalacja i reset hasła](docs/installation.pl.md).

Kreator dobiera oficjalny instalator Kiri do platformy. Wspomagana instalacja na Debianie i Ubuntu weryfikuje pakiet dla architektury komputera i uruchamia usługę po zgodzie na hoście. Administrator udostępnia panelowi dedykowany socket i wybiera jego alias w kreatorze.

Ten sam obraz przygotowano do uruchomienia przez zgodne CLI Kiri. [Instrukcja instalacji](docs/installation.pl.md) obejmuje Docker, Sklep DCC, Kiri, WSL2, Ubuntu, Debiana, Raspberry Pi 4/5 oraz macOS Intel i Apple Silicon. [Macierz zgodności](docs/compatibility.md) podaje zakres dowodów. Potok Windows i sockety między osobnymi VM są poza zakresem konektora OCI w tej wersji.

## Dokumentacja

- [Audyt źródeł Kiri i macierz operacji](docs/kiri-audit.md)
- [Architektura i dane](docs/architecture.md)
- [API panelu](docs/api.md)
- [Bezpieczeństwo](docs/security.md)
- [Procedura wydania](docs/release.md)
- [Weryfikacja lokalna i w GitHub Actions](docs/verification.md)

Aby zaktualizować panel, pobierz zatwierdzoną wersję i odtwórz jego kontener z dotychczasowym wolumenem. Przed aktualizacją zrób kopię danych panelu. `docker compose down` usuwa kontener panelu z zachowaniem wolumenu. Instrukcja opisuje również cofnięcie wersji i instalację przez CLI.

Kod jest objęty [licencją MIT repozytorium DCC](../../LICENSE). Informacje o zależnościach i grafikach zawiera [wykaz licencji](docs/licenses.md). [Oficjalna strona Kiri](https://runkiri.com/).
