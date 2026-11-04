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

W **AI / MCP → Eksport** pobierz konfigurację dla klienta, którego wybrano przy tworzeniu dostępu. Dla Codex dostępne są trzy formaty.

- **Paczka projektu (ZIP).** Rozpakuj w katalogu głównym projektu. Paczka dodaje `.codex/config.toml` i działa w zaufanym projekcie. Jeśli ten plik już istnieje, scal z nim sekcję `dcc` z pliku TOML. Aby ograniczyć dostęp do projektu, usuń ewentualny wpis `dcc` z globalnego `~/.codex/config.toml`. Otwórz nowy czat w projekcie.
- **TOML.** Dodaj sekcję `[mcp_servers.dcc]` do `~/.codex/config.toml` lub do `.codex/config.toml` zaufanego projektu. Jeśli sekcja już istnieje, zaktualizuj istniejący wpis.
- **Wtyczka Codex (ZIP).** Rozpakuj archiwum do osobnego katalogu i uruchom w nim `codex plugin marketplace add .`. Następnie zainstaluj **DCC Web MCP** ze źródła **DCC Web** w katalogu wtyczek Codex. W razie potrzeby odśwież katalog lub uruchom ponownie Codex.

Jeśli konfiguracja używa `docker exec`, kontekst Dockera w Codex musi wskazywać na host z kontenerem DCC Web. Narzędzia MCP przyjmują identyfikator profilu w argumencie `profile`. DCC Web sprawdza, czy token obejmuje ten profil, i łączy się z adresem zapisanym w profilu. Adres urządzenia pozostaje w DCC Web.

### Gdzie podać token Codex

Codex CLI i Desktop odczytują tę samą konfigurację MCP. Otwórz terminal w głównym folderze projektu z rozpakowaną konfiguracją i wybierz instrukcję dla swojego systemu.

#### Windows

**Jedna sesja CLI w PowerShellu**

1. Otwórz nowe okno PowerShella w folderze projektu i wklej poniższy blok.
2. Po wyświetleniu monitu wklej token i naciśnij Enter. Codex CLI uruchomi się z tą zmienną.
3. Po zakończeniu pracy zamknij okno PowerShella.

```powershell
$dccToken = Read-Host 'Wklej token DCC' -AsSecureString
$env:DCC_MCP_TOKEN = [System.Net.NetworkCredential]::new('', $dccToken).Password
$dccToken.Dispose()
codex
```

**Zachowanie tokenu po restarcie dla CLI i Desktop**

1. W menu Start otwórz **Edytuj zmienne środowiskowe dla swojego konta**.
2. W sekcji **Zmienne użytkownika** kliknij **Nowa**. Wpisz `DCC_MCP_TOKEN` jako nazwę i wklej token jako wartość.
3. Zatwierdź zmiany. Otwórz nowe okno PowerShella albo zamknij całkowicie i uruchom ponownie Codex Desktop.

**Zaszyfrowany magazyn dla CLI**

