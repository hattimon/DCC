"""Deployment settings are administrator-controlled, never taken from a profile."""
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
ALIAS = re.compile(r"[a-z][a-z0-9_-]{0,23}")
DEFAULT_DOCKER_SOCKETS = {"/var/run/docker.sock", "/run/docker.sock",
                          "/private/var/run/docker.sock"}


def parse_sockets(raw):
    try:
        sockets = json.loads(raw)
    except (ValueError, RecursionError):
        raise ValueError("KIRI_SOCKETS must be a JSON object of socket aliases") from None
    if not isinstance(sockets, dict) or len(sockets) > 8:
        raise ValueError("KIRI_SOCKETS accepts up to eight socket aliases")
    for name, path in sockets.items():
        if (not ALIAS.fullmatch(name) or not isinstance(path, str) or len(path.encode()) > 103
                or not path.startswith("/") or path.startswith("//")
                or str(PurePosixPath(path)) != path or ".." in PurePosixPath(path).parts
                or not path.endswith(".sock") or any(ord(char) < 32 for char in path)
                or path in DEFAULT_DOCKER_SOCKETS):
            raise ValueError("KIRI_SOCKETS requires a dedicated absolute Unix socket per alias")
    return sockets


@dataclass(frozen=True)
class Config:
    data_dir: Path
    sockets: dict
    bind: str = "127.0.0.1"
    port: int = 8796
    public_origin: str | None = None

    @classmethod
    def from_env(cls, env):
        origin = env.get("KIRI_PANEL_ORIGIN")
        if origin:
            url = urlsplit(origin)
            if (url.scheme != "https" or not url.hostname or url.username is not None
                    or url.path or url.query or url.fragment
                    or not re.fullmatch(r"https://(?:[a-z0-9.-]+|\[[a-f0-9:]+\])(?::[1-9][0-9]{0,4})?", origin)
                    or (url.port is not None and (url.port > 65535 or url.port == 443))):
                raise ValueError("KIRI_PANEL_ORIGIN requires a canonical HTTPS origin")
        bind = env.get("KIRI_PANEL_BIND", "127.0.0.1")
        port = int(env.get("KIRI_PANEL_PORT", "8796"))
        if bind not in {"127.0.0.1", "0.0.0.0", "::1"} or not 1 <= port <= 65535:
            raise ValueError("Invalid panel bind address or port")
        return cls(
            Path(env.get("KIRI_PANEL_DATA", ROOT / "data")),
            parse_sockets(env.get("KIRI_SOCKETS", "{}")),
            bind, port, origin,
        )

    @property
    def trusted_hosts(self):
        loopback = ["127.0.0.1", "localhost", "[::1]"]
        if self.public_origin:
            return [*loopback, urlsplit(self.public_origin).netloc]
        return loopback
