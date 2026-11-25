# DCC Web 0.3.7

DCC Web 0.3.7 expands log access-detail recognition, follows the newest log entry on refresh and delegates image selection and replacement to DCC Updater.

DCC Web 0.3.6 improves SSH Docker operations for Linux/Balena and Windows hosts. Docker JSON/Go templates and arguments containing spaces or shell metacharacters are passed intact. The profile wizard lets administrators select a remote shell (POSIX or Windows PowerShell), including for the Docker SDK connection used by container updates. Profiles still require trusted host keys and an explicit successful SSH/Docker check or conscious unverified save.

DCC Web 0.3.5 added a separate SSH connection test and MCP host permission guidance. Panel jobs and MCP Docker mutations on the same profile use a shared lock. The grant editor detects changes saved after the form was opened.

DCC Web 0.3.4 sends the media type required by zrok when releasing a verified stale share. Web can then reopen the saved reservation. Recovery consent persists through failed provider calls, and Updater 1.1.9 can transfer that consent when replacing a Web container with a stopped tunnel.

The panel gateway preserves document language and root attributes, opens locally published ports through a restricted Docker helper, and streams HTTP responses over verified SSH channels. The release workflow checks the Updater UI in Chromium and exercises upgrades from DCC Web 0.3.3 and 0.3.4 with the Updater 1.1.9 update service. The Docker test verifies the data volume, HTTPS port and CA, a running project panel, and tunnel resumption after both rollback and a successful update. It uses a simulated zrok provider.

Publication status is tracked by the GitHub release workflow. Compatibility limitations remain documented in `docs/panels.md`.
