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
- Read-only host bind mounts used by the updater to observe Compose files do not make the updater an application-data dependency. The same applies to read-only ancestor views in a system monitor that uses the host PID namespace and a read-only mount of `/`. Writable mounts, shared named volumes, explicit data mounts, other application readers and explicit Docker dependencies still block automatic replacement when coordination is required.
- Panel login controls access to the interface. The scheduler runs without a browser session and uses the same saved registry credentials as manual checks and updates. Configure private-registry access in the panel's registry settings; logging in to the panel does not grant registry access or publish a locally built image.
- Opening the panel automatically checks only its own GHCR image and offers **Update panel / Not now**. Container scans use **Scan containers**. An **Automatically scan on refresh** switch is off by default and saved in `/data`; enabling it allows scans after a page refresh or language switch, after the panel-version check and any update decision. The last completed scan, date and time are persisted and displayed without new registry requests. Restart-update opt-ins remain separate from this page preference.
- **Check** beside a container's status checks only that container. **Check selected…** opens a separate selection mode: select one or more containers, optionally using the search filter and select-all, then click **Check selected**. **Back to updates** restores the existing update-selection workflow and its checkbox choices. Checks never install updates. Results and last-check times for unselected containers are retained. Local container inventory is available before the first full scan, without contacting registries; dependency and port checks still consider all local containers.
- The panel version is shown in the footer. Container Updater releases use independent `updater-v*` tags and versioned GHCR images, alongside `latest` and commit tags. Desktop DCC releases remain separate.
- If the replacement fails to start or becomes unhealthy, the app removes the replacement and attempts to restore the original container. The old container is removed only after a running replacement passes its startup check.
- Compose services in the **Containers** tab retain the existing manual-only path. The updater reads the service model through the official Docker Compose CLI and will update one running replica only when the Compose file already declares the target image. That legacy path never edits the user's Compose files; the separate Docker Compose manager uses explicit file grants described below. It runs `pull SERVICE`, then `up -d --no-deps --no-build --pull never --wait --wait-timeout N SERVICE`; dependency services are not restarted. The updater blocks services with Compose dependents, any other container on the same Docker network, shared named volumes or bind mounts, conflicting published ports, multiple replicas, unavailable project files, unresolved environment variables or bind mounts outside the read-only roots. If Compose cannot be read safely, the row explains which path or dependency prevents the update. Compose changes use a temporary local tag of the previous image and attempt rollback if the replacement does not pass its health check. A single-service update still causes a short interruption; dependencies outside Docker cannot be inferred automatically.
- Version-pinned Compose projects must first have their `image:` field changed in the user's Compose file to the target version. The updater then detects that declared target and applies it without rewriting the file. It does not support Compose builds from source, Swarm, or custom-network standalone containers.
- Digest-only local images are checked through a unique local repository tag when available. Images with no tag or several ambiguous tags remain blocked with an explanation.
- The updater is skipped in the general container list; its dedicated self-update path uses a temporary helper so the process can safely replace its own container.

The Compose CLI and the updater image are built for both x86-64 and ARM64. Its downloaded CLI binary is pinned by version and SHA-256 checksum. Existing updater installations need one manual image update from DCC to receive this self-update feature and the Compose read-only mounts; preserve the existing `dcc_updater_data` volume to retain the panel password and settings. After that first update, the updater checks for its own newer image on every container or host restart and waits for confirmation in the panel before installing it. For projects outside the standard roots, add the project and bind-data directories as read-only host mounts and set `DCC_UPDATER_COMPOSE_ROOTS` to the comma-separated in-container paths.

## Schedule tab

Schedules are off by default. Choose scan-only or scan-and-update for an explicit list of standalone containers, with a one-time date/time, daily, weekly, monthly or an anchored interval in hours/days. Select an IANA time zone (initially the browser time zone). The next run and last result are shown in the tab. Calendar runs follow local daylight saving time: missing clock times move forward, repeated clock times run once, and short months use their last day. Hour intervals are elapsed-time intervals; day intervals keep the chosen local time.

The separate **Include panel updates** switch is also off by default. When enabled for the schedule, a newer panel image is installed first without an interactive prompt. The durable queue waits for a new process with that exact image and healthy startup before scanning/updating other containers. A failed panel check, unsupported update, failed replacement or ten-minute restart timeout stops that scheduled run and records the reason. The helper preserves the existing `/data` volume and configuration. Manual panel checks still ask before installing.

