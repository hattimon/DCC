# Architecture

Python 3.12 and Waitress serve Flask JSON endpoints and ES modules. SQLite holds configuration and a password hash. The panel has no client build step and no runtime dependency on DCC Desktop, DCC Web or Container Updater.

## Request path

1. A browser reaches the loopback-published panel or an explicitly configured HTTPS entry point.
2. The server verifies an administrator session. Changes to local configuration also require the exact Origin and a per-session CSRF token.
3. A resource URL names a stored profile. Kiri Connector maps its alias to a Unix socket configured by the administrator.
4. The connector checks socket type and identity, verifies Kiri and negotiates an API version. Every engine request is a fixed or validated GET.
5. Resource projections omit secrets, commands, host paths and arbitrary labels before the browser receives JSON.

The browser reads one selected running container per refresh. Polling runs after the prior request settles, pauses while the tab is hidden or the user is editing, and retains at most 24 samples in memory. A semaphore bounds concurrent engine reads. No poll writes metrics to SQLite.

## Profiles and persistence

`/data/config.sqlite3` is stored in the panel's own named volume. SQLite transactions serialize edits. Profile revisions detect stale edits, and deleting the active profile clears its pointer. Preferences survive a restart independently of the signed session, whose signing material is generated in memory at startup. Only hashed password and session data are written. Schema upgrades from established versions back up the SQLite database first and commit migrations atomically. A newer schema blocks startup with an older binary.

## Installation authority

The engine is installed by an administrator-approved program on the host. The container has no host execution interface. The wizard provides official upstream instructions and a pinned Debian/Ubuntu helper; an authorized administrator chooses and attaches the dedicated socket. In-container socket access and panel runtime are independent. See [installation](installation.md) and [security](security.md).
