# DCC Container Updater

A separate DCC catalog app that scans a Docker host and updates only the containers selected in its web panel. It does not require a new DCC desktop release after the catalog entry and image have been published.

## Install

Install **DCC Container Updater** from the DCC application store. Open `http://<host-ip>:8788` (DCC may choose another host port if 8788 is occupied). The first-run administrator password is printed once in the container logs and can also be surfaced by DCC from those logs. Change it in the panel after signing in.

The catalog preset mounts `/var/run/docker.sock` and persists panel credentials in the `dcc_updater_data` volume. This app uses Linux containers and supports `linux/amd64` and `linux/arm64`, including Docker Desktop in Linux-container mode and 64-bit Raspberry Pi OS.

## Updates and safety

- The scanner compares tagged images with the latest matching image in the DCC catalog. For unchanged tags, it compares local and registry digests when the daemon provides comparable digest data.
- A selected update pulls the target image first. It then recreates the container with its environment, command, ports, restart policy, security options, resource settings and mounts. Named and anonymous Docker volumes remain attached; volume deletion is never requested.
- If the replacement fails to start or becomes unhealthy, the app removes the replacement and attempts to restore the original container. The old container is removed only after a running replacement passes its startup check.
- Docker Compose, Swarm, auto-remove, custom-network and multi-network containers are shown as skipped. Update those through their owning Compose or orchestration configuration.
- The updater skips itself. Update the updater through DCC by replacing/reinstalling that catalog app after a new image is published.

## Security

Access to the Docker socket is effectively administrator access to the Docker host. The panel has password login, CSRF protection, a generated first-run password, and a password-change form. Keep it on a trusted LAN. Use HTTPS and network access controls before exposing it beyond that network.

## Build and publish

The GitHub Actions workflow `.github/workflows/container-updater.yml` tests the app and publishes a multi-architecture image to `ghcr.io/hattimon/dcc-container-updater:latest` when these files change on `main`. Set the GHCR package visibility to **Public** once so DCC users can pull the image.

Run tests locally with:

```powershell
python -m unittest discover -s apps/container-updater/tests -v
```
