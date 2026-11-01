# Installation and local operation

Requires Python 3.12, Docker CLI and access to the selected Docker host. WSL transport requires Windows. SSH uses Paramiko and verified `known_hosts`. There is no frontend compilation step.

```powershell
python -m venv apps/dcc-web/.venv
apps/dcc-web/.venv/Scripts/python.exe -m pip install -r apps/dcc-web/requirements.txt
apps/dcc-web/.venv/Scripts/python.exe apps/dcc-web/web.py --data apps/dcc-web/.data
```

Linux: create the equivalent venv with `python3 -m venv`, install the requirements and use `apps/dcc-web/start.sh`. Default address is `http://127.0.0.1:8789`. `/login` offers initial local administrator creation only while no user exists. Use your own password; test-fixture credentials are not production defaults. Run only one instance per port/data directory.

The Windows launcher also detects the prepared root `.venv-release-1311`. `DCC_WEB_PYTHON` overrides the interpreter; `-DataDirectory` and `-Port` select separate state/port. Default state without `--data` is `~/.dcc-web`.

## Local Docker image

From the repository root:

```powershell
docker build -f apps/dcc-web/Dockerfile -t dcc-web:local-0.1.0 .
docker run --rm dcc-web:local-0.1.0 --self-check
docker compose -f apps/dcc-web/compose.yaml run --rm --no-deps dcc-web --data /data --init-admin
docker compose -f apps/dcc-web/compose.yaml up -d
```

The administrator initialization is interactive and must precede the LAN-capable container entry point. The Compose example publishes only host localhost, retains state in `dcc_web_data`, drops all but the two capabilities used to drop privileges, and uses a read-only root filesystem. The entry point reads the mounted Docker socket's group ID and starts the web process as UID 10001 with only that supplementary group. A socket mount remains host-administrator authority despite these restrictions.

For a standalone health test without a socket, start the image with a separate writable data volume and a local-only listen option. A Windows Docker Desktop socket is only mounted inside the Linux VM in this Compose example; the direct Windows launcher uses Docker CLI instead.

## Desktop acceptance build

Prepared outputs are `release/DockerControlCenter-Setup-1.3.11.exe`, `release/DockerControlCenter_1.3.11_amd64.deb` and `release/SHA256SUMS-1.3.11.txt`. These are local candidates. README release URLs name the future version and will work only after an approved publication. Existing EXE handoff and Linux pkexec/apt-get flows remain in place.

Before a manual acceptance installation, export profiles and retain application settings. Automated upgrade checks use synthetic data and isolated installations; they do not replace interactive testing on the user's chosen target OS.
