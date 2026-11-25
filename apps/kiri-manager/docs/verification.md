# Weryfikacja 0.1.2

25 listopada 2026, izolowany worktree `codex/kiri-auto-detection`.

- Windows / PowerShell: bezpośredni odczyt przez `npipe:////./pipe/kiri` potwierdził nagłówek `Server`, odpowiedź `/version` i dostęp do listy kontenerów w rzeczywistym Kiri 0.2.2. Osobne testy syntetyczne sprawdziły odmowę dostępu i błędną tożsamość silnika.
- Instalator panelu: testy imitujące kontenery i wolumeny w izolacji; wymagana zgoda operatora w GUI, test dostępu w tymczasowym kontenerze przed utworzeniem panelu, ochrona istniejących paneli i `dcc_kiri_manager_data`. Dodatkowy test potwierdza, że brak dostępności HTTP nowego panelu z Windows usuwa tylko utworzony kontener, a odpowiedź usługi bez nagłówka `X-DCC-Panel: kiri-manager` nie przechodzi kontroli gotowości. Testy imitowane nie poświadczają uprawnień UID 10001 do socketu WSL ani przekierowania portu w rzeczywistym Kiri.
- Panel WWW: backend automatycznie rozpoznaje wyłącznie zatwierdzone endpointy po tożsamości Kiri i odczycie zasobów; połączenie wymaga zalogowanego administratora i CSRF. Alias, socket i terminal pozostają w opcjach zaawansowanych.
- Python: 54 zaliczone, 3 pominięte (testy Unix socket na Windows). Node: 3/3. Playwright 1.62.1: 13/13 scenariuszy dla panelu i witryny.
- Windows: oba EXE przeszły self-check. Kompilacja NSIS i regresja restartu instalatora przeszły. Pełnej aktualizacji zainstalowanej aplikacji desktopowej nie wykonywano.
- OCI: zweryfikowano konfigurację, manifesty i warstwy lokalnego archiwum dla linux/amd64 i linux/arm64. SHA-256 archiwum: `db893ec77622e90535b875bdb4687e450f4f8eafc7ee6e6ba61e3f0367145a97`.
- Aktualizacja na Docker Desktop (linux/amd64): kontener z opublikowanym obrazem 0.1.1, wymiana na lokalny obraz 0.1.2, restart i powrót do 0.1.1 na tym samym, izolowanym wolumenie. 0.1.2 zachowało konto i ustawienia. Po rollbacku login działał z hasłem zmienionym w 0.1.2, a wybrany język i motyw zostały zachowane.
- Oficjalna dokumentacja Kiri 0.2.2 potwierdza `npipe:////./pipe/kiri` na Windows oraz `/var/lib/kiri-daemon/.kiri/run/docker.sock` w dystrybucji WSL silnika. To nie dowodzi dostępności socketu z Docker Desktop lub innego WSL. Instalacja panelu zatrzymuje się, gdy test socketu w docelowym kontenerze nie przejdzie.

**Windows/WSL – NOT VERIFIED.** System odmówił dostępu do zarządzania Hyper-V, więc nie uruchomiono odizolowanego silnika Windows/WSL. Istniejąca instalacja Kiri posłużyła wyłącznie do odczytowej kontroli potoku.

---
# Weryfikacja wydania 0.1.0

Wyniki określają zakres dowodów dla wersji **EXPERIMENTAL**.

## Weryfikacja lokalna

25 listopada 2026 na Windows w osobnym worktree opartym na `origin/main` (`8a71642`).

| Obszar | Wynik | Dowód |
| --- | --- | --- |
| Python, autoryzacja i trwałość | PASS | Python 3.12.10. 19 przypadków lokalnie. Windows wykonał 16, a 3 testy transportu Unix uruchomiono w linuksowych etapach BuildKit obu architektur. Zestaw obejmuje sesje, CSRF, limity, identyfikację silnika, filtrowanie danych i wycofanie migracji schematu SQLite. |
| Store i konfiguracja Compose | PASS | Walidacja pojedynczego wpisu, konflikt portu skorygowany przez istniejący DCC Web z zachowaniem loopback, parser Compose w wariancie z socketem, składnia skryptu instalacji. |
| Panel i statyczna witryna | PASS | Playwright 1.62.1 i Chromium na Windows. Zaliczone rozmiary 1920×1080, 1440×900, 1280×800, 768×1024, 390×844, 360×800. Zbadano oba motywy i języki, kreator, walidację, przełączanie profili, logi, rozłączenie i ponowne połączenie, galerię, klawiaturę, interakcję dotykiem i brak poziomego przewijania. |
| Obraz OCI | PASS | Docker Desktop BuildKit. Zweryfikowano manifesty, nieuprzywilejowanego użytkownika, wolumen, healthcheck i SHA warstw obrazu dla obu architektur. |
| Izolowany smoke test obrazu | PASS | Odłączone od sieci etapy BuildKit dla amd64 i emulowanego arm64. Start, gotowość, logowanie, ponowne uruchomienie, zachowana konfiguracja i odrzucenie domyślnego socketu Docker. Connector ćwiczył też rzeczywisty mechanizm Unix socket na kontrolowanej atrapie HTTP. |
| Klient Kiri na Windows | PASS | Operator potwierdził, że oficjalny klient działa z Kiri 0.2.2 i API 1.47. |

