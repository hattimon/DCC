# DCC Web 0.1.0 — source preview checkpoint

This branch preserves the Desktop 1.3.11 candidate and existing DCC category work. It is a source preview, not a claim that every planned feature is released.

## Implemented

- Shared categories: All → Installed → bold DCC → AI; Updater remains in DCC and Updates. All three primary Web categories are bold.
- Unique panel endpoints with open/copy controls, full image-reference copying and themed scrollbars.
- Project/network/flat grouping, group checkboxes, sticky lifecycle/autostart/diagnostic controls and explicit profile permissions.
- Active-profile infrastructure in the centered header; Terminal → Store → New container in Overview and Containers.
- Separate terminal windows/tabs: verified SSH, Windows/Linux PTY and WSL; admin-only host.exec, session ownership and configurable limits (16 by default, up to 32).
- Host terminals require HTTPS outside localhost; SSH verifies known hosts. Terminal CSS permits inline styles for xterm; scripts remain self-only.
- Installation phases, streamed image-pull logs, success/failure, copy/download and encrypted startup access details explicitly revealed to the installing administrator.
- Home Assistant uses a published port and persistent /config volume by default. Host-network panel links can be inferred from catalog metadata.
- Existing EN/PL, AI proposal adapters, themes/audio, multi-source store and read-only MCP Preview remain available.

## Executed checks

- Web unit tests: **54 passed** (50 API/features and 4 terminal ownership/limit/buffer tests).
- Node translation/grouping tests and JavaScript syntax checks passed.
- Chromium operator checks: **6 scenarios passed**, no console errors.
- Real Windows PTY browser smoke: same authenticated session, test command executed, no console errors.
- Latest in-window tabs, group-header checkboxes and streamed installation UI still need final extended browser acceptance.
- Fresh Desktop regression after the shared-parser change: **152 passed**, no failures/errors/skips.
- git diff --check passed. Earlier isolated EXE/DEB and updater acceptance remains separate evidence.

## Remaining for subsequent work

- Final Web container bootstrap and one-click official App Store entry.
- Automatic Web update checks on refresh.
- Optional public HTTPS tunnel extension: installation, pause/disable/uninstall and public URL.
- Formatted in-app documentation (current routes still display Markdown text) and a polished public information page.
- Refreshed release artifacts, public release and catalog promotion after final acceptance.

Private user profiles, credentials, SQLite state, keys, runtime logs and local backups are excluded from Git. The original D:\CODEX\DCC working tree is preserved. Main and PR #2 are not automatically merged. Publishing this source branch does not publish an image, installer release or catalog entry.

Project: [hattimon/DCC](https://github.com/hattimon/DCC).
