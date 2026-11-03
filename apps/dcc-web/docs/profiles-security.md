# Profiles, encrypted keys and account recovery

## New connection wizard

Choose **Profiles → New profile**. The three steps collect the connection, authentication and explicit permissions. Only fields relevant to the selected transport are shown; CLI/context/user restrictions remain under Advanced. Test the connection before saving. Saving without a successful test requires an explicit choice. New profiles and imported profiles default to read-only; enable only the operations needed.

For SSH/Balena, first upload the intended key and a trusted `known_hosts` in **Keys and trusted hosts**. Select files or a local folder; recognized keys are proposed by contents, with or without an extension. Unrelated files and SSH `config` are excluded. Check the proposed names and fingerprints before approving. No host keys are trusted automatically. Enter a private key's passphrase manually in the profile if required.

## Encrypted storage and deletion

Profile configuration, connection passwords, private SSH keys, TOTP seeds and SMTP credentials are encrypted using the existing Fernet vault. Managed private key uploads are stored in the encrypted database, not as plaintext files under `/data/ssh`. Public keys and trusted host metadata need no confidentiality and remain bounded public files. On upgrade, existing managed private keys and profile JSON are migrated after verifying the encrypted copy; external directories are never migrated or deleted. The old key path remains a logical name for compatibility. Decryption happens in memory when establishing a connection.

Select individual files and **Delete selected files** to preview affected profiles, then approve. This removes only those stored identities and closes the affected terminals. Other keys, profiles, containers and volumes remain. It does not revoke a public key in a remote host's `authorized_keys`.

The master key is protected with Windows DPAPI for native Windows installations, or a mode-0600 key in the private data volume on Linux/container installations. Protect the volume and backups. Application encryption and login 2FA cannot protect against a Docker/host administrator who can read the master key and database. Use dedicated keys and passphrases, HTTPS or loopback for uploads, and restricted host/volume access. Historical filesystem snapshots and external backups are not erased by migration.

## Import and export

**Import** accepts a Desktop JSON export or a password-protected Web backup. Choose the file, enter the backup password when required, review profiles and select which to import. Matching an uploaded private key by basename is enabled by default and can be disabled. It turns a Windows path such as `C:\Users\name\.ssh\key.pem` into the corresponding vault identity. Unmatched paths are retained for deliberate selection. Duplicate connections are skipped; existing profiles are not overwritten. Legacy plaintext files cannot import passwords or private material.

**Export** includes selected profiles, or all profiles if none are selected. Every new Web export requires a separate password of at least 12 characters and your current account password, plus 2FA if enabled. Optionally include saved credentials and the relevant managed keys. Individual arbitrary host files and agent identities are never extracted. The portable archive uses Scrypt with fixed bounded parameters and authenticated Fernet encryption. Keep the backup password separately; it cannot be recovered. Imported permissions reset to read-only. Backups are decrypted in memory, not in a temporary plaintext file.

## SSH agent and read-only host folder

