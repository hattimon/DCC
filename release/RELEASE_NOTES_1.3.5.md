# Docker Control Center v1.3.5

## Changes
- Added a real manual container configuration mode. Creating a container no longer forces the first catalog preset to be selected.
- Fixed `Configure -> Edit start`: the header and form now stay attached to the actual container being edited, and background catalog refresh cannot replace its values with Agent Zero or another preset.
- Expanded reconstruction of existing `docker run` settings, including user/workdir, custom networks, capabilities, DNS, extra hosts, devices, memory/CPU limits, tmpfs, labels, named volumes and entrypoint handling.
- Fixed named-volume reconstruction so Docker volume names are preserved instead of being converted into `/var/lib/docker/volumes/...` bind mounts.
- Catalog presets deployed through Docker now use `--pull always`, so moving tags such as `latest` and `main` fetch the current image before start/recreate. Manual/local-image configurations are left unchanged.
- The main DCC application catalog is refreshed asynchronously at DCC startup and again when the deployment catalog is opened.
- Added upstream GitHub release metadata to catalog entries and display of the latest upstream release in the application card.
- Added `tools/update_catalog_metadata.py` and a scheduled GitHub Actions workflow that refreshes release metadata for existing catalog apps.
- Added automated discovery of popular self-hosted/container projects into `catalog/candidates.json`. Discovered projects require review before they can enter the installable catalog.

## Validation
- Python source and catalog-maintenance script compile successfully.
- Catalog, edit-mode and catalog-maintenance regression suite: 10 tests passing.

## Packages
- Windows installer: `DockerControlCenter-Setup-1.3.5.exe`
- Debian/Ubuntu/MX Linux package: `DockerControlCenter_1.3.5_amd64.deb`
