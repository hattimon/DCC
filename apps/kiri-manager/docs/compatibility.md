# Platform compatibility

Published panel image 0.1.3. Disposable GitHub-hosted Ubuntu 24.04.5 runners verified the 0.1.3 image with Kiri 0.2.2 and Docker on AMD64 and ARM64, including lifecycle actions, volume retention, SSH password and encrypted-key authentication, and host-key rejection. These runs establish compatibility on the isolated runner configuration; they do not establish access to an individual Windows/WSL installation. **SUPPORTED** denotes a complete integration run on the stated configuration. **EXPERIMENTAL** is limited evidence, **NOT VERIFIED** lacks end-to-end evidence, and **UNSUPPORTED** has no supported transport or architecture in this release.

Local OCI builds covered `linux/amd64` and `linux/arm64`. A Windows/amd64 operator confirmed that the native Docker CLI connected to Kiri 0.2.2 in context `kiri`, negotiated API 1.47 (server range 1.24–1.47) and saw Kiri's Linux/amd64 engine. That CLI observation is separate from the panel's own socket, API reads and OCI checks.

The supported Linux rows cover panel 0.1.3 with Kiri Lite 0.2.2 on Ubuntu 24.04 LTS GitHub runners. The integration used a dedicated Unix socket and the panel's UID 10001. For the release evidence, see the [0.1.3 verification report](verification.md#weryfikacja-wydania-013).

| System | Arch | Panel runtime | Upstream Kiri | Connection | Status |
| --- | --- | --- | --- | --- | --- |
| Windows 10/11 | amd64 | DCC desktop (host client) | Official WSL2 installer | Direct `npipe:////./pipe/kiri` Kiri identity + inventory | EXPERIMENTAL (read-only check passed with Kiri 0.2.2) |
| Windows 10/11 | amd64 | Docker Desktop | Official WSL2 installer | Windows pipe and cross-WSL/VM socket | UNSUPPORTED |
| Windows 10/11 | amd64 | Kiri / WSL2 | Official WSL2 installer | Same-engine Unix mount after disposable container preflight | NOT VERIFIED |
| Ubuntu 24.04.5 LTS | amd64 | Docker | Kiri Lite 0.2.2 | Dedicated same-host socket | SUPPORTED |
| Ubuntu 24.04.5 LTS | amd64 | Kiri | Kiri Lite 0.2.2 | Dedicated same-host socket | SUPPORTED |
| Ubuntu 24.04.5 LTS | arm64 | Docker | Kiri Lite 0.2.2 | Dedicated same-host socket | SUPPORTED |
| Ubuntu 24.04.5 LTS | arm64 | Kiri | Kiri Lite 0.2.2 | Dedicated same-host socket | SUPPORTED |
| Debian | amd64 | Docker | Official package | Dedicated same-host socket | NOT VERIFIED |
| Debian | amd64 | Kiri | Official package | Dedicated same-host socket | NOT VERIFIED |
| Debian | arm64 | Docker | Official package | Dedicated same-host socket | NOT VERIFIED |
| Debian | arm64 | Kiri | Official package | Dedicated same-host socket | NOT VERIFIED |
| Raspberry Pi OS 64-bit, Pi 4/5 | arm64 | Docker | Official arm64 Linux artifacts, board unverified | Dedicated same-host socket | NOT VERIFIED |
| Raspberry Pi OS 64-bit, Pi 4/5 | arm64 | Kiri | Official arm64 Linux artifacts, board unverified | Dedicated same-host socket | NOT VERIFIED |
| macOS 14+ Intel | amd64 | Docker Desktop | Official Intel build | Host-to-guest Unix socket | UNSUPPORTED |
| macOS 14+ Intel | amd64 | Kiri | Official Intel build | Host-to-guest Unix socket | UNSUPPORTED |
| macOS 14+ Apple Silicon | arm64 | Docker Desktop | Official Apple Silicon build | Host-to-guest Unix socket | UNSUPPORTED |
| macOS 14+ Apple Silicon | arm64 | Kiri | Official Apple Silicon build | Host-to-guest Unix socket | UNSUPPORTED |
| macOS 14+ Intel / Apple Silicon | amd64 / arm64 | Native Python | Official builds | Same-host Unix socket | EXPERIMENTAL |
| Linux 32-bit | armv7 / 386 | OCI | Outside prepared architectures | — | UNSUPPORTED |

**How to read the table.** Image build, container startup, Kiri availability, connector transport, API response formats and operation-by-operation behavior are independent. Unsupported connection rows can still be used in configuration mode if that runtime can start the image. Chromium and mock results do not establish production interoperability. See [audit](kiri-audit.md), [verification](verification.md) and [upstream install matrix](https://docs.runkiri.com/install/).

For release 0.1.3, SSH to Kiri and Docker over the fixed remote CLI and all six lifecycle actions passed on disposable GitHub-hosted runners for both architectures. The tests verified pinned host-key acceptance, rejection of a wrong key, password and encrypted private-key authentication, inventory, lifecycle operations and named-volume retention. A user's Windows/WSL engine was not used for release testing; cross-VM socket access remains **NOT VERIFIED**. A real SSH endpoint must retain the engine Server header and support persistent HTTP on dial-stdio.
