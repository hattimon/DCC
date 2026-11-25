# DCC Kiri Manager HTTP API

Requests and payloads use JSON. Open `GET /api/session` first to obtain the session state and `csrf`. Use the token from each login or setup response for subsequent state changes. For every mutation send `Content-Type: application/json`, the exact `Origin`, and `X-CSRF-Token`. The authenticated response includes preferences, configured socket aliases and profiles.

When `setup_available` is true, an initial local login returns `setup_pending: true` and `authenticated: false`. Complete setup with the new token and your chosen credentials. The setup response returns the authenticated session. An expired setup or an already configured account returns an error.

## Panel and settings

| Method and path | Purpose |
| --- | --- |
| GET `/healthz` | Process liveness only |
| GET `/api/session` | Session and bootstrap token |
| POST `/api/login` | `username`, `password` |
| POST `/api/setup` | Create the initial administrator with `username`, `password`, `confirmation` |
| POST `/api/logout` | Revoke the session, accepts an empty object |
| PUT `/api/preferences` | Any of `language` (en/pl), `theme` (dark/light), `interval` (0/15/30/60/120 s), `onboarded` (boolean) |
| GET `/api/install/linux` | Authenticated download of the optional Linux install helper |
| POST `/api/profiles` | Add a profile using `name`, `host`, `runtime`, `endpoint` |
| POST `/api/profiles/test` | Read availability without creating a profile |
| PUT `/api/profiles/{id}` | Edit using the four fields and the current `revision` |
| DELETE `/api/profiles/{id}` | Remove local settings using the current `revision` |
| PUT `/api/profiles/{id}/active` | Select the profile, accepts an empty object |

The endpoint field is a configured alias. Host values are `linux`, `wsl` and `macos`. Runtime values are `docker`, `kiri` and `native`. Profile IDs are local hexadecimal identifiers.

## Engine reads

All paths start with `/api/profiles/{id}`. Kiri must pass identity verification before an engine read. Missing values are absent or JSON null. Lists distinguish a successful empty response from an unavailable endpoint.

| GET route | Data |
| --- | --- |
| `/status` | Verified Kiri version, API range and selected API, architecture and OS |
| `/snapshot` | Resource lists, connections, counts and operation checks |
| `/inventory/{kind}` | Container, image, volume, network or Compose list |
| `/inventory/{kind}/{key}` | Sanitized detail from containers/images/volumes/networks |
| `/containers/{key}/logs?tail=100` | One bounded text block. Tail accepts 1–200 |
| `/containers/{key}/stats` | Single bounded CPU, memory, network and block I/O sample |
| `/disk` | Image layer bytes via Kiri `system/df` |

Failures return `{"error":"code"}`. Examples include `bad_engine`, `api_version`, `socket_missing`, `permission_denied`, `timeout`, `unsupported`, `large_response`, `profile_conflict` and `login_limited`. A profile test or snapshot may identify the engine while reporting individual unavailable reads. [Upstream operation matrix](kiri-audit.md).
