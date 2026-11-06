# Panele WWW kontenerów

DCC Web 0.3.1 rozdziela adres usługi od linku otwieranego po kliknięciu. Etykieta i **Kopiuj adres panelu** zachowują oryginalny host i opublikowany port TCP. Lokalne HTTP i HTTPS otwierają adres bezpośrednio. Publiczne wejście otwiera `/panels/view/...` pod bieżącym adresem DCC, z zachowaniem protokołu i portu DCC. Link zawiera identyfikatory, bez danych logowania.

Ustaw rzeczywisty, osiągalny z DCC adres LAN hosta w **Profile → Zaawansowane → Adres paneli / IP hosta**. Dla lokalnego hosta można też ustawić **Ustawienia → Dostęp do panelu i HTTPS → Adresy panelu**. DCC nie zastępuje nasłuchiwania `0.0.0.0`/`::` publiczną domeną przeglądarki. Gdy nie zna adresu, wskazuje potrzebę konfiguracji w wierszu kontenera. Jawne adresy interfejsów, IPv6 i loopback zachowują swoją postać.

Globalna opcja **Automatycznie otwieraj panele zdalne przez DCC Web** znajduje się w **Dostęp do panelu i HTTPS (TLS)**. Domyślnie włącza się przy skonfigurowanym HTTPS, domenie publicznej lub Remote Access. Ręczne wyłączenie/włączenie pozostaje zapisane po restarcie i aktualizacji. Wyłączenie pozostawia oryginalny adres, nigdy `publiczna-domena:port-usługi`. Prywatne IP i zapisana nazwa lokalna otwierają linki bezpośrednie również przez HTTPS. Nietypową lokalną nazwę DNS należy zapisać jako adres lokalny. Walidacja Host i zaufanych proxy pozostaje aktywna; dowolne nagłówki X-Forwarded-* nie zmieniają trybu.

## Transport i uprawnienia

Każde żądanie HTTP ponownie sprawdza pełny ID kontenera oraz stabilny identyfikator panelu w aktualnych opublikowanych portach. Obsługiwane są rozpoznane porty WWW oraz panele sieci hosta określone w katalogu. Przeglądarka nie może podać dowolnego hosta, URL ani portu. Ścieżki i nagłówki są ograniczone, a przekierowania poza wybraną usługę blokowane. Skopiowany link wymaga własnej aktywnej sesji DCC, ukończonego 2FA i bieżącego uprawnienia odczytu profilu.

Lokalny/Docker TCP profil wymaga rzeczywistej trasy z procesu DCC do usługi. Dostęp do Docker API jej nie zapewnia. Localhost kontenera DCC, host Docker Desktop i localhost zdalnego urządzenia to różne miejsca. Zdalne mapowanie tylko na loopback nie jest kierowane do localhost DCC. Profile SSH/Balena używają dotychczasowego uwierzytelniania i weryfikacji klucza hosta oraz kanału `direct-tcpip`: wildcard prowadzi do zdalnego loopback, jawny interfejs do jego adresu. SSH musi zezwalać na przekazywanie. Certyfikaty HTTPS usług są weryfikowane; nie ma automatycznego pomijania TLS.

SSE i WebSocket korzystają z połączeń serwerowych związanych z sesją oraz krótkiego, uwierzytelnionego odpytywania przez przeglądarkę. Nie wymagają osobnego publicznego listenera WebSocket, konkretnego dostawcy tunelu ani nowego agenta. Każdy odczyt/zapis sprawdza sesję i profil. Osobny monitor co sekundę zamyka także bezczynne połączenia po wygaśnięciu/wylogowaniu, zmianie 2FA, odebraniu dostępu lub wyłączeniu funkcji; planista systemu może dodać opóźnienie. Zmiana konfiguracji profilu/hosta unieważnia kontekst. Już wyświetlonych danych nie można cofnąć. Bezpośrednie wejście LAN chroni sama usługa.

