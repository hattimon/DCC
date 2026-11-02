# DCC Web 0.1.6

The store merges app versions by stable identity and uses the fetched/cached official catalog for membership, with bundled data only as offline fallback. New applications need only a catalog edit.

This release enables host terminal access from a loopback HTTP panel while preserving encrypted, host-key-verified SSH traffic to remote systems. It adds Polish documentation selected with the panel language and keeps the SSH vault collapsed by default. The previous release's encrypted profile configuration and private-key vault migration, portable encrypted backups, selected-key removal, a connection wizard, optional TOTP 2FA with one-use recovery codes, verified-email reset via TLS SMTP, settings tabs, read-only host-folder attachment and local/public domains with an optional Caddy HTTPS extension remain available.

See [setup and limitations](docs/profiles-security.md) and [security](docs/security.md). Host/Docker administrators with access to the master key can decrypt the vault. SSH-agent secrets cannot be extracted. Compose-managed mounts require a Compose override. Public DNS, incoming ports, a CGNAT tunnel and SMTP credentials require the administrator's configuration. No live user infrastructure is changed by automated tests.

Validation results for the final published commit are listed in its release and PR; earlier test counts do not certify later code.
