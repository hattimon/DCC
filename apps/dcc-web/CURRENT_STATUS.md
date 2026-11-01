# DCC Web 0.1.0 — release candidate for DCC Desktop 1.3.11

The release candidate is prepared on `codex/desktop-web-1-3-11`. It is not yet a public image or Desktop release. The App Store entry and formatted product page are included in this branch's `dcc-catalog.json` and will ship with Desktop 1.3.11.

## Implemented

- Shared multi-category store logic: All → Installed → bold DCC → AI; DCC Container Updater remains in Updates and DCC. DCC Web is in DCC, Administration and WWW.
- DCC Web product page in English and Polish, a formatted in-panel Markdown documentation view, and the Store Website link.
- Container links and image-reference copying, project/network grouping and selection, bulk actions, profile permissions, installation progress and logs.
- Centered active-host infrastructure, host terminals, grouped container controls, localized interface, and narrow-screen toolbar layout. At 375 px, search is 96 px wide while filters and actions stay aligned on one row.
- Local audio defaults to enabled; playback starts after browser interaction and can be disabled in settings.
- Docker image startup detects the mounted socket's group and drops to UID 10001. The catalog configuration supports its tmpfs and PID-limit options.

## Verified locally

- Desktop regression: 153 tests passed.
- Store catalog feature tests: 28 passed.
- DCC Web tests: 54 passed; frontend localization/grouping checks passed.
- Docker image built, self-check passed, and a restricted container verified Docker socket access and Compose as UID 10001.
- Chromium at 375 px confirmed 96 px search width and one-row filter/action alignment.
- A previous isolated Debian 1.3.10 → 1.3.11 package upgrade preserved profile and settings data.
- `git diff --check` and Python compilation passed.

## Publication gates

- The Windows 1.3.10 → 1.3.11 installer upgrade check runs on the hosted Windows CI runner.
- Candidate CI must pass before publishing the GHCR image and Desktop v1.3.11 release.
- PR #3 remains unmerged; the canonical `main` catalog stays untouched until the user chooses to merge it.

Private profiles, credentials, runtime logs and local QA data are excluded from the branch.