## Integracja na GitHub Actions

25 listopada 2026 przebieg z PR #41 uruchomił testy na odizolowanych maszynach GitHub z Ubuntu 24.04.5 LTS na natywnych procesorach amd64 i arm64. Użył Kiri Lite 0.2.2 i obrazu panelu 0.1.0 z commita `0387a09`. SHA-256 archiwum OCI wynosi `8dba9600f291646112aea370256964a760a32e9c80425d69b0a258007f3930f1`. [Przebieg GitHub Actions](https://github.com/hattimon/DCC/actions/runs/45555032798).

| Architektura | Start i restart w Dockerze | Panel w Dockerze połączony z Kiri | Panel uruchomiony bezpośrednio w Kiri |
| --- | --- | --- | --- |
| amd64 | PASS | PASS | [PASS](https://github.com/hattimon/DCC/actions/runs/45555032798/job/139006058124) |
| arm64 | PASS | PASS | [PASS](https://github.com/hattimon/DCC/actions/runs/45555032798/job/139006058137) |

Na obu maszynach skrypt zainstalował oficjalny pakiet Kiri i nadał dostęp dedykowanemu kontu panelu o UID 10001. Test potwierdził ten sam identyfikator i architekturę obrazu w Dockerze i Kiri, odczyt wersji silnika, kontenerów, obrazów, wolumenów, sieci, usług Compose, logów i statystyk. Restart samego panelu zachował profil i ustawienia. Testy używały własnych zasobów Compose i osobnego wolumenu panelu.

Publikacja obrazu, Pages, katalogu i wydania wymaga osobnej zgody. [Macierz zgodności](compatibility.md) · [Plan wydania](release.md).

## Lokalne archiwum i pomiary

Artefakt lokalny znajduje się w `browser-artifacts/kiri-manager.oci.tar`. SHA-256 archiwum: `ace919ff3a808ca6faba40776edd3c988d2dd53a67c1997acf24a905c54cebef`.

| Architektura | SHA-256 manifestu | Warstwy skompresowane | Gotowość | RSS procesu po logowaniu |
| --- | --- | ---: | ---: | ---: |
| amd64 | `c15ecc745b78888d41ac341fd55e453a311bb567777980580943ec769ac09b25` | 46 998 368 B | 0,926 s | 38 156 KiB |
| arm64 emulowane | `a8de692ebb5783cafc58c4c93915790f27cbd0db702aacc27b6a176f9c6725d6` | 46 659 966 B | 3,892 s | 86 392 KiB |

W obu próbach serwer działał jako jeden proces Pythona. W jednosekundowym pomiarze bezczynności nie zarejestrowano taktów CPU procesu. To pomiar w izolowanym buildzie, a wynik emulacji nie opisuje Raspberry Pi ani natywnego ARM64.

## Zrzuty i inspekcja wizualna

Galeria w `site/assets/screenshots/` zawiera 12 WebP z prawdziwego panelu w Chromium. Dwa dodatkowe ujęcia pokazują polski dashboard. Dane testowe oznaczono jako **DEMO**. Grafika Open Graph `site/assets/social-preview.png` używa zrzutu panelu i ma 1200×630 px. Pliki JSON `browser-artifacts/panel-results.json` i `browser-artifacts/site-results.json` podają wynik każdej rozdzielczości.

Koncepcję i przeglądarkę porównano w zakresie typografii, kolejności sekcji, nawigacji, kolorów, widoczności tabel i układu mobilnego. Zmniejszono karty silnika w widokach zasobów na telefonie. Przesunięto tabelę wyżej w przeglądzie, poszerzono mobilną wyszukiwarkę i dodano podziałkę wykresów. Koncepcja przyjmowała metryki zbiorcze. W działającym panelu wykresy pokazują próbki jednego wybranego kontenera. Wizytówka używa tekstu zgodnego z rzeczywistym zakresem i bieżącą matrycą zgodności. [Macierz zgodności](compatibility.md) · [Plan wydania](release.md).
