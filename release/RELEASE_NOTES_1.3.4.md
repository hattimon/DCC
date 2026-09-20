# Docker Control Center v1.3.4

## Changes
- Added `https://github.com/hattimon/DCC` as the permanent primary deployment catalog repository.
- The deployment catalog now checks repositories automatically in the background when the catalog window opens, without blocking the UI.
- The primary DCC repository cannot be removed accidentally; additional catalog repositories can still be added and removed by the user.
- Manual catalog refresh remains available and uses the same local cache fallback when a repository is temporarily unavailable.
- Added a canonical root `dcc-catalog.json` manifest intended to be updated in the DCC GitHub repository whenever new applications are added.

## Packages
- Windows 11 installer: `DockerControlCenter-Setup-1.3.4.exe`
- Debian/Ubuntu/MX Linux package: `DockerControlCenter_1.3.4_amd64.deb`
