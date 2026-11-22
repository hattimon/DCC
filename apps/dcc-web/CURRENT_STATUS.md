# DCC Web 0.3.5

DCC Web 0.3.5 adds an SSH connection test for host profiles and explains MCP host access denials. Panel jobs and MCP Docker mutations on the same profile use a shared lock. The grant editor detects changes saved after the form was opened.

DCC Web 0.3.4 sends the media type required by zrok when releasing a verified stale share. Web can then reopen the saved reservation. Recovery consent persists through failed provider calls, and Updater 1.1.9 can transfer that consent when replacing a Web container with a stopped tunnel.

The panel gateway preserves document language and root attributes, opens locally published ports through a restricted Docker helper, and streams HTTP responses over verified SSH channels. The release workflow checks the Updater UI in Chromium and exercises upgrades from DCC Web 0.3.3 and 0.3.4 with the Updater 1.1.9 update service. The Docker test verifies the data volume, HTTPS port and CA, a running project panel, and tunnel resumption after both rollback and a successful update. It uses a simulated zrok provider.

Publication status is tracked by the GitHub release workflow. Compatibility limitations remain documented in `docs/panels.md`.