## Izolacja i cookies

Zewnętrzna strona DCC jest zaufana. Dokument usługi trafia jako JSON/base64 do nieaktywnego szablonu, następnie działa wyłącznie w ramce sandbox bez `allow-same-origin`, okien popup i nawigacji nadrzędnej strony. CSP blokuje bezpośrednią sieć, a most MessageChannel dopuszcza wyłącznie wybraną usługę. JavaScript panelu nie odczytuje dokumentu, storage, cookies ani CSRF DCC. Szersza polityka potrzebna do skryptów i stylów dotyczy tylko strony pośredniczącej.

Cookies usługi pozostają w pamięci serwera, osobno dla sesji logowania DCC, profilu, kontenera i panelu. Nie są cookies DCC i nie są współdzielone pomiędzy kontami ani panelami. Skrypty dostają jedynie cookies usługi bez HttpOnly. Każda operacja gateway podlega zwykłej kontroli CSRF; nie ma wyjątku dla brakującego lub `null` Origin. Własne CSRF i Authorization usługi podróżują wewnątrz ograniczonego żądania. Logowanie do usługi jest osobne. Restart DCC lub utrata sesji wymaga ponownego logowania do usługi.

Uprawnienie odczytu profilu pozwala korzystać z interaktywnego panelu usługi; jej własne uprawnienia określają dozwolone działania. DCC nie zamienia panelu usługi w tryb tylko do odczytu. Izolacja nie chroni przed administratorem Docker/OS, administratorem samej usługi ani jej przejęciem.

## Zgodność i limity

Obsługiwane: klasyczny JS, CSS i jego zasoby, obrazy, API fetch/XHR tej samej usługi, formularze, multipart, pobieranie plików, cookies/logowanie, SSE oraz tekstowe i binarne WebSockety. Grafy ES modules, cykle, dynamiczne importy ze stałą nazwą, podstawowe import maps i `import.meta.url` są zamieniane na lokalne moduły blob ramki. Parser składni jest dołączony lokalnie na licencji MIT. Kod panelu nie jest wykonywany w zaufanej stronie DCC.

To nie jest pełny origin przeglądarki. Wyliczane nazwy dynamicznych importów, scoped import maps, synchroniczny XHR, service workers, obce domeny OAuth/płatności/CDN, ramki zagnieżdżone, WebRTC, nawigacja przez natywne location i trwały storage mogą wymagać konfiguracji URL bazowego albo osobnego reverse proxy/VPN. Storage ramki jest tymczasowy. Dynamiczne zasoby muszą używać obsługiwanych setterów elementów/fetch. Bezpośrednie pobieranie blob/data działa wewnątrz ramki. Most EventSource kończy pracę wraz ze strumieniem serwera; nie odtwarza automatycznego reconnect/Last-Event-ID. Szczegóły kodów zamknięcia WebSocket oraz postępu i strumieniowania XHR są uproszczone. Nie oznacza to zgodności z każdym panelem.

Limity: 1 MB rozkodowanego uploadu/wiadomości, 16 MiB odpowiedzi, 8 sekund braku postępu połączenia/odczytu, 30 sekund transferu zwykłej odpowiedzi, 10 minut życia strumienia, 30 sekund bez odpytywania, 1 MB bufora, 4 strumienie na użytkownika/32 łącznie, 256 kontekstów i 100 cookies na kontekst. Graf modułów: 128 modułów/4 MB źródeł. Dokument: 160 bezpośrednich zasobów. Po osiągnięciu limitu może być potrzebne odświeżenie. Duże pliki i natywne strumieniowanie multimediów mogą wymagać LAN/VPN.

Wyniki lokalnych testów i niewykonane weryfikacje są w `DCC_WEB_0.3.1_CONTINUATION.md` w katalogu repozytorium. Sztuczny serwer testowy nie potwierdza działania konkretnej instalacji produkcyjnej, publicznego certyfikatu ani zewnętrznego tunelu.
