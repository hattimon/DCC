# AI / MCP Preview

Transportem jest UTF-8 JSON-RPC przez stdio, z komunikatami rozdzielanymi nową linią. Narzędzia list_containers, inspect_container, container_logs, container_stats, list_images, list_volumes i list_networks są tylko do odczytu. Streamable HTTP, OAuth, zapis i operacje destrukcyjne są wyłączone. Nie ma ukrytego endpointu HTTP MCP.

Administrator tworzy zgodę z nazwą, istniejącymi profilami, narzędziami, klientem i terminem (także 2000 dni) albo wybiera Brak terminu. Token wyświetla się raz; przechowywany jest tylko SHA-256. Zgoda wymaga profilu read, nie przekracza zakresu i może być odwołana. Wywołania są audytowane, wyniki redagowane. Logi Docker traktuj jako niezaufane dane.

Uruchom proces z tym samym prywatnym katalogiem i użytkownikiem systemowym co backend:

```
python apps/dcc-web/web.py --data PATH_TO_PRIVATE_STATE --mcp-stdio
```

Środowisko procesu musi zawierać DCC_MCP_TOKEN. Stdout jest zarezerwowany na protokół, stderr na diagnostykę. Klient musi wykonać initialize i notifications/initialized. Serwer negocjuje wersje 2024-11-05, 2025-03-26, 2025-06-18 i 2025-11-25.

## Konfiguracja klientów

Instalacja natywna eksportuje prawdziwy interpreter, ścieżkę serwera i prywatnego katalogu. Instalacja kontenerowa rozpoznaje własny kontener i eksportuje polecenie `docker exec -i --env DCC_MCP_TOKEN ...`. Punkt wejścia uruchamia proces MCP jako UID 10001 z grupą socketu Docker. Token nie jest zapisywany w konfiguracji — przekazuje się jego wartość przez środowisko klienta lub obsługiwane pole sekretu. Na komputerze klienta musi działać Docker CLI z kontekstem wskazującym host tego kontenera. Pliki klienta nie są modyfikowane automatycznie.

Dla Codex ustaw serwer dcc, polecenie python i argumenty ścieżki web.py, --data, prywatny katalog i --mcp-stdio. Token powinien być przekazany przez środowisko. Klienci Claude, Cursor i Windsurf mogą użyć analogicznego wpisu JSON; nie umieszczaj rzeczywistego tokenu we wspólnym pliku. VS Code obsługuje wejście hasła promptString. Sprawdź dokumentację używanej wersji klienta. Testy integracyjne z zewnętrznymi klientami nie zostały wykonane.

## Profile i uprawnienia

Schema eksportu ma schema_version 1 i tablicę profiles z nazwą, typem połączenia, polami transportu, opcjonalnymi użytkownikami i uprawnieniami. Sekrety są szyfrowane osobno i nie trafiają do schema. MCP w tej wersji udostępnia tylko odczyt. Przyszłe operacje zapisu muszą egzekwować zakres profilu i interaktywne potwierdzenie.

Schema publiczna znajduje się w schemas/profile.schema.json. Walidacja runtime odbywa się w security.validate_profile. Zobacz [cykl życia MCP](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle), [transport stdio](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), [Codex](https://developers.openai.com/codex/mcp/) i [VS Code](https://code.visualstudio.com/docs/agents/reference/mcp-configuration).

Termin może wynosić od jednego dnia do 1000000 dni. Brak terminu zapisuje expires:null, ale zgodę nadal można odwołać i obowiązują zakresy profili/narzędzi. Istniejące zgody czasowe pozostają bez zmian.
