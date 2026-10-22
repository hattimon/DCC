# DCC Container Updater

A separate DCC catalog app that scans a Docker host and updates only the containers selected in its web panel. It does not require a new DCC desktop release after the catalog entry and image have been published.

## Install

Install **DCC Container Updater** from the DCC application store. Open `http://<host-ip>:8788` (DCC may choose another host port if 8788 is occupied). The first-run administrator password is printed once in the container logs and can also be surfaced by DCC from those logs. Change it in the panel after signing in.

The catalog preset mounts `/var/run/docker.sock` and persists panel credentials in the `dcc_updater_data` volume. For Compose, `/home`, `/opt`, `/srv`, `/mnt`, `/media` and `/root` are mounted read-only so the updater can read project files without changing them. This app uses Linux containers and supports `linux/amd64` and `linux/arm64`, including Docker Desktop in Linux-container mode and 64-bit Raspberry Pi OS.

## Updates and safety

- The scanner compares tagged images with the latest matching image in the DCC catalog. For unchanged tags, it compares local and registry digests when the daemon provides comparable digest data.
- The catalog is fetched from GitHub Raw, with GitHub API and jsDelivr fallbacks. If all catalog sources fail, the scanner labels the result **Not checked** and explains the connection error instead of claiming the installed tag is the latest release.
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
- Temporary registry failures (TLS timeouts, connection resets, rate limits and server errors) are retried during scans and image pulls. A failed pull leaves the current container running and the panel reports a short, actionable reason instead of a raw Docker API error. Registry checks for identical images are shared within each scan.
- Per-container automatic updates are opt-in and off by default. Enable them with the row checkbox in the panel. On updater/host startup it waits for Docker, checks only enabled containers and processes available updates sequentially, one container at a time. A container name is bound to its image repository so a different image reusing the name does not inherit the setting.
- The updater checks its own GHCR image at every container start, including a host restart. If the registry has a newer ARM64/AMD64 image, it pulls it and starts a one-shot helper from that exact image. The helper recreates the updater with the existing configuration, port bindings, restart policy and `/data` volume, then verifies startup before removing the old container. If the pull or replacement fails, the current updater stays available or is restored. A registry outage leaves the current version running; it checks again on the next restart. The panel also has **Check panel update** and **Update panel** buttons for a manual check and update while it is running.
- If the replacement fails to start or becomes unhealthy, the app removes the replacement and attempts to restore the original container. The old container is removed only after a running replacement passes its startup check.
- Compose services are manual-only. The updater reads the service model through the official Docker Compose CLI and will update one running replica only when the Compose file already declares the target image. It never edits the user's Compose files. It runs `pull SERVICE`, then `up -d --no-deps --no-build --pull never --wait --wait-timeout N SERVICE`; dependency services are not restarted. The updater blocks services with Compose dependents, any other container on the same Docker network, shared named volumes or bind mounts, conflicting published ports, multiple replicas, unavailable project files, unresolved environment variables or bind mounts outside the read-only roots. If Compose cannot be read safely, the row explains which path or dependency prevents the update. Compose changes use a temporary local tag of the previous image and attempt rollback if the replacement does not pass its health check. A single-service update still causes a short interruption; dependencies outside Docker cannot be inferred automatically.
- Version-pinned Compose projects must first have their `image:` field changed in the user's Compose file to the target version. The updater then detects that declared target and applies it without rewriting the file. It does not support Compose builds from source, Swarm, or custom-network standalone containers.
- Digest-only local images are checked through a unique local repository tag when available. Images with no tag or several ambiguous tags remain blocked with an explanation.
- The updater is skipped in the general container list; its dedicated self-update path uses a temporary helper so the process can safely replace its own container.

The Compose CLI and the updater image are built for both x86-64 and ARM64. Its downloaded CLI binary is pinned by version and SHA-256 checksum. Existing updater installations need one manual image update from DCC to receive this self-update feature and the Compose read-only mounts; preserve the existing `dcc_updater_data` volume to retain the panel password and settings. After that first update, the updater checks for its own newer image on every container or host restart. For projects outside the standard roots, add the project and bind-data directories as read-only host mounts and set `DCC_UPDATER_COMPOSE_ROOTS` to the comma-separated in-container paths.

## Security

Access to the Docker socket is effectively administrator access to the Docker host. The panel has password login, CSRF protection, a generated first-run password, and a password-change form. Keep it on a trusted LAN. Use HTTPS and network access controls before exposing it beyond that network.

## Build and publish

The GitHub Actions workflow `.github/workflows/container-updater.yml` tests the app and publishes a multi-architecture image to `ghcr.io/hattimon/dcc-container-updater:latest` when these files change on `main`. Set the GHCR package visibility to **Public** once so DCC users can pull the image.

Run tests locally with:

```powershell
python -m unittest discover -s apps/container-updater/tests -v
```
