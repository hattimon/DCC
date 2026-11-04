# Remote Access security and operations

## Network and credentials

Browser TLS terminates at the hosted zrok frontend. OpenZiti carries the connection to the zrok client. The final HTTP hop uses a dedicated internal Docker bridge with a separate DCC ingress port. There is no browser-to-DCC end-to-end TLS. The public frontend can see the HTTP payload. A separate bridge provides outbound connectivity, and the sidecar publishes no host ports.

DCC Web accepts traffic on the tunnel listener only from the inspected sidecar address and with the exact reserved Host. It rejects other Host and Origin values and ignores client-supplied forwarding headers. It issues Secure, HttpOnly, SameSite Strict session cookies and HSTS on that route. DCC login, MFA, CSRF, RBAC and profile capabilities still apply. Administrator accounts without MFA cannot sign in through the tunnel. The remote login rate limit uses a shared bucket so forwarded client identities cannot reset it. Remote Access configuration and credentials require the local panel. Host terminal access retains its existing profile permission.

The sidecar runs as UID 2171, with a read-only root filesystem, all capabilities dropped, no published ports, no Docker Socket, no SSH mount and no access to DCC's database or vault. Its enrollment material lives in a private tmpfs. At rest, DCC encrypts the enrollment using its existing vault. Preserve the DCC data volume and its master key together. Token input crosses Docker exec stdin and only enters zrok's transient process. The container log driver is disabled and raw provider command output is omitted from DCC responses and audit entries.

## Version and emergency policy

Reviewed image `docker.io/openziti/zrok2:2.0.9@sha256:00c5b65bbb5b7c045c1d23d35ab392f2edd43633ee8513c7a858899993f41d8f`. The index advertises Linux amd64 and arm64. It uses the Go HTTP proxy backend. It never starts the zrok controller, its public frontend or a Python ProxyShare on the DCC host.

- [CVE-2026-45568 / GHSA-jh67-hwqw-m5r7](https://github.com/openziti/zrok/security/advisories/GHSA-jh67-hwqw-m5r7) concerns absolute-URL SSRF in the Python ProxyShare, fixed in 2.0.3. The Go CLI proxy also validates the destination when rewriting proxy requests. [Pinned Go implementation](https://github.com/openziti/zrok/blob/v2.0.9/endpoints/proxy/backend.go)
- [CVE-2026-45576 / GHSA-c656-jcx2-7pqj](https://github.com/openziti/zrok/security/advisories/GHSA-c656-jcx2-7pqj) affects WebDAV copy and was fixed in 2.0.3. The [upstream advisories](https://github.com/openziti/zrok/security/advisories) also cover drive and hosted frontend/controller code. DCC uses HTTP proxy mode and depends on NetFoundry for hosted infrastructure updates.
- The source dependency check found reports in `golang.org/x/net` 0.59.0 and `golang.org/x/crypto` 0.57.0. The sidecar uses an HTTP/1 origin and disables Go's default HTTP/2 client and server paths. DCC's integration invokes no HTML parsing, rendering or OpenPGP modes in zrok. This review checked selected dependency versions and usage paths. [HTTP/2 advisory](https://pkg.go.dev/vuln/GO-2026-6603) · [HTML advisory](https://pkg.go.dev/vuln/GO-2026-6860) · [OpenPGP advisory](https://pkg.go.dev/vuln/GO-2026-5932) · [Go HTTP/2 settings](https://go.dev/doc/godebug)
- [zrok 2.0.9](https://github.com/openziti/zrok/releases/tag/v2.0.9) documents cleanup and retry fixes. A forced kill or provider outage can still leave an upstream registration. DCC closes its local ingress and refuses to attach to a name already held by a share. Release the stale share in the hosted console and retain the reserved name if you plan to reuse it.

An operator can add a confirmed affected digest to `/data/dcc-remote-blocked-digests.txt` (one lowercase SHA-256 digest per line) or set `DCC_REMOTE_BLOCKED_DIGESTS` at Web startup. An unreadable or malformed file closes the public gate. DCC checks policy on public requests and while monitoring. The sidecar also checks a local lease and exits when DCC is unavailable or the lease is withdrawn. This policy affects the tunnel only.

## Future Security Monitor contract

The local administrator's `GET /api/admin/remote-access` response reports the module version, image digest, security state, container and tunnel states, last connection, last safe error and update availability. It contains no credentials. `POST /api/admin/remote-access/disable` withdraws the ingress and stops the managed sidecar; the action is idempotent, CSRF-protected, auditable and bound to a fresh, single-use confirmation. Enable/restart require a local administrator, current password, MFA, confirmation and an eligible pinned image. Check-update reports upstream metadata without applying it.

A future monitor can use these fields for check/status and request a scoped disable. A future request-update action should authorize a reviewed digest and require an explicit restart/rollback plan. The monitor does not need Docker Socket access. An operator can already close the gate independently of the Docker action through the blocklist.

## Compose and test scope

`compose.yaml` describes the same hardened sidecar for managed-network diagnostics. The panel uses Docker's API to create the per-instance networks and container. To validate the Compose configuration without starting anything, set `DCC_REMOTE_OWNER=fixture` and `DCC_REMOTE_SUPERVISOR` to the contents of `supervise.sh`, then run `docker compose -f apps/dcc-remote-access/compose.yaml config --quiet` from the root. The network names refer to the panel-managed networks. Installation, token handling and lease issuance use the DCC Web UI.

The local tests do not prove NetFoundry enrollment, DNS, the hosted frontend, live public MFA/recovery, or an arm64 runtime. For a live acceptance test, use a disposable DCC Web installation and an authorized zrok account. Verify HTTPS and login end to end, then disable and confirm the endpoint can no longer reach DCC.
