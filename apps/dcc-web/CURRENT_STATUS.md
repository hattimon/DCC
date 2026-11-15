# DCC Web 0.3.4

DCC Web 0.3.4 sends the zrok v2 API media type when releasing a verified stale share, allowing the saved reservation to be reused. Recovery consent persists through failed provider calls. Updater 1.1.8 can transfer existing consent from an older, stopped tunnel when replacing Web.

The panel gateway preserves document language and root attributes, opens locally published ports through a restricted Docker helper, and streams HTTP responses over verified SSH channels. The release workflow exercises the Updater UI in Chromium and upgrades the published DCC Web 0.3.1 image while checking its data volume, Caddy and a running project panel. A separate test checks managed tunnel handoff and rollback with a synthetic zrok provider.

Publication status is tracked by the GitHub release workflow. Compatibility limitations remain documented in `docs/panels.md`.
