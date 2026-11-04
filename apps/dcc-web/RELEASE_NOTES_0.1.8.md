# DCC Web 0.1.8

## English

- Fixed local HTTPS opened by IP address. The generated Caddy configuration selects the LAN certificate when browsers omit TLS SNI, including when a port such as 9444 is mapped to the proxy.
- Fixed HTTPS login, CSRF Origin checks and Secure session cookies behind Waitress. HTTPS is authenticated with the per-installation Caddy marker rather than relying on forwarded headers that the server removes.
- Reorganized Administration and security into collapsed, clearly described sections for panel access, HTTPS/TLS and certificates, two-factor authentication, recovery email and user management. HTTPS settings can be opened directly without saving addresses again.
- Retained the configured HTTPS port and CA across restarts. Release verification now performs actual IP-based TLS, CSS loading, administrator login, Secure-cookie checks and panel/proxy restarts against disposable Docker fixtures.
- Updated Web downloads and English/Polish guidance while preserving the desktop screenshots in the repository README.

## Polski

- Naprawiono lokalne HTTPS otwierane przez adres IP. Konfiguracja Caddy wybiera certyfikat adresu LAN także wtedy, gdy przeglądarka nie wysyła TLS SNI, również przy mapowaniu portu, np. 9444.
- Naprawiono logowanie HTTPS, sprawdzanie Origin dla CSRF i bezpieczne ciasteczka sesji za Waitress. Rozpoznanie HTTPS używa uwierzytelnionego znacznika Caddy przypisanego do instalacji zamiast nagłówków proxy usuwanych przez serwer.
- Uporządkowano Administrację i bezpieczeństwo: zwijane sekcje z jasnymi opisami prowadzą do adresów panelu, HTTPS/TLS i certyfikatów, 2FA, poczty odzyskiwania oraz użytkowników. Ustawienia HTTPS można otworzyć bez ponownego zapisywania adresów.
- Zachowano skonfigurowany port HTTPS i CA przy ponownym uruchomieniu. Weryfikacja wydania sprawdza rzeczywiste TLS przez IP, ładowanie CSS, logowanie administratora, Secure-cookie i restarty panelu oraz proxy na jednorazowych kontenerach testowych.
- Zaktualizowano pobieranie Web i instrukcje EN/PL, zachowując zrzuty desktopu w głównym README.
