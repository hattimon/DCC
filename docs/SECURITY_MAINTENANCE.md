# Utrzymanie kontroli bezpieczeństwa i wydajności DCC

## Pierwsze uruchomienie

Po zaakceptowaniu zmian w GitHub uruchom `DCC checks` ręcznie z gałęzi domyślnej i sprawdź wyniki. Na PR do `main` kontrola `pr-gate` podsumowuje wymagane wyniki. Jeśli ochrona gałęzi wymaga starych, usuniętych z PR kontroli, zastąp je kontrolą `pr-gate` po jej pierwszym przebiegu.

W ustawieniach repozytorium włącz alerty Dependabot, aktualizacje bezpieczeństwa i grupowanie aktualizacji bezpieczeństwa. Konfiguracja grupuje poprawki Python i ogranicza rutynowe aktualizacje akcji do jednej grupy poprawek miesięcznie. Każda propozycja przechodzi zwykły przegląd oraz CI. Konfiguracja działa bez klucza do AI. [Opcje Dependabot](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference)

| Kiedy | Zakres |
|---|---|
| PR do `main` | Dobór zestawów do ścieżek zmian, Gitleaks na zmianach i kontrola workflow. Zmiany Web uruchamiają testy API, MCP i JS, kontrolę archiwum oraz pomiar monitoringu z limitem wywołań, zapisów i bajtów. |
| Zmiana manifestu lub Dockerfile | Dodatkowy skan rozwiązywanych zależności Python na Windows lub Linux, w tym zależności przechodnich. |
| Poniedziałek 04:23 UTC lub uruchomienie ręczne | Gitleaks dla bieżącego drzewa, audyt manifestów i Grype dla publicznych obrazów Web, Updatera i zrok na AMD64 oraz ARM64. |
| Kandydat do wydania | Istniejące kontrole instalatorów i migracji oraz kontrole obrazów dla wydania. `DCC release candidate checks` można uruchomić ręcznie. Workflow publikacji Updatera uruchomiony ręcznie na `main` ma prawo publikować. |

GitHub Actions uruchamia te kontrole na osobnych runnerach. Narzędzia skanujące mają przypiętą wersję i SHA-256. Skany PR używają uprawnień do odczytu repozytorium. Akcje mają przypięte pełne identyfikatory commitów. [Bezpieczne używanie GitHub Actions](https://docs.github.com/en/actions/reference/security/secure-use)

## Obsługa wyników

1. Zacznij od nazwy pakietu, identyfikatora podatności, wersji i źródła pakietu. Przy obrazach sprawdź obie architektury. Dla pakietów systemowych porównaj pełną wersję dystrybucji z jej trackerem, ponieważ dystrybucja może przenieść poprawkę do starszej wersji. Zgrupuj aliasy CVE i GHSA tego samego błędu.
2. Odtwórz problem na danych testowych, wprowadź możliwie małą poprawkę i zapisz wynik jej weryfikacji w raporcie. Dla obrazu sprawdź po kompilacji manifesty obu architektur, zgodność Compose, kontrolę zdrowia i zachowanie wolumenów. Przy zmianie zrok sprawdź stan zapisanych udostępnień i możliwość powrotu do poprzedniej wersji na kopii danych.
3. Przy nowym dopasowaniu Gitleaks potraktuj wynik jako dane do sprawdzenia. Przy rzeczywistym sekrecie unieważnij go zgodnie z procedurą jego dostawcy. W przypadku pliku `apps/dcc-web/static/vendor/xterm.js` porównaj zawartość z oficjalnym pakietem npm i udokumentuj każdą różnicę przed zmianą sumy w CI. Bieżący plik odpowiada xterm 6.0.0 po usunięciu komentarza mapy źródeł. [Oficjalna paczka npm](https://www.npmjs.com/package/@xterm/xterm/v/6.0.0)
4. Przed publikacją pakietów zachowaj dotychczasowy proces testowania aktualizacji z zainstalowanej wersji i porównania SHA-256. Sprawdzaj urządzenia tylko w zakresie przyznanego profilu i operacji DCC MCP. Publikacja i wdrożenie wymagają osobnej zgody.

## Przebieg lokalny

Uruchom wybrany zestaw z katalogu głównego repozytorium, w osobnym środowisku Pythona z odpowiednim manifestem. Przy testach Desktop bez ekranu ustaw `QT_QPA_PLATFORM=offscreen`. Pełne próby z demonem Dockera wykonuj na odizolowanym runnerze.

```powershell
python -m unittest discover -s tests -q
python -m unittest discover -s apps/dcc-web/tests -q
node apps/dcc-web/tests/frontend_unit.mjs
python tools/benchmark_web_monitoring.py --check
python -m unittest discover -s apps/container-updater/tests -q
```

Pomiar wykorzystuje tymczasowy katalog i symulowany transport Docker. Aby porównać wyniki, skopiuj sam skrypt do katalogu `tools` w osobnym checkoutcie bazy wskazanej w [raporcie](../SECURITY_PERFORMANCE_AUDIT.md). Uruchom go z tymi samymi parametrami w obu checkoutach, bez `--check`. Kontrola CI dopuszcza do dwóch pomiarów przy ośmiu równoległych klientach oraz 16 KiB odpowiedzi na klienta. Czas CPU i czas ścienny służą do porównań i zależą od runnera.

Po przerwaniu pracy zaktualizuj sekcję „Stan prac i wznowienie” w raporcie. Zapisz gałąź i bazę, ostatni udany przebieg, ewentualny błąd i konkretną następną komendę lub kontrolę. Przy wznowieniu zacznij od tej sekcji.
