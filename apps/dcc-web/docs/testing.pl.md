# Testowanie i odbiór

Z katalogu głównego repozytorium:

    python -m unittest discover -s apps/dcc-web/tests -p test_web.py -v
    python apps/dcc-web/web.py --self-check
    git diff --check

Testy używają tymczasowego stanu i jawnego FakeBackend. Produkcyjna aplikacja nie wybiera go. tests/review_server.py udostępnia lokalną trasę QA oraz profil syntetyczny i nie wchodzi do obrazu produkcyjnego.

Test przeglądarki wymaga Python Playwright i Chromium:

    python apps/dcc-web/tests/review_server.py --port 8790 --data PATH_TO_QA_ONLY_DATA
    python apps/dcc-web/tests/browser_smoke.py --url http://127.0.0.1:8790 --out PATH_TO_SCREENSHOTS

Dane testowe są syntetyczne i opisane w kodzie. Testy obejmują logowanie, wyszukiwanie, potwierdzenia, mock instalacji/zatrzymania, kategorie Updatera, logi, monitoring, Compose/MCP, profile, motywy, dźwięk, układy desktop/tablet/telefon i 1000 wierszy. CSP pozostaje restrykcyjne.

Desktop używa istniejącego zestawu tests/ z odizolowanym APPDATA/QSettings. Testy instalatora Windows wymagają NSIS i zbudowanego EXE. Pillow jest zależnością tylko testową. Testy Linux Updatera obejmują sukces, autoryzację, anulowanie i błąd; testy pakietów używają jednorazowych danych.

Należy odróżnić mocki, rzeczywistą instalację i GUI. Test headless nie potwierdza promptu polkit, interfejsu instalatora Windows, podpisu, każdego hosta ani zewnętrznego klienta MCP. Raport powinien opisywać wyłącznie wykonane sprawdzenia. Przed publikacją ręcznie sprawdź aktualizację, profile, ustawienia, wymagany transport oraz klienta MCP. Testy nie mogą usuwać kontenerów ani wolumenów użytkownika.

Rozszerzony test operatora uruchamia browser_extended.py względem serwera syntetycznego na 8790. Obejmuje karty, działania masowe, porty, AI, długie zgody i EN/PL. frontend_unit.mjs sprawdza tłumaczenie tekstu UI bez modyfikowania danych Docker.