All scheduled scans and updates use the same single-operation queue as manual actions. Busy jobs delay the schedule. After downtime, one overdue run is claimed durably; missed runs do not pile up. A completed/claimed one-time schedule does not repeat. An interrupted container-update phase is reported rather than replayed automatically. Settings, restart continuation and last result are saved in `/data/schedule.json`; a damaged file disables scheduled execution without overwriting the evidence.

Choose **Scan and update selected containers** to restrict updates to selected, matching image repositories. A different image reusing a name does not inherit that permission. Alternatively, **Scan and update all containers** checks the current inventory on every run, including containers installed later; it requires no individual selections and updates only verified, eligible newer images. It uses the same serial queue and safety checks. The panel is controlled separately by **Include panel updates**. The general schedule does not opt Compose projects in; their separate schedules and safety policies are configured in Docker Compose. Blocked or unverified services are explained in the last result and Reports. Explicit Links, VolumesFrom, shared namespaces and shared writable persistent mounts block automatic replacement, including when rechecked just before execution. Volumes are kept, but image rollback cannot reverse database migrations. Run one updater instance per Docker host/data volume; unrelated external Docker operations cannot be serialized by this panel.

## Reports and error alerts

The **Reports** tab retains the latest 200 local events, ten per page, with an issues-only filter. Successful runs stay on one compact line; errors and blockers expand on demand. Panel replacement is marked complete only after the exact expected image is observed. Viewing reports or their delivery status never scans registries. Events are stored in `/data/reports.json` using a versioned structure for future integrations.

**Error notifications** are off by default. Configure channels under Reports, save their settings, and explicitly use **Send test message** to verify your account. Successful standalone runs do not send alerts. Compose information, progress and success each have an independent opt-in, all OFF by default. Scan warnings require a separate opt-in. Messages contain a short summary and up to five affected containers. Repeated identical alerts are muted for an hour; delivery status is retained beside the report. Sending runs in a separate bounded worker queue, so a messenger outage does not block Docker work. Failed or unconfirmed sends are not automatically replayed after a restart, avoiding duplicate alerts; new unsent recent errors can resume.

