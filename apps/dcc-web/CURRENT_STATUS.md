# DCC Web 0.3.0

Web 0.3.0 removes the permanent tunnel shutdown after eight failed public HTTPS checks. Unexpected sidecar exits recover during the authorized session. A separate local password/MFA-confirmed option persists recovery across Web/computer restarts; existing installations must opt in. Valid Updater handoffs preserve this consent, bind it to the replacement image and retry temporary startup failures. Disable, uninstall, reconfiguration and security revocation cancel recovery. Safe event names are recorded in Web logs and audit.

Web 0.2.9 supports the opt-in zrok handoff in Container Updater 1.1.4. For compatible Web images, the updater pauses the managed tunnel during replacement and resumes it after the new container is healthy, preserving the configured public domain without manual disablement. The compatibility procedure for older Web images remains visible in Remote Internet Access settings.

Web 0.2.7 uses BalenaOS SSH port 22222 by default, migrates existing Balena profiles saved with the former default 22, and replaces generic errors for common SSH transport failures with safe, actionable messages. It also moves legacy DCC Remote Access panel networks into a collision-checked subnet pool, preventing the isolated network from taking routes to remote hosts even before profiles are added. The tunnel sidecar stops during a network migration and must be enabled again. Unreadable saved credentials identify the need to restore the matching data volume and master key.

Web 0.2.6 recognizes the hosted zrok domain `shares.zrok.io` and pre-fills pending names when resuming Remote Access setup.

Web 0.2.5 fixes reporting the result of Remote Access configuration, activation and restart in workspaces with custom profile IDs.

Web 0.2.4 fixes Remote Access 0.1.0 installation when the local Docker profile has a custom ID and restores the managed module in the DCC App Store category. DCC Container Updater can replace the previous Web image while retaining the data volume and managed local HTTPS. The remote tunnel remains disabled until an administrator configures and confirms it. [Setup and security boundaries](../dcc-remote-access/README.md)

This release displays each profile ID in the Profiles list, the active profile ID in Overview → Host details, and the selected profile ID beside the host address on the Containers page.

Web 0.2.4 adds grant-scoped instructions and project ZIPs for all seven MCP clients. Codex users can choose a separate ChatGPT Web variant. Web 0.2.2 introduced pausable MCP grants, audited removal from the grant list, profile name/host selectors, manual refresh and configurable polling. [MCP setup and export](docs/mcp.md)

IP-based HTTPS selects the configured certificate even without client SNI. The authenticated Caddy marker keeps HTTPS login, CSRF Origin checks and Secure cookies working behind Waitress. Administration settings use collapsed, described sections with direct access to IP/domain and HTTPS/certificate controls. Real Docker verification covers login and proxy recreation with the saved port and CA.

Optional local HTTPS is managed through a Caddy sidecar. It binds only to the selected private/loopback host address, keeps the existing HTTP mapping and `/data` volume unchanged, scans Docker ports from 9443 to 9499 and retries port-allocation conflicts. The local CA can be downloaded from Settings after the HTTPS endpoint has issued its first certificate. Trust that CA on each client device.

The store merges app versions by stable identity and uses the fetched/cached official catalog for membership, with bundled data only as offline fallback. New applications need only a catalog edit.

This release enables host terminal access from a loopback HTTP panel while preserving encrypted, host-key-verified SSH traffic to remote systems. It adds Polish documentation selected with the panel language and keeps the SSH vault collapsed by default. The previous release's encrypted profile configuration and private-key vault migration, portable encrypted backups, selected-key removal, a connection wizard, optional TOTP 2FA with one-use recovery codes, verified-email reset via TLS SMTP, settings tabs, read-only host-folder attachment and local/public domains with an optional Caddy HTTPS extension remain available.

See [setup and limitations](docs/profiles-security.md) and [security](docs/security.md). Host/Docker administrators with access to the master key can decrypt the vault. SSH-agent secrets cannot be extracted. Compose-managed mounts require a Compose override. Public DNS, incoming ports, a CGNAT tunnel and SMTP credentials require the administrator's configuration. No live user infrastructure is changed by automated tests.

Validation results for the final published commit are listed in its release and PR; earlier test counts do not certify later code.
