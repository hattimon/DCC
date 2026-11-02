# DCC Web 0.1.4

## PL

- Sklep pokazuje jedną najnowszą definicję aplikacji. Oficjalny katalog GitHub steruje listą; dodawanie aplikacji nie wymaga wydania Desktop ani Web.
- Kreator połączeń z testem, import z wyborem pliku i podglądem, dopasowanie kluczy Windows oraz pomijanie istniejących profili.
- Szyfrowane profile i prywatne klucze w magazynie, szyfrowane kopie eksportu i usuwanie wybranych kluczy z podglądem skutków.
- Opcjonalne 2FA TOTP, jednorazowe kody odzyskiwania i reset przez wcześniej zweryfikowany email po konfiguracji SMTP z TLS.
- Zakładki wyglądu i administracji/bezpieczeństwa, Deep Ocean domyślnie, kolumna autostartu kontenerów.
- Opcjonalne podłączenie folderu hosta tylko do odczytu oraz osobne ustawienia domeny lokalnej i publicznej. Rozszerzenie Caddy ułatwia HTTPS dla własnej domeny z prawidłowym DNS i osiągalnymi portami 80/443.
- Zachowane profile, dane, terminale, instalator, wspólny katalog i dotychczasowe funkcje. Importowane profile zaczynają od odczytu; uprawnienia nadaje administrator.

## EN

- One newest application definition across the store. The official GitHub catalog controls membership; new listings need no Desktop/Web rebuild.
- Connection wizard with testing, file-based import previews, Windows key matching and duplicate-profile skipping.
- Encrypted profile configuration/private key vault, password-protected portable backups and selected-key deletion with affected-profile previews.
- Optional TOTP 2FA, single-use recovery codes and reset through a previously verified email address after TLS SMTP setup.
- Appearance and administration/security tabs, Deep Ocean defaults and container restart-policy indicators.
- Optional read-only host SSH directory mounting and separate local/public hostname settings. The Caddy extension automates HTTPS for an owned domain with correct DNS and reachable ports 80/443.
- Existing data, profiles, terminals, installer, shared catalog and features retained. Imported profiles default to read-only.

An SSH agent signs authentication; it cannot export a passphrase/private key. Native Windows agents and explicitly mounted Unix agent sockets are supported according to the transport. A Windows OpenSSH named pipe needs an explicit trusted bridge for Linux containers. Public DNS, router configuration, SMTP accounts, SMS services and CGNAT tunnels are not provisioned without configuration. See the profile/security guide for setup and limits.
