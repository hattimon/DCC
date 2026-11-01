# DCC Web 0.1.0

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

Przy pierwszym wejściu otwórz `/login` i utwórz własne konto administratora. Nie ma domyślnego hasła.

## Bezpieczeństwo

Dostęp do `/var/run/docker.sock` daje panelowi administracyjną kontrolę nad hostem. Proces serwera działa jako UID 10001; kontener odczytuje grupę socketu i zachowuje tylko możliwości potrzebne do obniżenia uprawnień. Ogranicz dostęp HTTP do zaufanej sieci. Przed udostępnieniem panelu poza LAN skonfiguruj HTTPS, VPN lub zaufany reverse proxy.

## Dokumentacja i kod

[Instalacja](docs/installation.md) · [Bezpieczeństwo](docs/security.md) · [Profile](docs/configuration.md) · [Sklep](docs/catalogs.md) · [Funkcje i ograniczenia](docs/feature-matrix.md)

Kod źródłowy: [hattimon/DCC](https://github.com/hattimon/DCC/tree/v1.3.11/apps/dcc-web).
