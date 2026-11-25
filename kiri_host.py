"""Read-only Windows Kiri discovery for the trusted DCC desktop process.

Never use a Docker context name as proof of engine identity. This probe connects
only to Kiri's documented, fixed local named pipe and makes no host changes.
"""

import os
import re
import json
import errno
import http.client
import time
from pathlib import Path

KIRI_PIPE = "npipe:////./pipe/kiri"
KIRI_MANAGER_NAME = "dcc-kiri-manager"
KIRI_MANAGER_VOLUME = "dcc_kiri_manager_data"
KIRI_MANAGER_IMAGE = re.compile(r"ghcr\.io/hattimon/dcc-kiri-manager:[0-9]+\.[0-9]+\.[0-9]+")
KIRI_CONTAINER_SOCKET = "/run/dcc-kiri/engine.sock"
# The documented Kiri Windows WSL daemon socket. This is a candidate bind
# inside *that Kiri engine* only; preflight must prove it is available to UID 10001.
# Docker Desktop cannot mount this path from another WSL distribution.
KIRI_RUNTIME_SOCKET = "/var/lib/kiri-daemon/.kiri/run/docker.sock"
KIRI_INSTALL_URL = "https://docs.runkiri.com/windows/"
KIRI_VERSION = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}(?:[-+][0-9A-Za-z.-]{1,32})?")


def check_identity(header, body):
    """Reject ordinary Docker or a context merely named 'kiri'."""
    if not isinstance(body, dict):
        return None
    version = body.get("KiriVersion")
    components = body.get("Components")
    if (not isinstance(version, str) or not KIRI_VERSION.fullmatch(version)
            or header != f"Kiri/{version} (linux)"
            or not isinstance(body.get("Platform"), dict)
            or body["Platform"].get("Name") != "Kiri"
            or not isinstance(components, list)
            or [c.get("Version") for c in components
                if isinstance(c, dict) and c.get("Name") == "Kiri"] != [version]
            or body.get("Os") != "linux"):
        return None
    return version


def verify_kiri_client(client):
    """Verify Kiri's dedicated response and container inventory access."""
    response = client.api._get(client.api._url("/version", versioned_api=False))
    version = check_identity(response.headers.get("Server", ""), response.json())
    if not version:
        raise ValueError("identity_unverified")
    client.containers.list(all=True)
    return version


def is_manager_template(template):
    return (getattr(template, "name", "") == "DCC Kiri Manager"
            and bool(KIRI_MANAGER_IMAGE.fullmatch(str(getattr(template, "image", "")))))


def store_action(probe, *, connected=False, installed=False):
    """Pure Store decision: never uninstall or overwrite an existing panel."""
    if probe.get("status") == "ready":
        if not connected:
            return "connect"
        return "installed" if installed else "install_panel"
    if probe.get("status") == "missing":
        return "install_kiri"
    return "help"


class KiriPanelInstallError(RuntimeError):
    pass


