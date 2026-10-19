"""Safe, opt-in image update support for Docker containers."""

from __future__ import annotations

import copy
import json
import re
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


DCC_CATALOG_URL = "https://raw.githubusercontent.com/hattimon/DCC/main/dcc-catalog.json"
SELF_LABEL = "com.hattimon.dcc-updater"
SUPPORTED_NETWORK_MODES = {"default", "bridge", "host", "none"}
CONFIG_UPDATE_FIELDS = {
    "command", "hostname", "user", "stdin_open", "tty", "ports", "environment",
    "volumes", "network_disabled", "entrypoint", "working_dir", "domainname",
    "mac_address", "labels", "stop_signal", "healthcheck", "stop_timeout", "runtime",
}
HOST_CONFIG_UPDATE_FIELDS = {
    "Binds", "Mounts", "PortBindings", "RestartPolicy", "Tmpfs", "VolumesFrom",
    "Memory", "MemoryReservation", "MemorySwap", "NanoCpus", "CpuShares", "CpuQuota",
    "CpuPeriod", "CpusetCpus", "CpusetMems", "PidsLimit", "ShmSize", "ReadonlyRootfs",
    "SecurityOpt", "CapAdd", "CapDrop", "Init", "Ulimits", "LogConfig", "Dns",
    "DnsSearch", "ExtraHosts", "GroupAdd", "Sysctls", "UsernsMode", "OomKillDisable",
    "OomScoreAdj",
}


def image_reference(reference: str) -> tuple[str, str]:
    """Return repository and tag for a Docker reference (digest refs have no tag)."""
    value = str(reference or "").strip()
    name = value.split("@", 1)[0]
    last_component = name.rsplit("/", 1)[-1]
    if ":" in last_component:
        repository, tag = name.rsplit(":", 1)
    else:
        repository, tag = name, "latest"
    return repository, tag


def normalized_repository(reference: str) -> str:
    repository, _tag = image_reference(reference)
    parts = repository.lower().split("/")
    if len(parts) == 1:
        parts.insert(0, "docker.io")
    elif "." not in parts[0] and ":" not in parts[0] and parts[0] != "localhost":
        parts.insert(0, "docker.io")
    if parts[0] == "docker.io" and len(parts) == 2:
        parts.insert(1, "library")
    return "/".join(parts)


