# DCC Kiri Manager 0.1.0

**Experimental**. An independent, read-only browser workspace for the Kiri engine, maintained in the Docker Control Center (DCC) repository. Kiri is developed by libracoder. References to Kiri and Docker identify the software used by the panel.

![DCC Kiri Manager dark overview with synthetic test data](site/assets/screenshots/dashboard-dark.webp)

[Polski](README.pl.md) · [Project site after deployment](https://hattimon.github.io/DCC/kiri-manager/) · [GitHub release after approval](https://github.com/hattimon/DCC/releases/tag/kiri-manager-v0.1.0) · [GHCR package](https://github.com/hattimon/DCC/pkgs/container/dcc-kiri-manager) · [Support the author on Ko-fi](https://ko-fi.com/hattimon)

## What it does

- Recognizes Kiri using its published engine identity and negotiates the API version over an explicitly configured Unix socket.
- Lists containers, images, volumes, networks and Compose services. The panel shows details, bounded logs and recent samples of a selected container.
- Saves connection profiles, language, theme and polling interval. A first-run wizard guides setup and can be completed with an unavailable engine.
- Serves a local login with revocable sessions. The package runs as UID/GID 10001.

## Install and connect

After the image is published, run `docker compose up -d` from this directory for the Docker installation. Create the local administrator with `docker compose exec panel python -m backend.admin` and open [the loopback panel](http://127.0.0.1:8796). The image uses `dcc_kiri_manager_data` and defines its own healthcheck. Install from the DCC Store once the catalog entry appears. The Website action opens the project site. Use the loopback address on the Docker host for the installed panel.

The wizard offers the platform-specific official Kiri installer. The Debian/Ubuntu helper verifies the architecture-specific upstream package before installing and starting Kiri after host approval. For a directly mounted socket, the administrator attaches the dedicated Kiri socket and selects its configured alias in the wizard.

The same image is prepared for direct use with Kiri’s Docker-compatible CLI. Check the [installation instructions](docs/installation.md) for Docker, the Store, Kiri, WSL2, Ubuntu, Debian, Raspberry Pi 4/5 and both Mac architectures. Follow the [compatibility matrix](docs/compatibility.md) for evidence and connection limitations. Currently the native Windows pipe and cross-VM socket paths are outside the OCI connector.

## Documentation

- [Kiri source audit and API matrix](docs/kiri-audit.md)
- [Architecture and data storage](docs/architecture.md)
- [HTTP API](docs/api.md)
- [Security](docs/security.md)
- [Release procedure](docs/release.md)
- [Local and GitHub Actions verification](docs/verification.md)

Update by pulling an approved version and recreating only the panel using its existing volume. Back up the panel’s data before upgrading. To remove the panel, run `docker compose down` without volume removal. See the installation guide for rollback and standalone CLI installs.

DCC Kiri Manager uses the [DCC repository MIT license](../../LICENSE). Dependency and artwork details are listed in [third-party notices](docs/licenses.md). [Official Kiri website](https://runkiri.com/).