Skonfiguruj lokalny magazyn `SecretStore` według [instrukcji Microsoft](https://learn.microsoft.com/en-us/powershell/utility-modules/secretmanagement/get-started/using-secretstore). Zapisz token raz. Następnie uruchamiaj Codex z folderu projektu, wczytując token do zmiennej w nowym oknie PowerShella.

```powershell
# Zapis jednorazowy
Set-Secret -Vault SecretStore -Name dcc-mcp -Secret (Read-Host 'Wklej token DCC' -AsSecureString)

# Przy uruchamianiu Codex w projekcie
& {
    $env:DCC_MCP_TOKEN = Get-Secret -Vault SecretStore -Name dcc-mcp -AsPlainText -ErrorAction Stop
    codex
}
```

#### macOS

1. Otwórz aplikację **Terminal** i przejdź do głównego katalogu projektu.
2. Uruchom poniższe polecenie. Po wyświetleniu monitu wklej token i naciśnij Enter.
3. Codex CLI uruchomi się w tym projekcie. Po wyjściu z CLI wartość znika ze środowiska tej sesji.

```sh
zsh -c 'printf "%s" "Wklej token DCC: " >&2; IFS= read -rs DCC_MCP_TOKEN && printf "\n" && export DCC_MCP_TOKEN && exec codex'
```

**Zachowanie tokenu w Pęku kluczy**

Zapisz token raz za pomocą pierwszego polecenia. Wklej token dopiero po wyświetleniu monitu. Przy kolejnych uruchomieniach użyj drugiego polecenia w katalogu projektu. macOS może poprosić o zgodę na odczyt z Pęku kluczy.

```sh
security add-generic-password -a "$USER" -s dcc-mcp -T "" -w
(dcc_token=$(security find-generic-password -a "$USER" -s dcc-mcp -w) && [ -n "$dcc_token" ] && DCC_MCP_TOKEN="$dcc_token" codex)
```

#### Linux

1. Otwórz terminal i przejdź do głównego katalogu projektu.
2. Uruchom poniższe polecenie. Po wyświetleniu monitu wklej token i naciśnij Enter.
3. Codex CLI uruchomi się w tym projekcie. Po wyjściu z CLI wartość znika ze środowiska tej sesji.

```sh
bash -c 'IFS= read -rsp "Wklej token DCC: " DCC_MCP_TOKEN && printf "\n" && export DCC_MCP_TOKEN && exec codex'
```

**Zachowanie tokenu w magazynie Secret Service**

W sesji z działającą usługą Secret Service, np. GNOME Keyring, użyj `secret-tool` z pakietu narzędzi libsecret. Pierwsze polecenie poprosi o token i zapisze go. Drugie uruchamia Codex z tokenem w katalogu projektu. Na hoście bez tej usługi możesz użyć powyższego monitu Bash.

```sh
secret-tool store --label='DCC MCP' service dcc-mcp account "$USER"
(dcc_token=$(secret-tool lookup service dcc-mcp account "$USER") && [ -n "$dcc_token" ] && DCC_MCP_TOKEN="$dcc_token" codex)
```

#### Token między uruchomieniami

Konfiguracja MCP w projekcie pozostaje po restarcie. Token zachowuje ważność do wygaśnięcia lub odwołania w DCC Web. Przykłady jednorazowe proszą o jego wartość przy każdym uruchomieniu. Jeśli masz oddzielne tokeny dla projektów, użyj innej nazwy zamiast `dcc-mcp` w poleceniach zapisu i odczytu dla każdego projektu. Program uruchamiający Codex CLI lub Desktop musi przekazać wartość jako `DCC_MCP_TOKEN`. Zmienna ustawiona w terminalu trafia do procesów uruchomionych z tego terminala.

Jeśli korzystasz z formularza niestandardowego serwera STDIO, w sekcji **Zmienne środowiska** wpisz `DCC_MCP_TOKEN` jako **Klucz**, a token jako **Wartość**. Codex zapisze wartość jawnie w swojej konfiguracji. Przy korzystaniu ze zmiennej systemowej lub powłoki wpisz tylko jej nazwę w polu **Klucz dostępu zmiennej środowiskowej**. Pliki TOML i ZIP z eksportu są już skonfigurowane do pobierania zmiennej ze środowiska.

Przechowuj token poza folderem projektu. Plik `.env` zawiera zwykły tekst i wymaga skryptu, który wczyta wartość do środowiska przed uruchomieniem Codex. Nawet jeśli Git ignoruje ten plik, agent z dostępem do projektu może go odczytać. W `AGENTS.md` możesz wskazać serwer MCP `dcc` i identyfikator profilu. Po uruchomieniu Codex sprawdź połączenie poleceniem `/mcp`.

Token ogranicza dostęp do wybranych profili i narzędzi DCC Web. Każdy czat, w którym ten serwer MCP jest dostępny, może korzystać z jego uprawnień. Konfiguracja zaufanego projektu pozwala zawęzić dostęp do projektu. **Odbierz dostęp** w DCC Web unieważnia token dla kolejnych wywołań.

Profile importowane z DCC Desktop są w Web domyślnie tylko do odczytu. MCP może wykonać wyłącznie operacje dozwolone jednocześnie przez dostęp MCP i uprawnienia danego profilu.

Schema profili znajduje się w `schemas/profile.schema.json`; walidacja runtime w `security.validate_profile`. Zobacz [Codex MCP](https://developers.openai.com/codex/mcp/), [transport stdio MCP](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) i [cykl życia MCP](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle).

Dostęp może trwać od 1 do 1 000 000 dni albo nie mieć terminu. Każdy token pozostaje odwoływalny, a istniejące dostępy zachowują swoje ustawienia.
