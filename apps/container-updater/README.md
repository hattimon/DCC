# DCC Container Updater

A separate DCC catalog app that scans a Docker host and updates only the containers selected in its web panel. It does not require a new DCC desktop release after the catalog entry and image have been published.

## Install

Install **DCC Container Updater** from the DCC application store. Open `http://<host-ip>:8788` (DCC may choose another host port if 8788 is occupied). The first-run administrator password is printed once in the container logs and can also be surfaced by DCC from those logs. Change it in the panel after signing in.

The catalog preset mounts `/var/run/docker.sock` and persists panel credentials in the `dcc_updater_data` volume. For Compose, `/home`, `/opt`, `/srv`, `/mnt`, `/media` and `/root` are mounted read-only so the updater can read project files without changing them. This app uses Linux containers and supports `linux/amd64` and `linux/arm64`, including Docker Desktop in Linux-container mode and 64-bit Raspberry Pi OS.

The interface defaults to **English** and offers **Polski** on the login page and in the panel. The last language selected after signing in is saved in `/data` and survives logout and restarts. The footer links back to DCC, of which this panel is an integral part.

## Updates and safety

- **Advanced options** are collapsed by default beside each container. They show detected persistent mount destinations, explain data/backup limitations, and offer manual Compose, registry or original-deployment alternatives when relevant. No alternative command is executed by expanding the section.
- Images and containers are handled generically, using Docker metadata and registry digests; no container-name-specific update rules are needed. The optional DCC catalog adds known newer tags. Outside the catalog, the current tag can be checked for a new digest, but unrelated version tags, unpublished local builds and application-specific migration procedures cannot be inferred automatically.
- The scanner compares tagged images with the latest matching image in the DCC catalog. For unchanged tags, it compares local and registry digests when the daemon provides comparable digest data.
- The catalog is fetched from GitHub Raw, with GitHub API and jsDelivr fallbacks. If all catalog sources fail, the scanner labels the result **Not checked** and explains the connection error instead of claiming the installed tag is the latest release.
- A selected update pulls the target image first. It then recreates the container with its current environment, command, ports, restart policy, security options, resource settings, labels and mounts. Named and anonymous Docker volumes remain attached; volume deletion is never requested. Files stored only in the old container writable layer are not copied into its replacement. Back up application/database data before migrations: image rollback does not reverse database migrations.
- The current container configuration is preserved by default. A matching DCC catalog entry may declare an `update_instructions` object to override only named settings. The supported structure is:

  ```json
  {
    "update_instructions": {
      "config": { "command": ["server", "--new-mode"] },
      "host_config": { "RestartPolicy": { "Name": "unless-stopped" }, "Memory": 536870912 }
    }
  }
  ```

  `config` accepts Docker create options such as `command`, `entrypoint`, `environment`, `ports`, `volumes`, `working_dir`, `user`, `labels`, `healthcheck` and `stop_signal`. `host_config` accepts a limited set of restart, mount, port-binding and resource settings. Every omitted setting remains copied from the running container. Invalid or unsupported instructions stop the update before the existing container is stopped. Network mode, privileged mode, auto-remove and device access cannot be changed through these instructions.
- Before offering an update, the scanner checks configured and currently published host ports against all other containers, including stopped containers with saved port bindings. It accounts for TCP/UDP, host IP bindings and port ranges. A conflict blocks the update without changing the port. Docker checks again when the replacement starts; if a host process or a new race occupies the port, the updater reports the conflict and restores the previous container.
- Temporary registry failures (TLS timeouts, connection resets, rate limits and server errors) are retried during scans and image pulls. A failed pull leaves the current container running and the panel reports a short, actionable reason instead of a raw Docker API error. Registry checks for identical images are shared within each scan.
- Per-container automatic updates are opt-in and off by default. Enable them with the row checkbox in the panel. On updater/host startup it waits for Docker, checks only enabled containers and processes available updates sequentially, one container at a time. A container name is bound to its image repository so a different image reusing the name does not inherit the setting.
- Opening the panel automatically checks only its own GHCR image and offers **Update panel / Not now**. Container scans use **Scan containers**. An **Automatically scan on refresh** switch is off by default and saved in `/data`; enabling it allows scans after a page refresh or language switch, after the panel-version check and any update decision. The last completed scan, date and time are persisted and displayed without new registry requests. Restart-update opt-ins remain separate from this page preference.
- If the replacement fails to start or becomes unhealthy, the app removes the replacement and attempts to restore the original container. The old container is removed only after a running replacement passes its startup check.
- Compose services are manual-only. The updater reads the service model through the official Docker Compose CLI and will update one running replica only when the Compose file already declares the target image. It never edits the user's Compose files. It runs `pull SERVICE`, then `up -d --no-deps --no-build --pull never --wait --wait-timeout N SERVICE`; dependency services are not restarted. The updater blocks services with Compose dependents, any other container on the same Docker network, shared named volumes or bind mounts, conflicting published ports, multiple replicas, unavailable project files, unresolved environment variables or bind mounts outside the read-only roots. If Compose cannot be read safely, the row explains which path or dependency prevents the update. Compose changes use a temporary local tag of the previous image and attempt rollback if the replacement does not pass its health check. A single-service update still causes a short interruption; dependencies outside Docker cannot be inferred automatically.
- Version-pinned Compose projects must first have their `image:` field changed in the user's Compose file to the target version. The updater then detects that declared target and applies it without rewriting the file. It does not support Compose builds from source, Swarm, or custom-network standalone containers.
- Digest-only local images are checked through a unique local repository tag when available. Images with no tag or several ambiguous tags remain blocked with an explanation.
- The updater is skipped in the general container list; its dedicated self-update path uses a temporary helper so the process can safely replace its own container.