- **E-mail (SMTP):** your SMTP hostname, port, sender and up to ten recipient addresses. STARTTLS (usually port 587) or implicit TLS (usually port 465) is required, with certificate verification. Provide both username and password/app password if authentication is needed. Passwordless trusted relays still require TLS. Unencrypted SMTP is not supported.
- **Telegram:** a Bot API token and chat ID where that bot is allowed to send. Uses plain-text `sendMessage` through the official Telegram API.
- **Signal:** an existing, registered [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api) gateway reachable from the updater container. Supply its base URL, sender number and recipient numbers. A gateway bearer token is optional. This integration does not install the gateway or register a phone number.
- **WhatsApp:** your WhatsApp Cloud API token, phone-number ID, API version and recipient numbers. Supply an approved text-only template with exactly one body text parameter for the alert summary, plus its language code. The implementation follows [Meta's template-message example](https://github.com/fbsamples/whatsapp-api-examples/blob/main/template-for-ecommerce-js/messageHelper.js). Account setup, template approval and provider messaging charges remain with your configured account.

Secrets are stored only in `/data/notifications.json` with restrictive file permissions. GET responses expose only whether a secret was saved, never its value. Blank secret fields retain the saved value; disable a channel and choose Delete saved token/password to remove it. Diagnostic alerts redact common password/token patterns; delivery errors record exception types or HTTP codes rather than request URLs or tokens. No credentials, SMTP account, Signal bridge or recipient accounts are bundled in the image. External delivery requires your configuration; no real recipient is contacted during local automated tests.

## Safe Compose Update Manager / Bezpieczne aktualizacje Compose

The **Docker Compose** tab discovers projects and replicas from existing Compose
labels. It shows service images/IDs, update availability, configuration paths,
approved source revision, dependencies, networks, persistent mounts, detected
database images, operation state and timestamps. Discover is an explicit scan;
viewing this tab or its history does not contact a registry. PL/EN and all six
existing themes are supported. Progress shows stages, never invented percentages.

### Available modes and deliberate limits

- **Monitoring only** is the default, with project automation **OFF** and database
  policy **Unknown — block**. Discovery, differences and analysis never pull
  images or deploy services.
- **Controlled manual** prepares an exact plan and requires **Approve plan**, then
  **Update**. Approval expires after 30 minutes. Any settings, runtime, source or
  input-file change invalidates the plan. Dry-run plans cannot be approved.
- **Conditional automatic** requires BOTH project mode and project automation to
  be conditional, plus service consent, a schedule and every gate below. General
  “update all” and legacy container startup opt-ins never grant this consent.
- **Approved migration** can be selected for documenting intent, but production
  migration/restore has **no executable adapter** and stays blocked. Unknown
  databases, engine upgrades and application schema migrations are never guessed.

The only executable new deployment profile is `stateless-v1`: a complete reviewed
project, one healthy replica per service, digest-pinned old/new images in the same
repositories, application tests for exact versions, no persistent mounts or image
VOLUME declarations, no database images, no unreviewed external dependencies or
shared outside networks. Include/extends, profiles, builds, lifecycle hooks,
privilege/device changes, additional/removal of services and non-image
configuration changes remain blocked. Compatibility evidence must describe an
isolated test of these exact normalized models and image IDs; selecting “No
database” or “Compatible” alone proves nothing. There are no bundled approved
application profiles. An administrator must review each version pair; a new
release requires new evidence and a new pinned source bundle.

### Configuration and semantic review

The official Compose CLI renders the complete ordered `-f` set, `.env`,
`env_file`, secrets/config files and normalized service model. Override files must
be explicitly listed, exactly as recorded in running container labels; the manager
does not guess an unlisted compose.override.yaml. Extra CLI environment files,
unresolved interpolation and unprovable recursive inputs block deployment.
All input hashes, missing optional-file sentinels, Compose service configuration
hashes, policies and runtime fingerprints are rechecked immediately before write
and again after pulls. The effective candidate model must equal the reviewed
target. Shell interpolation inherits only minimal Docker/runtime variables,
never arbitrary updater environment secrets.

`BASE`, `LOCAL`, and `UPSTREAM` comparisons operate on CLI-normalized models.
Maps recurse, Compose unique resources use target/port identities, and ordered
commands stay atomic. Compose itself validates the generated override; a generic
YAML merge is never used as deployment evidence. Local independent changes are
preserved. Without BASE the result is explicitly a two-way review and cannot
deploy. Sensitive upstream environment/ports/volumes/secrets/config/dependency
changes and conflicts require manual edits, fresh normalized sources, reviewed
evidence and another analysis. The UI shows changed/added/removed paths and
conflicts while withholding all values and sensitive key names. This version
does not provide an in-browser conflict resolver or general config writer.

Sources are **local, explicitly approved, hash-pinned JSON exports** of Compose
models. There is no URL download/execution endpoint. The source revision may
identify a reviewed commit/release; the SHA-256 of each imported model is the
actual immutable content check. Do not import “latest compose” from random URLs.

### Narrow optional write access

All catalog mounts and the catalog `extra` remain read-only. Deployments through
the new manager require a separate, existing image-only override JSON file,
listed LAST in the original Compose `-f` set and in the local approval bundle.
Its only fields may be `services.<name>.image`. Only this exact file is writable
by the adapter. The operator must opt in on the host and prepare the original
deployment definition before recreating the updater; no Docker-socket helper is
created and no permissions are granted by the UI.

For example, keep the existing `/srv:/srv:ro` mount and separately mount just the
approved project's small override directory at the SAME in-container location:

```text
--mount type=bind,src=/srv/my-stack/.dcc-safe,dst=/srv/my-stack/.dcc-safe
```

This is an example to adapt to a verified existing project, not a remote path
the manager creates. Mount a directory containing only the granted override,
not the whole project RW. The override must belong to the updater's uid/gid
(root:root in the default image), with a directory writable by that uid; the
adapter does not request CHOWN or broad DAC capabilities. A single-file bind mount does not support atomic rename
and is not suitable. Update using the original installation definition to retain
every existing mount, option and `dcc_updater_data`. Labels must already record
both Compose files. Keep directory ownership restricted to trusted administrators.

The Linux writer rejects traversal, symlinks/junctions and hard links, walks
directory descriptors with O_NOFOLLOW, checks hashes and file identity, keeps a
private original, preserves uid/gid/mode and atomically renames one file. Undo
checks the current hash before restoring; it will never overwrite a later edit.
File sets or multi-service Docker operations are not atomic. External host
writers are outside the updater's serial queue; stop them during deployment.
The writer is deliberately unavailable on Windows hosts running Python directly;
the published updater runs inside a Linux container on Docker Desktop.

### Locally approved bundle (example schema)

Install the following **inside the existing updater data volume**, using trusted
administrator file access, under `/data/safe-compose/trusted/my-stack/`:

```json
{
  "project": "my-stack",
  "approved": true,
  "root": "/srv/my-stack",
  "files": ["compose.yaml", ".dcc-safe/images.json"],
  "source": {
    "revision": "reviewed-commit-or-release",
    "base": "base.json",
    "base_sha256": "<sha256-of-base-file-bytes>",
    "upstream": "upstream.json",
    "upstream_sha256": "<sha256-of-upstream-file-bytes>"
  },
  "write": {"file": ".dcc-safe/images.json"},
  "profile": {
    "kind": "stateless-v1",
    "approved": true,
    "evidence": {"file": "isolated-test-report.json", "sha256": "<report-file-sha256>"},
    "services": {
      "web": {
        "source_image_id": "sha256:<64-hex-local-image-id>",
        "target_image": "registry.example/team/web@sha256:<64-hex-registry-digest>",
        "application_check": {
          "kind": "http-sha256", "port": 8080, "path": "/ready",
          "body_sha256": "<sha256-of-reviewed-expected-response-bytes>"
        }
      }
    }
  }
}
```

Save that manifest as `approval.json`, with actual values, not placeholders.
Both base.json and upstream.json contain complete Compose-normalized models.
Export using the same project name, directory, file order and Compose version as
the updater (`docker-compose ... config --format json`). These exports contain
resolved secrets: use restrictive permissions, never commit or share them.
The independent isolated test report schema is:

```json
{
  "schema": 1,
  "source_model_sha256": "<canonical-model-hash>",
  "target_model_sha256": "<canonical-model-hash>",
  "versions": {"web": {"source": ["sha256:<old-id>"], "target": "registry.example/team/web@sha256:<new-digest>"}},
  "isolated": true,
  "application_checks_passed": true,
  "persistent_data": [],
  "external_data_dependencies": [],
  "test_suite": "<name-and-result-reference-of-the-actual-reviewed-test-suite>"
}
```

Canonical model hashes use `compose_config.digest(model)` (sorted JSON keys,
compact separators). File hashes use raw bytes. A fabricated report is not a test:
the local approver is responsible for independently reviewing its origin/results.
No checkbox or public metadata can create this trusted evidence through the API.
The HTTP adapter runs a fixed argument list for `curl` INSIDE each approved
container as uid 65534, without a shell, proxy or redirects, and compares response
bytes to the pinned hash. Curl must exist there; no tools are installed in the
application. It tests the old version before deployment and the replacement after
Docker's mandatory healthcheck. Response bodies are never logged or exported.

### Database policy, backup and recovery

Image updates, database-engine updates and application schema changes are treated
separately. Detected engine names are inventory hints, not migration knowledge.
Database policy defaults to unknown. No database-bearing project is deployed by
the initial adapter, even with an apparently good healthcheck or preserved volume.
Only stateless-v1 reports data backup as not applicable, with its scope explicit.

The real `sqlite-online-v1` backup adapter can be configured in approval.json:

```json
{"backup": {"adapter": "sqlite-online-v1", "file": "data/application.sqlite"}}
```

**Verify backup** opens the approved SQLite file read-only and uses SQLite's online
backup API, copies it to a separate restore-test database, then runs
`PRAGMA integrity_check`. The backup and restored copy stay private under
`/data/safe-compose/backups/<operation-id>/`. The result exposes only scope,
checksum and timestamps. It checks SQLite structural integrity, not business
invariants, multiple databases, external data or application migration safety.
It never makes a database deployment READY and never restores over live data.
Postgres/MySQL/other engine backup adapters and production migrations/restores
are unsupported and blocked. Ordinary volume retention is not a backup.

The durable SQLite state machine records DETECTED → ANALYZING → PLAN_READY →
CONFIG_VALIDATED → BACKUP_VERIFIED → MIGRATION_PRECHECK → READY → APPLYING →
HEALTH_CHECK → APPLICATION_CHECK → COMPLETED, timestamps, operation/project,
image versions, checks and error/rollback codes. State is persisted before
mutations. A restart invalidates unfinished preparation; interrupted deployment
becomes MANUAL_INTERVENTION and is NEVER replayed. That condition also blocks
other Docker mutations in the shared queue. Read-only monitoring still works.

On failure, a stateless deployment attempts only the approved old pinned images
and original configuration, with full checks. Old images, evidence and private
config copies are retained. Restore failure or uncertain write outcome holds the
project lock and reports intervention. Do not delete state.sqlite or clear a
lock to “retry”. Inspect/reconcile live state, configuration and evidence on the
host, restore the original deployment through its verified procedure, then have
an administrator reconcile the operation record under exclusive maintenance.
There is intentionally no UI button that guesses whether unknown production
state is safe. Production data restoration is never attempted by this release.

### Schedules, notifications and safe rollout

Each project has OFF / check / analyze-and-notify / conditional automation,
per-service modes and its own one-time/daily/weekly/monthly/interval settings.
It reuses `scheduler.validate_config` and `next_run`, IANA zones, DST behavior,
the existing scheduler loop and JobManager serial queue. Due time is consumed
durably before work; missed runs do not pile up or replay after a restart.
Projects sharing outside networks/data/dependencies remain blocked. Settings,
plans and event history persist under `/data/safe-compose/` without changing
legacy settings files or the `dcc_updater_data` volume.

Compose events flow through existing Reports and Telegram, Signal, WhatsApp and
SMTP transports, the bounded delivery queue and hourly deduplication. Errors and
blockers use existing alert configuration. Information, progress and success each
have independent switches, OFF by default. No real messenger is contacted by the
test suite. Compose event reports contain diagnostic codes, IDs and field paths,
never Compose values, tokens, application response bodies or backup records.

For a safe rollout: start in monitoring, inspect discovery, run Analyze/Dry run,
resolve missing/conflicting inputs manually, validate the exact version pair in
an isolated environment, install the approved hash-pinned bundle, prepare only
the narrow write mount, select manual mode and database policy, analyze again,
review the plan, approve and deploy during a maintenance window. Verify the
application and history before considering project-specific conditional mode.
For any database/migration/unknown dependency, keep monitoring/manual external
administration until an application-specific verified adapter exists.

The manager is an intentionally restricted first implementation. Fixture/API/
CLI tests do not establish production readiness for arbitrary applications or
replace an installed-version upgrade and restore rehearsal.

## Appearance, sound and host identification

### Windows Cinema Hub with an existing SQLite volume

Compose discovery checks the DCC catalog for newer version tags as well as
registry digests, and displays the target image. A running container can outlive
its local image metadata; that service is shown with a diagnostic instead of
hiding every project. Inventory reads also tolerate a container removed between
Docker's list and inspect calls. Self-update checks reuse one inventory.

For a single Cinema Hub service launched from Windows Compose paths, the project
card offers **Windows: prepare a database-preserving update**. The Linux web
panel exports a PowerShell 7 workflow for the Windows Docker Desktop host. Its
existing deployment gates remain in effect: this is a manually run host workflow,
not permission to schedule database updates from the web container.

Run the downloaded script without options to prepare a private online SQLite
backup together with `credentials.key`, verify integrity, and start the pinned
published GHCR image against an isolated copy without networking or host ports.
The workflow checks schema, encryption key and protected account/library table
fingerprints. It refuses changed schemas or data that need a migration review.
It does not build from the local source tree. Backup directories contain private
account data, encryption keys and resolved environment settings; keep them local.

After reviewing `result.json`, `-Apply` repeats preparation, stops this service
for a fresh offline backup and isolated test, then uses native Docker Compose
with the exact reviewed configuration, the pinned image and the same named
volume. Source files and local overrides are preserved. A failed deployment can
return to the pinned old image only if protected data still match the offline
backup. Database backups are never automatically restored over live data.
An unexpected schema/key/account change requires manual recovery from the saved
private operation directory. Other services and shared volumes are excluded.

The operation directory retains `images.override.json` and the reviewed Compose
model. Include that image override in subsequent manual Compose runs to retain
the selected published image; running the original development files alone can
select their original image again. The normal `Update` action remains blocked
until its separate profile requirements are met. This workflow does not enable
automatic database migrations or arbitrary stateful Compose deployment.

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
