# Audyt i macierz funkcji Desktop/Web

DCC Desktop zachowuje swoje natywne dialogi, akcje, adaptery Docker/SSH/WSL, Sklep, RepoBuilder, pakowanie i testy. DCC Web udostępnia odpowiedniki przeglądarkowe, ale nie deklaruje pełnej zgodności z aplikacją natywną.

| Funkcja | DCC Web i ograniczenia |
|---|---|
| Docker lokalny/konteksty CLI | Profile, informacje i odczyt domyślny |
| Zdalny TCP | Profil TLS z CA i certyfikatem klienta |
| SSH/Balena | Zweryfikowane SSH i cytowane argumenty |
| Docker Desktop/WSL | Lokalny CLI lub wybrana dystrybucja WSL |
| Profile | Tworzenie, edycja, usuwanie, szyfrowany import/eksport |
| Tunele Desktop | Połączenie z już istniejącym tunelem localhost; Web go nie tworzy |
| Kontenery | Lista, stan, zdrowie, wyszukiwanie, porty, linki paneli, inspekcja |
| Cykl życia | Start/stop/restart/pauza/wznów/usunięcie po potwierdzeniu |
| Autostart | Zmiana polityki restartu po potwierdzeniu |
| Inspekcja | Dane Docker z redakcją sekretów |
| Terminal kontenera | Ograniczone polecenie nieinteraktywne; brak PTY/WebSocket |
| Edycja kontenera | Zmienne, komenda, użytkownik, katalog, porty i restart przez bezpieczny updater |
| Montowania/sieci | Zachowanie przy odtwarzaniu; zaawansowana edycja przez Compose |
| Logi | Odświeżanie, wyszukiwanie, pobieranie i wyróżnianie błędów |
| Monitoring | Statystyki i ograniczone wykresy CPU/RAM |
| Obrazy/wolumeny/sieci | Lista, inspekcja i podstawowe operacje po potwierdzeniu |
| Compose | Odkrywanie, import, walidacja, start/stop/logi; zdalny import wymaga pliku na hoście |
| Sklep | Wspólny katalog, podgląd instalacji i odinstalowanie bez usuwania wolumenów |
| Kategorie Sklepu | Wszystkie → Zainstalowane → pogrubione DCC → AI; wiele kategorii |
| Dodatkowe katalogi | GitHub/HTTPS/pliki, walidacja, cache i odświeżanie |
| Aktualizacje kontenerów | Bezpieczny UpdateService; ograniczenia zależą od adaptera |
| Motywy i dźwięk | Pięć motywów, podgląd na żywo, lokalne dźwięki |
| EN/PL | Pełny interfejs, trwały wybór języka i lokalizowana dokumentacja |
| Asystent AI | OpenAI, zgodny endpoint i Ollama; wynik propozycją, nie wykonywany automatycznie |
| MCP | Ograniczone, tylko do odczytu stdio |
| Instalacja systemu/ponowne uruchomienie hosta | DCC Web tego nie wykonuje |
| Tray, skróty i funkcje Qt | Pozostają funkcjami Desktop |
| Bezpieczeństwo Web | Logowanie, CSRF, RBAC, vault, potwierdzenia i audyt |

Operacje Web mają odpowiadające im endpointy API; niedostępny adapter zwraca błąd zamiast raportować sukces. Mock transportu sprawdza konstrukcję poleceń, a nie dostępność prawdziwego hosta. Testy destrukcyjne korzystają wyłącznie z syntetycznych danych. Raport odbioru powinien oddzielać wyniki wykonane od planowanych.