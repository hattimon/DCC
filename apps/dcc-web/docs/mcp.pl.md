# AI / MCP

DCC Web udostępnia serwer MCP przez UTF-8 JSON-RPC po `stdio`. Nie wystawia transportu HTTP. Narzędzia obejmują odczyt kontenerów, inspekcji, logów, statystyk, obrazów, wolumenów i sieci, a także wybrane operacje cyklu życia, tworzenie kontenera i opcjonalne usuwanie kontenera.

Administrator tworzy osobny dostęp dla klienta, wybierając profile, konkretne narzędzia, tryb i czas ważności. Tryb **Tylko odczyt** jest domyślny. Tryb **Odczyt i modyfikacje** wymaga ponownego podania hasła oraz kodu 2FA, jeśli jest włączone. Uprawnienia profilu są sprawdzane ponownie przy każdym wywołaniu, więc cofnięcie ich od razu blokuje narzędzie. Nowy dostęp pokazuje token tylko raz i przechowuje wyłącznie jego SHA-256. Dostęp można w każdej chwili unieważnić.

## Zakres i zabezpieczenia

- `container_start`, `container_stop`, `container_restart`, `container_pause` i `container_unpause` wymagają uprawnienia cyklu życia kontenerów w każdym wybranym profilu.
- `create_container` wymaga uprawnienia instalowania aplikacji. Parametry są walidowane; nazwa musi być unikalna, porty nie mogą kolidować, wolumeny są wyłącznie nazwane, a opublikowany port domyślnie wiąże się z `127.0.0.1`. Narzędzie nie przyjmuje flag host-mount ani trybu privileged.
- `container_remove` wymaga włączenia osobnej zgody destrukcyjnej przy tworzeniu dostępu, wybrania narzędzia oraz uprawnienia destrukcyjnego w profilu. Usunięcie kontenera nie usuwa wolumenów.
- Każde wywołanie jest audytowane. Wyniki inspekcji i logów są redagowane; wartości zmiennych środowiskowych nie są zwracane przez narzędzia MCP. Treści logów i wyniki narzędzi traktuj jako niezaufane dane.
- Token ogranicza profile i listę narzędzi; nie daje ogólnego dostępu do Docker CLI. Transport HTTP i OAuth nie są udostępnione.

## Uruchamianie klienta

Uruchom proces z tym samym prywatnym katalogiem i użytkownikiem systemowym co backend:

```powershell
python apps/dcc-web/web.py --data PATH_TO_PRIVATE_STATE --mcp-stdio
```

Proces klienta musi otrzymać `DCC_MCP_TOKEN` z menedżera sekretów lub środowiska użytkownika. Nie wklejaj rzeczywistego tokenu do współdzielonego pliku konfiguracji. Stdout jest zarezerwowany na protokół, stderr na diagnostykę. Klient musi wykonać `initialize` i `notifications/initialized`. Serwer negocjuje wersje 2024-11-05, 2025-03-26, 2025-06-18 i 2025-11-25.

## Eksport konfiguracji

Konfiguracja Codex, VS Code, Claude, Cursor i innych klientów wskazuje nazwę zmiennej `DCC_MCP_TOKEN`; sam token jest pokazywany tylko raz. Dla instalacji kontenerowej eksporter rozpoznaje kontener DCC Web i używa `docker exec -i`. Klient musi mieć Docker CLI z kontekstem wskazującym host kontenera. Konfiguracja klienta nie jest zapisywana ani zmieniana automatycznie. Sprawdź format obsługiwany przez zainstalowaną wersję klienta.

Profile importowane z DCC Desktop są w Web domyślnie tylko do odczytu. MCP może wykonać wyłącznie operacje dozwolone jednocześnie przez dostęp MCP i uprawnienia danego profilu.

Schema profili znajduje się w `schemas/profile.schema.json`; walidacja runtime w `security.validate_profile`. Zobacz [Codex MCP](https://developers.openai.com/codex/mcp/), [transport stdio MCP](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) i [cykl życia MCP](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle).

Dostęp może trwać od 1 do 1 000 000 dni albo nie mieć terminu. Każdy token pozostaje odwoływalny, a istniejące dostępy zachowują swoje ustawienia.