def _panel_http_ready(*, timeout=12):
    """Confirm Windows loopback actually reaches the newly started panel.

    A successful Engine API container start does not guarantee that Kiri's WSL
    networking forwards the published port to Windows. Never use a proxy or
    query a host address that came from the engine response.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        connection = http.client.HTTPConnection("127.0.0.1", 8796, timeout=1)
        try:
            connection.request("GET", "/healthz")
            response = connection.getresponse()
            if (response.status == 200
                    and response.getheader("X-DCC-Panel", "") == "kiri-manager"
                    and response.getheader("Content-Type", "").split(";", 1)[0] == "application/json"
                    and json.loads(response.read(512)) == {"status": "ok"}):
                return True
        except (OSError, ValueError, http.client.HTTPException):
            pass
        finally:
            connection.close()
        time.sleep(0.25)
    return False


def _panel_socket_mount(mount_factory=None):
    # Docker's legacy -v/volumes bind form may create a missing host path as a
    # directory. An explicit --mount bind fails closed when the socket is absent.
    if mount_factory is None:
        from docker.types import Mount
        mount_factory = Mount
    return mount_factory(target=KIRI_CONTAINER_SOCKET, source=KIRI_RUNTIME_SOCKET,
                         type="bind", read_only=True)


def _manager_exists(containers):
    for container in containers.list(all=True):
        if container.name == KIRI_MANAGER_NAME:
            return True
        tags = getattr(getattr(container, "image", None), "tags", ()) or ()
        if any(KIRI_MANAGER_IMAGE.fullmatch(str(tag)) for tag in tags):
            return True
        # Protect older, renamed and locally tagged installations that keep
        # their state in the same named volume. Never boot a second panel on it.
        mounts = getattr(container, "attrs", {}).get("Mounts", [])
        if any(isinstance(mount, dict) and mount.get("Type") == "volume"
               and mount.get("Name") == KIRI_MANAGER_VOLUME for mount in mounts):
            return True
    return False


def install_panel_on_verified_kiri(client, image, *, mount_factory=None, panel_ready=None):
    """Install only on a verified Kiri engine, after an explicit GUI consent.

    A throwaway panel-image container first proves the actual socket bind,
    Kiri identity and inventory access as UID 10001. Failure leaves existing
    containers and named volumes untouched; no access rights are changed.
    """
    if not KIRI_MANAGER_IMAGE.fullmatch(image):
        raise KiriPanelInstallError("invalid_image")
    if panel_ready is None:
        panel_ready = _panel_http_ready
    try:
        verify_kiri_client(client)
        if _manager_exists(client.containers):
            raise KiriPanelInstallError("already_installed")
        try:
            client.images.get(image)
        except Exception:
            client.images.pull(image)
        socket_env = {"KIRI_SOCKETS": json.dumps({"auto": KIRI_CONTAINER_SOCKET})}
        socket_mount = _panel_socket_mount(mount_factory)
        # Only use modules present in the already published 0.1.x image.
        # The installed image may predate backend.discovery.
        preflight = (
            "import os\n"
            "from backend.config import Config\n"
            "from backend.kiri_client import Connector\n"
            "from backend import resources\n"
            "cfg = Config.from_env(os.environ)\n"
            "with Connector(cfg.sockets).connect('auto') as kiri:\n"
            "    resources.rows(kiri.read('containers'))\n"
            "    assert kiri.identity['version']\n"
        )
        test = None
        try:
            test = client.containers.create(
                image, command=["python", "-c", preflight],
                environment=socket_env, mounts=[socket_mount],
                user="10001:10001", read_only=True, network_disabled=True,
                cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
                tmpfs={"/tmp": "size=8m,mode=1777", "/data": "size=8m,mode=0700"},
            )
            test.start()
            status = test.wait(timeout=20)
            if status.get("StatusCode") != 0:
                raise KiriPanelInstallError("socket_preflight_failed")
        finally:
            if test is not None:
                try:
                    test.remove(force=True, v=True)
                except Exception:
                    pass
        # Recheck; a concurrent installation must never be overwritten.
        if _manager_exists(client.containers):
            raise KiriPanelInstallError("already_installed")
        panel = None
        try:
            panel = client.containers.create(
                image, name=KIRI_MANAGER_NAME,
                ports={"8796/tcp": ("127.0.0.1", 8796)},
                environment=socket_env,
                mounts=[socket_mount],
                volumes={KIRI_MANAGER_VOLUME: {"bind": "/data", "mode": "rw"}},
                user="10001:10001", read_only=True,
                cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
                tmpfs={"/tmp": "size=8m,mode=1777"}, pids_limit=40, mem_limit="192m",
                restart_policy={"Name": "unless-stopped"},
            )
            panel.start()
            if not panel_ready():
                raise KiriPanelInstallError("panel_not_reachable")
            return panel.name
        except Exception:
            if panel is not None:
                try:
                    panel.remove(force=True, v=False)
                except Exception:
                    pass
            raise
    except KiriPanelInstallError:
        raise
    except Exception as exc:
        # Do not leak socket paths, access tokens or exception internals into GUI.
        raise KiriPanelInstallError("engine_or_transport_error") from exc


def _pipe_failure(error):
    """Classify nested docker SDK/requests/pywin32 failures without logging paths.

    A DockerException often wraps a requests exception which wraps the original
    OSError. The outer exception usually has neither errno nor winerror.
    """
    pending, visited = [error], set()
    found_missing = False
    for _ in range(16):
        if not pending:
            break
        current = pending.pop()
        if id(current) in visited or not isinstance(current, BaseException):
            continue
        visited.add(id(current))
        code, winerror = getattr(current, "errno", None), getattr(current, "winerror", None)
        if isinstance(current, PermissionError) or code in {errno.EACCES, errno.EPERM} or winerror == 5:
            return "permission_denied"
        if isinstance(current, FileNotFoundError) or code in {errno.ENOENT, errno.ENOTDIR} or winerror in {2, 3}:
            found_missing = True
        pending.extend(child for child in (current.__cause__, current.__context__)
                       if isinstance(child, BaseException))
        pending.extend(arg for arg in current.args if isinstance(arg, BaseException))
    return "pipe_missing" if found_missing else "engine_unreachable"


def probe_windows_kiri(*, client_factory=None, local_app_data=None, windows=None):
    if windows is None:
        windows = os.name == "nt"
    if not windows:
        return {"status": "unsupported", "reason": "windows_only"}
    location = Path(local_app_data if local_app_data is not None else
                    os.environ.get("LOCALAPPDATA", "")) / "Kiri"
    try:
        installed = location.is_dir()
    except OSError:
        # A protected installation directory is not evidence about the pipe.
        # Continue with the fixed pipe probe and report its actual result.
        installed = False
    if client_factory is None:
        import docker
        client_factory = docker.DockerClient
    client = None
    try:
        client = client_factory(base_url=KIRI_PIPE, timeout=2, version="1.47")
        # Keep the response header: Docker SDK's .version() discards it.
        try:
            version = verify_kiri_client(client)
        except ValueError:
            return {"status": "unsupported", "reason": "identity_unverified"}
        return {"status": "ready", "version": version, "transport": "windows_named_pipe"}
    except Exception as error:
        # Never return paths, command lines or credentials from exceptions.
        failure = _pipe_failure(error)
        if failure == "permission_denied":
            return {"status": "blocked", "reason": "permission_denied"}
        if failure == "pipe_missing":
            return {"status": "stopped" if installed else "missing", "reason": "pipe_missing"}
        return {"status": "stopped" if installed else "blocked", "reason": "engine_unreachable"}
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
