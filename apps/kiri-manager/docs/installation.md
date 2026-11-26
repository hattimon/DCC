# Installation

The panel listens internally on 8796/tcp. The supplied mappings expose it on the host's loopback interface. It runs without Kiri and opens configuration after administrator sign-in.

## Preferred automatic flow (DCC Windows + panel)

Open **DCC Store → DCC Kiri Manager**. The desktop app probes `npipe:////./pipe/kiri` directly, confirms Kiri's `/version` identity and reads the container inventory. It then offers **Connect**. If the pipe is absent, it offers **Install Kiri** with the [official Windows installation guide](https://docs.runkiri.com/windows/). Access denied or a non-Kiri endpoint shows a specific reason and a next step. Switching Docker contexts is not required.

After connecting to Kiri in DCC, reopen the Store entry to install the panel. The desktop app asks for administrator consent before mounting the engine socket, pulls the approved panel image and launches a disposable Kiri container to test the *actual* WSL socket bind, Kiri identity and inventory as panel UID 10001. Only a successful test permits panel creation with `dcc_kiri_manager_data:/data`. DCC then requests `http://127.0.0.1:8796/healthz` from Windows and verifies both a panel-specific response header and JSON payload. If the WSL port is not reachable from Windows, it removes only the new container and preserves the data volume; check WSL port forwarding and port 8796 conflicts before retrying. Failed tests do not change existing installations. Docker Desktop cannot automatically access the Windows named pipe or an unrelated WSL distribution's socket. Full Windows/WSL panel installation is **not yet verified on a real Windows host**.

Inside the web panel, **Connect** appears automatically if the administrator already supplied an accessible, verified Kiri socket. Otherwise the page explains whether transport is missing, access was refused or engine identity failed, and links to setup guidance. The manual alias and terminal wizard is under **Advanced manual configuration**. A browser cannot install a host runtime or change container mounts on its own.

## Docker and the DCC Store

From the module directory on the intended Docker host:

```sh
docker compose up -d
```

Open http://127.0.0.1:8796/ on that host. To use a different host port, set `KIRI_PANEL_HOST_PORT` before Compose. In the Store, choose **DCC → DCC Kiri Manager** and use the local address shown after installation. The **Website** button opens the project site.

### First sign-in

When the volume has no administrator, sign in locally with username `admin` and password `admin`. The startup logs show those temporary credentials. Before entering the panel, choose a password of 14–128 characters and optionally change the username. Upgrading an existing volume preserves configured credentials and settings.

### Install from the command line

```sh
docker run -d --name dcc-kiri-manager --restart unless-stopped \
  -p 127.0.0.1:8796:8796 --volume dcc_kiri_manager_data:/data \
  --read-only --tmpfs /tmp:size=8m,mode=1777 --cap-drop ALL \
  --security-opt no-new-privileges:true --memory 192m --pids-limit 40 \
  ghcr.io/hattimon/dcc-kiri-manager:0.1.2
```

## Terminal setup and password reset

Expand the help on the sign-in screen to see commands for the host. For a reset, run the command for your runtime using the actual panel container name.

```sh
# Docker
docker exec -it dcc-kiri-manager python -m backend.admin --reset

# Kiri with the kiri context
docker --context kiri exec -it dcc-kiri-manager python -m backend.admin --reset

# Kiri on native Linux
docker --host unix:///run/kiri/docker.sock exec -it dcc-kiri-manager python -m backend.admin --reset

# Native Python, from the panel directory with the same KIRI_PANEL_DATA
python -m backend.admin --reset
```

Enter and confirm the new password in the terminal. Resetting revokes active sessions and preserves the username, profiles and settings. Add `--username operator` to change the username. For first-time terminal setup, use `python -m backend.admin` as the command in the container or directly from the native Python environment. Provision the account before exposing the panel through a configured HTTPS reverse proxy.

## Linux, Ubuntu or Debian