def version_tuple(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)(?:[-+][0-9A-Za-z.-]+)?", str(value).strip())
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def compare_versions(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    width = max(len(left), len(right))
    a = left + (0,) * (width - len(left))
    b = right + (0,) * (width - len(right))
    return (a > b) - (a < b)


def load_catalog(url: str = DCC_CATALOG_URL) -> list[dict[str, Any]]:
    request = urllib.request.Request(url, headers={"User-Agent": "DCC-Container-Updater/1.0"})
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    apps = payload.get("apps", []) if isinstance(payload, dict) else []
    return [item for item in apps if isinstance(item, dict) and item.get("image")]


@dataclass
class UpdateCandidate:
    available: bool
    target_image: str
    source: str
    message: str
    update_instructions: dict[str, Any] | None = None


class UpdateService:
    def __init__(
        self,
        client: Any,
        catalog_loader: Callable[[], list[dict[str, Any]]] = load_catalog,
        wait_seconds: int = 60,
    ) -> None:
        self.client = client
        self.catalog_loader = catalog_loader
        self.wait_seconds = max(1, min(int(wait_seconds), 180))
        self._catalog_cache: tuple[float, list[dict[str, Any]]] | None = None

    def _catalog(self) -> tuple[list[dict[str, Any]], str | None]:
        now = time.monotonic()
        if self._catalog_cache and now - self._catalog_cache[0] < 600:
            return self._catalog_cache[1], None
        try:
            apps = self.catalog_loader()
            self._catalog_cache = (now, apps)
            return apps, None
        except Exception as exc:  # registry checks can still run if GitHub is unavailable
            return [], f"Nie udało się pobrać katalogu DCC: {type(exc).__name__}"

    @staticmethod
    def _catalog_update_instructions(image: str, apps: list[dict[str, Any]]) -> dict[str, Any] | None:
        image_repo = normalized_repository(image)
        for app in apps:
            if normalized_repository(str(app.get("image", ""))) != image_repo:
                continue
            instructions = app.get("update_instructions")
            return copy.deepcopy(instructions) if isinstance(instructions, dict) else None
        return None

    @staticmethod
    def _is_self(container: Any) -> bool:
        labels = (container.attrs.get("Config") or {}).get("Labels") or {}
        name = str(getattr(container, "name", "")).lstrip("/").lower()
        return labels.get(SELF_LABEL) == "true" or name in {"dcc-container-updater", "container-updater"}

    @staticmethod
    def _unsupported_reason(container: Any) -> str | None:
        attrs = container.attrs
        config = attrs.get("Config") or {}
        labels = config.get("Labels") or {}
        if labels.get("com.docker.compose.project"):
            return "Kontenerem zarządza Docker Compose; aktualizacja wymaga użycia jego pliku Compose."
        if any(key.startswith("com.docker.swarm.") for key in labels):
            return "Kontener jest zarządzany przez Docker Swarm."
        host = attrs.get("HostConfig") or {}
        if host.get("AutoRemove"):
            return "Kontener ma włączone automatyczne usuwanie; nie można bezpiecznie zachować kopii."
        mode = str(host.get("NetworkMode") or "default")
        if mode.startswith("container:"):
            return "Kontener współdzieli przestrzeń sieciową innego kontenera."
        if mode not in SUPPORTED_NETWORK_MODES:
            return "Niestandardowa sieć Docker wymaga odtworzenia endpointów; pominięto ją dla bezpieczeństwa."
        networks = (attrs.get("NetworkSettings") or {}).get("Networks") or {}
        names = set(networks)
        if len(names) > 1 or any(name not in {"bridge", "host", "none"} for name in names):
            return "Kontener używa niestandardowej lub wielokrotnej sieci Docker."
        return None

    @staticmethod
    def _host_port_bindings(host_config: dict[str, Any]) -> list[tuple[str, str, str]]:
        output: list[tuple[str, str, str]] = []
        bindings = host_config.get("PortBindings") or {}
        if not isinstance(bindings, dict):
            return output
        for container_port, raw_entries in bindings.items():
            protocol = str(container_port).rsplit("/", 1)[-1].lower() if "/" in str(container_port) else "tcp"
            entries = raw_entries if isinstance(raw_entries, list) else [raw_entries]
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                host_port = str(entry.get("HostPort") or "").strip()
                if not host_port or host_port == "0":
                    continue
                host_ip = str(entry.get("HostIp") or "").strip().lower()
                output.append((host_ip, host_port, protocol))
        return output

    @classmethod
    def _container_host_port_bindings(cls, container: Any) -> list[tuple[str, str, str]]:
        """Return configured and currently published bindings, without duplicates."""
        attrs = getattr(container, "attrs", {}) or {}
        bindings = cls._host_port_bindings(attrs.get("HostConfig") or {})
        seen = set(bindings)
        runtime_ports = (attrs.get("NetworkSettings") or {}).get("Ports") or {}
        if isinstance(runtime_ports, dict):
            for container_port, entries in runtime_ports.items():
                protocol = str(container_port).rsplit("/", 1)[-1].lower() if "/" in str(container_port) else "tcp"
                for entry in entries or []:
                    if not isinstance(entry, dict):
                        continue
                    host_port = str(entry.get("HostPort") or "").strip()
                    if not host_port or host_port == "0":
                        continue
                    binding = (str(entry.get("HostIp") or "").strip().lower(), host_port, protocol)
                    if binding not in seen:
                        bindings.append(binding)
                        seen.add(binding)
        return bindings

    @staticmethod
    def _ports_overlap(left: str, right: str) -> bool:
        def span(value: str) -> tuple[int, int] | None:
            match = re.fullmatch(r"(\d+)(?:-(\d+))?", value)
            if not match:
                return None
            start = int(match.group(1))
            end = int(match.group(2) or start)
            return min(start, end), max(start, end)

        left_span, right_span = span(left), span(right)
        if left_span and right_span:
            return left_span[0] <= right_span[1] and right_span[0] <= left_span[1]
        return left.lower() == right.lower()

    @staticmethod
    def _host_ips_overlap(left: str, right: str) -> bool:
        wildcards = {"", "0.0.0.0", "::", "::0", "0:0:0:0:0:0:0:0"}
        return left in wildcards or right in wildcards or left == right

    def _port_conflict_reason(
        self,
        container: Any,
        instructions: dict[str, Any] | None,
        all_containers: list[Any] | None,
    ) -> str | None:
        host = copy.deepcopy(container.attrs.get("HostConfig") or {})
        overrides = (instructions or {}).get("host_config") or {}
        if isinstance(overrides, dict):
            host.update(overrides)
        proposed = self._host_port_bindings(host)
        if not proposed and not (isinstance(overrides, dict) and "PortBindings" in overrides):
            proposed = self._container_host_port_bindings(container)
        if not proposed:
            return None

        own_id = str(getattr(container, "id", ""))
        for other in all_containers or []:
            if str(getattr(other, "id", "")) == own_id:
                continue
            for address, port, protocol in self._container_host_port_bindings(other):
                for proposed_address, proposed_port, proposed_protocol in proposed:
                    if (
                        protocol == proposed_protocol
                        and self._ports_overlap(port, proposed_port)
                        and self._host_ips_overlap(address, proposed_address)
                    ):
                        other_name = str(getattr(other, "name", "nieznany")).lstrip("/")
                        ip_label = proposed_address or "*"
                        return (
                            f"Konflikt portu hosta {ip_label}:{proposed_port}/{proposed_protocol} "
                            f"z kontenerem {other_name}. Portów nie zmieniono; popraw mapowanie przed aktualizacją."
                        )
        return None

    def _catalog_candidate(self, image: str, apps: list[dict[str, Any]]) -> UpdateCandidate | None:
        matches = [
            app for app in apps
            if normalized_repository(str(app.get("image", ""))) == normalized_repository(image)
        ]
        if not matches:
            return None
        current_repo, current_tag = image_reference(image)
        current_version = version_tuple(current_tag)
        app = matches[0]
        instructions = self._catalog_update_instructions(image, apps)
        target = str(app["image"])
        _target_repo, target_tag = image_reference(target)
        target_version = version_tuple(target_tag)
        release_version = version_tuple(str(app.get("latest_release", "")))

        if normalized_repository(target) != normalized_repository(image):
            return None
        if target != image:
            if current_version and target_version and compare_versions(target_version, current_version) <= 0:
                return UpdateCandidate(False, target, "katalog DCC", "Zainstalowana wersja nie jest starsza od katalogowej.")
            if current_version and not target_version and release_version:
                if compare_versions(release_version, current_version) <= 0:
                    return UpdateCandidate(False, target, "katalog DCC", "Zainstalowana wersja nie jest starsza od katalogowej.")
            return UpdateCandidate(
                True,
                target,
                "katalog DCC",
                f"Katalog DCC wskazuje obraz {target}.",
                instructions,
            )
        return None

    def _registry_digest(self, image: str, local_image: Any) -> tuple[bool | None, str]:
        try:
            distribution = self.client.api.inspect_distribution(image)
            local_attrs = getattr(local_image, "attrs", {}) or {}
            local_os = str(local_attrs.get("Os") or "linux").lower()
            local_arch = str(local_attrs.get("Architecture") or "").lower()
            platforms = distribution.get("Platforms") or []
            platform_digests = set()
            for platform in platforms:
                descriptor = platform.get("Descriptor") or {}
                if (
                    str(platform.get("OS") or "").lower() == local_os
                    and str(platform.get("Architecture") or "").lower() == local_arch
                    and descriptor.get("digest")
                ):
                    platform_digests.add(str(descriptor["digest"]))
            descriptor = distribution.get("Descriptor") or {}
            if descriptor.get("digest"):
                platform_digests.add(str(descriptor["digest"]))
            repo_digests = set()
            for value in local_attrs.get("RepoDigests") or []:
                if "@" in value:
                    repo_digests.add(value.rsplit("@", 1)[1])
            if not platform_digests or not repo_digests:
                return None, "Rejestr nie udostępnił porównywalnego digestu obrazu."
            return not bool(platform_digests & repo_digests), "Porównano digest obrazu z rejestrem."
        except Exception as exc:
            return None, f"Nie udało się sprawdzić rejestru: {type(exc).__name__}"

    def inspect_container(
        self,
        container: Any,
        apps: list[dict[str, Any]],
        catalog_error: str | None = None,
        all_containers: list[Any] | None = None,
    ) -> dict[str, Any]:
        attrs = container.attrs
        config = attrs.get("Config") or {}
        current = str(config.get("Image") or "")
        result: dict[str, Any] = {
            "id": str(container.id),
            "name": str(getattr(container, "name", container.id)).lstrip("/"),
            "current_image": current,
            "target_image": current,
            "update_available": False,
            "supported": True,
            "source": "",
            "status": str((attrs.get("State") or {}).get("Status") or getattr(container, "status", "unknown")),
            "message": "",
            "has_update_instructions": bool(self._catalog_update_instructions(current, apps)) if current else False,
        }
        if self._is_self(container):
            result.update(supported=False, message="To jest panel aktualizujący; pominięto aktualizację samego panelu.")
            return result
        reason = self._unsupported_reason(container)
        if reason:
            result.update(supported=False, message=reason)
            return result
        if not current or current.startswith("sha256:"):
            result.update(supported=False, message="Kontener nie przechowuje nazwy obrazu, której można użyć do pobrania aktualizacji.")
            return result

        candidate = self._catalog_candidate(current, apps)
        if candidate and candidate.available:
            conflict = self._port_conflict_reason(container, candidate.update_instructions, all_containers)
            if conflict:
                result.update(supported=False, source=candidate.source, message=conflict)
                return result
            result.update(
                update_available=True,
                target_image=candidate.target_image,
                source=candidate.source,
                message=candidate.message,
                has_update_instructions=bool(candidate.update_instructions),
            )
            return result
        if candidate:
            result.update(source=candidate.source, message=candidate.message)

        image_id = attrs.get("Image")
        try:
            local_image = self.client.images.get(image_id) if image_id else container.image
        except Exception:
            local_image = getattr(container, "image", None)
        available, digest_message = self._registry_digest(current, local_image)
        if available is True:
            instructions = self._catalog_update_instructions(current, apps)
            conflict = self._port_conflict_reason(container, instructions, all_containers)
            if conflict:
                result.update(supported=False, source=result["source"] or "digest rejestru", message=conflict)
                return result
            result.update(
                update_available=True,
                target_image=current,
                source="digest rejestru",
                message="Ten sam tag wskazuje w rejestrze nowszy obraz.",
            )
        elif available is False:
            result.update(source=result["source"] or "digest rejestru", message="Obraz jest aktualny.")
        else:
            result.update(source=result["source"] or "rejestr", message=catalog_error or digest_message)
        return result

    def scan(self, progress: Callable[[str], None] | None = None) -> list[dict[str, Any]]:
        apps, catalog_error = self._catalog()
        containers = self.client.containers.list(all=True)
        results = []
        for index, container in enumerate(containers, start=1):
            if progress:
                progress(f"Sprawdzanie kontenera {index}/{len(containers)}: {getattr(container, 'name', container.id)}")
            try:
                results.append(self.inspect_container(container, apps, catalog_error, containers))
            except Exception as exc:
                results.append({
                    "id": str(container.id),
                    "name": str(getattr(container, "name", container.id)).lstrip("/"),
                    "current_image": "",
                    "target_image": "",
                    "update_available": False,
                    "supported": False,
                    "source": "",
                    "status": "error",
                    "message": f"Nie udało się odczytać kontenera: {type(exc).__name__}",
                })
        return results

    def _create_config(
        self,
        container: Any,
        target_image: str,
        update_instructions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        attrs = container.attrs
        config = attrs.get("Config") or {}
        host = copy.deepcopy(attrs.get("HostConfig") or {})
        for generated in ("ContainerIDFile", "Cgroup", "MaskedPaths", "ReadonlyPaths"):
            host.pop(generated, None)

        # Docker inspect reports actual mounts separately; re-add anonymous volumes too,
        # so the replacement attaches to the same persistent volume instead of a new one.
        mounts = list(host.get("Mounts") or [])
        covered_targets = {str(mount.get("Target") or mount.get("Destination") or "") for mount in mounts}
        for bind in host.get("Binds") or []:
            parts = str(bind).split(":")
            if len(parts) >= 2:
                covered_targets.add(parts[-2] if parts[-1] in {"ro", "rw"} else parts[-1])
        runtime_mounts = attrs.get("Mounts") or []
        for mount in runtime_mounts:
            target = str(mount.get("Destination") or "")
            if not target or target in covered_targets:
                continue
            mount_type = str(mount.get("Type") or "")
            if mount_type == "bind":
                spec = {
                    "Type": "bind",
                    "Source": mount.get("Source"),
                    "Target": target,
                    "ReadOnly": not bool(mount.get("RW", True)),
                }
                propagation = mount.get("Propagation")
                if propagation:
                    spec["BindOptions"] = {"Propagation": propagation}
                mounts.append(spec)
                covered_targets.add(target)
            elif mount_type == "volume" and mount.get("Name"):
                mounts.append({
                    "Type": "volume",
                    "Source": mount["Name"],
                    "Target": target,
                    "ReadOnly": not bool(mount.get("RW", True)),
                })
                covered_targets.add(target)
        if mounts:
            host["Mounts"] = mounts

        instructions = update_instructions or {}
        if not isinstance(instructions, dict) or set(instructions) - {"config", "host_config"}:
            raise ValueError("Instrukcje aktualizacji muszą zawierać wyłącznie config i host_config.")
        config_overrides = instructions.get("config") or {}
        host_overrides = instructions.get("host_config") or {}
        if not isinstance(config_overrides, dict) or set(config_overrides) - CONFIG_UPDATE_FIELDS:
            raise ValueError("Instrukcje aktualizacji zawierają nieobsługiwane pola config.")
        if not isinstance(host_overrides, dict) or set(host_overrides) - HOST_CONFIG_UPDATE_FIELDS:
            raise ValueError("Instrukcje aktualizacji zawierają nieobsługiwane lub niebezpieczne pola host_config.")
        host.update(copy.deepcopy(host_overrides))

        create_options = {
            "image": target_image,
            "command": config.get("Cmd"),
            "hostname": config.get("Hostname"),
            "user": config.get("User"),
            "detach": True,
            "stdin_open": bool(config.get("OpenStdin")),
            "tty": bool(config.get("Tty")),
            "ports": config.get("ExposedPorts"),
            "environment": config.get("Env"),
            "volumes": config.get("Volumes"),
            "network_disabled": bool(config.get("NetworkDisabled")),
            "entrypoint": config.get("Entrypoint"),
            "working_dir": config.get("WorkingDir"),
            "domainname": config.get("Domainname"),
            "host_config": host,
            "mac_address": config.get("MacAddress"),
            "labels": config.get("Labels"),
            "stop_signal": config.get("StopSignal"),
            "healthcheck": config.get("Healthcheck"),
            "stop_timeout": config.get("StopTimeout"),
            "runtime": config.get("Runtime"),
        }
        create_options.update(copy.deepcopy(config_overrides))
        return self.client.api.create_container_config(
            **create_options,
        )

    def _wait_until_healthy(self, container: Any) -> None:
        deadline = time.monotonic() + self.wait_seconds
        has_healthcheck = bool((container.attrs.get("Config") or {}).get("Healthcheck"))
        while time.monotonic() <= deadline:
            container.reload()
            state = container.attrs.get("State") or {}
            status = state.get("Status")
            health = (state.get("Health") or {}).get("Status")
            if status != "running":
                raise RuntimeError(f"Nowy kontener zakończył pracę (status: {status or 'nieznany'}).")
            if health == "unhealthy":
                raise RuntimeError("Nowy kontener zgłosił stan unhealthy.")
            if health == "healthy":
                return
            if not has_healthcheck and time.monotonic() >= deadline - self.wait_seconds + min(5, self.wait_seconds):
                return
            time.sleep(1)
        if has_healthcheck:
            raise RuntimeError("Przekroczono czas oczekiwania na stan healthy.")

    @staticmethod
    def _is_docker_port_conflict(error: Exception) -> bool:
        message = str(error).lower()
        return any(marker in message for marker in (
            "port is already allocated",
            "address already in use",
            "port is already in use",
            "bind: cannot assign requested address",
        ))

    def update_one(
        self,
        container: Any,
        target_image: str,
        update_instructions: dict[str, Any] | None = None,
    ) -> str:
        if self._is_self(container):
            raise RuntimeError("Aktualizacja samego panelu nie jest obsługiwana.")
        reason = self._unsupported_reason(container)
        if reason:
            raise RuntimeError(reason)

        # Validate and build the replacement config while the original is still running.
        raw_config = self._create_config(container, target_image, update_instructions)
        # Pull first: a registry or network failure leaves the running service untouched.
        self.client.images.pull(target_image)
        original_name = str(getattr(container, "name", "")).lstrip("/")
        was_running = str((container.attrs.get("State") or {}).get("Status")) == "running"
        existing_names = {
            str(getattr(item, "name", "")).lstrip("/")
            for item in self.client.containers.list(all=True)
        }
        base_backup_name = f"dcc-backup-{str(container.id)[:10]}"
        backup_name = base_backup_name
        suffix = 1
        while backup_name in existing_names:
            suffix += 1
            backup_name = f"{base_backup_name}-{suffix}"
        try:
            if was_running:
                container.stop(timeout=15)
            container.rename(backup_name)
        except Exception:
            if was_running:
                try:
                    container.start()
                except Exception:
                    pass
            raise

        replacement = None
        try:
            created = self.client.api.create_container_from_config(raw_config, name=original_name)
            replacement = self.client.containers.get(created["Id"])
            if was_running:
                replacement.start()
                self._wait_until_healthy(replacement)
            try:
                container.remove(v=False)
                return f"Zaktualizowano do {target_image}; wolumeny i konfiguracja zostały zachowane."
            except Exception as exc:
                return f"Zaktualizowano do {target_image}; stary kontener pozostał jako kopia {backup_name} ({type(exc).__name__})."
        except Exception as exc:
            port_conflict = self._is_docker_port_conflict(exc)
            if replacement is not None:
                try:
                    replacement.stop(timeout=5)
                except Exception:
                    pass
                try:
                    replacement.remove(v=False)
                except Exception:
                    pass
            try:
                container.rename(original_name)
                if was_running:
                    container.start()
            except Exception as rollback_exc:
                reason = "Docker wykrył konflikt portu" if port_conflict else "Aktualizacja nie powiodła się"
                raise RuntimeError(
                    f"{reason} ({type(exc).__name__}); przywrócenie starego kontenera wymaga interwencji ({type(rollback_exc).__name__})."
                ) from exc
            if port_conflict:
                raise RuntimeError(
                    "Docker wykrył zajęty port podczas uruchamiania nowego kontenera; przywrócono poprzedni kontener."
                ) from exc
            raise RuntimeError(f"Aktualizacja nie powiodła się; przywrócono poprzedni kontener ({type(exc).__name__}).") from exc

    def update_selected(
        self,
        container_ids: list[str],
        progress: Callable[[str], None] | None = None,
    ) -> list[dict[str, Any]]:
        apps, catalog_error = self._catalog()
        output = []
        for index, container_id in enumerate(container_ids, start=1):
            try:
                container = self.client.containers.get(container_id)
                all_containers = self.client.containers.list(all=True)
                current = self.inspect_container(container, apps, catalog_error, all_containers)
                if not current["supported"] or not current["update_available"]:
                    output.append({
                        "name": current["name"],
                        "result": current["message"] or "Brak dostępnej aktualizacji.",
                        "ok": False,
                    })
                    continue
                if progress:
                    progress(f"Aktualizowanie {index}/{len(container_ids)}: {current['name']}")
                instructions = self._catalog_update_instructions(current["current_image"], apps)
                message = self.update_one(container, current["target_image"], instructions)
                output.append({"name": current["name"], "result": message, "ok": True})
            except Exception as exc:
                output.append({"name": str(container_id)[:12], "result": str(exc), "ok": False})
        return output
