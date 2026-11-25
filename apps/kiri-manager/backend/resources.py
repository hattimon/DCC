"""Only explicitly selected resource metadata may reach the browser."""
import math
import re
import time
from collections import Counter

from .kiri_client import IDS, KiriError

COMPOSE_LABELS = {
    "project": "com.docker.compose.project",
    "service": "com.docker.compose.service",
    "replica": "com.docker.compose.container-number",
    "oneoff": "com.docker.compose.oneoff",
    "version": "com.docker.compose.version",
}
STATES = {"running", "exited", "created", "restarting", "paused", "dead", "removing"}
HEALTH = {"healthy", "unhealthy", "starting"}
SECRET_LINE = re.compile(
    r"(?i)\b(?:auth(?:orization)?|credential[s]?|token[s]?|pass(?:word|wd)?|cookie|secret[s]?|"
    r"api[-_ ]?key|private[-_ ]?key)\b|(?:https?|ssh)://[^/\s]+@|"
    r"\b(?:gh[pousr]_|github_pat_|sk-(?:proj-)?|AKIA)[a-zA-Z0-9_/-]{8,}|"
    r"\beyJ[A-Za-z0-9_-]{7,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
)
CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069\ud800-\udfff]")
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def mapping(value):
    return value if isinstance(value, dict) else {}


def wrapped(value, key):
    if not isinstance(value, dict) or key not in value:
        raise KiriError("bad_response")
    return value[key] if value[key] is not None else []


def rows(value):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise KiriError("bad_response")
    if len(value) > 2000:
        raise KiriError("large_response")
    return value


def text(value, limit=240):
    return CONTROLS.sub("", value[:limit]) if isinstance(value, str) else None


def strings(value, limit=32):
    return [text(item) for item in value[:limit] if isinstance(item, str)] if isinstance(value, list) else []


def uint(value):
    return value if type(value) is int and 0 <= value < 2**63 else None


def number(value):
    if type(value) is int:
        return uint(value)
    return value if type(value) is float and math.isfinite(value) and value >= 0 else None


def choice(value, options):
    return value if isinstance(value, str) and value in options else None


def date(value):
    return uint(value) if type(value) is int else text(value, 50)


def resource_id(value, resource):
    if not isinstance(value, str) or not IDS[resource].fullmatch(value):
        return None
    return value


def compose_labels(value):
    labels = mapping(value)
    # File paths, working directories and arbitrary project labels are private.
    return {key: text(labels[label], 100) for key, label in COMPOSE_LABELS.items() if isinstance(labels.get(label), str)}


def container_port(row):
    return {"private": uint(row.get("PrivatePort")), "public": uint(row.get("PublicPort")),
            "protocol": choice(row.get("Type"), {"tcp", "udp", "sctp"})}


def container(row):
    state = choice(row.get("State"), STATES)
    status = text(row.get("Status"), 140) or ""
    match = re.search(r"\((?:health: )?(healthy|unhealthy|starting)\)$", status)
    names = strings(row.get("Names"), 1)
    ports = row.get("Ports")
    return {"id": resource_id(row.get("Id"), "containers"), "name": names[0].lstrip("/") if names else None,
            "image": text(row.get("Image")), "created": date(row.get("Created")),
            "state": state, "health": match[1] if match else None,
            "ports": [container_port(p) for p in ports[:40] if isinstance(p, dict)] if isinstance(ports, list) else [],
            "compose": compose_labels(row.get("Labels"))}


