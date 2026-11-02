# Asystent konfiguracji AI

Asystent AI proponuje konfiguracje Docker i poprawia polecenia. MCP to osobna funkcja, która udostępnia klientom przyznane narzędzia tylko do odczytu. Żadna z nich nie daje automatycznego, nieograniczonego dostępu do Docker.

Administrator ustawia dostawcę, bazowy URL, model, opcjonalny klucz i włącza asystenta. Obsługiwane są OpenAI Responses (https://api.openai.com/v1), endpointy zgodne z OpenAI, np. http://127.0.0.1:1234/v1, oraz Ollama (http://127.0.0.1:11434). Klucz jest szyfrowany. Zmiana dostawcy lub endpointu usuwa zapamiętany klucz. Lokalny serwer bez uwierzytelniania go nie wymaga.

Serwer modelu musi już działać; DCC go nie uruchamia. W kontenerze localhost oznacza sam kontener. Dostęp do LAN wymaga zgody; publiczne API powinno korzystać z HTTPS, a redirecty są odrzucane.

## Propozycja, podgląd i zastosowanie

Asystent jest dostępny w osobnym widoku, konfiguracji nowego kontenera/Sklepu i edytorze istniejącego kontenera. Podaj polecenie lub opis; przed wysłaniem sprawdź poufne dane. Każde kliknięcie generowania wysyła żądanie i dostawca zewnętrzny może naliczyć opłatę. Typowe pola sekretów są maskowane.

Backend waliduje uporządkowaną propozycję przez normalny planer instalacji. Zastosowanie zmienia formularz, nie uruchamia modelowego tekstu. Instalacja i odtworzenie nadal wymagają uprawnień, podglądu i potwierdzenia. Równolegle działają maksymalnie dwa żądania.

Automatyczny wybór portu pokazuje zmiany w podglądzie; Docker weryfikuje końcowe przypisanie. Edycja pomija konflikt z portami edytowanego kontenera. Bezpieczny Updater zachowuje montowania i dane.

Testy adapterów używają mocków i modelu syntetycznego, bez płatnych wywołań. Po skonfigurowaniu modelu sprawdź go samodzielnie. Źródła: [OpenAI Responses](https://developers.openai.com/api/docs/guides/migrate-to-responses), [Chat Completions](https://platform.openai.com/docs/api-reference/chat/create), [Ollama](https://docs.ollama.com/api/generate).