An SSH agent provides signatures; its protocol cannot export private keys or their passphrases. Select **SSH agent** only after a trusted agent socket is accessible to the Web process. Native Windows can use supported local agents. Windows OpenSSH named pipes cannot be mounted directly into Linux containers; use an explicitly configured trusted WSL/Unix bridge or upload the encrypted key and enter its passphrase. See [agent configuration](configuration.md#ssh-agent).

For a container installed directly by the App Store, **Connect host folder** accepts an absolute directory on that same Docker host. A Windows path is translated for Docker Desktop. The panel verifies that the source exists and is readable, then requests approval to recreate only its own container with a read-only mount at `/mnt/dcc-ssh`. Existing image, environment, ports and data volumes are preserved by the existing rollback-capable recreation service. Terminals disconnect during recreation. Profiles using the encrypted vault remain unchanged; choose **Host directory — read-only** only in profiles intended to use the mount. External keys remain protected by their host filesystem and any existing key passphrase; they are not encrypted by the vault.

Compose-managed installations must add the mount to the original Compose configuration instead. Do not discard other service settings:

```yaml
services:
  dcc-web:
    volumes:
      - type: bind
        source: C:/Users/YOUR_USER/.ssh
        target: /mnt/dcc-ssh
        read_only: true
```

On Linux, replace the source with the intended absolute host directory. Recreate that service with its existing Compose project. The browser cannot directly open a server folder in your local Explorer; file upload opens your local file picker.

## Optional login 2FA

Open **Settings → Administration and security → Enable 2FA**. Enter your account password, add the secret manually to Google Authenticator or another RFC 6238-compatible app, then confirm a current six-digit code. The secret is never sent to a third-party QR service. Save the ten recovery codes displayed once, outside DCC Web. Each works once. Enabling or disabling 2FA revokes other sessions. Login requires the account password plus an unused TOTP or recovery code. Enrollment expires after ten minutes and is tied to the initiating session; replayed codes are rejected.

To disable 2FA while signed in, provide your password and a fresh code/recovery code. For email recovery, an administrator must first configure **Recovery email — SMTP** with verified TLS (STARTTLS or implicit TLS). Set and verify your own recovery address using an emailed code while you still have access. SMTP credentials and addresses are encrypted. The login recovery form requires the account password and a short-lived, one-use code sent only to that previously verified address; it disables 2FA and revokes sessions so you can enroll again. Request/verification attempts are bounded. No SMS provider or paid sending service is provisioned automatically. Without SMTP/verified email, use a saved recovery code.

## Local and public domains

In **Settings → Administration and security → Local and public domains**, enter a private IP address (recommended) or hostname without a scheme, port or path. Local and public names are separate. For a local name such as `dcc.home.arpa`, create an IP-to-name record in your router DNS; DCC Web resolves it to a private host IP and binds HTTPS only to that address. The panel cannot configure a router whose credentials have not been supplied.

For local HTTPS, open **HTTPS access → Enable local HTTPS**. The managed Caddy extension uses a dedicated Docker network and persistent certificate volume, keeps the existing HTTP port and `/data` volume unchanged, and chooses a host port from 9443–9499. It publishes HTTPS only on the selected private or loopback address. Docker port conflicts trigger another candidate port; if provisioning fails, the previous extension is restored. Open the displayed URL once so Caddy creates its certificate, then download `DCC-Web-local-root-CA.crt` and install it as a trusted root CA on each client device. Only the public certificate is downloadable; the CA private key remains in the persistent Caddy volume. Local HTTPS cookies are Secure, but HSTS is not enabled for the LAN endpoint, so the existing HTTP URL continues to work.

Public HTTPS remains a separate optional mode. It uses the same managed Caddy service and persistent certificate volume, but publishes ports 80/443, obtains and renews a publicly trusted certificate, and requires a domain you own, correct public DNS and reachable ports. If both modes are enabled, the extension serves both. Stop, restart or remove it in **HTTPS access**; removal preserves certificate volumes. **Check HTTPS** validates the public certificate and panel health. The app trusts forwarded HTTPS only from its managed proxy using an encrypted per-installation token; arbitrary forwarded headers are not trusted.

For a server behind CGNAT without inbound reachability, supply your own tunnel/VPN/reverse proxy configuration. This release does not invent public DNS records or activate a third-party account. See [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https), [Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/) and the [security model](security.md).

# Profile i bezpieczeństwo — skrót PL

Nowy profil prowadzi przez połączenie, klucz/hasło/agenta oraz test i uprawnienia. Wgraj wybrane klucze i zaufany `known_hosts` bezpośrednio w panelu. Klucze prywatne i konfiguracja są szyfrowane; wybrane klucze można usunąć po podglądzie skutków. Nie trzeba otwierać `/data/ssh`.

Import wybiera plik Desktop lub szyfrowaną kopię Web, pokazuje podgląd, dopasowuje nazwy kluczy i pomija duplikaty. Eksport Web zawsze wymaga osobnego hasła; dołączenie sekretów jest opcjonalne. Agent nie ujawnia hasła ani klucza prywatnego. Własne foldery można podłączyć tylko do odczytu; instalacje Compose wymagają wpisu w dotychczasowym pliku Compose.

W ustawieniach są zakładki wyglądu oraz administracji i bezpieczeństwa. Włącz opcjonalne 2FA w aplikacji TOTP, zachowaj jednorazowe kody. Reset przez email wymaga wcześniej zweryfikowanego adresu, hasła konta i skonfigurowanego SMTP z TLS. SMS nie jest automatycznie uruchamiany.

Domena lokalna wymaga wpisu DNS/hosts w Twojej sieci. Publiczne HTTPS może zapewnić rozszerzenie Caddy po ustawieniu własnej domeny, DNS i osiągalnych portów 80/443. Za CGNAT potrzebny jest skonfigurowany tunel lub VPN. Administrator hosta z dostępem do klucza głównego i bazy może odszyfrować dane; 2FA nie zastępuje ochrony hosta.