Kiri publishes amd64 and arm64 packages. For supported native Debian/Ubuntu systems with systemd, the optional helper can show its plan. With your approval it verifies the official package hash and architecture, installs Kiri Lite only if a Kiri package is absent, starts `kiri.service` and checks the dedicated socket.

```sh
bash setup-kiri-linux.sh --plan
bash setup-kiri-linux.sh --apply
```

This is a host-side operation. Review the package and configuration before running it on a host you administer. Official package alternatives and requirements are in [Kiri on Linux](https://docs.runkiri.com/linux/).

### Authorize a containerized panel on native Linux

Kiri 0.2.2 checks the connecting process's host UID against the host account database as well as the socket's filesystem permissions. Give the panel's host UID `10001` a dedicated non-login account and authorize it in Kiri before using either container variant. This helper option assumes the container UID maps directly to the host UID. It stops if that UID or account name is already allocated to another user. [Kiri peer UID check](https://github.com/libracoder/kiri/blob/v0.2.2/crates/kiri/src/daemon/access.rs).

```sh
bash setup-kiri-linux.sh --plan --grant-panel-access
bash setup-kiri-linux.sh --apply --grant-panel-access
```

The explicit grant enrolls `dcc-kiri-panel` through `kiri host-access`. Kiri group membership carries engine-level authority. To revoke the grant, remove that account from the `kiri` group on the host. User-namespace mappings need an independent check of the effective host UID.

### Panel on Docker connected to Kiri

For a runtime on the same Linux host with permission to bind the **dedicated** socket:

```sh
export KIRI_SOCKET_PATH=/run/kiri/docker.sock
export KIRI_SOCKET_GID="$(stat -c %g "$KIRI_SOCKET_PATH")"
docker compose -f compose.yaml -f compose.kiri-socket.yaml config
docker compose -f compose.yaml -f compose.kiri-socket.yaml up -d
```

Choose alias `local` in the wizard. The overlay attaches one socket file and the corresponding supplementary group. Avoid permissive socket modes, privileged containers and aliases that point at Docker. A file bind can retain the old inode when the engine recreates its socket. Recheck Kiri, then recreate only the panel while retaining the data volume. For a Store-installed panel, have the administrator recreate that panel only using its existing data volume and the reviewed socket options, or use a separately approved same-host native panel. The browser cannot change a running container's mounts.

### Panel directly on Kiri

Use the Docker-compatible CLI with the explicit Kiri endpoint. This example uses the official Linux socket and requires an authorized client. The runtime settings passed integration with Kiri Lite 0.2.2 on Ubuntu 24.04.5 LTS for amd64 and arm64. [Compatibility](compatibility.md).

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
  ghcr.io/hattimon/dcc-kiri-manager:0.1.2
```

The integration run confirmed the socket mount, loopback port, non-root startup and retained configuration after a panel restart on both architectures. It loaded the image from the verified archive on each runner. [Integration results](verification.md#integracja-na-github-actions).

### Raspberry Pi 4/5

Use Raspberry Pi OS **64-bit** and the arm64 image. Verify the board's kernel, systemd/cgroups and official Kiri package compatibility before installing. The AArch64 package exists upstream; Raspberry Pi OS and both board models remain **NOT VERIFIED**. Follow the same-host Linux instructions only on an approved and compatible installation. A 32-bit OS has no image for this release.

## Windows 10/11 AMD64 and WSL2

Install through [Kiri's Windows setup](https://docs.runkiri.com/windows/). Choose Kiri Linux for a dedicated WSL distribution or Ubuntu if you plan to inspect the daemon from a standard Linux shell. Use localhost for a loopback panel. Verify Windows CLI with `docker --context kiri version` before any run command. The official native named pipe is `npipe:////./pipe/kiri`.

Kiri documents its WSL daemon at `/var/lib/kiri-daemon/.kiri/run/docker.sock`. DCC uses that as a **candidate bind within Kiri's own runtime only**, then tests the mount and effective panel permissions before installation. This does not authorize Docker Desktop to mount a foreign WSL file. A failed test means the operator must review Kiri's WSL socket access with the administrator; DCC never changes WSL ownership, permissions, or an installed manager automatically. The installer/WSL setup may request Windows administrator elevation; DCC does not silently approve it.

- **Docker Desktop running the panel** can use the default Docker installation in configuration mode. Connecting through the Windows named pipe or a socket in another WSL distribution is outside the OCI connector's supported paths.
- **Kiri running the panel directly** uses `docker --context kiri` with the loopback port, named volume and security options shown in the CLI command above. Connection requires access to `/var/lib/kiri-daemon/.kiri/run/docker.sock` inside Kiri's own WSL installation. Treat socket permissions and mount visibility as **NOT VERIFIED**. Inspect them on a test installation before applying the Linux bind configuration. Use admin credentials from that same engine.

## macOS Intel and Apple Silicon

Install Kiri on macOS 14 or later with the official Intel or ARM64 package. macOS applications can use `$HOME/.kiri/run/docker.sock` after Kiri starts. Both a Docker Desktop panel and a Kiri-hosted Linux panel can use the respective CLI to run in configuration mode. They have a separate guest kernel. A native host Unix socket is not an OCI connection method across that boundary in this version. [Official macOS installation](https://docs.runkiri.com/install/) · [Kiri architecture](https://docs.runkiri.com/how-it-works/).

An **experimental native Python** variant keeps the process and socket on macOS. Use Python 3.12, install the module's requirements in a virtual environment and start `python -m backend`. Set `KIRI_SOCKETS` to a JSON mapping with an absolute canonical path to the dedicated socket, for example `{"mac":"/Users/alex/.kiri/run/docker.sock"}`. Open the local address to set up the administrator.

## Diagnose, update, remove

- **No aliases:** configure `KIRI_SOCKETS` and attach the dedicated endpoint where supported. Reopen the wizard.
- **Permission denied or immediate disconnect:** check the socket group and make sure the panel's effective host UID is enrolled in Kiri. The socket overlay also needs the socket's numeric group.
- **Kiri identity rejected:** verify the socket, upstream version and Docker context. Identity checks require the explicit Kiri fields and Server header.
- **Timeout or disconnect:** verify the engine is running, check whether its socket inode was replaced and retry. On-demand image storage may require longer than the current request limit.
- **Upgrade or rollback:** back up the dedicated data volume using a consistent SQLite backup or while this panel is stopped. Recreate the panel using the selected version and existing volume. If the schema is newer than the old image, restore the corresponding backup.
- **Uninstall:** remove only the panel container, for example `docker compose down` without volume removal. To keep profiles for later, retain `dcc_kiri_manager_data`. Restarting or removing Kiri itself is a separate host decision.

## 0.1.3 review candidate and SSH

The default Compose file and Store continue to reference published 0.1.2. For an isolated review environment, the standalone review file is `compose.candidate.yaml`; it builds `dcc-kiri-manager:0.1.3-review` from source. Use only after explicit authorization on the intended host, with an isolated data volume and port. No extra UID/GID access is required for the existing socket. To configure SSH, open Connections → New SSH profile, choose the expected engine, host/port/user, enter a verified unhashed known_hosts line and password or private key. The remote Docker CLI must already target the intended engine and the account must have engine permissions. Test before saving and activating. A changed endpoint requires fresh credentials. Back up the database and master-key privately. Schema 3 is incompatible with 0.1.2: to roll back, stop the panel and restore the schema-2 backup from before upgrade; changes made after migration are not carried back.

For an approved isolated review, use only the standalone file (optionally add the socket overlay): `docker compose -f compose.candidate.yaml up --build -d`. The review project, container, data volume and loopback port 18796 are separate from the published panel. Do not combine this file with the published compose.yaml. Production migration must be planned separately.
