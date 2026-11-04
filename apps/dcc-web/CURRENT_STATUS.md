# DCC Web 0.2.4

Web 0.2.4 fixes Remote Access 0.1.0 installation when the local Docker profile has a custom ID and restores the managed module in the DCC App Store category. DCC Container Updater can replace the previous Web image while retaining the data volume and managed local HTTPS. The remote tunnel remains disabled until an administrator configures and confirms it. [Setup and security boundaries](../dcc-remote-access/README.md)

This release displays each profile ID in the Profiles list, the active profile ID in Overview → Host details, and the selected profile ID beside the host address on the Containers page.

Web 0.2.4 adds grant-scoped instructions and project ZIPs for all seven MCP clients. Codex users can choose a separate ChatGPT Web variant. Web 0.2.2 introduced pausable MCP grants, audited removal from the grant list, profile name/host selectors, manual refresh and configurable polling. [MCP setup and export](docs/mcp.md)

IP-based HTTPS selects the configured certificate even without client SNI. The authenticated Caddy marker keeps HTTPS login, CSRF Origin checks and Secure cookies working behind Waitress. Administration settings use collapsed, described sections with direct access to IP/domain and HTTPS/certificate controls. Real Docker verification covers login and proxy recreation with the saved port and CA.

Optional local HTTPS is managed through a Caddy sidecar. It binds only to the selected private/loopback host address, keeps the existing HTTP mapping and `/data` volume unchanged, scans Docker ports from 9443 to 9499 and retries port-allocation conflicts. The local CA can be downloaded from Settings after the HTTPS endpoint has issued its first certificate. Trust that CA on each client device.

The store merges app versions by stable identity and uses the fetched/cached official catalog for membership, with bundled data only as offline fallback. New applications need only a catalog edit.

This release enables host terminal access from a loopback HTTP panel while preserving encrypted, host-key-verified SSH traffic to remote systems. It adds Polish documentation selected with the panel language and keeps the SSH vault collapsed by default. The previous release's encrypted profile configuration and private-key vault migration, portable encrypted backups, selected-key removal, a connection wizard, optional TOTP 2FA with one-use recovery codes, verified-email reset via TLS SMTP, settings tabs, read-only host-folder attachment and local/public domains with an optional Caddy HTTPS extension remain available.

See [setup and limitations](docs/profiles-security.md) and [security](docs/security.md). Host/Docker administrators with access to the master key can decrypt the vault. SSH-agent secrets cannot be extracted. Compose-managed mounts require a Compose override. Public DNS, incoming ports, a CGNAT tunnel and SMTP credentials require the administrator's configuration. No live user infrastructure is changed by automated tests.

Validation results for the final published commit are listed in its release and PR; earlier test counts do not certify later code.
