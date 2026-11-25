"""Synthetic engine responses. No real engine or Docker state is read."""
import hashlib
import itertools
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from backend.kiri_client import KiriError

ENGINE = "Kiri/0.2.2 (linux)"
VERSION = {
    "Platform": {"Name": "Kiri"}, "Components": [{"Name": "Engine", "Version": "27.5.1"},
                                                {"Name": "Kiri", "Version": "0.2.2"}],
    "Version": "27.5.1", "KiriVersion": "0.2.2", "ApiVersion": "1.47",
    "MinAPIVersion": "1.24", "Os": "linux", "Arch": "amd64",
}
SEED = [
    ("northstar-web", "nginx:1.27-alpine", "running", "northstar", "web"),
    ("northstar-api", "example.invalid/northstar/api:0.8", "running", "northstar", "api"),
    ("northstar-db", "postgres:16-alpine", "running", "northstar", "db"),
    ("relay-worker", "example.invalid/relay/worker:2", "running", "relay", "worker"),
    ("relay-cache", "redis:7-alpine", "exited", "relay", "cache"),
    ("batch-preview", "alpine:3.22", "created", "", ""),
]
SECRET = "fixture-never-echo-this-value"
BASE_DATE = 1795510800


def labels(project, service):
    return {"com.docker.compose.project": project, "com.docker.compose.service": service,
            "com.docker.compose.container-number": "1", "com.docker.compose.version": "2.40.3",
            "com.docker.compose.project.working_dir": "/private/fixture", "private": SECRET}


CONTAINERS = [
    {"Id": hashlib.sha256(name.encode()).hexdigest(), "Names": ["/" + name], "Image": image,
     "Created": BASE_DATE - index * 14300, "State": state,
     "Status": "Up 4 hours (healthy)" if state == "running" else "Exited (0)",
     "Labels": labels(project, service), "Command": SECRET,
     "Ports": [{"PrivatePort": 80, "PublicPort": 8080, "Type": "tcp"}] if index == 0 else []}
    for index, (name, image, state, project, service) in enumerate(SEED)
]
CID = CONTAINERS[0]["Id"]
IMAGES = [
    {"Id": "sha256:" + format(index + 601, "064x"), "RepoTags": [tag],
     "Size": (index + 2) * 10_242_880, "Created": BASE_DATE - index * 29000}
    for index, (_, tag, *_rest) in enumerate(SEED)
]
VOLUMES = [{"Name": name, "Driver": "local", "Scope": "local", "CreatedAt": "2026-11-24T08:00:00Z",
            "Mountpoint": "/private/fixture", "Labels": labels("northstar", "")}
           for name in ("northstar_pg", "northstar_uploads", "relay_cache")]
NETWORKS = [
    {"Id": format(index + 700, "064x"), "Name": name, "Driver": driver, "Scope": "local",
     "IPAM": {"Config": [{"Subnet": f"192.0.2.{index * 16}/28"}]} if driver == "bridge" else {}}
    for index, (name, driver) in enumerate([("bridge", "bridge"), ("host", "host"), ("none", "null"),
                                           ("northstar_default", "bridge"), ("relay_default", "bridge")])
]
sequence = itertools.count()


class FixtureTransport:
    def __init__(self, alias):
        self.mode = Path(alias).name

    def get(self, path, limit, expected=None):
        if self.mode == "offline":
            raise KiriError("socket_missing", 503)
        if self.mode == "denied":
            raise KiriError("permission_denied", 403)
        target = urlsplit(path)
        p = target.path
        if p == "/version":
            if self.mode == "docker":
                value = {**VERSION, "KiriVersion": None, "Platform": {"Name": "Docker Engine"}}
                return "Docker/27.5.1", "application/json", json.dumps(value).encode()
            return ENGINE, "application/json", json.dumps(VERSION).encode()
        assert expected == ENGINE and p.startswith("/v1.47/")
        route = p[len("/v1.47"):]
        if route == "/volumes" and self.mode == "partial":
            raise KiriError("unsupported", 501)
        data = {
            "/info": {"NCPU": 4, "MemTotal": 8_589_934_592, "Driver": "overlayfs", "KernelVersion": "6.8.0",
                      "Warnings": [], "Name": SECRET, "DockerRootDir": "/private/fixture"},
            "/containers/json": CONTAINERS if "filters" not in parse_qs(target.query) else CONTAINERS[:1],
            "/images/json": IMAGES, "/volumes": {"Volumes": VOLUMES},
            "/networks": NETWORKS, "/system/df": {"LayersSize": 449_593_344},
        }
        if route.endswith("/stats"):
            index = next(sequence) % 13
            data[route] = {
                "cpu_stats": {"cpu_usage": {"total_usage": 10000 + 43 * index}, "system_cpu_usage": 95000, "online_cpus": 4},
                "precpu_stats": {"cpu_usage": {"total_usage": 9250}, "system_cpu_usage": 72000},
                "memory_stats": {"usage": 155_385_856 + 918_027 * index, "limit": 402_653_184,
                                 "stats": {"inactive_file": 22_020_096}},
                "networks": {"eth0": {"rx_bytes": 265_328_192 + index * 1476, "tx_bytes": 113_450_215}},
                "blkio_stats": {"io_service_bytes_recursive": [{"op": "read", "value": 74_031_210},
                                                              {"op": "write", "value": 18_442_149}]},
            }
        if route.endswith("/logs"):
            message = f"2026-11-25T08:00:00Z Serving fixture requests\npassword={SECRET}\n".encode()
            return ENGINE, "application/vnd.docker.multiplexed-stream", b"\1\0\0\0" + len(message).to_bytes(4, "big") + message
        if route.startswith("/containers/") and route.endswith("/json") and route != "/containers/json":
            row = next((r for r in CONTAINERS if r["Id"] == route.split("/")[2]), None)
            if row:
                data[route] = {"Id": row["Id"], "Name": row["Names"][0], "Created": "2026-11-24T08:00:00Z",
                               "State": {"Status": row["State"], "Health": {"Status": "healthy", "Log": [SECRET]}},
                               "Config": {"Image": row["Image"], "Env": [f"TOKEN={SECRET}"], "Labels": row["Labels"]},
                               "NetworkSettings": {"Ports": {"80/tcp": [{"HostPort": "8080", "HostIp": "192.0.2.3"}]},
                                                   "Networks": {"northstar_default": {}}}}
        if route.startswith("/images/") and route.endswith("/json") and route != "/images/json":
            row = next((i for i in IMAGES if i["Id"] == route.split("/")[2]), None)
            if row:
                data[route] = {**row, "Architecture": "amd64", "Os": "linux", "Config": {"Env": [SECRET]}}
        if route.startswith("/volumes/"):
            row = next((v for v in VOLUMES if v["Name"] == route.split("/")[2]), None)
            if row:
                data[route] = row
        if route.startswith("/networks/"):
            row = next((n for n in NETWORKS if n["Id"] == route.split("/")[2]), None)
            if row:
                data[route] = {**row, "Containers": {CID: {"Name": "northstar-web", "IPv4Address": "192.0.2.5/28"}}}
        if route not in data:
            raise KiriError("resource_missing", 404)
        body = json.dumps(data[route]).encode()
        assert len(body) <= limit
        return ENGINE, "application/json", body
