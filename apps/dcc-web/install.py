"""Install DCC Web with Docker Compose, selecting an unused loopback port."""
from __future__ import annotations

import os
import ipaddress
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
from typing import Callable, Iterable
from urllib.parse import urlsplit

APP_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = APP_DIR.parents[1]
COMPOSE_FILE = APP_DIR / "compose.release.yaml"
CONTAINER_NAME = "dcc-web-standalone"
DEFAULT_PORT = 8789
LAST_PORT = 8888

for import_path in (APP_DIR, REPOSITORY_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from ports import published_ports  # noqa: E402


def docker_published_tcp_ports(output: str) -> set[int]:
    """Return published TCP host ports reported by `docker ps` output."""
    occupied: set[int] = set()
    for line in str(output or "").splitlines():
        for binding in published_ports(line):
            if binding["protocol"] == "tcp":
                occupied.add(int(binding["host_port"]))
    return occupied


def host_port_is_available(port: int) -> bool:
    """Check whether Compose can bind the same IPv4 loopback address it uses."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", int(port)))
        except OSError:
            return False
    return True


def choose_host_port(
    occupied: Iterable[int],
    *,
    start: int = DEFAULT_PORT,
    end: int = LAST_PORT,
    is_available: Callable[[int], bool] | None = None,
) -> int:
    if is_available is None:
        is_available = host_port_is_available
    reserved = {int(port) for port in occupied}
    for port in range(int(start), int(end) + 1):
        if port not in reserved and is_available(port):
            return port
    raise RuntimeError(f"No free localhost port was found in range {start}-{end}.")


def config_directory() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return base / "DCC Web"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "DCC Web"
    return Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "dcc-web"


def saved_port(path: Path) -> int | None:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == "DCC_WEB_PORT" and value.strip().isdigit():
                port = int(value.strip())
                if 1 <= port <= 65535:
                    return port
    except OSError:
        return None
    return None


def write_port(path: Path, port: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        old_lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        old_lines = []
    new_lines = [line for line in old_lines if line.partition("=")[0].strip() != "DCC_WEB_PORT"]
    new_lines.append(f"DCC_WEB_PORT={int(port)}")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f"{path.name}.", suffix=".tmp", delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write("\n".join(new_lines) + "\n")
        try:
            temporary_path.chmod(0o600)
        except OSError:
            pass
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def compose_prefix(env_file: Path) -> list[str]:
    return [
        "docker", "compose",
        "--project-directory", str(APP_DIR),
        "--env-file", str(env_file),
        "-f", str(COMPOSE_FILE),
    ]


def validate_local_docker_endpoint(endpoint: str) -> None:
    """The installer publishes a localhost URL, so reject remote Docker contexts."""
    value = str(endpoint or "").strip()
    if value.startswith(("unix://", "npipe://")):
        return
    parsed = urlsplit(value)
    if parsed.scheme in {"tcp", "http", "https"} and parsed.hostname:
        if parsed.hostname.casefold() == "localhost":
            return
        try:
            if ipaddress.ip_address(parsed.hostname).is_loopback:
                return
        except ValueError:
            pass
    raise RuntimeError(
        "The active Docker context is remote. Run this installer with a local Docker context; "
        "the standalone installer publishes a localhost-only address."
    )


def active_docker_endpoint() -> str:
    context = subprocess.run(
        ["docker", "context", "show"], check=False, capture_output=True, text=True,
    )
    if context.returncode:
        detail = (context.stderr or context.stdout).strip()
        raise RuntimeError(f"Cannot read the active Docker context: {detail or context.returncode}")
    name = context.stdout.strip()
    result = subprocess.run(
        ["docker", "context", "inspect", name, "--format", "{{json .Endpoints}}"],
        check=False, capture_output=True, text=True,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Cannot inspect the active Docker context: {detail or result.returncode}")
    try:
        endpoint = json.loads(result.stdout).get("docker", {}).get("Host")
    except (AttributeError, json.JSONDecodeError):
        endpoint = None
    if not endpoint:
        raise RuntimeError("The active Docker context has no Docker endpoint.")
    return str(endpoint)


def run_checked(command: list[str], *, cwd: Path | None = None) -> None:
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode:
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(command)}")


def active_container_ports() -> set[int]:
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Ports}}"],
        check=False, capture_output=True, text=True,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Cannot inspect running Docker containers: {detail or result.returncode}")
    return docker_published_tcp_ports(result.stdout)


def existing_installation() -> bool:
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name=^/{CONTAINER_NAME}$", "--format", "{{.Names}}"],
        check=False, capture_output=True, text=True,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Cannot check for an existing DCC Web container: {detail or result.returncode}")
    return CONTAINER_NAME in {line.strip() for line in result.stdout.splitlines()}


def selected_port(env_file: Path, *, exclude: Iterable[int] = ()) -> int:
    occupied = active_container_ports() | {int(port) for port in exclude}
    previous = saved_port(env_file)
    if previous is not None and previous not in occupied and host_port_is_available(previous):
        return previous
    return choose_host_port(occupied)


def port_conflict(output: str) -> bool:
    text = str(output or "").casefold()
    return any(marker in text for marker in (
        "port is already allocated", "address already in use", "failed to bind", "port binding failed",
    ))


def install() -> str:
    if not shutil_which("docker"):
        raise RuntimeError("Docker CLI is required. Install Docker Desktop or Docker Engine and try again.")
    validate_local_docker_endpoint(active_docker_endpoint())
    if os.environ.get("DOCKER_HOST"):
        validate_local_docker_endpoint(os.environ["DOCKER_HOST"])
    run_checked(["docker", "compose", "version"])
    run_checked(["docker", "info", "--format", "{{.ServerVersion}}"])
    if existing_installation():
        raise RuntimeError(
            f"A container named {CONTAINER_NAME} already exists. It was left untouched; open its existing address or remove it yourself before reinstalling."
        )

    env_file = config_directory() / "compose.env"
    port = selected_port(env_file)
    if port != DEFAULT_PORT:
        print(f"Port {DEFAULT_PORT} is occupied. DCC Web will use free localhost port {port}.")
    else:
        print(f"Port {port} is free; using the default DCC Web address.")
    write_port(env_file, port)
    # Compose gives shell environment variables precedence over --env-file.
    # Pin the selected port so a stale exported value cannot undo the scan.
    os.environ["DCC_WEB_PORT"] = str(port)
    compose = compose_prefix(env_file)

    run_checked([*compose, "config", "--quiet"])
    run_checked([*compose, "pull", "dcc-web"])
    print("\nCreate the DCC Web administrator account:")
    run_checked([*compose, "run", "--rm", "--no-deps", "dcc-web", "--data", "/data", "--init-admin"])

    for attempt in range(8):
        result = subprocess.run(
            [*compose, "up", "-d", "--no-build"],
            check=False, capture_output=True, text=True,
        )
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        if result.returncode == 0:
            break
        details = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
        if not port_conflict(details):
            raise RuntimeError(details or f"docker compose up failed with exit code {result.returncode}.")
        port = selected_port(env_file, exclude={port})
        write_port(env_file, port)
        os.environ["DCC_WEB_PORT"] = str(port)
        compose = compose_prefix(env_file)
        print(f"A port became occupied during startup; retrying on {port}.")
    else:
        raise RuntimeError("Could not reserve a free localhost port after 8 attempts.")

    return f"http://127.0.0.1:{port}"


def shutil_which(command: str) -> str | None:
    # Keep this installer self-contained; no third-party Python modules are needed.
    from shutil import which
    return which(command)


def main() -> int:
    try:
        url = install()
    except (OSError, RuntimeError) as exc:
        print(f"DCC Web installation failed: {exc}", file=sys.stderr)
        return 1
    print(f"\nDCC Web is ready: {url}")
    print("Only this computer can reach the default localhost address.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