The Compose CLI and the updater image are built for both x86-64 and ARM64. Its downloaded CLI binary is pinned by version and SHA-256 checksum. Existing updater installations need one manual image update from DCC to receive this self-update feature and the Compose read-only mounts; preserve the existing `dcc_updater_data` volume to retain the panel password and settings. After that first update, the updater checks for its own newer image on every container or host restart and waits for confirmation in the panel before installing it. For projects outside the standard roots, add the project and bind-data directories as read-only host mounts and set `DCC_UPDATER_COMPOSE_ROOTS` to the comma-separated in-container paths.

## Schedule tab

Schedules are off by default. Choose scan-only or scan-and-update for an explicit list of standalone containers, with a one-time date/time, daily, weekly, monthly or an anchored interval in hours/days. Select an IANA time zone (initially the browser time zone). The next run and last result are shown in the tab. Calendar runs follow local daylight saving time: missing clock times move forward, repeated clock times run once, and short months use their last day. Hour intervals are elapsed-time intervals; day intervals keep the chosen local time.

The separate **Include panel updates** switch is also off by default. When enabled for the schedule, a newer panel image is installed first without an interactive prompt. The durable queue waits for a new process with that exact image and healthy startup before scanning/updating other containers. A failed panel check, unsupported update, failed replacement or ten-minute restart timeout stops that scheduled run and records the reason. The helper preserves the existing `/data` volume and configuration. Manual panel checks still ask before installing.

All scheduled scans and updates use the same single-operation queue as manual actions. Busy jobs delay the schedule. After downtime, one overdue run is claimed durably; missed runs do not pile up. A completed/claimed one-time schedule does not repeat. An interrupted container-update phase is reported rather than replayed automatically. Settings, restart continuation and last result are saved in `/data/schedule.json`; a damaged file disables scheduled execution without overwriting the evidence.

Choose **Scan and update selected containers** to restrict updates to selected, matching image repositories. A different image reusing a name does not inherit that permission. Alternatively, **Scan and update all containers** checks the current inventory on every run, including containers installed later; it requires no individual selections and updates only verified, eligible newer images. It uses the same serial queue and safety checks. The panel is controlled separately by **Include panel updates**. Compose remains manual-only; blocked or unverified services are explained in the last result and Reports. Explicit Links, VolumesFrom, shared namespaces and shared writable persistent mounts block automatic replacement, including when rechecked just before execution. Volumes are kept, but image rollback cannot reverse database migrations. Run one updater instance per Docker host/data volume; unrelated external Docker operations cannot be serialized by this panel.

## Reports and error alerts

The **Reports** tab retains the latest 200 local events, ten per page, with an issues-only filter. Successful runs stay on one compact line; errors and blockers expand on demand. Panel replacement is marked complete only after the exact expected image is observed. Viewing reports or their delivery status never scans registries. Events are stored in `/data/reports.json` using a versioned structure for future integrations.

**Error notifications** are off by default. Configure channels under Reports, save their settings, and explicitly use **Send test message** to verify your account. Successful runs do not send alerts. Scan warnings require a separate opt-in. Messages contain a short summary and up to five affected containers. Repeated identical alerts are muted for an hour; delivery status is retained beside the report. Sending runs in a separate bounded worker queue, so a messenger outage does not block Docker work. Failed or unconfirmed sends are not automatically replayed after a restart, avoiding duplicate alerts; new unsent recent errors can resume.

