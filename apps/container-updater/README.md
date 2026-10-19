# DCC Container Updater

A separate DCC catalog app that scans a Docker host and updates only the containers selected in its web panel. It does not require a new DCC desktop release after the catalog entry and image have been published.

## Install

Install **DCC Container Updater** from the DCC application store. Open `http://<host-ip>:8788` (DCC may choose another host port if 8788 is occupied). The first-run administrator password is printed once in the container logs and can also be surfaced by DCC from those logs. Change it in the panel after signing in.

The catalog preset mounts `/var/run/docker.sock` and persists panel credentials in the `dcc_updater_data` volume. This app uses Linux containers and supports `linux/amd64` and `linux/arm64`, including Docker Desktop in Linux-container mode and 64-bit Raspberry Pi OS.

## Updates and safety

- The scanner compares tagged images with the latest matching image in the DCC catalog. For unchanged tags, it compares local and registry digests when the daemon provides comparable digest data.
- A selected update pulls the target image first. It then recreates the container with its current environment, command, ports, restart policy, security options, resource settings, labels and mounts. Named and anonymous Docker volumes remain attached; volume deletion is never requested.
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
- Per-container automatic updates are opt-in and off by default. Enable them with the row checkbox in the panel. On updater/host startup it waits for Docker, checks only enabled containers and processes available updates sequentially, one container at a time. A container name is bound to its image repository so a different image reusing the name does not inherit the setting.
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
