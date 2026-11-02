# Security model

DCC Web is a Docker administration application. Docker socket access, privileged containers, host bind mounts and some Compose files can grant host-level access. The browser never connects directly to a Docker socket. Run the backend under a dedicated OS identity and expose it only to trusted administrators.

## Implemented controls

- Scrypt password hashes, a one-time random App Store bootstrap credential, interactive local-only setup for standalone mode and a login attempt limit (8 per address/10 minutes).
- Rotated signed cookie plus server-side hashed session IDs, 12-hour expiry, HttpOnly and SameSite Strict. Secure cookies and HSTS are enabled for configured HTTPS deployments.
- CSRF checks on every mutation, same-origin checks, hostname allowlist, no permissive CORS, no WebSocket server. Upgrade requests do not expose an alternate unauthenticated channel.
- Role and profile permissions on API routes, default read-only profiles, revocable profile/tool-scoped MCP tokens stored only as hashes.
- One-use confirmations bound to session/action/profile/target, expiring after 120 seconds. Volume deletion has an additional irreversible-data consent and mounted-volume protection. Uninstall and Compose down retain volumes.
- SSH host key verification, verified TLS for remote TCP and argument arrays instead of host shell execution. Remote SSH arguments are shell-quoted. Exec runs only inside the selected container.
- Connection secrets use Fernet. Generated Windows keys are DPAPI-protected for the service user; Linux keys use a private directory and mode 0600. An external master key can be supplied from a secret manager. Protect backups and filesystem ACLs as well as the database. Losing the key loses access to the encrypted credentials.
- JSON/HTML escaping, restrictive CSP without unsafe-eval, frame denial, no-sniff, bounded bodies/logs/jobs/history and secret redaction in inspection/log responses. Audit stores actor/action/target/result rather than request bodies.
- Remote catalog fetching accepts HTTPS only, resolves and pins public addresses, rejects private/loopback/link-local DNS results, checks every redirect, validates TLS and limits data size. Local JSON upload supports private catalogs without enabling server-side network access to internal endpoints.

## HTTPS / reverse proxy

Keep Waitress listening on `127.0.0.1:8789`, put a trusted TLS reverse proxy in front, preserve the configured Host, and configure `DCC_WEB_HTTPS=1`, `DCC_WEB_PUBLIC_ORIGIN=https://dcc.example.net` and `DCC_WEB_HOSTS=dcc.example.net`. For manual/public deployments, create the administrator locally first with `--init-admin`; the DCC App Store image instead creates a one-time random administrator password on first start and writes it once to container logs so setup cannot be claimed anonymously over the network. Restrict access at the firewall or VPN. Do not add a wildcard CORS policy or blindly trust forwarded headers. For a container network, publish only localhost as in `compose.yaml` and proxy that port.

Example Nginx location (adapt certificates/DNS separately; no production deployment is performed):

```nginx
location / {
    proxy_pass http://127.0.0.1:8789;
    proxy_set_header Host dcc.example.net;
    proxy_set_header X-Forwarded-Proto https;
    client_max_body_size 2m;
}
```

## Scope of evidence

Automated tests cover auth, session revocation, rate limits, CSRF, Host/Origin rejection, role/profile restrictions, encryption/export, confirmations, command construction, SSRF rejection, catalog safety and MCP revocation. This is not a penetration-test certification. SSH/Balena/WSL transports are tested with mocks; no credentials or destructive operations on user infrastructure are used. General log redaction cannot recognize every application-specific secret: avoid putting secrets into ordinary application output.

MCP clients receive Docker metadata/logs as untrusted data, not privileged instructions. This Preview has no write tools or HTTP listener. A malicious client with OS-level access to the data directory is outside the application isolation boundary.

AI endpoints are configured by administrators only. Secrets stay in the encrypted vault, retained keys are cleared on endpoint/provider changes, HTTP redirects are rejected, local networking requires consent, and common secret fields are masked before model submission. Provider output is validated and never automatically executed. MCP grants may explicitly have no expiry; revocation and scope checks still apply.


## SSH file storage

Shared SSH file management is administrator-only and protected by the existing session, CSRF and Origin checks. Preview data and audit entries contain metadata, never uploaded key contents. Files are bounded to 20 per request, 128 KiB each and 1 MiB total; only supported SSH private/public keys and valid `known_hosts` text are accepted. Paths, Windows device names, duplicates and symlink targets are rejected. Managed private keys are encrypted in the vault; public files use a dedicated directory (0700) and staged files (0600). External mount directories remain read-only.

A one-use confirmation is bound to the session, operation, exact file hashes, current destination contents, directory and replacement choice. Bulk profile confirmations also bind the selected profile configurations. Changes after preview require another confirmation. Managed private keys are encrypted using the application vault. A host administrator with the master key and database can decrypt them. Protect the volume and backups, use a dedicated passphrase-protected key and HTTPS, and never upload your entire `.ssh` folder or SSH `config`.

All three SSH paths (Docker CLI, Docker SDK and interactive host terminals) load the same configured trusted host keys and retain Paramiko `RejectPolicy`. Missing shared keys or `known_hosts` stop connection attempts with an actionable error. This feature does not trust new host keys, run `ssh-keyscan`, widen profile permissions, or copy files from a browser-supplied host path automatically.

## Profiles, 2FA and domains

See the [step-by-step guide](profiles-security.md) for encrypted backups, key deletion, the connection wizard, host folder mounting, TOTP recovery, TLS SMTP and local/public domains.