def safe_container_detail(row):
    state = mapping(row.get("State"))
    networking = mapping(row.get("NetworkSettings"))
    ports = []
    for private, bindings in list(mapping(networking.get("Ports")).items())[:40]:
        port, _, protocol = private.partition("/")
        if not re.fullmatch(r"\d{1,5}", port) or protocol not in {"tcp", "udp", "sctp"}:
            continue
        for binding in (bindings[:8] if isinstance(bindings, list) and bindings else [{}]):
            public = mapping(binding).get("HostPort")
            ports.append({"private": int(port), "public": int(public) if isinstance(public, str)
                          and re.fullmatch(r"\d{1,5}", public) else None, "protocol": protocol})
    return {
        "id": resource_id(row.get("Id"), "containers"), "name": (text(row.get("Name")) or "").lstrip("/"),
        "image": text(mapping(row.get("Config")).get("Image")), "state": choice(state.get("Status"), STATES),
        "health": choice(mapping(state.get("Health")).get("Status"), HEALTH),
        "exit_code": uint(state.get("ExitCode")), "created": date(row.get("Created")),
        "started": date(state.get("StartedAt")), "ports": ports,
        "networks": strings(list(mapping(networking.get("Networks")).keys())),
        "compose": compose_labels(mapping(row.get("Config")).get("Labels")),
    }


def image(row):
    return {"id": resource_id(row.get("Id"), "images"), "tags": strings(row.get("RepoTags")),
            "bytes": uint(row.get("Size")), "created": date(row.get("Created")),
            "architecture": text(row.get("Architecture"), 32), "os": text(row.get("Os"), 32)}


def images(value):
    unique = {}
    for row in rows(value):
        item = image(row)
        previous = unique.get(item["id"])
        if previous is not None and item["id"]:
            previous["tags"] = sorted(set(previous["tags"]) | set(item["tags"]))[:64]
        else:
            unique[item["id"] or len(unique)] = item
    return list(unique.values())


def volume(row):
    name = resource_id(row.get("Name"), "volumes")
    return {"id": name, "name": text(row.get("Name")), "driver": text(row.get("Driver")),
            "scope": text(row.get("Scope")), "created": date(row.get("CreatedAt")),
            "compose": compose_labels(row.get("Labels"))}


def network(row):
    subnets = mapping(row.get("IPAM")).get("Config")
    clients = row.get("Containers")
    return {"id": resource_id(row.get("Id"), "networks"), "name": text(row.get("Name")),
            "driver": text(row.get("Driver")), "scope": text(row.get("Scope")),
            "created": date(row.get("Created")), "internal": row.get("Internal") if type(row.get("Internal")) is bool else None,
            "subnets": [text(entry.get("Subnet"), 64) for entry in subnets[:16]
                        if isinstance(entry, dict) and entry.get("Subnet")] if isinstance(subnets, list) else None,
            "containers": [text(mapping(client).get("Name")) for client in list(clients.values())[:150]]
                          if isinstance(clients, dict) else None}


def projects(containers):
    groups = {}
    for row in containers:
        labels = row["compose"]
        project, service = labels.get("project"), labels.get("service")
        if not project or not service:
            continue
        services = groups.setdefault(project, {})
        services.setdefault(service, []).append(row)
    return [
        {"name": name, "services": [{"name": service, "containers": members}
                                    for service, members in sorted(services.items())]}
        for name, services in sorted(groups.items())
    ]


def snapshot(kiri):
    values, checks = {}, {}
    for resource, convert in INVENTORY.items():
        try:
            values[resource] = convert(kiri.read(resource))
            checks[resource] = "available"
        except KiriError as e:
            if e.code in {"bad_engine", "socket_changed"}:
                raise
            checks[resource] = e.code

    containers = values.get("containers")
    states = Counter(row["state"] for row in containers) if containers is not None else None
    values["compose"] = projects(containers) if containers is not None else None
    checks["compose"] = checks["containers"]
    return {"engine": kiri.identity, "values": values, "checks": checks,
            "counts": {key: len(value) if isinstance(value, list) else None
                       for key, value in values.items() if key != "info"},
            "running": states["running"] if states is not None else None,
            "stopped": sum(states[state] for state in ("exited", "dead")) if states is not None else None,
            "at": int(time.time())}


