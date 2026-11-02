# DCC Web 0.1.3 â€” unique current catalog entries

Version 0.1.3 ships the catalog merge fix that was absent from the published 0.1.2 image. Duplicate cached/bundled versions of the same application merge into one entry; older numeric versions cannot replace newer ones. DCC Web keeps Administration as its legacy primary category and adds DCC and WWW for clients supporting multiple categories. Desktop v1.3.12 includes the same catalog merge fix in EXE and DEB installers.

## Changes retained from 0.1.2

- Administrator-managed private SSH folder, browser-selected uploads, metadata/fingerprint previews and separate consent. External mounted folders remain read-only through the upload API.
- Select individual/all profiles, apply the shared folder only to selected SSH/Balena connections and retain individual paths elsewhere.
- Bulk profile removal with preview and confirmation, closing the affected terminals while retaining Docker resources and SSH files.
- Strict host verification in Docker CLI, SDK and terminal transports. No automatic transfer of private keys or trust of new hosts.
- Existing container controls, shared catalog, EN/PL interface, installation logs and monitoring are retained.

## Verified during preparation

- Desktop regression suite: 156 tests passed on Windows.
- Web API/transport tests: 77 run on Windows, OK with one symlink test skipped because the OS did not allow its creation; all 77 passed on Linux.
- The 13 SSH profile tests passed under UID 10001 in the built candidate image.
- Node frontend checks passed. Isolated Chromium exercised import, selection, migration, uploads/consent, editing, cancel deletion and EN/PL/mobile rendering without page errors.
- Image build and self-check passed; private keys from the user and production profiles were not accessed or altered.

## Limits

Remote SSH hosts were not contacted with user credentials. Imported Desktop paths still require explicit migration and copying selected files. Passphrases remain per-profile. Protect the data volume and backups: uploaded key files are not encrypted by DCC Web. Use a dedicated passphrase-protected key and HTTPS for non-loopback uploads. MCP remains a read-only Preview; see the feature matrix for transport restrictions.
