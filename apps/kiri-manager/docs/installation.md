# Installation

The panel listens internally on 8796/tcp. The supplied mappings expose it on the host's loopback interface. It runs without Kiri and opens configuration after administrator sign-in. Official releases will be linked from GitHub and GHCR once approved.

## Docker and the DCC Store

From the module directory on the intended Docker host:

```sh
docker compose up -d
docker compose exec panel python -m backend.admin
```

Open http://127.0.0.1:8796/ on that host. To use a different host port, set `KIRI_PANEL_HOST_PORT` before Compose. Authorize a local password of at least 14 characters. For a CLI install of the approved release:

```sh
docker run -d --name dcc-kiri-manager --restart unless-stopped \
  -p 127.0.0.1:8796:8796 --volume dcc_kiri_manager_data:/data \
  --read-only --tmpfs /tmp:size=8m,mode=1777 --cap-drop ALL \
  --security-opt no-new-privileges:true --memory 192m --pids-limit 40 \
  ghcr.io/hattimon/dcc-kiri-manager:0.1.0
docker exec -it dcc-kiri-manager python -m backend.admin
```

After the public Store entry appears, choose **DCC → DCC Kiri Manager** and review the loopback port in the installation preview. The Store's **Website** button points to the project site. Open the published loopback address on the Docker host for the installed panel. Run the same administrator command on that host using the actual container name. The default install has a data volume and no approved engine endpoint.

## Linux, Ubuntu or Debian

Kiri publishes amd64 and arm64 packages. For supported native Debian/Ubuntu systems with systemd, the optional helper can show its plan. With your approval it verifies the official package hash and architecture, installs Kiri Lite only if a Kiri package is absent, starts `kiri.service` and checks the dedicated socket.

```sh
bash setup-kiri-linux.sh --plan
bash setup-kiri-linux.sh --apply
```

This is a host-side operation. Review the package and configuration before running it on a host you administer. Kiri group membership carries engine-level authority. The script leaves membership to the administrator. Official package alternatives and requirements are in [Kiri on Linux](https://docs.runkiri.com/linux/).

### Panel on Docker connected to Kiri

For a runtime on the same Linux host with permission to bind the **dedicated** socket:

```sh
export KIRI_SOCKET_PATH=/run/kiri/docker.sock
export KIRI_SOCKET_GID="$(stat -c %g "$KIRI_SOCKET_PATH")"
docker compose -f compose.yaml -f compose.kiri-socket.yaml config
docker compose -f compose.yaml -f compose.kiri-socket.yaml up -d
```

Choose alias `local` in the wizard. The overlay attaches one socket file and the corresponding supplementary group. Avoid permissive socket modes, privileged containers and aliases that point at Docker. A file bind can retain the old inode when the engine recreates its socket. Recheck Kiri, then recreate only the panel while retaining the data volume. For a Store-installed panel, have the administrator recreate that panel only using its existing data volume and the reviewed socket options, or use a separately approved same-host native panel. The browser cannot change a running container's mounts.

### Panel directly on Kiri (NOT VERIFIED)

After candidate checks in [compatibility](compatibility.md), use the compatible CLI with the explicit Kiri endpoint. Docker Engine isn't required. This example uses the official Linux socket and requires an authorized client.

```sh
socket=/run/kiri/docker.sock
gid="$(stat -c %g "$socket")"
docker --host "unix://$socket" version
docker --host "unix://$socket" run -d --name dcc-kiri-manager \
  -p 127.0.0.1:8796:8796 --volume dcc_kiri_manager_data:/data \
  --mount "type=bind,src=$socket,dst=/run/dcc-kiri/engine.sock,readonly" \
  --group-add "$gid" -e 'KIRI_SOCKETS={"local":"/run/dcc-kiri/engine.sock"}' \
  --cap-drop ALL --security-opt no-new-privileges:true --read-only \
  --tmpfs /tmp:size=8m,mode=1777 --restart unless-stopped \
  ghcr.io/hattimon/dcc-kiri-manager:0.1.0
docker --host "unix://$socket" exec -it dcc-kiri-manager python -m backend.admin
```

Kiri documents the restart policy, volume and port inputs. The panel's socket mount, named-volume permissions, health and restart behavior require live Kiri testing on each architecture. If it cannot run with these minimum permissions, stop and review the diagnostic evidence. [Kiri Docker compatibility](https://docs.runkiri.com/features/).

### Raspberry Pi 4/5

Use Raspberry Pi OS **64-bit** and the arm64 image. Verify the board's kernel, systemd/cgroups and official Kiri package compatibility before installing. The AArch64 package exists upstream; Raspberry Pi OS and both board models remain **NOT VERIFIED**. Follow the same-host Linux instructions only on an approved and compatible installation. A 32-bit OS has no image for this release.

## Windows 10/11 AMD64 and WSL2

Install through [Kiri's Windows setup](https://docs.runkiri.com/windows/). Choose Kiri Linux for a dedicated WSL distribution or Ubuntu if you plan to inspect the daemon from a standard Linux shell. Use localhost for a loopback panel. Verify Windows CLI with `docker --context kiri version` before any run command. The official native named pipe is `npipe:////./pipe/kiri`.

- **Docker Desktop running the panel** can use the default Docker installation in configuration mode. Its Linux container does not see a Windows named pipe or another WSL distribution's socket. OCI connectivity for that arrangement is unsupported in 0.1.0.
- **Kiri running the panel directly** uses `docker --context kiri` with the loopback port, named volume and security options shown in the CLI command above. Connection requires access to `/var/lib/kiri-daemon/.kiri/run/docker.sock` inside Kiri's own WSL installation. Treat socket permissions and mount visibility as **NOT VERIFIED**. Inspect them on a test installation before applying the Linux bind configuration. Use admin credentials from that same engine.

## macOS Intel and Apple Silicon

Install Kiri on macOS 14 or later with the official Intel or ARM64 package. macOS applications can use `$HOME/.kiri/run/docker.sock` after Kiri starts. Both a Docker Desktop panel and a Kiri-hosted Linux panel can use the respective CLI to run in configuration mode. They have a separate guest kernel. A native host Unix socket is not an OCI connection method across that boundary in this version. [Official macOS installation](https://docs.runkiri.com/install/) · [Kiri architecture](https://docs.runkiri.com/how-it-works/).

An **experimental native Python** variant keeps the process and socket on macOS. Use Python 3.12, install the module's requirements in a virtual environment and start `python -m backend.admin` followed by `python -m backend`. Set `KIRI_SOCKETS` to a JSON mapping with an absolute canonical path to the dedicated socket, for example `{"mac":"/Users/alex/.kiri/run/docker.sock"}`. The default listener is loopback. This variant is separate from the OCI release.

## Diagnose, update, remove

- **No aliases:** configure `KIRI_SOCKETS` and attach the dedicated endpoint where supported. Reopen the wizard.
- **Permission denied:** check the socket ownership and numeric group. Match the panel's allowed supplementary group.
- **Kiri identity rejected:** verify the socket, upstream version and Docker context. Identity checks require the explicit Kiri fields and Server header.
- **Timeout or disconnect:** verify the engine is running, check whether its socket inode was replaced and retry. On-demand image storage may require longer than the current request limit.
- **Upgrade or rollback:** back up the dedicated data volume using a consistent SQLite backup or while this panel is stopped. Recreate the panel using the selected version and existing volume. If the schema is newer than the old image, restore the corresponding backup.
- **Uninstall:** remove only the panel container, for example `docker compose down` without volume removal. To keep profiles for later, retain `dcc_kiri_manager_data`. Restarting or removing Kiri itself is a separate host decision.
