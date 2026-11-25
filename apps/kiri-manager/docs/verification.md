# Weryfikacja lokalna wydania 0.1.0

Zweryfikowano 25 listopada 2026 na Windows w osobnym worktree opartym na `origin/main` (`8a71642`). Wyniki określają zakres dowodów dla wersji **EXPERIMENTAL**.

| Obszar | Wynik | Dowód |
| --- | --- | --- |
| Python, autoryzacja i trwałość | PASS | Python 3.12.10. 19 przypadków lokalnie. Windows wykonał 16, a 3 testy transportu Unix uruchomiono w linuksowych etapach BuildKit obu architektur. Zestaw obejmuje sesje, CSRF, limity, identyfikację silnika, filtrowanie danych i wycofanie migracji schematu SQLite. |
| Store i konfiguracja Compose | PASS | Walidacja pojedynczego wpisu, konflikt portu skorygowany przez istniejący DCC Web z zachowaniem loopback, parser Compose w wariancie z socketem, składnia skryptu instalacji. |
| Panel i statyczna witryna | PASS | Playwright 1.62.1 i Chromium na Windows. Zaliczone rozmiary 1920×1080, 1440×900, 1280×800, 768×1024, 390×844, 360×800. Zbadano oba motywy i języki, kreator, walidację, przełączanie profili, logi, rozłączenie i ponowne połączenie, galerię, klawiaturę, interakcję dotykiem i brak poziomego przewijania. |
| Obraz OCI | PASS | Docker Desktop BuildKit. Zweryfikowano manifesty, nieuprzywilejowanego użytkownika, wolumen, healthcheck i SHA warstw obrazu dla obu architektur. |
| Izolowany smoke test obrazu | PASS | Odłączone od sieci etapy BuildKit dla amd64 i emulowanego arm64. Start, gotowość, logowanie, ponowne uruchomienie, zachowana konfiguracja i odrzucenie domyślnego socketu Docker. Connector ćwiczył też rzeczywisty mechanizm Unix socket na kontrolowanej atrapie HTTP. |
| Docker jako natywne środowisko startowe | NOT TESTED | Zakres lokalny obejmował izolowane etapy BuildKit. Dedykowany workflow przygotowuje także rzeczywisty start kontenera na obu natywnych runnerach Linux. |
| Panel połączony z prawdziwym Kiri | NOT TESTED | Uruchomienie z dedykowanym socketem, named volume i restartem przygotowano na disposable runnerach GitHub. Przebieg wymaga zgody na udostępnienie gałęzi i uruchomienie workflow lub osobnego środowiska testowego. |
| Instalacja Kiri | NOT TESTED | Wariant wspomagany dla Debiana/Ubuntu przeszedł walidację składni. Windows ma potwierdzenie operatora, że oficjalny klient działa z Kiri 0.2.2, API 1.47. |
| Publiczne GHCR, Pages, katalog i wydanie | BLOCKED | Publikacja zależy od rzeczywistego testu Kiri, zatwierdzenia wydania i konfiguracji Pages. Artefakt witryny został złożony lokalnie z docelowymi odnośnikami canonical i metadanymi Open Graph. |

## Archiwum i pomiary

Artefakt lokalny znajduje się w `browser-artifacts/kiri-manager.oci.tar`. SHA-256 archiwum: `ace919ff3a808ca6faba40776edd3c988d2dd53a67c1997acf24a905c54cebef`.

| Architektura | SHA-256 manifestu | Warstwy skompresowane | Gotowość | RSS procesu po logowaniu |
| --- | --- | ---: | ---: | ---: |
| amd64 | `c15ecc745b78888d41ac341fd55e453a311bb567777980580943ec769ac09b25` | 46 998 368 B | 0,926 s | 38 156 KiB |
| arm64 emulowane | `a8de692ebb5783cafc58c4c93915790f27cbd0db702aacc27b6a176f9c6725d6` | 46 659 966 B | 3,892 s | 86 392 KiB |

W obu próbach serwer działał jako jeden proces Pythona. W jednosekundowym pomiarze bezczynności nie zarejestrowano taktów CPU procesu. To pomiar w izolowanym buildzie, a wynik emulacji nie opisuje Raspberry Pi ani natywnego ARM64.

## Zrzuty i inspekcja wizualna

Galeria w `site/assets/screenshots/` zawiera 12 WebP z prawdziwego panelu w Chromium. Dwa dodatkowe ujęcia pokazują polski dashboard. Dane testowe oznaczono jako **DEMO**. Grafika Open Graph `site/assets/social-preview.png` używa zrzutu panelu i ma 1200×630 px. Pliki JSON `browser-artifacts/panel-results.json` i `browser-artifacts/site-results.json` podają wynik każdej rozdzielczości.

Koncepcję i przeglądarkę porównano w zakresie typografii, kolejności sekcji, nawigacji, kolorów, widoczności tabel i układu mobilnego. Zmniejszono karty silnika w widokach zasobów na telefonie. Przesunięto tabelę wyżej w przeglądzie, poszerzono mobilną wyszukiwarkę i dodano podziałkę wykresów. Koncepcja przyjmowała metryki zbiorcze. W działającym panelu wykresy pokazują próbki jednego wybranego kontenera. Wizytówka używa tekstu zgodnego z rzeczywistym zakresem i bieżącą matrycą zgodności. [Macierz zgodności](compatibility.md) · [Plan wydania](release.md).