- **E-mail (SMTP):** your SMTP hostname, port, sender and up to ten recipient addresses. STARTTLS (usually port 587) or implicit TLS (usually port 465) is required, with certificate verification. Provide both username and password/app password if authentication is needed. Passwordless trusted relays still require TLS. Unencrypted SMTP is not supported.
- **Telegram:** a Bot API token and chat ID where that bot is allowed to send. Uses plain-text `sendMessage` through the official Telegram API.
- **Signal:** an existing, registered [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) gateway reachable from the updater container. Supply its base URL, sender number and recipient numbers. A gateway bearer token is optional. This integration does not install the gateway or register a phone number.
- **WhatsApp:** your WhatsApp Cloud API token, phone-number ID, API version and recipient numbers. Supply an approved text-only template with exactly one body text parameter for the alert summary, plus its language code. The implementation follows [Meta's template-message example](https://github.com/fbsamples/whatsapp-api-examples/blob/main/template-for-ecommerce-js/messageHelper.js). Account setup, template approval and provider messaging charges remain with your configured account.

Secrets are stored only in `/data/notifications.json` with restrictive file permissions. GET responses expose only whether a secret was saved, never its value. Blank secret fields retain the saved value; disable a channel and choose Delete saved token/password to remove it. Diagnostic alerts redact common password/token patterns; delivery errors record exception types or HTTP codes rather than request URLs or tokens. No credentials, SMTP account, Signal bridge or recipient accounts are bundled in the image. External delivery requires your configuration; no real recipient is contacted during local automated tests.

## Appearance, sound and host identification

Self-updates recreate the panel using its verified `repository@sha256:digest` reference rather than a bare image ID. This preserves recognition by the existing desktop DCC store without relying on a mutable `latest` tag. The replacement's actual image ID must match the selected update before it starts; a mismatch triggers rollback. A panel previously created with a bare ID regains its store identity on its next successful self-update, after refreshing DCC's container list.

The header identifies the Docker daemon's host name, operating system/version, architecture and Docker version, with CPU/RAM information. It uses a cached, read-only daemon query, independently of registry scans. Docker Desktop exposes its virtual-machine environment; the physical Windows/macOS version is not guessed from it. Unavailable host information does not block the rest of the panel.

Blocked, unchecked and unavailable containers are hidden by default. **Show all** reveals them with their diagnostics and remembers that choice. Up-to-date supported containers and the updater itself remain visible; filtering the list does not change scan results, schedules, reports or update permissions.

**Settings** offers six dark colour themes and three short synthesized event-sound styles. Sounds are on by default and can be disabled; browsers require a user gesture before allowing audio. Preview changes, then save to retain them in `/data/preferences.json` across sessions and restarts. Themes also apply to sign-in. No sound files or external audio service are required.

Reports retain expanded details while refreshing. Alternating diagnostic rows and bold container names improve readability. Known diagnostics include deduplicated suggested recovery steps, with no automatic repair commands. The error-notification configuration opens from a highlighted disclosure button; its animation honours reduced-motion preferences.

**Advanced updates** is collapsed under Settings. Registry credentials are scoped to one registry, kept in `/data/registry_credentials.json`, and passed to Docker's image inspection and pull APIs only for matching images. Private Compose pulls use the same scoped credentials while retaining the service's platform. Passwords/tokens are never returned to the browser. Save, remove and undo preserve one previous credential change per registry; Docker administrators can read these local secrets and their undo copy.

The read-only Compose access planner generates Linux/SSH instructions from the detected updater container and Compose labels. It does not execute commands, recreate containers, or grant permissions. It shows a private inspect backup, a narrow read-only bind parameter, configuration backup/rollback steps, and a Compose fragment when the updater itself is Compose-managed. For standalone installations, the original installation definition must be used to recreate all settings; the planner deliberately provides no generic replacement `docker run`. Data volume contents are shared with the saved configuration and are not an independent data backup. An explicit optional `DAC_READ_SEARCH` parameter explains its broader file-read consequences and is off by default. Finish active operations, protect backups and prepare the replacement configuration before stopping anything. Windows/macOS Docker Desktop host paths need their own installation-specific mapping; these Linux paths/commands must not be pasted blindly into PowerShell.

## Security

Access to the Docker socket is effectively administrator access to the Docker host. The panel has password login, CSRF protection, a generated first-run password, and a password-change form. Keep it on a trusted LAN. Use HTTPS and network access controls before exposing it beyond that network.

## Build and publish

The GitHub Actions workflow `.github/workflows/container-updater.yml` tests the app and publishes a multi-architecture image to `ghcr.io/hattimon/dcc-container-updater:latest` when these files change on `main`. Set the GHCR package visibility to **Public** once so DCC users can pull the image.

Run tests locally with:

```powershell
python -m unittest discover -s apps/container-updater/tests -v
```
