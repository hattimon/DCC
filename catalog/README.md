# Docker Control Center deployment catalogs

The canonical public catalog for Docker Control Center is `dcc-catalog.json` in the root of `https://github.com/hattimon/DCC`. DCC treats that repository as its permanent primary source, refreshes it automatically at application startup and again when the deployment catalog opens, and keeps a local cache so the application remains usable when GitHub is temporarily unavailable.

To publish a new application to every DCC user, update the root `dcc-catalog.json` file and push it to the default branch. A new DCC release is not required for catalog-only changes.

DCC can also load optional application catalogs from a direct HTTP/HTTPS JSON URL, a local JSON file, or another GitHub repository root URL. For a GitHub repository root DCC looks for `dcc-catalog.json` or `catalog.json` on `main` and `master`.

The JSON root can be an `apps` array or an object with an `apps` array. Each app requires `name` and `image`. Supported optional fields are `category`, `description`, `default_name`, `container_port`, `host_port`, `extra`, `command`, `notes`, `lightweight`, `category_en`, `description_en`, `notes_en`, `engines`, `archs`, `source_url`, `docs_url`, `homepage_url`, `icon_text`, `upstream_repo`, `latest_release`, `latest_release_url`, `last_checked`, `verified`, `requires`, `gpu`, `ram_min_mb`, `storage_type`, `backup_priority`, `security_exposure`, `compose_required`, and `balena_verified`.

The deployment metadata fields are advisory and let DCC distinguish a simple single-container preset from a heavier or security-sensitive service. `requires` lists external services or prerequisites, `gpu` marks workloads that need a GPU, `ram_min_mb` is a documented minimum when known, `storage_type` describes persistence needs, `backup_priority` helps identify state that should be protected, `security_exposure` describes the intended exposure such as `lan_only` or `reverse_proxy_required`, `compose_required` marks applications that should be installed from a Compose template rather than forced into a single `docker run`, and `balena_verified` is true only after the preset has actually been validated on Balena. Multi-architecture Docker support alone is not sufficient to set `balena_verified`.

`tools/update_catalog_metadata.py` and `.github/workflows/catalog-maintenance.yml` maintain upstream release metadata. Existing catalog entries can be refreshed automatically from GitHub releases/tags. Newly discovered self-hosted projects are written only to `catalog/candidates.json` and proposed for review; discovery never makes a project installable by itself. This keeps automated discovery separate from the trusted deployment manifest.

When a user deploys a catalog preset with Docker, DCC adds `--pull always` so tags such as `latest` or `main` are refreshed before the container is started. Manual container definitions do not force a pull, which keeps local/private images usable.

DCC treats repository manifests as configuration data. It never executes code from the repository itself. Before deployment it checks current Docker container names and published host ports, proposes safe deterministic changes, and shows a separate confirmation for elevated options such as `--privileged`, host networking, devices, Docker socket mounts, or host-root mounts.

For a larger ecosystem, keep the root `dcc-catalog.json` URL stable as the client-facing endpoint and move catalog maintenance to a dedicated repository only if independent contributors or release/versioning needs justify it. The DCC repository can then keep a small compatibility manifest or redirect strategy without changing existing clients.