def engine_info(value):
    if not isinstance(value, dict):
        raise KiriError("bad_response")
    memory = uint(value.get("MemTotal"))
    return {"cpus": uint(value.get("NCPU")) or None, "memory_bytes": memory or None,
            "driver": text(value.get("Driver"), 32), "kernel": text(value.get("KernelVersion"), 80),
            "warning_count": len(value["Warnings"]) if isinstance(value.get("Warnings"), list) else None}


INVENTORY = {
    "info": engine_info, "containers": lambda values: [container(row) for row in rows(values)],
    "images": images, "volumes": lambda values: [volume(row) for row in rows(wrapped(values, "Volumes"))],
    "networks": lambda values: [network(row) for row in rows(values)],
}
DETAIL = {"containers": safe_container_detail, "images": image, "networks": network, "volumes": volume}


def disk_usage(row):
    if not isinstance(row, dict):
        raise KiriError("bad_response")
    return {"image_layers_bytes": uint(row.get("LayersSize"))}


def stats(row):
    if not isinstance(row, dict):
        raise KiriError("bad_response")

    def cpu_stats(key):
        sample = mapping(row.get(key))
        return (uint(mapping(sample.get("cpu_usage")).get("total_usage")), uint(sample.get("system_cpu_usage")),
                uint(sample.get("online_cpus")))

    cpu, system, cpus = cpu_stats("cpu_stats")
    previous, previous_system, _ = cpu_stats("precpu_stats")
    percent = None
    if None not in (cpu, system, previous, previous_system) and cpus and cpu >= previous and system > previous_system:
        percent = round((cpu - previous) / (system - previous_system) * cpus * 100, 2)

    memory = mapping(row.get("memory_stats"))
    used = uint(memory.get("usage"))
    inactive = uint(mapping(memory.get("stats")).get("inactive_file"))
    if used is not None and inactive is not None and used >= inactive:
        used -= inactive

    interfaces = mapping(row.get("networks")).values()
    received = [uint(mapping(iface).get("rx_bytes")) for iface in interfaces]
    sent = [uint(mapping(iface).get("tx_bytes")) for iface in interfaces]
    operations = mapping(row.get("blkio_stats")).get("io_service_bytes_recursive") or []
    disk = {"read": [], "write": []}
    for entry in operations if isinstance(operations, list) else []:
        if not isinstance(entry, dict):
            continue
        op = (text(entry.get("op"), 10) or "").lower()
        if op in disk and (value := uint(entry.get("value"))) is not None:
            disk[op].append(value)
    return {
        "at": int(time.time()), "cpu_percent": percent, "memory_bytes": used,
        "limit_bytes": uint(memory.get("limit")) or None,
        "rx_bytes": sum(received) if received and None not in received else None,
        "tx_bytes": sum(sent) if sent and None not in sent else None,
        "read_bytes": sum(disk["read"]) if disk["read"] else None,
        "write_bytes": sum(disk["write"]) if disk["write"] else None,
    }


def sanitized_logs(content_type, body):
    if content_type == "application/vnd.docker.multiplexed-stream":
        chunks = []
        pos = 0
        while pos < len(body):
            header = body[pos:pos + 8]
            if len(header) != 8 or header[:4] not in {b"\x01\0\0\0", b"\x02\0\0\0"}:
                raise KiriError("bad_response")
            end = pos + 8 + int.from_bytes(header[4:], "big")
            if end > len(body):
                raise KiriError("bad_response")
            chunks.append(body[pos + 8:end])
            pos = end
        body = b"".join(chunks)
    elif content_type not in {"application/vnd.docker.raw-stream", "text/plain"}:
        raise KiriError("bad_response")

    lines, private = [], False
    for line in ANSI.sub("", body.decode("utf-8", "replace")).splitlines():
        clean = CONTROLS.sub("", line)
        if "-----BEGIN " in clean and ("KEY-----" in clean or "CERTIFICATE-----" in clean):
            private = True
        if private or SECRET_LINE.search(clean):
            lines.append("[REDACTED]")
        else:
            lines.append(clean)
        if private and "-----END " in clean:
            private = False
    return "\n".join(lines)
