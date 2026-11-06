// Only authored UI strings/template fragments are translated. Interpolated Docker data is preserved.
let language='EN';
const pairs=`
Automatycznie otwieraj panele zdalne przez DCC Web|Automatically open remote panels through DCC Web
Przy publicznym wejściu panele otwierają się przez sesję DCC. Lokalne linki i kopiowane adresy pozostają bezpośrednie. Panel zachowuje własne logowanie.|Public access opens panels through your DCC session. Local links and copied addresses stay direct. Each panel keeps its own sign-in.
Ustaw adres hosta paneli w profilu|Set the panel host address in the profile
Otwórz przez DCC Web|Open through DCC Web
Narzędzia tylko do odczytu|Read-only tools
Narzędzia modyfikujące|Modifying tools
Uprawnienia MCP|MCP permissions
Edytuj dostęp MCP|Edit MCP grant
Zapisz dostęp|Save grant
Zmień termin ważności|Change expiry
Zezwól na dostęp terminalowy|Allow host terminal access
Urządzenia z dostępem terminalowym|Devices with host terminal access
Narzędzia terminala MCP|MCP terminal tools
Zapis zachowa obecny token. Wszystkie czaty używające tego tokena otrzymają nowy zakres. Otwarte terminale zostaną zamknięte.|Saving keeps the current token. All chats using it receive the new scope. Open terminals will be closed.
Ta zgoda włącza container_remove i potwierdza usuwanie. Wolumeny pozostają. Nie ogranicza poleceń wykonywanych przez terminal.|This consent enables container_remove and authorizes removal. Volumes remain. It does not restrict shell commands.
Polecenia działają jako użytkownik SSH profilu i mogą zmieniać lub usuwać dane hosta. Uprawnienia root lub sudo zależą od tego konta. Wybierz urządzenia osobno.|Commands run as the profile SSH account and can modify or delete host data. Root or sudo privileges depend on that account. Select devices separately.
Dostępne są profile SSH i Balena z uprawnieniem host.exec. Profil Local w kontenerze nie udostępnia terminala hosta.|SSH and Balena profiles with host.exec are eligible. A containerized Local profile does not provide a host shell.
Dostęp zapisany. Token pozostał ten sam. Połącz MCP ponownie i pobierz aktualne instrukcje.|Grant saved. The token is unchanged. Reconnect MCP and export updated instructions.
ZIP nigdy nie zawiera tokena. Wartość jest widoczna tylko przy utworzeniu dostępu; DCC zapisuje wyłącznie jej skrót. Zmiana zakresu zachowuje aktywny token. Po utracie tokena utwórz nowy dostęp.|The ZIP never contains the token. Its value is shown only when creating a grant; DCC stores only its hash. Scope edits preserve the active token. If it is lost, create a new grant.
System komputera z klientem MCP|MCP client computer platform
System klienta jest niezależny od systemu urządzenia. Instrukcja zawiera znane dane profili i osobny zakres terminala.|The client platform is separate from the device OS. Instructions include known profile facts and the separate terminal scope.
Instalacja krok po kroku|Step-by-step setup
Wybierz system klienta i pobierz paczkę projektu ZIP.|Select the client platform and download the project ZIP.
Rozpakuj w głównym katalogu projektu. Jeśli AGENTS.md lub konfiguracja już istnieją, rozpakuj osobno i scal pliki bez zastępowania własnych ustawień.|Extract at the project root. If AGENTS.md or configuration already exists, extract separately and merge without replacing your settings.
Sprawdź wymagany runtime opisany w README z paczki. Adres publicznego panelu nie jest endpointem HTTP MCP.|Check the runtime requirements in the bundled README. The public panel URL is not an HTTP MCP endpoint.
Jeśli DCC_MCP_TOKEN jest już w środowisku, zachowaj ją. Zamknij całkowicie klienta i uruchom go ponownie, aby odziedziczył aktualną zmienną. Nie wklejaj sekretu do czatu.|If DCC_MCP_TOKEN is already in the environment, keep it. Fully quit and restart the client to inherit the current value. Do not paste the secret into chat.
Otwórz zaufany projekt i nowy czat. Poproś o listę kontenerów przyznanego profilu przez DCC MCP. Udany odczyt potwierdza połączenie.|Open a trusted project and a new chat. Ask DCC MCP to list containers in a granted profile. A successful read confirms the connection.
Po zmianie zakresu: połącz MCP ponownie i scal nowy eksport instrukcji. Nie musisz zmieniać tokena.|After changing scope, reconnect MCP and merge the new instruction export. You do not need to change the token.
Paczka zawiera konfigurację, instrukcje agenta i README dla wybranej platformy. Nie instaluje ani nie nadpisuje plików automatycznie.|The package contains configuration, agent instructions and a README for the selected platform. It does not install or overwrite files automatically.
Podgląd i osobne pliki|Preview and individual files
ChatGPT Web — wymagane DCC MCP|ChatGPT Web — DCC MCP required
Alternatywa: wtyczka Codex|Alternative: Codex plugin
Użyj zamiast konfiguracji projektu. Rozpakuj w osobnym folderze, uruchom codex plugin marketplace add . i zainstaluj DCC Web MCP z tego źródła. Wtyczka także wymaga DCC_MCP_TOKEN i nie zawiera sekretu.|Use this instead of project configuration. Extract into a separate folder, run codex plugin marketplace add . and install DCC Web MCP from that source. The plugin also requires DCC_MCP_TOKEN and contains no secret.
Ładowanie zainstalowanych aplikacji z hosta. Katalog pozostaje dostępny.|Loading installed apps from the host. The catalog remains available.
Odświeżanie stanu hosta w tle; katalog pozostaje dostępny.|Refreshing host status in the background; the catalog remains available.
Stan hosta jest sprawdzany w tle|Host status is being checked in the background
Stan hosta nieznany|Host status unknown
Sprawdzanie hosta…|Checking host…
Sprawdzanie połączenia, portów i konfiguracji na wybranym hoście…|Checking the connection, ports and configuration on the selected host…
Konfiguracja sprawdzona. Przygotowuję bezpieczny podgląd instalacji…|Configuration checked. Preparing the installation review…
Nie udało się sprawdzić konfiguracji hosta. Szczegóły są widoczne powyżej.|Could not check the host configuration. Details are shown above.
Łączenie z hostem…|Connecting to host…
Adres odbiorcy testowego|Test recipient address
Wysyłanie testowego emaila…|Sending test email…
Testowy email został wysłany.|The test email was sent.
Wyślij wiadomość testową|Send test message
Bez zaznaczenia: wymagane STARTTLS. Certyfikat jest weryfikowany. Dane SMTP są szyfrowane. Test wysyła neutralną wiadomość i nie zapisuje ustawień.|Without this option, STARTTLS is required. The certificate is verified. SMTP credentials are encrypted. The test sends a neutral message and does not save settings.
Wybierz klucze i zaufany plik known_hosts z własnego komputera. Zawartość kluczy nie będzie wyświetlana. Eksport kluczy jest możliwy wyłącznie w szyfrowanej kopii po dodatkowym potwierdzeniu.|Select intended keys and a trusted known_hosts file from your computer. Key contents are never displayed. Exporting keys is possible only in a password-protected backup after additional confirmation.
Zezwalam na zapis wybranych plików SSH w prywatnym folderze DCC Web. Klucze prywatne zostaną zaszyfrowane w magazynie. Administrator hosta mający dostęp do klucza głównego może je odszyfrować. Zalecany jest osobny klucz z passphrase. Przesyłaj przez HTTPS lub lokalne połączenie.|I authorize storing the selected SSH files in DCC Web. Private keys will be encrypted in the vault. A host administrator with the master key can decrypt them. Prefer a dedicated passphrase-protected key. Upload over HTTPS or loopback.

Klucze i zaufane hosty|Keys and trusted hosts
Szyfrowany magazyn|Encrypted vault
Plik zewnętrzny — bez szyfrowania magazynu|External file — not encrypted by the vault
Plik publiczny|Public file
Usuń wybrane pliki|Delete selected files
Podłącz folder hosta|Connect host folder
Folder na hoście Docker|Directory on the Docker host
Folder hosta — tylko odczyt|Host directory — read-only
Zaawansowane ustawienia plików|Advanced file settings
Wgraj wybrane pliki z komputera. Klucze prywatne w magazynie DCC Web są szyfrowane. Nie musisz otwierać folderu kontenera.|Upload selected files from your computer. Private keys in the DCC Web vault are encrypted. You do not need to navigate into the container.
Zewnętrzne foldery pozostają tylko do odczytu. Agent podpisuje połączenie; nie udostępnia hasła ani klucza prywatnego do eksportu.|External directories remain read-only. An agent signs connections; it cannot export the password or private key.
Usunięte zostaną wybrane pliki z magazynu. Wskazane profile utracą dostęp do tych kluczy, a ich terminale zostaną zamknięte. Klucze na zdalnych hostach nie będą zmienione.|Selected vault files will be deleted. The listed profiles will lose access to these keys and their terminals will close. Remote authorized keys will not be modified.
Folder zostanie zamontowany tylko do odczytu. DCC Web uruchomi ponownie swój kontener; terminale zostaną zamknięte. Profile i dane pozostaną zachowane. Wybierz klucze, którym ufasz. Dla instalacji Compose użyj instrukcji w dokumentacji.|The directory will be mounted read-only. DCC Web will recreate its container and close terminals. Profiles and data are preserved. Select trusted keys. For Compose installations, follow the documentation.
Zezwalam panelowi korzystać z plików tego folderu oraz ponownie uruchomić DCC Web.|I authorize the panel to access this directory and restart DCC Web.
Szyfrowany eksport profili|Encrypted profile export
Eksport obejmie zaznaczone profile.|Selected profiles will be exported.
Eksport obejmie wszystkie profile.|All profiles will be exported.
Dołącz hasła i klucze z szyfrowanego magazynu|Include passwords and keys from the encrypted vault
Pliki z indywidualnych ścieżek i klucze agenta nie są pobierane automatycznie. Import przywraca profile tylko do odczytu.|Individual file paths and agent keys are not read automatically. Imported profiles are restored as read-only.
Hasło kopii — minimum 12 znaków|Backup password — at least 12 characters
Powtórz hasło kopii|Repeat backup password
Pobierz zaszyfrowaną kopię|Download encrypted backup
Hasła nie są identyczne|Passwords do not match
Wybierz eksport DCC Desktop albo szyfrowaną kopię DCC Web. Źródło pozostaje bez zmian.|Choose a DCC Desktop export or an encrypted DCC Web backup. The source remains unchanged.
Plik profili|Profile file
Wklej JSON zamiast pliku|Paste JSON instead of a file
Hasło szyfrowanej kopii — jeśli wymagane|Encrypted backup password — if required
Zastąp istniejące pliki SSH z tej kopii|Replace existing SSH files from this backup
Podgląd importu|Import preview
Wybierz profile do importu|Select profiles to import
Już istnieje — pominięty|Already exists — skipped
Uprawnienia po imporcie: tylko odczyt. Klucze i hasła z szyfrowanej kopii zostaną zapisane w szyfrowanym magazynie.|Imported permissions: read-only. Keys and passwords from encrypted backups will be stored in the encrypted vault.
Potwierdzam import wybranych profili. Istniejące profile nie zostaną nadpisane.|I confirm importing the selected profiles. Existing profiles will not be overwritten.
Nowe profile są domyślnie tylko do odczytu. Konfiguracja i klucze są szyfrowane. Eksport jest chroniony osobnym hasłem.|New profiles are read-only by default. Configuration and keys are encrypted. Exports require a separate password.
1 / 3 · Połączenie|1 / 3 · Connection
2 / 3 · Uwierzytelnianie|2 / 3 · Authentication
3 / 3 · Test i uprawnienia|3 / 3 · Test and permissions
Dalej|Next
Wstecz|Back
Zaawansowane|Advanced
Bez klucza|No key
Indywidualna ścieżka klucza na serwerze Web|Individual key path on the Web server
Wgraj klucz i zaufany known_hosts w sekcji Klucze i zaufane hosty. Nazwy kluczy są rozpoznawane niezależnie od rozszerzenia.|Upload a key and trusted known_hosts in Keys and trusted hosts. Keys are detected by content, regardless of extension.
Agent SSH dostępny|SSH agent available
Agent SSH niedostępny w kontenerze|SSH agent unavailable inside the container
Certyfikaty muszą być dostępne na serwerze DCC Web. Połączenie wymaga zweryfikowanego TLS.|Certificates must be accessible to the DCC Web server. Verified TLS is required.
To połączenie korzysta z lokalnego silnika i kontekstu Docker serwera DCC Web.|This connection uses the Docker engine and context of the DCC Web server.
Sprawdź połączenie|Test connection
Sprawdzanie połączenia…|Testing connection…
Domyślnie tylko odczyt. Włączaj wyłącznie potrzebne operacje.|Read-only by default. Enable only the operations you need.
Zapisz bez udanego testu połączenia|Save without a successful connection test
Sprawdź połączenie lub świadomie zapisz bez testu|Test the connection or explicitly choose to save without a test
Wygląd i dźwięki|Appearance and sounds
Administracja i bezpieczeństwo|Administration and security
Uwierzytelnianie 2FA|Two-factor authentication
2FA jest włączone|2FA is enabled
2FA jest wyłączone|2FA is disabled
Włącz 2FA|Enable 2FA
Wyłącz 2FA|Disable 2FA
Obsługiwane są aplikacje TOTP, np. Google Authenticator oraz aplikacje uwierzytelniające na iPhone. Kody odzyskiwania są jednorazowe.|Supports TOTP apps including Google Authenticator and iPhone authenticators. Recovery codes are single-use.
Odzyskiwanie dostępu|Account recovery
Brak zweryfikowanego adresu email|No verified recovery email
Reset 2FA przez email wymaga wcześniej zweryfikowanego adresu i hasła konta.|Email-based 2FA reset requires a previously verified address and your account password.
Najpierw skonfiguruj SMTP z TLS. Bez emaila możesz użyć jednorazowego kodu odzyskiwania.|Configure TLS SMTP first. Without email you can use a single-use recovery code.
Najpierw skonfiguruj SMTP z TLS.|Configure TLS SMTP first.
Zweryfikuj adres email|Verify recovery email
Ustawienia administracyjne|Administration settings
Poczta odzyskiwania — SMTP|Recovery email — SMTP
Domena lokalna i publiczna|Local and public domains
Pozostałe sesje zostaną wylogowane.|Other sessions will be signed out.
Przygotuj aplikację uwierzytelniającą. Sekretny klucz zobaczysz tylko podczas konfiguracji.|Prepare your authenticator app. The secret key is shown only during enrollment.
Dodaj konto w aplikacji TOTP|Add an account in your TOTP app
Wybierz ręczne dodanie konta w aplikacji: DCC Web, klucz poniżej, typ czasowy TOTP, 6 cyfr, 30 sekund.|Add an account manually: DCC Web, the key below, time-based TOTP, 6 digits, 30 seconds.
Kopiuj klucz|Copy key
Adres otpauth|otpauth URI
Kod z aplikacji|Authenticator code
Zapisz kody odzyskiwania|Save recovery codes
Zapisz te kody w bezpiecznym miejscu poza DCC Web. Każdy działa jeden raz. Nie zostaną pokazane ponownie.|Store these codes safely outside DCC Web. Each works once. They will not be displayed again.
Kody odzyskiwania|Recovery codes
Email odzyskiwania|Recovery email
Wyślij kod|Send code
Potwierdź adres email|Confirm recovery email
Kod z wiadomości email|Email verification code
Zweryfikuj|Verify
Adres email został zweryfikowany|Email address verified
Serwer SMTP|SMTP server
Port SMTP|SMTP port
Adres nadawcy|Sender address
Użytkownik SMTP|SMTP username
Hasło SMTP — puste zachowuje obecne|SMTP password — blank keeps the current value
TLS od początku (zwykle port 465)|Implicit TLS (usually port 465)
Bez zaznaczenia: wymagane STARTTLS. Certyfikat jest weryfikowany. Dane SMTP są szyfrowane. Nie jest używana płatna usługa SMS.|Otherwise STARTTLS is required. Certificates are verified. SMTP credentials are encrypted. No paid SMS service is used.
Domena lokalna|Local domain
Nazwa lub prywatny adres IP w sieci lokalnej|Local name or private IP address
Możesz podać prywatny adres IP, np. 192.168.0.222, albo nazwę z DNS/hosts. Lokalne HTTPS używa własnego CA; po instalacji pobierz certyfikat i zaufaj mu na urządzeniach. HTTP na dotychczasowym porcie localhost pozostaje dostępne.|Enter a private IP address such as 192.168.0.222 or a name from DNS/hosts. Local HTTPS uses its own CA; download the certificate after setup and trust it on your devices. HTTP on the existing localhost port remains available.
Nazwa w sieci lokalnej|Local network hostname
Dodaj w DNS routera lub pliku hosts wpis: adres IP hosta Docker → nazwa lokalna. To ustawienie dopuszcza nazwę w panelu; nie zmienia konfiguracji routera. Port panelu pozostaje bez zmian.|Add Docker host IP → local hostname in your router DNS or hosts file. This allows that name in the panel; it does not configure the router. The panel port is unchanged.
Domena publiczna|Public domain
Twoja domena publiczna|Your public domain
Publiczny DNS musi wskazywać hosta. Rozszerzenie Caddy może automatycznie uzyskać certyfikat HTTPS na portach 80/443. Wymaga publicznej osiągalności hosta. Przy CGNAT użyj własnego tunelu lub VPN i reverse proxy. Włącz silne hasło i 2FA przed publikacją.|Public DNS must point to this host. The Caddy extension can obtain HTTPS certificates automatically on ports 80/443. The host must be publicly reachable. With CGNAT, configure your own tunnel or VPN and reverse proxy. Enable a strong password and 2FA before publishing.
Zapisz domeny|Save domains
ID profilu|Profile ID
Adres hosta|Host address
Dostęp HTTPS|HTTPS access
Dostęp do panelu i HTTPS (TLS)|Panel access and HTTPS (TLS)
Adres IP, domenę i szyfrowanie ustawisz w sekcji „Dostęp do panelu i HTTPS (TLS)”. Uwierzytelnianie i odzyskiwanie konta mają osobne sekcje poniżej.|Set the IP address, domain and encryption in “Panel access and HTTPS (TLS)”. Authentication and account recovery have their own sections below.
Ustaw logowanie dwuetapowe i sposób odzyskania konta w sekcjach poniżej.|Set up two-factor authentication and account recovery in the sections below.
Lokalny adres IP, domena publiczna, szyfrowanie i certyfikat.|Local IP address, public domain, encryption and certificate.
Najpierw wybierz „Adresy panelu”, aby zapisać lokalny adres IP lub domenę. W „HTTPS i certyfikaty” włącz szyfrowanie i znajdź dokładny adres panelu oraz certyfikat CA.|Choose “Panel addresses” to save your local IP address or domain. Open “HTTPS and certificates” to enable encryption and find the exact panel URL and CA certificate.
Adresy panelu — IP i domeny|Panel addresses — IP and domains
HTTPS i certyfikaty|HTTPS and certificates
Logowanie i uwierzytelnianie 2FA|Sign-in and two-factor authentication
Serwer poczty, szyfrowanie TLS i test wysyłania kodów odzyskiwania.|Mail server, TLS encryption and a recovery message delivery test.
Skonfiguruj serwer poczty i wyślij wiadomość testową. Następnie zweryfikuj adres odbiorcy w sekcji „Odzyskiwanie dostępu”.|Configure the mail server and send a test message. Then verify the recipient address in “Account recovery”.
Konfiguruj pocztę odzyskiwania|Configure recovery email
Konto i użytkownicy|Account and users
Hasło konta oraz role i uprawnienia użytkowników panelu.|Account password and panel user roles and permissions.
Dostęp publiczny — domena|Public access — domain
Zapisz adresy i przejdź do HTTPS|Save addresses and continue to HTTPS
HTTPS (TLS) i certyfikaty|HTTPS (TLS) and certificates
Działa bez publicznej domeny. Panel wybierze wolny port od 9443 wzwyż i przypisze go tylko do wybranego prywatnego adresu hosta. Pobierz lokalny certyfikat CA, zaufaj mu na swoich urządzeniach i otwórz wyświetlony adres HTTPS. Numer portu jest częścią adresu i pozostaje zapisany.|Works without a public domain. DCC Web selects a free port starting at 9443 and binds it only to the selected private host address. Download the local CA certificate, trust it on your devices and open the displayed HTTPS URL. The port is part of the URL and remains saved.
HTTPS w sieci lokalnej|Local network HTTPS
Działa bez publicznej domeny. Panel wybierze wolny port od 9443 wzwyż. Przy pierwszym użyciu przeglądarka może nie ufać lokalnemu CA; pobierz certyfikat poniżej i zainstaluj go jako zaufany urząd certyfikacji.|Works without a public domain. DCC Web selects a free port starting at 9443. Your browser may not trust the local CA initially; download the certificate below and install it as a trusted certificate authority.
Pobierz lokalny certyfikat CA|Download local CA certificate
Włącz lokalne HTTPS|Enable local HTTPS
Zastosuj ustawienia lokalnego HTTPS|Apply local HTTPS settings
HTTPS publiczne|Public HTTPS
Włącz publiczne HTTPS|Enable public HTTPS
Zastosuj ustawienia publicznego HTTPS|Apply public HTTPS settings
Opcjonalne. Ustaw domenę publiczną, DNS i osiągalność portów 80/443, jeśli zechcesz wystawić panel z Internetu.|Optional. Configure a public domain, DNS and reachable ports 80/443 if you want to expose the panel to the Internet.
Wyłącz HTTPS|Disable HTTPS
Włącz zapisane tryby HTTPS|Enable saved HTTPS modes
Usuń rozszerzenie HTTPS|Remove HTTPS extension
HTTPS zostało skonfigurowane. Otwórz podany adres i pobierz lokalny certyfikat CA.|HTTPS is configured. Open the displayed address and download the local CA certificate.
Lokalne HTTPS utworzy lub zaktualizuje usługę Caddy, wybierze wolny port od 9443 wzwyż i zachowa wolumen danych oraz certyfikat CA.|Local HTTPS creates or updates the Caddy service, selects a free port starting at 9443, and preserves its data volume and CA certificate.
Operacja może zająć porty 80/443 i/lub port lokalnego HTTPS. Zatrzymanie wyłącza aktywne tryby, a usunięcie zachowuje wolumeny certyfikatów.|This operation may use ports 80/443 and/or the local HTTPS port. Stopping disables active modes; removing the extension preserves certificate volumes.
Potwierdzam zmianę konfiguracji HTTPS.|I confirm changing the HTTPS configuration.
Publiczny dostęp HTTPS|Public HTTPS access
Rozszerzenie działa na tym samym hoście Docker co DCC Web. Instalacja pobiera oficjalny obraz Caddy i publikuje porty 80 oraz 443. Certyfikaty są przechowywane w osobnym wolumenie.|The extension runs on the same Docker host as DCC Web. Installation pulls the official Caddy image and publishes ports 80 and 443. Certificates use a separate persistent volume.
Zainstaluj HTTPS|Install HTTPS
Włącz dostęp|Enable access
Wyłącz dostęp|Disable access
Usuń rozszerzenie|Remove extension
Sprawdź HTTPS|Check HTTPS
HTTPS działa poprawnie|HTTPS verified
Potwierdź operację HTTPS|Confirm HTTPS operation
Instalacja zajmie porty 80/443. Wyłączenie zatrzyma publiczny dostęp przez rozszerzenie. Usunięcie zachowuje wolumeny certyfikatów.|Installation reserves ports 80/443. Disabling stops public access through the extension. Removal preserves certificate volumes.
Potwierdzam zmianę publicznego dostępu HTTPS.|I confirm changing public HTTPS access.
Kod 2FA lub kod odzyskiwania — jeśli włączone|2FA or recovery code — if enabled

Agent musi być dostępny dla serwera DCC Web. Udostępnienie socketu pozwala panelowi używać kluczy załadowanych do agenta. Nie jest przekazywany dalej na zdalny host.|The agent must be accessible to the DCC Web server. Sharing its socket lets the panel authenticate with keys loaded into the agent. The agent is not forwarded to remote hosts.
Agent SSH — konfiguracja|SSH agent setup

Autostart|Autostart
Klucz prywatny|Private key
Klucz publiczny|Public key
Zaufane hosty|Trusted hosts
Nieobsługiwany plik|Unsupported file
Wymaga passphrase|Passphrase required
Dostępny|Available
Niedostępny lub brak kluczy|Unavailable or no keys
Wybierz folder SSH|Select SSH folder
Nie znaleziono kluczy SSH|No SSH keys found
Dopasuj klucze już wgrane do wspólnego folderu|Match keys already uploaded to the shared directory
Uwierzytelnianie SSH|SSH authentication
Automatycznie|Automatic
Klucz / hasło profilu|Profile key / password
Agent SSH|SSH agent

Postęp instalacji|Installation progress
Instalacja trwa…|Installation in progress…
Sprawdzanie konfiguracji|Checking configuration
Pobieranie obrazu|Pulling image
Tworzenie kontenera|Creating container
Uruchamianie i kontrola stanu|Starting and checking health
Odczyt logów i danych dostępowych|Reading logs and access details
Instalacja zakończona|Installation completed
Instalacja nie powiodła się|Installation failed
Kopiuj logi|Copy logs
Pobierz logi|Download logs
Pokaż dane dostępowe|Show access details
Wykryj dane dostępowe|Detect access details
Dane dostępowe wykryte w logach|Access details detected in logs
Nie wykryto gotowych danych logowania. Utwórz konto w aplikacji przy pierwszym uruchomieniu.|No ready-made credentials were detected. Create an account in the application on first launch.
Zamknięcie okna nie przerywa instalacji. Postęp można ponownie otworzyć w sklepie.|Closing this window does not cancel installation. Reopen progress from the store.
Kontener został utworzony. Sprawdź jego panel i stan uruchomienia.|The container was created. Check its panel and startup status.
Brak zapisanej instalacji|No saved installation
Kliknij, aby skopiować pełną ścieżkę obrazu|Click to copy the full image reference
Zaznacz grupę|Select group
Grupuj|Group by
Projekty|Projects
Projekt|Project
Lista płaska|Flat list
Samodzielne kontenery|Standalone containers
Bez sieci|No network
kontenerów|containers
uruchomionych|running
Zaznacz jeden kontener|Select one container
Brak uprawnienia profilu|Profile permission required
Włącz zarządzanie kontenerami|Enable container management
Profil zezwala na odczyt, ale zarządzanie kontenerami jest wyłączone.|This profile allows reading, but container management is disabled.
Profil zezwala na odczyt, ale zarządzanie kontenerami jest wyłączone. Możesz włączyć start, stop, restart, pauzę i edycję konfiguracji dla tego profilu.|This profile allows reading, but container management is disabled. You can enable start, stop, restart, pause and configuration editing for this profile.
Poproś administratora o uprawnienie containers.write.|Ask an administrator to enable containers.write.
Niektóre operacje nie powiodły się.|Some operations failed.
Wynik operacji zbiorczej|Bulk operation results
Infrastruktura hosta Docker|Docker host infrastructure
Odczytywanie infrastruktury…|Reading infrastructure…
Nie udało się odczytać infrastruktury hosta Docker.|Could not read Docker host infrastructure.
Aktywny profil|Active profile
Język|Language
Dokumentacja|Documentation
Wyloguj|Sign out
Twoje profile. Twoje dane.|Your profiles. Your data.
Sklep|Store
Terminal hosta|Host terminal
Adres SSH|SSH address
Maksymalna liczba sesji terminala|Maximum terminal sessions
Sprawdzaj aktualizacje panelu przy odświeżaniu|Check panel updates on refresh
Nowa zakładka|New tab
Zamknij zakładkę|Close tab
Połącz|Connect
Rozłącz|Disconnect
Kopiuj|Copy
Otwórz kolejne okno|Open another window
Włącz terminal dla tego profilu|Enable terminal for this profile
Połączenie z hostem…|Connecting to host…
Sesja terminala zakończona.|Terminal session ended.
Wpisywane polecenia działają na wybranym hoście.|Commands run on the selected host.
Terminal wymaga osobnego uprawnienia host.exec.|Terminal requires the separate host.exec permission.
Terminal|Terminal
Wszystkie|All
Zainstalowane|Installed
Zainstalowana|Installed
Niezainstalowana|Not installed
Przegląd|Overview
Kontenery|Containers
Kontener|Container
Uruchomione|Running
Uruchomiony|Running
Zatrzymane|Stopped
Zatrzymany|Stopped
Wstrzymane|Paused
Wstrzymany|Paused
Utworzony|Created
Zdrowy|Healthy
Nieznany|Unknown
Sukces|Success
Błąd|Error
Logi|Logs
Monitoring|Monitoring
Obrazy|Images
Obrazy Docker|Docker images
Wolumeny|Volumes
Sieć hosta|Host network
Sieci|Networks
Sieć|Network
Sklep aplikacji|App Store
Profile|Profiles
Profile połączeń|Connection profiles
Dziennik operacji|Audit log
Asystent AI|AI assistant
Asystent konfiguracji AI|AI configuration assistant
Ustawienia|Settings
Motywy|Themes
Nazwa|Name
Stan|State
Obraz|Image
CPU|CPU
Sortuj według CPU|Sort by CPU usage
Pamięć|Memory
Sortuj według RAM|Sort by memory usage
Sortuj według RAM %|Sort by memory percentage
Sortuj według Sieć|Sort by total network traffic
Sortuj według Dysk I/O|Sort by total disk I/O
Sortuj według Procesy|Sort by process count
Akcje|Actions
Porty / panele|Ports / panels
Porty|Ports
Dostępny port|Available port
Brak zmian konfiguracji|No configuration changes
Polityka restartu|Restart policy
Montowania i pozostałe ustawienia są zachowywane. Zmiana obrazu jest osobną operacją aktualizacji.|Mounts and other settings are retained. Image updates are a separate operation.
Porty — [IP:]HOST:CONTAINER/tcp lub /udp, po jednym na linię|Ports — [IP:]HOST:CONTAINER/tcp or /udp, one per line
Polecenie silnika (docker / balena / balena-engine, opcjonalnie)|Engine CLI (docker / balena / balena-engine, optional)
Port hosta|Host port
Port kontenera|Container port
Nowy kontener|New container
Uruchom|Start
Zatrzymaj|Stop
Pauza|Pause
Wznów|Resume
Więcej operacji|More actions
Operacje zaznaczonych|Selected actions
Zaznacz wszystkie|Select all
Zaznacz|Select
zaznaczonych|selected
Zaznaczone:|Selected:
Zaznacz kontenery|Select containers
Cykl życia|Lifecycle
Cykl życia kontenerów|Container lifecycle
Konfiguracja|Configuration
Diagnostyka|Diagnostics
Odnośniki i dane|Links and data
Aktualizacje i usuwanie|Updates and removal
Operacje kontenera|Container actions
Operacja|Operation
Operacje|Actions
Edytuj|Edit
Edytuj konfigurację startu|Edit startup configuration
Włącz autostart|Enable autostart
Wyłącz autostart|Disable autostart
Polecenie w kontenerze|Run command in container
Polecenie wewnątrz kontenera|Command inside container
Szczegóły|Details
Szczegóły konfiguracji|Configuration details
Szczegóły i konfiguracja|Details and configuration
Szczegóły zasobu|Resource details
Adresy paneli / porty|Panel addresses / ports
Kopiuj adres panelu|Copy panel address
Kopiuj szczegóły|Copy details
Kopiuj porty|Copy ports
Kopiuj sieci|Copy networks
Kopiuj dane|Copy data
Zaznacz i skopiuj|Select and copy
Skopiowano do schowka|Copied to clipboard
Sprawdź aktualizację obrazu|Check image update
Aktualizuj bezpiecznie obraz|Safely update image
Usuń kontener — zachowaj wolumeny|Remove container — retain volumes
Usuń kontenery|Remove containers
Usuń|Remove
Wynik aktualizacji|Update result
Wynik polecenia|Command output
Komenda|Command
Konfiguracja startu kontenera|Container startup configuration
Nowa komenda (opcjonalnie)|New command (optional)
Użytkownik kontenera (opcjonalnie)|Container user (optional)
Katalog roboczy (opcjonalnie)|Working directory (optional)
Zmienne do zmiany — pozostałe zostaną zachowane|Environment changes — other values are retained
Wymagana postać KEY=value|Use KEY=value format
Adresy HTTP/HTTPS są wyznaczane z opublikowanych portów TCP. Usługi inne niż WWW mogą nie obsługiwać przeglądarki.|HTTP/HTTPS addresses are inferred from published TCP ports. Non-web services may not open in a browser.
Operacje wymagają odpowiednich uprawnień profilu. Wolumeny nie są automatycznie usuwane.|Actions require profile permissions. Volumes are not removed automatically.
Sekrety środowiska są maskowane. Porty, montowania, healthcheck i konfiguracja pochodzą z Docker inspect.|Environment secrets are masked. Ports, mounts, health checks and configuration come from Docker inspect.
Polecenie działa wewnątrz wybranego kontenera. Docker socket lub uprzywilejowany kontener może zapewniać dostęp do hosta.|The command runs inside the selected container. A Docker socket or privileged container may provide host access.
Kontener zostanie odtworzony z zachowaniem konfiguracji i montowań przez istniejący bezpieczny updater DCC. Usługi Compose i sam Updater wymagają ich własnej ścieżki aktualizacji.|The existing DCC updater recreates the container while preserving configuration and mounts. Compose services and the Updater itself require their own update path.
Odtwórz kontener z nową konfiguracją. Montowania i pozostałe ustawienia zostaną zachowane.|Recreate the container with the new configuration. Mounts and other settings are retained.
Pełna kontrola cyklu życia — z zachowaniem danych.|Container lifecycle control while retaining persistent data.
Szukaj kontenera|Search containers
Szukaj nazwy lub obrazu…|Search name or image…
Filtr stanu|State filter
Wszystkie stany|All states
Twoje środowisko Docker w jednym miejscu|Your Docker environment in one place
Wszystkie w tym profilu|All in this profile
zatrzymanych|stopped
rdzeni hosta|host cores
Użycie kontenerów|Container usage
kontenerów w profilu|containers in this profile
kontenerów. Dane w wolumenach pozostaną zachowane.|containers. Volume data is retained.
kontenerów|containers
Zobacz wszystkie →|View all →
Ostatnie operacje|Recent actions
Dziennik →|Audit log →
Użycie zasobów|Resource usage
Bieżąca historia|Recorded history
Brak pomiaru|No measurement
Historia użycia CPU|CPU history
Historia użycia pamięci|Memory history
Pamięć (MiB)|Memory (MiB)
Szczegóły hosta|Host details
Architektura|Architecture
Architektury|Architectures
Sterownik|Driver
Wersja Engine|Engine version
Pamięć hosta|Host memory
Czas|Time
Wynik|Result
Logi i diagnostyka|Logs and diagnostics
Bieżący strumień zdarzeń z wybranego kontenera.|Current events from the selected container.
Automatyczne odświeżanie, wyszukiwanie i pobieranie logów.|Automatic refresh, search and log downloads.
Brak kontenerów w tym profilu.|No containers in this profile.
Szukaj w logach|Search logs
Szukaj w logach…|Search logs…
Liczba linii|Line count
Na żywo|Live
Pobierz .log|Download .log
Wyjście kontenera|Container output
Ładowanie logów…|Loading logs…
Ładowanie…|Loading…
linii|lines
CPU, pamięć, sieć i I/O. Historia obejmuje zebrane pomiary tego profilu.|CPU, memory, network and I/O. History contains measurements collected for this profile.
CPU kontenerów (%)|Container CPU (%)
Aktualne zasoby|Current resources
pomiarów|measurements
Dysk I/O|Disk I/O
Procesy|Processes
Wcześniej|Earlier
Teraz|Now
Wykres pojawi się po zebraniu co najmniej dwóch pomiarów|A chart appears after at least two measurements
Lokalne obrazy, tagi i pobieranie z rejestrów.|Local images, tags and registry downloads.
Repozytorium|Repository
Identyfikator|Identifier
Utworzony|Created
Rozmiar|Size
Pobierz obraz|Pull image
Obraz, np. alpine:3.22|Image, e.g. alpine:3.22
Szukaj zasobu…|Search resources…
Szukaj zasobu|Search resources
Nowy tag obrazu|New image tag
Docelowy tag|Destination tag
Nowy wolumen|New volume
Nazwa wolumenu|Volume name
Zakres|Scope
Nowa sieć|New network
Nazwa sieci bridge|Bridge network name
Połączenia kontenerów i szczegóły sieci Docker.|Container connectivity and Docker network details.
Trwałe dane kontenerów. Usuwanie wymaga dodatkowego potwierdzenia.|Persistent container data. Deletion requires additional confirmation.
Trwałe dane tego wolumenu zostaną bezpowrotnie usunięte. Wolumen używany przez kontener nie może być usunięty.|This volume's persistent data will be permanently deleted. Attached volumes cannot be removed.
Wybrany zasób zostanie usunięty. Wykorzystywane zasoby mogą blokować tę operację.|The selected resource will be removed. Resources in use can block this operation.
Przygotuj projekt Compose|Prepare Compose project
Projekty wykryte na wybranym hoście Docker.|Projects detected on the selected Docker host.
Up i Pull mogą zmienić obrazy usług. Down nie usuwa wolumenów. Konfiguracja i logi są dostępne bez uruchamiania projektu.|Up and Pull may change service images. Down retains volumes. Configuration and logs are available without starting the project.
Projekt|Project
Pliki konfiguracji|Configuration files
Zarządzaj →|Manage →
Nazwa projektu|Project name
Plik Compose YAML|Compose YAML file
Plik zostanie zapisany i zweryfikowany przez docker compose config. Uruchomienie projektu jest osobną, potwierdzaną operacją. Ścieżki montowań muszą być dostępne na wybranym hoście Docker.|The file is saved and validated by docker compose config. Starting the project requires separate confirmation. Mount paths must exist on the selected Docker host.
Zapisz i zweryfikuj dostarczony plik Compose.|Save and validate the supplied Compose file.
Projekt zweryfikowany|Project validated
Zapisany plik:|Saved file:
Uruchom ten zapisany projekt poleceniem Docker Compose albo wybierz go z listy przygotowanych projektów.|Start this saved project with Docker Compose or select it from the prepared project list.
Status usług|Service status
Sprawdź konfigurację|Check configuration
Logi projektu|Project logs
Uruchom / zastosuj konfigurację|Start / apply configuration
Pobierz obrazy|Pull images
Zatrzymaj i usuń kontenery projektu|Stop and remove project containers
Wynik Compose|Compose result
w wybranym projekcie. Wolumeny nie będą automatycznie usuwane.|in the selected project. Volumes are retained.
Operacje panelu i klientów MCP — bez zapisywania sekretów.|Panel and MCP client actions, without recording secrets.
Użytkownik|User
Cel|Target
Jeden katalog dla DCC Desktop i Web. Wybierz, sprawdź, zainstaluj.|One catalog for DCC Desktop and Web. Choose, review, install.
Katalogi|Catalogs
Odśwież katalogi|Refresh catalogs
Szukaj obrazu, opisu lub nazwy…|Search image, description or name…
Szukaj aplikacji|Search applications
aplikacji|applications
aktywnych źródeł|active sources
Wybierz aplikację|Choose an application
Przejrzyj katalog lub zmień filtr.|Browse the catalog or change the filter.
Zainstalowana na tym hoście|Installed on this host
Odinstaluj|Uninstall
Zainstaluj|Install
Najważniejsze funkcje|Key features
Obraz Docker|Docker image
Dowolna|Any
Porty host → kontener|Host → container ports
Nie wymaga|Not required
Silniki|Engines
RAM minimum|Minimum RAM
Nie podano|Not specified
Dane trwałe|Persistent data
Wolumeny / montowania — sprawdź konfigurację|Volumes / mounts — review configuration
Według konfiguracji|According to configuration
Ta aplikacja korzysta z Docker socket i może uzyskać uprawnienia administratora hosta.|This application uses a Docker socket and can gain host administrator access.
Ważne uwagi i wymagania|Important notes and requirements
Zbuduj obraz ze źródeł|Build image from source
Dokumentacja|Documentation
Strona|Website
Katalog jest dostępny z lokalnego cache. Nie udało się potwierdzić stanu instalacji — sprawdź połączenie Docker.|The cached catalog is available. Installation state could not be verified; check the Docker connection.
Brak aplikacji dla wybranego filtra.|No applications match this filter.
Sprawdzanie katalogów…|Checking catalogs…
Katalogi odświeżone. Niedostępne źródła korzystają z cache.|Catalogs refreshed. Unavailable sources use cached data.
Instalowanie jest wyłączone w tym profilu|Installation is disabled for this profile
Profil ma domyślnie tylko odczyt. Instalacja wymaga osobnej zgody administratora w Profile / Uprawnienia. To ograniczenie uprawnień, a nie kontenera testowego.|Profiles are read-only by default. An administrator must enable installation in Profiles / Permissions. This is a permission restriction, not a test-container restriction.
Otwórz uprawnienia profilu|Open profile permissions
Zezwól na instalowanie w tym profilu|Allow installation on this profile
Nazwa kontenera|Container name
Automatycznie wybierz dostępny port przy konflikcie|Automatically choose an available port on conflict
Zmienne środowiskowe — jedna KEY=value na linię|Environment variables — one KEY=value per line
Opcje kontenera — montowania, sieć, limity i restart|Container options — mounts, network, limits and restart
Sprawdź porty i trwałe dane. Docker socket daje dostęp administratora hosta. Instalacja wymaga osobnego potwierdzenia.|Review ports and persistent data. Docker socket access grants host administration. Installation requires separate confirmation.
Wybrany port nie koliduje z opublikowanymi portami Docker.|The selected port does not conflict with published Docker ports.
Każda zmienna wymaga postaci KEY=value|Each variable must use KEY=value format
Podgląd instalacji|Installation preview
Akceptuję dostęp do Docker socket i uprawnienia administratora hosta.|I accept Docker socket access and host administration privileges.
Sprawdziłem montowania i sposób przechowywania danych trwałych.|I reviewed mounts and persistent data storage.
Akceptuję dodatkowe uprawnienia, urządzenia lub capabilities kontenera.|I accept additional container privileges, devices or capabilities.
Zapewniłem wymagane usługi zależne.|I provided the required dependent services.
Instalacja rozpocznie się dopiero po potwierdzeniu. Wolumeny nie są automatycznie usuwane.|Installation starts only after confirmation. Volumes are not removed automatically.
Aplikacja została zainstalowana|Application installed
Główny katalog DCC jest stałym źródłem. Błędne odświeżenie nie usuwa ostatniej poprawnej zawartości.|The main DCC catalog is permanent. Failed refreshes retain the last valid contents.
Oficjalny katalog DCC|Official DCC catalog
wpisów|entries
Kopia dołączona do aplikacji|Bundled catalog copy
Zawartość|Contents
STAŁE ŹRÓDŁO|PERMANENT SOURCE
Aktywne|Enabled
Repozytorium GitHub lub bezpośredni adres HTTPS do JSON|GitHub repository or direct HTTPS JSON URL
Lub wybierz lokalny plik JSON|Or choose a local JSON file
Katalogi aplikacji|Application catalogs
Sprawdź i dodaj|Validate and add
Podaj adres katalogu albo wybierz plik JSON|Enter a catalog URL or choose a JSON file
Katalog został sprawdzony i dodany|Catalog validated and added
Lokalny Docker, WSL, SSH, Balena i zdalny Docker przez TLS.|Local Docker, WSL, SSH, Balena and remote Docker over TLS.
Importuj|Import
Eksportuj|Export
Nowy profil|New profile
Nowe profile są domyślnie tylko do odczytu. Sekrety połączeń są szyfrowane. Eksport nie zawiera haseł, tokenów ani kluczy prywatnych.|New profiles are read-only by default. Connection secrets are encrypted. Exports exclude passwords, tokens and private keys.
Profil|Profile
Połączenie|Connection
Dostęp|Access
Aktywny|Active
Sprawdź|Test
Edytuj profil|Edit profile
Usuń zapisany profil połączenia. Zasoby Docker pozostaną zachowane.|Remove the saved connection profile. Docker resources are retained.
Import profili|Import profiles
JSON eksportu Desktop lub Web|Desktop or Web export JSON
Import dotyczy konfiguracji połączeń. Hasła i klucze nie są importowane w jawnym JSON. Dane źródłowe nie są modyfikowane.|Import transfers connection metadata. Passwords and keys are not imported as plaintext JSON. Source data is unchanged.
Nazwa profilu|Profile name
Typ połączenia|Connection type
Lokalny Docker / Docker Desktop|Local Docker / Docker Desktop
Balena OS przez SSH|Balena OS over SSH
Zdalny Docker z TLS|Remote Docker with TLS
Istniejący tunel na localhost|Existing localhost tunnel
Kontekst Docker CLI (opcjonalnie)|Docker CLI context (optional)
Dystrybucja WSL|WSL distribution
Adres paneli / IP hosta (opcjonalnie)|Panel hostname / host IP (optional)
Host SSH / Balena|SSH / Balena host
Użytkownik SSH|SSH username
Ścieżka klucza SSH|SSH key path
Endpoint Docker, np. tcp://server:2376|Docker endpoint, e.g. tcp://server:2376
Hasło SSH — puste zachowuje obecne|SSH password — leave blank to retain
Passphrase klucza — puste zachowuje obecną|Key passphrase — leave blank to retain
Ścieżka CA TLS|TLS CA path
Ścieżka certyfikatu klienta TLS|TLS client certificate path
Ścieżka klucza klienta TLS|TLS client key path
Identyfikatory użytkowników, oddzielone przecinkami — puste: wszyscy|User IDs, comma-separated — blank allows all users
Uprawnienia profilu|Profile permissions
Odczyt|Read
Polecenia w kontenerach|Container exec
Zarządzanie obrazami|Manage images
Tworzenie wolumenów|Create volumes
Tworzenie sieci|Create networks
Operacje Compose|Compose actions
Instalowanie aplikacji|Install applications
Aktualizacje|Updates
Operacje destrukcyjne|Destructive actions
Dostęp do Docker może dawać kontrolę nad hostem. Włączaj tylko potrzebne operacje. SSH wymaga zweryfikowanego wpisu known_hosts; TCP używa TLS, chyba że jest to świadomie wybrany lokalny tunel.|Docker access can grant host control. Enable only required operations. SSH requires a verified known_hosts entry; TCP uses TLS except for an explicitly configured localhost tunnel.
Zapisz profil|Save profile
Profil został zapisany|Profile saved
Wygląd, dźwięki i bezpieczeństwo Twojej przestrzeni.|Appearance, sounds and workspace security.
Theme Settings|Theme Settings
Wybierz charakter przestrzeni. Podgląd działa od razu; zapis zatwierdza ustawienia.|Preview your workspace appearance instantly, then save to keep the changes.
Kolor akcentowy|Accent color
Intensywność akcentów|Accent intensity
Gęstość interfejsu|Interface density
Komfortowa|Comfortable
Kompaktowa|Compact
Język katalogu i nawigacji|Interface language
Język interfejsu|Interface language
Efekty wizualne|Visual effects
Subtelne przejścia|Subtle transitions
Dźwięki|Sounds
Krótkie, lokalne efekty. Dźwięk uruchamia się po interakcji i może być całkowicie wyłączony.|Short local effects. Sound starts after interaction and can be disabled completely.
Włącz dźwięki|Enable sounds
Głośność Master|Master volume
Głośność efektów|Effects volume
Głośność powiadomień|Notification volume
Styl dźwięków|Sound style
Soft — delikatny|Soft — gentle
Clear — czytelny|Clear — distinct
Warm — ciepły|Warm — mellow
Odsłuchaj efekt|Play test sound
Odświeżanie|Refresh
Interwał odświeżania (sekundy)|Refresh interval (seconds)
Odświeżanie zatrzymuje się na ukrytej karcie i podczas edycji formularzy. Katalogi mają osobne odświeżanie i cache.|Refresh pauses in hidden tabs and while editing forms. Catalogs have separate refresh and cache.
Odświeżaj panel kontenerów tylko po wykryciu zmian|Refresh the Containers page only when changes are detected
Ten tryb sprawdza skrót listy co ustawiony interwał. Przy braku zmian nie pobiera pełnych szczegółów ani metryk; zmiany pojawią się z opóźnieniem do długości interwału. To nadal okresowe sprawdzanie, a nie nasłuch zdarzeń Dockera.|This mode checks a compact container-list fingerprint at the selected interval. When nothing changes, it skips full details and metrics; changes appear within one interval. This remains periodic polling, not a Docker event stream.
Odśwież kontenery|Refresh containers
Sprawdzono|Checked
Nie udało się sprawdzić zmian|Could not check for changes
Panel kontenerów|Containers panel
Sesje terminala|Terminal sessions
Przywróć domyślne|Reset defaults
Anuluj podgląd|Cancel preview
Zapisz ustawienia|Save settings
Ustawienia zapisane|Settings saved
Konto i zabezpieczenia|Account and security
Zmień hasło|Change password
Zarządzaj użytkownikami|Manage users
Hasła są hashowane scrypt. Sesja: HttpOnly, SameSite Strict i ochrona CSRF. Administrator przypisuje uprawnienia w profilach.|Passwords use scrypt. Sessions use HttpOnly, SameSite Strict and CSRF protection. Administrators assign profile permissions.
Włącz dźwięki, aby uruchomić odsłuch|Enable sounds to play a sample
Zaznacz wszystkie|Select all
Odznacz wszystkie|Deselect all
Wybór języka|Language selection
Tylko odczyt|Read only
Odczyt i modyfikacje|Read and modify
Uprawnienia MCP|MCP permissions
Wybierz konkretne narzędzia i profile. Uprawnienia profilu są sprawdzane przy każdym wywołaniu.|Choose specific tools and profiles. Profile permissions are checked on every call.
Modyfikacje wymagają ponownego potwierdzenia hasłem i 2FA, jeśli jest włączone.|Write access requires password confirmation and 2FA, if enabled.
Operacje destrukcyjne wymagają osobnego zaznaczenia.|Destructive actions require a separate confirmation.
Profil nie ma uprawnienia wymaganego przez wybrane narzędzie|The profile does not have the permission required by the selected tool
Zezwól na usuwanie kontenerów|Allow container removal
Test SMTP|Test SMTP
Adres odbiorcy testowego|Test recipient address
Wyślij wiadomość testową|Send test message
Wiadomość testowa została wysłana|Test message sent
Podaj poprawny adres odbiorcy testowego|Enter a valid test recipient address
Test wiadomości DCC Web — konfiguracja SMTP działa prawidłowo.|DCC Web mail test — SMTP configuration is working.
Obecne hasło|Current password
Nowe hasło — co najmniej 12 znaków|New password — at least 12 characters
Użytkownicy|Users
Rola|Role
Nazwa nowego użytkownika|New username
Hasło — minimum 12 znaków|Password — at least 12 characters
Viewer — odczyt|Viewer — read only
Operator — kontenery i exec|Operator — containers and exec
Dodaj użytkownika|Add user
Użytkownik został dodany|User added
Profile i narzędzia dla klientów MCP — jawnie ograniczony Preview.|Profiles and tools for MCP clients — explicitly limited Preview.
Nowy dostęp|New grant
Klienci|Clients
Granice dostępu|Access boundaries
Przydzielone dostępy|Access grants
Nazwa / klient|Name / client
Ważny do|Expires
Eksport|Export
Odbierz dostęp|Revoke access
Pauzuj dostęp|Pause access
Wznów dostęp|Resume access
Usuń z historii|Remove from history
Odebrany|Revoked
Potwierdź zmianę dostępu|Confirm access change
Potwierdzam świadomie tę zmianę.|I consciously confirm this change.
Zatrzymanie tego grantu natychmiast odrzuci kolejne wywołania MCP. Później możesz wznowić dostęp.|Pausing this grant immediately rejects further MCP calls. You can resume access later.
Klient ponownie uzyska dostęp do przydzielonych profili i narzędzi.|The client will regain access to its granted profiles and tools.
Token zostanie trwale unieważniony. Tego dostępu nie będzie można wznowić.|The token will be permanently revoked. This grant cannot be resumed.
Grant zniknie z tej listy. Zapis odebrania dostępu pozostanie w dzienniku operacji.|The grant will be removed from this list. Its revocation record will remain in the operation log.
Dostęp wstrzymany|Access paused
Dostęp wznowiony|Access resumed
Dostęp odebrany|Access revoked
Grant usunięty z historii|Grant removed from history
W Codexie profil wybierzesz po nazwie lub adresie hosta; ID pozostaje dostępne w razie niejednoznaczności.|In Codex, select a profile by its name or host address; the ID remains available if the name or address is ambiguous.
Nowy dostęp MCP|New MCP grant
Nazwa dostępu|Grant name
Klient|Client
Ważność w dniach|Validity in days
Bez limitu czasowego|No expiry
Zdalny dostęp przez Internet|Remote Internet Access
Zarządzaj zdalnym dostępem|Manage remote access
Wymaga konfiguracji|Configuration required
Zablokowany ze względów bezpieczeństwa|Blocked by security policy
Wyłączony|Disabled
Łączenie|Connecting
Ponowne łączenie|Reconnecting
Skonfiguruj|Configure
Włącz dostęp|Enable access
Wyłącz dostęp|Disable access
Uruchom ponownie|Restart
Stan tunelu|Tunnel status
Zarezerwowana nazwa|Reserved name
Ostatnie połączenie|Last connected
Polityka bezpieczeństwa|Security policy
Przypięty obraz zrok|Pinned zrok image
Brak nowszej wersji|Up to date
Kopiuj adres|Copy address
Otwórz panel|Open panel
Sprawdź aktualizacje|Check for updates
Token konta zrok|zrok account token
Nazwa publiczna (pusta oznacza nazwę automatyczną)|Public name (leave empty to generate one)
Zainstaluj izolowany kontener zrok. Dostęp publiczny pozostanie wyłączony.|Install the isolated zrok container. Public access will stay disabled.
Zarejestruj środowisko zrok i zarezerwuj nazwę publiczną. Dostęp publiczny pozostanie wyłączony.|Enroll a zrok environment and reserve a public name. Public access will stay disabled.
Panel administracyjny będzie dostępny przez Internet przez bramę zrok. Logowanie DCC i MFA administratora nadal obowiązują.|The administration panel will be reachable over the Internet through the zrok gateway. DCC sign-in and administrator MFA still apply.
Zamknij tunel publiczny. Zarezerwowana nazwa pozostanie dostępna do ponownego użycia.|Close the public tunnel. The reserved name will remain available for reuse.
Uruchom ponownie tunel po ponownym sprawdzeniu wymagań bezpieczeństwa.|Restart the tunnel after checking the security policy again.
Zatrzymaj tunel i usuń jego kontener. Wybierz, czy zachować rezerwację i środowisko zrok.|Stop the tunnel and remove its container. Choose whether to keep the zrok environment and reservation.
Utwórz konto, otwórz konsolę zrok i skopiuj token konta z kreatora.|Create an account, open the zrok console and copy the account token from the wizard.
Środowisko zrok jest już zapisane. Możesz zarezerwować nazwę publiczną.|Your zrok environment is already saved. You can reserve a public name.
Dokończ zapamiętaną rezerwację. Aby wybrać inną nazwę, najpierw zwolnij wcześniejszą rezerwację w konsoli zrok.|Complete the remembered reservation. To pick another name, first release the earlier reservation in the zrok console.
Zachowaj środowisko i rezerwację zrok|Keep the zrok environment and reservation
Środowisko i nazwę usunięto już w konsoli zrok.|The environment and name have already been removed in the zrok console.
Udostępnij panel przez HTTPS za pośrednictwem zrok.|Share the panel over HTTPS through zrok.
Instalacja jest dostępna w kontenerowym DCC Web na lokalnym silniku Docker.|Installation is available in containerized DCC Web on its local Docker engine.
Zarządzaj zdalnym dostępem z lokalnego panelu.|Manage remote access from the local panel.
Ręczna aktualizacja DCC Web z tunelem zrok|Manually updating DCC Web with a zrok tunnel
Wznawiaj tunel po aktualizacjach DCC Web przez Updater|Resume the tunnel after DCC Web updates through Updater
Updater zatrzyma tunel na czas podmiany i wznowi go po sprawdzeniu panelu.|Updater will pause the tunnel during replacement and resume it after checking the panel.
Wznawiaj tunel po restarcie DCC Web lub komputera|Resume the tunnel after restarting DCC Web or the computer
Zgoda pozostaje zapisana do wyłączenia dostępu. Połączenie wróci po sprawdzeniu HTTPS i 2FA administratora. Przerwa w Internecie nie wyłącza dostępu na stałe.|This authorization is saved until you disable access. The connection returns after checking HTTPS and administrator MFA. An Internet outage does not disable access permanently.
Automatyczne wznowienie po restarcie jest włączone. Wyłączenie dostępu anuluje tę zgodę.|Automatic recovery after restart is enabled. Disabling access revokes this authorization.
Wznowienie tunelu po aktualizacji przez Updater jest dozwolone.|Tunnel resumption after an update through Updater is authorized.
Otwórz DCC Web przez lokalny adres HTTPS. W tej sekcji kliknij „Wyłącz dostęp” i potwierdź.|Open DCC Web using its local HTTPS address. In this section, click “Disable access” and confirm.
W DCC Container Updater kliknij „Sprawdź” przy DCC Web, zaznacz kontener i kliknij „Aktualizuj zaznaczone”.|In DCC Container Updater, click “Check” next to DCC Web, select the container, and click “Update selected”.
Po aktualizacji wróć tu przez lokalny adres HTTPS. Kliknij „Włącz dostęp” i potwierdź hasłem oraz kodem 2FA. Zarezerwowana domena zostanie zachowana.|After the update, return here using the local HTTPS address. Click “Enable access” and confirm with your password and a 2FA code. Your reserved domain will be kept.
Włącz 2FA na swoim koncie administratora, aby uruchomić tunel.|Enable 2FA on your administrator account to start the tunnel.
Aktualizacja|Update
Niezainstalowany|Not installed
Narzędzia tylko do odczytu|Read-only tools
Utwórz dostęp|Create grant
Token — pokazany tylko raz|Token — shown once
Zapisz token w menedżerze sekretów klienta. Nie będzie można ponownie go odczytać.|Save the token in your client's secret manager. It cannot be retrieved again.
Eksport konfiguracji jest dostępny w tabeli; zamiast tokenu zawiera bezpieczny znacznik środowiska.|Configuration export is available in the table and contains no token value.
Konfiguracja MCP stdio|MCP stdio configuration
Eksport AI / MCP|AI / MCP export
Instrukcje agenta AI|AI Agent Instructions
Wariant instrukcji w podglądzie i paczce ZIP|Instruction variant for preview and ZIP
Standardowy Codex — domyślnie|Standard Codex — default
ChatGPT Web — połączenia pośrednie|ChatGPT Web — indirect connections
Pobierz AGENTS.md|Download AGENTS.md
Pobierz AGENTS.md — ChatGPT Web|Download AGENTS.md — ChatGPT Web
Pobierz instrukcję|Download instructions
Kopiuj instrukcje|Copy instructions
Scal instrukcję w pokazanej ścieżce projektu. Kroki konfiguracji znajdziesz w README.md w paczce.|Merge the instructions at the displayed project path. Setup steps are in the bundled README.md.
Skopiuj instrukcję ręcznie do czatu lub instrukcji projektu. Kroki konfiguracji znajdziesz w README.md w paczce.|Copy the instructions into chat or project instructions. Setup steps are in the bundled README.md.
W zwykłym ChatGPT Web skopiuj instrukcję ręcznie do czatu lub instrukcji projektu. Czat nie wczytuje lokalnego AGENTS.md.|In a regular ChatGPT Web chat, copy the instructions into chat or project instructions. The chat does not load the local AGENTS.md file.
Wygasł|Expired
Pobierz konfigurację|Download configuration
Pobierz paczkę projektu (ZIP)|Download project package (ZIP)
Pobierz wtyczkę Codex (ZIP)|Download Codex plugin (ZIP)
Pliki eksportu są generowane bez wartości tokenu. Ustaw DCC_MCP_TOKEN w kliencie MCP lub w środowisku, z którego jest uruchamiany.|Exported files omit the token value. Set DCC_MCP_TOKEN in your MCP client or its launch environment.
Instrukcja tokenu według systemu|Token setup by operating system
Jak połączyć Codex i podać token|Connect Codex and set the token
Aby udostępnić MCP w projekcie, rozpakuj paczkę projektu w jego katalogu głównym i otwórz zaufany projekt w Codex. Jeśli projekt ma już plik .codex/config.toml, dopisz do niego sekcję dcc z pobranego TOML.|To enable MCP in a project, extract the project package at the project root and open the trusted project in Codex. If .codex/config.toml already exists, add the dcc section from the downloaded TOML to that file.
Aby dodać wtyczkę do katalogu Codex, rozpakuj ZIP wtyczki w osobnym folderze i uruchom w nim poniższe polecenie. Następnie zainstaluj DCC Web MCP ze źródła DCC Web.|To add the plugin to the Codex directory, extract the plugin ZIP into a separate folder and run the command below in that folder. Then install DCC Web MCP from the DCC Web source.
Jeśli eksport używa Dockera, wybierz kontekst, w którym działa kontener DCC Web. Zdalny host Docker wybierasz przez profil przydzielony tokenowi w DCC Web.|If the export uses Docker, select the context running the DCC Web container. Select a remote Docker host through a DCC Web profile assigned to the token.
Przy ręcznym dodawaniu serwera STDIO możesz podać DCC_MCP_TOKEN w polu Klucz i wkleić token w polu Wartość. Codex zapisze go jawnie w swojej konfiguracji. Pole Klucz dostępu zmiennej środowiskowej służy do podania samej nazwy zmiennej.|When adding a custom STDIO server, you can set Key to DCC_MCP_TOKEN and paste the token into Value. Codex stores it in plain text in its configuration. The environment-variable allowlist field takes only the variable name.
Token uprawnia do wybranych profili i narzędzi. Może z niego korzystać każdy czat z dostępem do tego serwera MCP. Kliknij Odbierz dostęp w DCC Web, aby zablokować kolejne wywołania tym tokenem.|The token grants access to the selected profiles and tools. Any chat with access to this MCP server can use it. Select Revoke access in DCC Web to block subsequent calls with the token.
Instrukcja konfiguracji MCP|MCP setup guide
Dostęp odebrany|Access revoked
DCC Web udostępnia zakresowane narzędzia MCP przez stdio. Dostępy do odczytu i modyfikacji wybiera administrator; uprawnienia profilu są sprawdzane przy każdym wywołaniu.|DCC Web provides scoped MCP tools over stdio. Administrators choose read or write access; profile permissions are checked on every call.
Konfiguracja pozostaje niezależna od dostawcy AI. Eksport używa standardowego procesu MCP, a token trafia do środowiska klienta lub menedżera sekretów.|Configuration is provider-neutral. Export starts a standard MCP process; the token comes from the client environment or secret manager.
Tylko wybrane profile i narzędzia. Odczyt jako domyślny zakres, termin ważności, dziennik i możliwość natychmiastowego odebrania dostępu.|Only selected profiles and tools are accessible. Read-only scope, optional expiry, audit and immediate revocation.
Lokalny lub zewnętrzny model do tworzenia i poprawiania konfiguracji Docker.|Use a local or external model to create and improve Docker configurations.
AI proponuje konfigurację. Instalacja pozostaje osobną operacją z kontrolą portów, uprawnień i potwierdzeniem.|AI proposes configuration. Installation remains a separate operation with port validation, permissions and confirmation.
Połączenie AI|AI connection
Dostawca|Provider
Adres bazowy API|API base URL
Model|Model
Klucz API — puste zachowuje obecny|API key — leave blank to retain
Klucz API (opcjonalny dla serwera lokalnego)|API key (optional for a local server)
Zezwól na świadomie wskazany serwer lokalny / LAN|Allow the explicitly configured local / LAN server
Włącz asystenta AI|Enable AI assistant
Klucz jest szyfrowany po stronie backendu i nie jest zwracany w konfiguracji ani eksportach. Serwer modelu musi być już uruchomiony; DCC nie uruchamia modeli automatycznie.|The backend encrypts the key and excludes it from configuration and exports. The model server must already be running; DCC does not start models automatically.
Zapisz połączenie AI|Save AI connection
Pobierz listę modeli|Fetch model list
Przygotuj kontener|Prepare a container
Obecna komenda Docker (opcjonalnie)|Current Docker command (optional)
Obraz Docker (opcjonalnie)|Docker image (optional)
Co chcesz uruchomić lub poprawić?|What would you like to run or improve?
Opisz aplikację, porty, dane trwałe i wymagania…|Describe the application, ports, persistent data and requirements…
Dołącz architekturę, RAM i zajęte porty hosta|Include host architecture, RAM and occupied ports
Żądanie trafia do skonfigurowanego dostawcy AI. Dostawca może naliczać opłaty. Propozycja nie jest wykonywana automatycznie.|The request is sent to the configured AI provider, which may charge for usage. Proposals are never executed automatically.
Wygeneruj / popraw z AI|Generate / improve with AI
Ustawienia AI ↗|AI settings ↗
Zastosuj propozycję do formularza|Apply proposal to form
Propozycja AI została zastosowana do formularza. Sprawdź konfigurację przed instalacją.|AI proposal applied to the form. Review the configuration before installation.
Połączenie AI zostało zapisane|AI connection saved
OpenAI-compatible — lokalny lub zewnętrzny endpoint|OpenAI-compatible — local or external endpoint
Brak danych do wyświetlenia|No data to display
Zapisz|Save
Zamknij|Close
Anuluj|Cancel
Dalej|Next
Potwierdź operację|Confirm operation
Sprawdź i potwierdź|Review and confirm
Potwierdzam|Confirm
Rozumiem skutki tej operacji i potwierdzam jej wykonanie.|I understand the consequences and confirm this operation.
Operacja w toku…|Operation in progress…
Operacja zakończona|Operation completed
Operacja na zaznaczonych kontenerach|Action on selected containers
Operacja nadal trwa. Sprawdź stan Dockera przed ponowieniem.|The operation is still running. Check Docker before retrying.
Sesja wygasła|Session expired
Nieprawidłowa odpowiedź serwera|Invalid server response
Nie udało się wykonać operacji|The operation could not be completed
Połączono|Connected
Połączono ·|Connected ·
Połączono z|Connected to
Brak połączenia Docker|Docker disconnected
Odświeżono|Refreshed
Odśwież|Refresh
Wymagane sprawdzenie profilu|Check the connection profile
Sprawdź profil połączenia i uprawnienia.|Check the connection profile and permissions.
Jak kontynuować|How to continue
Upewnij się, że Docker działa, a proces DCC Web ma do niego dostęp. Nowe profile mają tylko odczyt; operacje zapisu włącza administrator w profilu.|Ensure Docker is running and accessible to DCC Web. New profiles are read-only; an administrator enables write operations.
Sprawdź profile|Check profiles
Spróbuj ponownie|Try again
Aktywny profil|Active profile
Wyloguj|Sign out
Twoje profile. Twoje dane.|Your profiles. Your data.
Konfiguracja:|Configuration:
Zmieniono zajęte porty:|Occupied ports changed:
Dodaj tag:|Add tag:
Uruchom polecenie:|Run command:
Zatrzymaj i usuń kontenery aplikacji|Stop and remove application containers
Wolumeny i montowane katalogi pozostaną zachowane; dane tylko w warstwie kontenera mogą zostać utracone.|Volumes and mounted directories are retained; data only in the container writable layer can be lost.
Potwierdzasz przegląd repozytorium|You confirm review of the repository
Docker zbuduje obraz; kod źródłowy nie będzie wykonywany bezpośrednio na hoście.|Docker builds the image; source code is not executed directly on the host.
Wspólne pliki SSH|Shared SSH files
To folder na serwerze lub w kontenerze DCC Web. Ścieżki z Windows nie są automatycznie dostępne w kontenerze.|This folder belongs to the DCC Web server or container. Windows paths are not automatically available inside a container.
Pliki:|Files:
Zmień folder|Change directory
Kopiuj ścieżkę|Copy path
Wgraj pliki SSH|Upload SSH files
Jak skopiować pliki|How to copy files
Folder zewnętrzny jest używany tylko do odczytu. Pliki skopiuj na serwer lub zamontuj folder w kontenerze.|External directories are read-only in this panel. Copy files on the server or mount the directory into the container.
Użyj wspólnego folderu|Use shared directory
Usuń zaznaczone profile|Delete selected profiles
Zaznacz wszystkie profile|Select all profiles
Zaznaczone profile:|Selected profiles:
Wspólny folder|Shared directory
Ścieżka indywidualna|Individual path
Brak wybranych profili SSH lub Balena|No SSH or Balena profiles selected
Usunięte zostaną tylko wybrane profile i ich zapisane hasła. Kontenery, wolumeny oraz pliki SSH pozostaną zachowane. Aktywne terminale tych profili zostaną zamknięte.|Only selected profiles and their stored credentials will be deleted. Containers, volumes and SSH files are retained. Their active terminals will be closed.
Wybrane profile SSH i Balena będą korzystać ze wspólnego folderu i pliku known_hosts. Nazwy kluczy zostaną zachowane. Pozostałe profile nie zostaną zmienione.|Selected SSH and Balena profiles will use the shared directory and known_hosts file. Key filenames are preserved. Other profiles remain unchanged.
Pominięte profile:|Skipped profiles:
Folder na serwerze DCC Web|Directory on the DCC Web server
Folder zarządzany przyjmuje pliki z przeglądarki. Inny folder musi istnieć na serwerze; w kontenerze zamontuj go tylko do odczytu. Zmiana obejmie wyłącznie profile korzystające ze wspólnego folderu.|Browser uploads go to the managed directory. Other directories must already exist on the server; mount them read-only in containers. Only profiles using the shared directory are affected.
Zmiana folderu nie przenosi ani nie usuwa plików. Profile z indywidualnymi ścieżkami pozostaną bez zmian.|Changing the directory does not move or delete files. Profiles with individual paths remain unchanged.
Wybierz klucze i zaufany plik known_hosts z własnego komputera. Zawartość kluczy nie będzie wyświetlana ani eksportowana.|Select keys and a trusted known_hosts file from your computer. Key contents will not be displayed or exported.
Pliki SSH|SSH files
Zastąp istniejące pliki|Replace existing files
Maksymalnie 20 plików, 128 KiB na plik i 1 MiB łącznie. Pliki zachowają swoje nazwy. Nie kopiuj pliku config. Weryfikuj odciski kluczy hostów z zaufanego źródła.|Up to 20 files, 128 KiB each and 1 MiB total. Filenames are retained. Do not copy SSH config. Verify host key fingerprints using a trusted source.
Zezwalam na zapis wybranych plików SSH w prywatnym folderze DCC Web. Administrator serwera i osoby z dostępem do wolumenu mogą odczytać te pliki. Zalecany jest osobny klucz z passphrase. Przesyłaj przez HTTPS lub lokalne połączenie.|I allow the selected SSH files to be stored in the private DCC Web directory. Server administrators and people with volume access can read them. A dedicated passphrase-protected key is recommended. Upload over HTTPS or a local connection.
Zastąpienie pliku|Replacing existing file
Pliki SSH zostały zapisane|SSH files saved
Najprościej użyć Wgraj pliki SSH i wybrać pliki w oknie systemowym. Przeglądarka nie może otworzyć folderu serwera w lokalnym Eksploratorze.|Use Upload SSH files to select files in the system dialog. A browser cannot open the server directory in your local file explorer.
Przykład dla lokalnego kontenera o nazwie dcc-web. Folder źródłowy wybierasz samodzielnie. Polecenia wykonuj na hoście Dockera.|Example for a local container named dcc-web. Choose the source directory yourself and run commands on the Docker host.
PowerShell — kopia wybranego klucza i known_hosts|PowerShell — copy a selected key and known_hosts
Użyj folderu źródłowego zamontowanego tylko do odczytu.|Use a source directory mounted read-only.
Polecenia dotyczą domyślnego folderu /data/ssh w obrazie kontenerowym. Nie kopiuj całego folderu SSH. Hasło klucza ustaw osobno w profilu. Zmiana kluczy nie przyznaje uprawnień do operacji Docker.|Commands target the default /data/ssh directory in the container image. Do not copy your entire SSH directory. Set the key passphrase separately in the profile. Changing keys does not grant Docker operation permissions.
Po imporcie wybierz profile SSH i użyj wspólnego folderu. Wgraj klucze oraz zaufany known_hosts; ścieżka C:/Users/... nie działa wewnątrz kontenera Linux.|After import, select SSH profiles and use the shared directory. Upload keys and trusted known_hosts; C:/Users/... paths do not work inside Linux containers.
Źródło klucza SSH|SSH key source
Klucz SSH — pełna ścieżka lub nazwa pliku we wspólnym folderze|SSH key — full path or filename in the shared directory
known_hosts — indywidualna ścieżka (opcjonalnie)|known_hosts — individual path (optional)
`;
const messages=Object.fromEntries(pairs.trim().split('\n').filter(line=>line.includes('|')).map(line=>line.split('|')));
const reverse=Object.fromEntries(Object.entries(messages).filter(([a,b])=>a!==b).map(([a,b])=>[b,a]));
const errorPL={
"Select at least one write tool":"Wybierz przynajmniej jedno narzędzie modyfikujące lub terminalowe.",
"Select terminal devices within this grant and explicitly allow terminal access":"Wybierz urządzenia w tym grancie i jawnie zezwól na dostęp terminalowy.",
"Terminal devices require SSH or Balena profiles with host.exec permission":"Terminal wymaga profilu SSH lub Balena z uprawnieniem host.exec.",
"This grant changed or was revoked. Reload it before editing.":"Dostęp został zmieniony lub odebrany. Wczytaj go ponownie przed edycją.",
"A revoked token cannot be restored; create a new grant":"Nie można przywrócić odebranego tokena. Utwórz nowy dostęp.",
"This native stdio export requires the server OS and paths. Use a container export for another client platform.":"Eksport natywny stdio wymaga systemu i ścieżek serwera. Dla innego systemu klienta użyj eksportu kontenerowego.",

 'The reservation is outside the supported hosted namespace.':'Rezerwacja należy do nieobsługiwanej publicznej domeny zrok.',
 'Complete or release the pending reservation before choosing a different name.':'Dokończ oczekującą rezerwację albo zwolnij ją w konsoli zrok przed wyborem innej nazwy.',
 'This MCP grant is paused or expired.':'Ten dostęp MCP jest wstrzymany lub wygasł.',
"The DCC Web container cannot open a host shell through the Docker socket. Create or select an SSH profile for this same Docker host, then enable host.exec for it.":"Kontener DCC Web nie otworzy powłoki systemowej przez socket Docker. Utwórz lub wybierz profil SSH prowadzący do tego samego hosta Docker i włącz w nim uprawnienie host.exec.",
"Use a simple SSH filename without directories":"Podaj prostą nazwę pliku SSH bez katalogów.",
"SSH paths must not contain symbolic links":"Ścieżki SSH nie mogą zawierać dowiązań symbolicznych.",
"Copy a trusted known_hosts file into the shared SSH directory first":"Najpierw wgraj zaufany plik known_hosts do wspólnego folderu SSH.",
"The SSH key is missing from the shared directory; upload it in Profiles":"Brakuje klucza we wspólnym folderze. Wgraj go w zakładce Profile.",
"SSH files must be nonempty text files no larger than 128 KiB":"Pliki SSH muszą zawierać tekst i mieć od 1 B do 128 KiB.",
"SSH files must contain UTF-8 text":"Pliki SSH muszą zawierać tekst UTF-8.",
"Invalid known_hosts entry; copy verified entries from a trusted SSH client":"Nieprawidłowy known_hosts. Skopiuj zweryfikowane wpisy z zaufanego klienta SSH.",
"known_hosts must contain at least one verified host key":"known_hosts musi zawierać co najmniej jeden zweryfikowany klucz hosta.",
"Invalid SSH public key":"Nieprawidłowy klucz publiczny SSH.",
"Only SSH private keys, public keys and known_hosts can be uploaded":"Można przesyłać wyłącznie klucze SSH i plik known_hosts.",
"Invalid or unsupported SSH private key":"Nieprawidłowy lub nieobsługiwany klucz prywatny SSH.",
"Provide an absolute directory on the DCC Web server":"Podaj bezwzględną ścieżkę folderu na serwerze DCC Web.",
"The external SSH directory must already exist and be readable by DCC Web":"Zewnętrzny folder SSH musi istnieć i być dostępny do odczytu dla DCC Web.",
"Select between 1 and 100 profiles":"Zaznacz od 1 do 100 profili.",
"A selected profile no longer exists; refresh the list":"Wybrany profil już nie istnieje. Odśwież listę.",
"Browser uploads are allowed only in the managed private SSH directory":"Przesyłanie plików jest możliwe tylko do zarządzanego prywatnego folderu SSH.",
"Select at most 20 SSH files with a total size of 1 MiB":"Wybierz maksymalnie 20 plików SSH, łącznie do 1 MiB.",
"Duplicate SSH filenames are not allowed":"Nazwy przesyłanych plików SSH nie mogą się powtarzać.",
"The target SSH file cannot be replaced":"Docelowego pliku SSH nie można zastąpić.",
"A file already exists; explicitly enable replacement to continue":"Plik już istnieje. Aby go zastąpić, zaznacz odpowiednią zgodę.",
"Invalid SSH key scope":"Nieprawidłowe źródło klucza SSH.",
"Invalid SSH file path":"Nieprawidłowa ścieżka pliku SSH.",

'Installation is disabled for this profile. Enable Install applications in Profiles / Permissions. Only an administrator can change this setting.':'Instalowanie jest wyłączone w tym profilu. Administrator musi włączyć Instalowanie aplikacji w Profile / Uprawnienia.',
'Configure and enable the AI connection first':'Najpierw skonfiguruj i włącz połączenie AI.',
'Another operation is already running for this profile':'W tym profilu trwa już inna operacja. Poczekaj na jej zakończenie.',
'Use the image update action to change the existing container image':'Do zmiany obrazu istniejącego kontenera użyj osobnej operacji aktualizacji.',
'Invalid AI credential':'Nieprawidłowy format klucza API.',
'Enable installation or container management for this profile to use the AI assistant':'Włącz instalowanie lub zarządzanie kontenerami w uprawnieniach tego profilu, aby korzystać z AI.',
'Local HTTP endpoints require explicit local-network consent':'Lokalny endpoint HTTP wymaga zaznaczenia zgody na połączenie z siecią lokalną.',
'Specify the AI model name':'Podaj nazwę modelu AI.',
'AI did not return a valid configuration proposal':'AI nie zwróciło poprawnej propozycji konfiguracji.',
'AI provider is unavailable or returned invalid JSON':'Dostawca AI jest niedostępny lub zwrócił niepoprawny JSON.',
'A fresh explicit confirmation is required':'Wymagane jest nowe, jawne potwierdzenie.',
'Administrator permission required':'Wymagane są uprawnienia administratora.',
'Profile access denied':'Brak dostępu do profilu.',
'Open the local panel over HTTPS for this operation.':'Otwórz lokalny panel przez HTTPS, aby wykonać tę operację.',
'Enable 2FA for your administrator account before enabling remote access.':'Włącz 2FA administratora przed włączeniem zdalnego dostępu.',
'This zrok image is blocked by the security policy.':'Polityka bezpieczeństwa blokuje ten obraz zrok.',
'The public HTTPS endpoint has not passed verification.':'Publiczny adres HTTPS nie przeszedł weryfikacji.',
'The zrok process stopped. Check the reservation and account.':'Proces zrok zatrzymał się. Sprawdź rezerwację i konto.',
'The name could not be reserved. It may already be in use.':'Nie udało się zarezerwować nazwy. Może być już zajęta.',
'zrok rejected the account token or the hosted service is unavailable.':'zrok odrzucił token konta lub usługa jest niedostępna.',
'Login required':'Wymagane jest logowanie.',
'Invalid CSRF token':'Nieprawidłowy token CSRF. Odśwież stronę.',
'Docker is unavailable or the operation timed out. Check the selected profile.':'Docker jest niedostępny lub przekroczono limit czasu. Sprawdź wybrany profil.',
'Docker access denied; check this profile\'s host permissions':'Brak dostępu do Docker. Sprawdź uprawnienia na hoście tego profilu.',
'Docker rejected the operation. Check the profile and resource state.':'Docker odrzucił operację. Sprawdź profil i stan zasobu.',
'Operation failed; review the selected profile, configuration and Docker state':'Operacja nie powiodła się. Sprawdź profil, konfigurację i stan Docker.'
};
const escape=value=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
const keys=Object.keys(messages).filter(key=>messages[key]!==key).sort((a,b)=>b.length-a.length);
const pattern=new RegExp('(?<![\\p{L}\\p{N}_])(?:'+keys.map(escape).join('|')+')(?![\\p{L}\\p{N}_])','gu');
export function setLanguage(value){language=value==='PL'?'PL':'EN';if(typeof document!=='undefined')document.documentElement.lang=language.toLowerCase();}
export function getLanguage(){return language;}
export function t(value){const text=String(value??''),trim=text.trim();if(language==='PL'&&text.startsWith('Terminal session limit ('))return 'Osiągnięto limit sesji terminala '+text.match(/\(\d+\)/)?.[0]+'. Zamknij nieużywaną sesję albo zmień limit w Ustawieniach.';if(language==='PL'&&text==='Close an existing terminal before opening another one')return 'Osiągnięto limit aktywnych sesji terminala. Wliczane są sesje ze wszystkich kart i okien.';if(language==='PL'&&text.startsWith('This profile does not permit the operation: '))return 'Profil nie zezwala na tę operację: '+text.slice(42)+'. Sprawdź uprawnienia profilu.';if(language==='PL')return errorPL[text]||(text==='Theme Settings'?'Ustawienia motywu':text);if(messages[trim])return text.replace(trim,messages[trim]);return text;}
export function literal(value){return language==='EN'?String(value).replace(pattern,key=>messages[key]):String(value).replace('Theme Settings','Ustawienia motywu');}
export function html(parts,...values){return parts.map((part,index)=>literal(part)+(index<values.length?String(values[index]??''):'')).join('');}
