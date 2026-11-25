# Kiri upstream audit

Reviewed on 2026-11-25. Latest tagged upstream release observed was **Kiri 0.2.2**, published on 2026-11-19. GitHub marks the tag as a normal release; upstream labels Kiri beta on Windows, macOS and Linux. The Kiri repository is Apache-2.0, with Linux guest kernel sources offered separately under GPL-2.0. [Release](https://github.com/libracoder/kiri/releases/tag/v0.2.2) · [License](https://github.com/libracoder/kiri/blob/v0.2.2/LICENSE) · [Official installation](https://docs.runkiri.com/install/).

Kiri supplies a Docker-compatible Engine API, Docker CLI, Compose and Buildx. BuildKit runs builds. Linux packages use a systemd daemon on the Linux kernel. macOS uses Apple's Virtualization framework and a macOS host socket. Windows has a real Kiri daemon inside WSL2, bridged to `npipe:////./pipe/kiri` for Windows clients. Official docs describe OCI images, named volumes, Unix mounts, bridge networks, published ports, logs and stats. Kiri also provides k3s and Kiri Share. Their management is outside the panel's read-only scope. [Architecture](https://docs.runkiri.com/how-it-works/) · [Features](https://docs.runkiri.com/features/) · [Linux](https://docs.runkiri.com/linux/) · [Windows](https://docs.runkiri.com/windows/) · [CLI](https://docs.runkiri.com/cli/).

## Engine identity and read matrix

Kiri 0.2.2 reports the Docker compatibility version `27.5.1`. The upstream `GET /version` implementation separately identifies `Platform.Name=Kiri`, `KiriVersion`, a same-version named component and a matching `Server: Kiri/<version> (linux)` header. The panel checks all of those values and rejects ambiguous or legacy replies. A successful transport grant still depends on the filesystem publisher being trusted. The connector accepts a negotiated Docker API in `1.41–1.47` and refuses a non-overlapping range. Kiri 0.2.2 advertises 1.24–1.47. [Version routes](https://github.com/libracoder/kiri/blob/v0.2.2/crates/kiri/src/daemon/api.rs#L385-L413) · [HTTP headers](https://github.com/libracoder/kiri/blob/v0.2.2/crates/kiri/src/daemon/http.rs#L283-L303).

| GET operation | Source evidence | Panel behavior |
| --- | --- | --- |
| `/version` | Kiri fields and Docker version range | Identity before reading any resources |
| `/info` | Engine-reported resources and warnings | OS and architecture from identity, counts and bounded reporting. No raw warnings or host paths |
| `/containers/json?all=1` | Known states, names, ports, labels, health text | Inventory, filtering, Compose labels and dashboard counts |
| `/containers/{id}/json` | Inspect and health where available | Safe state, dates, network names and ports |
| `/containers/{id}/logs` | Raw TTY or Docker multiplexed framing, bounded tail, driver-dependent | On demand, up to 200 lines / 128 KiB, common secret masking |
| `/containers/{id}/stats?stream=0` | Two samples for CPU where present | Selected container CPU, memory, network and block counters |
| `/images/json`, `/images/{id}/json` | Image tags, sizes, creation and inspect architecture | Group tags by ID, architecture on detail |
| `/volumes`, `/volumes/{name}` | Metadata and names | No private files. Attachments via container list volume filter |
| `/networks`, `/networks/{id}` | Drivers, IPAM, endpoints on inspect | Names, subnets and connected container names |
| `/system/df` | Deduplicated image layers, guest measurement where available | Read image-layer total on explicit request. Kiri can spend longer than the panel timeout |
| Compose | Standard labels via containers and CLI documentation | Observed project/service groups. Volume contents and Compose files are outside scope |

Routes are implemented upstream at [api.rs](https://github.com/libracoder/kiri/blob/v0.2.2/crates/kiri/src/daemon/api.rs) and [ops.rs](https://github.com/libracoder/kiri/blob/v0.2.2/crates/kiri/src/daemon/ops.rs). Managed BuildKit, Kiri's local domains and advanced UI are separate. Kiri adds its own resource names, rewrites version for client compatibility and has platform-specific network and permission constraints. Unknown read routes, incompatible versions, endpoint errors and timeouts surface separately. The connector uses upstream's background request hint to avoid counting routine polls as activity. [Daemon request handling](https://github.com/libracoder/kiri/blob/v0.2.2/crates/kiri/src/daemon/api.rs#L20-L43).

Relevant upstream reports include [Compose stop-state display #903](https://github.com/libracoder/kiri/issues/903) and [registry TLS trust #885](https://github.com/libracoder/kiri/issues/885). The panel translates the API state field and does not alter registry validation. Platform evidence and remaining gaps are in the [compatibility matrix](compatibility.md).
