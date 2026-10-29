"""Safe, opt-in image update support for Docker containers."""

from __future__ import annotations

import copy
import base64
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DCC_CATALOG_URL = "https://raw.githubusercontent.com/hattimon/DCC/main/dcc-catalog.json"
DCC_CATALOG_FALLBACK_URLS = (
    "https://api.github.com/repos/hattimon/DCC/contents/dcc-catalog.json?ref=main",
    "https://cdn.jsdelivr.net/gh/hattimon/DCC@main/dcc-catalog.json",
)
SELF_LABEL = "com.hattimon.dcc-updater"
SELF_UPDATE_HELPER_LABEL = "com.hattimon.dcc-updater-self-update-helper"
SELF_IMAGE = "ghcr.io/hattimon/dcc-container-updater:latest"
SELF_UPDATE_HELPER_NAME = "dcc-updater-self-update-helper"
SUPPORTED_NETWORK_MODES = {"default", "bridge", "host", "none"}
COMPOSE_PROJECT_LABEL = "com.docker.compose.project"
COMPOSE_SERVICE_LABEL = "com.docker.compose.service"
COMPOSE_WORKING_DIR_LABEL = "com.docker.compose.project.working_dir"
COMPOSE_CONFIG_FILES_LABEL = "com.docker.compose.project.config_files"
COMPOSE_CONFIG_ROOTS = ("/home", "/opt", "/srv", "/mnt", "/media", "/root")
REGISTRY_RETRY_DELAYS = (2, 5)
COMPOSE_TIMEOUT = 45
COMPOSE_PULL_TIMEOUT = 900
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


def same_image_reference(left: str, right: str) -> bool:
    left_value, right_value = str(left or "").strip(), str(right or "").strip()
    if "@" in left_value or "@" in right_value:
        left_repo, _, left_digest = left_value.partition("@")
        right_repo, _, right_digest = right_value.partition("@")
        return (
            bool(left_digest and right_digest)
            and normalized_repository(left_repo) == normalized_repository(right_repo)
            and left_digest.lower() == right_digest.lower()
        )
    left_repo, left_tag = image_reference(left_value)
    right_repo, right_tag = image_reference(right_value)
    return normalized_repository(left_repo) == normalized_repository(right_repo) and left_tag == right_tag


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
    sources = tuple(dict.fromkeys((url, *DCC_CATALOG_FALLBACK_URLS)))
    failures = []
    for source in sources:
        request = urllib.request.Request(source, headers={
            "Accept": "application/vnd.github+json, application/json",
            "User-Agent": "DCC-Container-Updater/1.0",
        })
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                raw_payload = response.read()
            if source.startswith("https://api.github.com/"):
                metadata = json.loads(raw_payload.decode("utf-8"))
                if metadata.get("encoding") != "base64" or not isinstance(metadata.get("content"), str):
                    raise ValueError("GitHub API nie zwróciło katalogu w formacie base64.")
                raw_payload = base64.b64decode(metadata["content"], validate=False)
            payload = json.loads(raw_payload.decode("utf-8"))
            apps = payload.get("apps") if isinstance(payload, dict) else None
            if not isinstance(apps, list):
                raise ValueError("Odpowiedź nie zawiera listy aplikacji.")
            valid_apps = [item for item in apps if isinstance(item, dict) and item.get("image")]
            if not valid_apps:
                raise ValueError("Pobrany katalog nie zawiera aplikacji.")
            return valid_apps
        except Exception as exc:
            host = source.split("/", 3)[2] if "://" in source else source
            detail = str(exc).strip().replace("\n", " ")[:160]
            failures.append(f"{host}: {type(exc).__name__}{(': ' + detail) if detail else ''}")
    raise RuntimeError("Nie udało się pobrać katalogu DCC z żadnego źródła. Sprawdź połączenie z Internetem, DNS i TLS. " + " | ".join(failures))


@dataclass
class UpdateCandidate:
    available: bool
    target_image: str
    source: str
    message: str
    update_instructions: dict[str, Any] | None = None


@dataclass
class ComposeProject:
    project: str
    service: str
    working_dir: Path
    config_files: tuple[Path, ...]
    config: dict[str, Any]


def _error_text(error: Any) -> str:
    """Extract a short searchable error body without assuming Docker SDK types."""
    values = [str(error)]
    explanation = getattr(error, "explanation", None)
    if explanation:
        values.append(json.dumps(explanation, ensure_ascii=False) if isinstance(explanation, dict) else str(explanation))
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    if status:
        values.append(str(status))
    return " ".join(values).lower()


def _error_excerpt(error: Any) -> str:
    explanation = getattr(error, "explanation", None)
    if isinstance(explanation, dict):
        value = json.dumps(explanation, ensure_ascii=False)
    elif explanation:
        value = str(explanation)
    else:
        value = str(error)
    value = re.sub(r"https?://\S+|http\+docker://\S+", "adres rejestru", value)
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())[:180]


def friendly_registry_error(error: Any, operation: str = "Sprawdzanie") -> str:
    """Translate Docker/Compose registry failures into a concise Polish message."""
    detail = _error_text(error)
    suffix = "Działający kontener nie został zatrzymany; ponów próbę za chwilę."
    if any(term in detail for term in ("tls handshake timeout", "i/o timeout", "context deadline exceeded", "timed out", "timeout")):
        return f"{operation}: rejestr nie odpowiedział na czas (timeout TLS/sieci). {suffix}"
    if "no matching manifest" in detail or "does not match the specified platform" in detail:
        return f"{operation}: obraz nie udostępnia wariantu dla architektury hosta (Raspberry Pi wymaga zwykle linux/arm64)."
    if "429" in detail or "too many requests" in detail or "rate limit" in detail:
        return f"{operation}: rejestr ograniczył liczbę zapytań. Odczekaj i spróbuj ponownie."
    if "401" in detail or "unauthorized" in detail or "authentication required" in detail:
        return f"{operation}: rejestr wymaga logowania. Sprawdź dane dostępowe Dockera."
    if "403" in detail or "forbidden" in detail or "denied: requested access" in detail:
        return f"{operation}: rejestr odmówił dostępu do obrazu. Sprawdź uprawnienia obrazu."
    if "manifest unknown" in detail or "404" in detail or "not found" in detail:
        return f"{operation}: rejestr nie znalazł wskazanego obrazu lub tagu. Sprawdź jego nazwę."
    if any(term in detail for term in ("no such host", "temporary failure in name resolution", "dns")):
        return f"{operation}: host nie może rozwiązać adresu rejestru (DNS). Sprawdź sieć hosta."
    if any(term in detail for term in ("connection reset", "connection refused", "network is unreachable", "unexpected eof")):
        return f"{operation}: połączenie z rejestrem zostało przerwane. Sprawdź sieć hosta i ponów próbę."
    if any(term in detail for term in ("500", "502", "503", "504", "internal server error", "service unavailable", "bad gateway")):
        return f"{operation}: rejestr lub Docker chwilowo zwraca błąd serwera. {suffix}"
    if isinstance(error, str):
        excerpt = " ".join(error.split())[:180]
        return f"{operation}: {excerpt or 'nieznany błąd rejestru'}. {suffix}"
    excerpt = _error_excerpt(error)
    return f"{operation}: błąd komunikacji z rejestrem ({type(error).__name__}){': ' + excerpt if excerpt else ''}. {suffix}"


def _is_transient_registry_error(error: Any) -> bool:
    detail = _error_text(error)
    return any(term in detail for term in (
        "tls handshake timeout", "i/o timeout", "context deadline exceeded", "timed out", "timeout",
        "temporary failure in name resolution", "no such host", "connection reset", "connection refused",
        "network is unreachable", "unexpected eof", "too many requests", "rate limit",
        "500", "502", "503", "504", "internal server error", "service unavailable",
    ))


class UpdateService:
    def __init__(
        self,
        client: Any,
        catalog_loader: Callable[[], list[dict[str, Any]]] = load_catalog,
        wait_seconds: int = 60,
        compose_roots: tuple[str, ...] | list[str] | None = None,
        registry_auth_loader: Callable[[str], dict[str, str] | None] | None = None,
    ) -> None:
        self.client = client
        self.registry_auth_loader = registry_auth_loader
        self.catalog_loader = catalog_loader
        self.wait_seconds = max(1, min(int(wait_seconds), 180))
        self._catalog_cache: tuple[float, list[dict[str, Any]]] | None = None
        configured_roots = os.environ.get("DCC_UPDATER_COMPOSE_ROOTS", "")
        roots = compose_roots or tuple(value.strip() for value in configured_roots.split(",") if value.strip()) or COMPOSE_CONFIG_ROOTS
        self.compose_roots = tuple(roots)
        self.compose_bin = os.environ.get("DCC_UPDATER_COMPOSE_BIN", "docker-compose")
        self._compose_cache: dict[tuple[str, ...], tuple[dict[str, Any] | None, str | None]] = {}
        self._registry_cache: dict[tuple[str, str, str, tuple[str, ...]], tuple[bool | None, str]] = {}

    def _catalog(self) -> tuple[list[dict[str, Any]], str | None]:
        now = time.monotonic()
        if self._catalog_cache and now - self._catalog_cache[0] < 600:
            return self._catalog_cache[1], None
        try:
            apps = self.catalog_loader()
            self._catalog_cache = (now, apps)
            return apps, None
        except Exception as exc:  # registry checks can still run if GitHub is unavailable
            detail = str(exc).strip().replace("\n", " ")[:500]
            return [], f"Nie udało się pobrać katalogu DCC: {detail or type(exc).__name__}"

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
    def _is_self_update_helper(container: Any) -> bool:
        labels = (container.attrs.get("Config") or {}).get("Labels") or {}
        return labels.get(SELF_UPDATE_HELPER_LABEL) == "true"

    @staticmethod
    def _self_update_docker_socket_mount(container: Any) -> dict[str, Any] | None:
        mounts = container.attrs.get("Mounts") or []
        host_mounts = (container.attrs.get("HostConfig") or {}).get("Mounts") or []
        for mount in (*mounts, *host_mounts):
            destination = str(mount.get("Destination") or mount.get("Target") or "")
            if destination == "/var/run/docker.sock" and mount.get("Source"):
                return {"Source": mount["Source"], "Destination": destination, "Type": "bind"}
        binds = (container.attrs.get("HostConfig") or {}).get("Binds") or []
        for bind in binds:
            parts = str(bind).split(":", 2)
            if len(parts) >= 2 and parts[1] == "/var/run/docker.sock" and parts[0]:
                return {"Source": parts[0], "Destination": parts[1], "Type": "bind"}
        return None

    def _find_self_container(self, containers: list[Any] | None = None) -> Any | None:
        if containers is None:
            containers = self.client.containers.list(all=True, ignore_removed=True)
        matches = [container for container in containers if self._is_self(container)]
        if not matches:
            return None
        hostname = os.environ.get("HOSTNAME", "").strip().lower()
        if hostname:
            current = [
                container for container in matches
                if str(getattr(container, "id", "")).lower().startswith(hostname)
                or hostname.startswith(str(getattr(container, "id", "")).lower())
            ]
            if len(current) == 1:
                return current[0]
        running = [
            container for container in matches
            if str((container.attrs.get("State") or {}).get("Status") or "").lower() == "running"
        ]
        if len(running) == 1:
            return running[0]
        if len(matches) == 1:
            return matches[0]
        preferred = [
            container for container in running
            if str(getattr(container, "name", "")).lstrip("/").lower() == "dcc-container-updater"
        ]
        if len(preferred) == 1:
            return preferred[0]
        raise RuntimeError("Znaleziono kilka kontenerów DCC Container Updater; nie można bezpiecznie wybrać panelu do aktualizacji.")

    def check_self_update(self, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
        # Docker inspects each listed container separately. Short-lived jobs can
        # disappear between these calls; they must not abort a panel check.
        # Reuse the same complete inventory for identity and port checks.
        all_containers = self.client.containers.list(all=True, ignore_removed=True)
        container = self._find_self_container(all_containers)
        if container is None:
            return {
                "checked": False,
                "update_available": False,
                "message": "Nie rozpoznano kontenera DCC Container Updater na tym hoście.",
            }
        local_image = self._local_image(container)
        if local_image is None:
            return {
                "checked": False,
                "update_available": False,
                "message": "Nie można odczytać lokalnego obrazu panelu; nie zmieniono działającego kontenera.",
            }
        current, image_error = self._named_local_image(container, local_image)
        if not current or normalized_repository(current) != normalized_repository(SELF_IMAGE):
            return {
                "checked": False,
                "update_available": False,
                "message": image_error or "Obraz panelu nie pochodzi z oficjalnego repozytorium DCC Container Updater.",
            }
        if progress:
            progress("Sprawdzanie najnowszego obrazu DCC Container Updater…")
        available, detail = self._registry_digest(SELF_IMAGE, local_image)
        if available is True:
            blocker = None
            if self._is_compose(container):
                blocker = "Panel jest zarządzany przez Docker Compose; jego własną aktualizację należy wykonać przez plik Compose."
            else:
                blocker = self._unsupported_reason(container) or self._port_conflict_reason(
                    container,
                    None,
                    all_containers,
                )
            if not blocker and self._self_update_docker_socket_mount(container) is None:
                blocker = "W kontenerze panelu brakuje montowania /var/run/docker.sock wymaganego do bezpiecznej podmiany."
            return {
                "checked": True,
                "update_available": True,
                "supported": not bool(blocker),
                "container_id": str(container.id),
                "current_image_id": str(getattr(local_image, "id", "")),
                "current_image": current,
                "target_image": SELF_IMAGE,
                "message": blocker or "W rejestrze znaleziono nowszy obraz panelu. Możesz uruchomić aktualizację.",
            }
        if available is False:
            return {
                "checked": True,
                "update_available": False,
                "current_image_id": str(getattr(local_image, "id", "")),
                "current_image": current,
                "target_image": SELF_IMAGE,
                "message": "Panel DCC Container Updater jest aktualny. Nie ma nowszego obrazu.",
            }
        return {
            "checked": False,
            "update_available": False,
            "current_image": current,
            "target_image": SELF_IMAGE,
            "message": f"Nie udało się sprawdzić wersji panelu. Obecny kontener działa bez zmian. {detail}",
        }

    def start_self_update(
        self, progress: Callable[[str], None] | None = None,
        prepare_restart: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        checked = self.check_self_update(progress)
        if not checked.get("update_available"):
            return {**checked, "started": False}
        if not checked.get("supported", True):
            return {**checked, "started": False}

        container = self.client.containers.get(str(checked["container_id"]))
        socket_mount = self._self_update_docker_socket_mount(container)
        if socket_mount is None:
            return {
                **checked,
                "started": False,
                "message": "Nie można uruchomić bezpiecznej podmiany: w kontenerze panelu nie znaleziono montowania /var/run/docker.sock.",
            }

        try:
            if progress:
                progress("Pobieranie nowego obrazu panelu; obecny kontener pozostaje uruchomiony…")
            self._pull_image_with_retry(SELF_IMAGE)
            image = self.client.images.get(SELF_IMAGE)
            target_image_id = str(getattr(image, "id", ""))
            if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", target_image_id):
                raise RuntimeError("Docker nie zwrócił prawidłowego, przypiętego identyfikatora nowego obrazu.")
            current_image = self._local_image(container)
            if current_image is not None and str(getattr(current_image, "id", "")) == target_image_id:
                return {
                    **checked,
                    "started": False,
                    "update_available": False,
                    "message": "Obraz panelu zdążył się zaktualizować; nowy kontener nie jest potrzebny.",
                }

            if prepare_restart:
                prepare_restart(target_image_id)
            existing_helpers = [
                candidate for candidate in self.client.containers.list(all=True, ignore_removed=True)
                if str(getattr(candidate, "name", "")).lstrip("/") == SELF_UPDATE_HELPER_NAME
            ]
            for helper in existing_helpers:
                labels = ((helper.attrs.get("Config") or {}).get("Labels") or {})
                if labels.get(SELF_UPDATE_HELPER_LABEL) != "true":
                    raise RuntimeError(f"Nazwa pomocniczego kontenera {SELF_UPDATE_HELPER_NAME} jest już zajęta.")
                status = str((helper.attrs.get("State") or {}).get("Status") or "").lower()
                if status in {"created", "restarting", "running", "paused"}:
                    return {
                        **checked,
                        "started": True,
                        "target_image_id": target_image_id,
                        "message": "Pomocniczy kontener aktualizujący już działa; poczekaj na ponowne uruchomienie panelu.",
                    }
                helper.remove(v=False)

            if progress:
                progress("Uruchamianie pomocniczego kontenera. Panel zostanie odtworzony z zachowaniem konfiguracji i danych…")
            self.client.containers.run(
                target_image_id,
                command=["python", "/app/self_update.py", str(container.id), target_image_id],
                name=SELF_UPDATE_HELPER_NAME,
                detach=True,
                auto_remove=False,
                volumes={str(socket_mount["Source"]): {
                    "bind": "/var/run/docker.sock",
                    "mode": "rw",
                }},
                network_mode="none",
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                labels={SELF_UPDATE_HELPER_LABEL: "true"},
                restart_policy={"Name": "no"},
            )
            return {
                **checked,
                "started": True,
                "target_image_id": target_image_id,
                "message": "Aktualizacja panelu została uruchomiona. Kontener zostanie bezpiecznie odtworzony z zachowaniem konfiguracji i wolumenów.",
            }
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            return {
                **checked,
                "started": False,
                "message": f"Nie udało się uruchomić aktualizacji panelu. Działający kontener pozostawiono bez zmian. {message}",
            }

    def replace_self_from_helper(self, container_id: str, target_image_id: str) -> str:
        if not re.fullmatch(r"[0-9a-fA-F]{12,64}", str(container_id)):
            raise ValueError("Nieprawidłowy identyfikator kontenera panelu.")
        if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(target_image_id)):
            raise ValueError("Nieprawidłowy identyfikator obrazu aktualizacji.")
        container = self.client.containers.get(container_id)
        if not self._is_self(container):
            raise RuntimeError("Wskazany kontener nie jest oznaczonym panelem DCC Container Updater.")
        image = self.client.images.get(target_image_id)
        references = [
            *(getattr(image, "attrs", {}).get("RepoTags") or []),
            *(getattr(image, "attrs", {}).get("RepoDigests") or []),
        ]
        if not any(normalized_repository(str(reference)) == normalized_repository(SELF_IMAGE) for reference in references):
            raise RuntimeError("Przypięty obraz nie pochodzi z repozytorium DCC Container Updater.")
        # Keep the repository visible to existing DCC installations while still
        # using immutable content. Config.Image=sha256:<id> loses store identity.
        pinned_reference = None
        for reference in sorted(set(str(value) for value in (getattr(image, "attrs", {}).get("RepoDigests") or []))):
            if (normalized_repository(reference) != normalized_repository(SELF_IMAGE)
                    or not re.fullmatch(r"[^@\s]+@sha256:[0-9a-fA-F]{64}", reference)):
                continue
            resolved = self.client.images.get(reference)
            if str(getattr(resolved, "id", "")) == target_image_id:
                pinned_reference = reference
                break
        if not pinned_reference:
            raise RuntimeError("Brak przypiętej nazwy repozytorium dla obrazu panelu; działający kontener pozostawiono bez zmian.")
        return self.update_one(
            container,
            pinned_reference,
            _allow_self=True,
            _image_already_pulled=True,
            _expected_image_id=target_image_id,
        )

    @staticmethod
    def _is_compose(container: Any) -> bool:
        labels = ((container.attrs.get("Config") or {}).get("Labels") or {})
        return bool(labels.get(COMPOSE_PROJECT_LABEL))

    @staticmethod
    def _unsupported_reason(container: Any) -> str | None:
        attrs = container.attrs
        config = attrs.get("Config") or {}
        labels = config.get("Labels") or {}
        if any(key.startswith("com.docker.swarm.") for key in labels):
            return "Kontener jest zarządzany przez Docker Swarm."
        host = attrs.get("HostConfig") or {}
        if host.get("AutoRemove"):
            return "Kontener ma włączone automatyczne usuwanie; nie można bezpiecznie zachować kopii."
        mode = str(host.get("NetworkMode") or "default")
        if mode.startswith("container:"):
            return "Kontener współdzieli przestrzeń sieciową innego kontenera."
        is_compose = bool(labels.get(COMPOSE_PROJECT_LABEL))
        if not is_compose and mode not in SUPPORTED_NETWORK_MODES:
            return "Niestandardowa sieć Docker wymaga odtworzenia endpointów; pominięto ją dla bezpieczeństwa."
        networks = (attrs.get("NetworkSettings") or {}).get("Networks") or {}
        names = set(networks)
        if not is_compose and (len(names) > 1 or any(name not in {"bridge", "host", "none"} for name in names)):
            return "Kontener używa niestandardowej lub wielokrotnej sieci Docker."
        return None

    @staticmethod
    def _path_is_under(path: Path, roots: tuple[str, ...]) -> bool:
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError):
            return False
        for root_value in roots:
            try:
                root = Path(root_value).resolve(strict=True)
                resolved.relative_to(root)
                return True
            except (OSError, RuntimeError, ValueError):
                continue
        return False

    @staticmethod
    def automatic_dependency_blocker(container: Any, all_containers: list[Any]) -> str | None:
        """Explicit Docker dependencies need a human-controlled coordinated update."""
        host = container.attrs.get("HostConfig") or {}
        if (host.get("VolumesFrom") or host.get("Links")
                or any(str(host.get(key) or "").startswith("container:") for key in ("NetworkMode", "PidMode", "IpcMode"))):
            return "Automatyczna aktualizacja zablokowana: kontener deklaruje zależności Links, VolumesFrom lub współdzielone przestrzenie."
        identifiers = {str(container.id), str(getattr(container, "name", "")).lstrip("/")}
        own_mounts = container.attrs.get("Mounts") or []
        for other in all_containers:
            if str(other.id) == str(container.id):
                continue
            other_host = other.attrs.get("HostConfig") or {}
            for key in ("NetworkMode", "PidMode", "IpcMode"):
                value = str(other_host.get(key) or "")
                if value.startswith("container:"):
                    target = value.split(":", 1)[1]
                    if target and any(name == target or (len(target) >= 12 and name.startswith(target)) for name in identifiers):
                        return f"Automatyczna aktualizacja zablokowana: przestrzeń kontenera współdzieli usługa {other.name}."
            for value in other_host.get("VolumesFrom") or []:
                target = str(value).split(":", 1)[0].lstrip("/")
                if target in identifiers:
                    return f"Automatyczna aktualizacja zablokowana: VolumesFrom używa usługa {other.name}."
            for value in other_host.get("Links") or []:
                if str(value).split(":", 1)[0].lstrip("/") in identifiers:
                    return f"Automatyczna aktualizacja zablokowana: Links używa usługa {other.name}."
            for mount in own_mounts:
                if mount.get("Type") not in {"bind", "volume"} or mount.get("Destination") == "/var/run/docker.sock":
                    continue
                source = str((mount.get("Name") or mount.get("Source") or "") if mount.get("Type") == "volume" else mount.get("Source") or "").replace("\\", "/")
                for peer in other.attrs.get("Mounts") or []:
                    if peer.get("Type") != mount.get("Type") or not (mount.get("RW", True) or peer.get("RW", True)):
                        continue
                    peer_source = str((peer.get("Name") or peer.get("Source") or "") if peer.get("Type") == "volume" else peer.get("Source") or "").replace("\\", "/")
                    overlap = source and peer_source and (source == peer_source or (
                        mount.get("Type") == "bind" and (
                            peer_source.startswith(source.rstrip("/") + "/")
                            or source.startswith(peer_source.rstrip("/") + "/"))
                    ))
                    if overlap:
                        # Management tools observe directories rather than share
                        # application data. The updater's read-only binds and a
                        # host-PID monitor's read-only ancestor views are safe;
                        # explicit data mounts and other consumers stay blocked.
                        if peer.get("Type") == "bind" and peer.get("RW") is False:
                            host_observer = other_host.get("PidMode") == "host" and any(
                                view.get("Type") == "bind" and view.get("Source") == "/"
                                and view.get("RW") is False
                                for view in other.attrs.get("Mounts") or []
                            )
                            ancestor_view = source != peer_source and source.startswith(peer_source.rstrip("/") + "/")
                            if UpdateService._is_self(other) or (host_observer and ancestor_view):
                                continue
                        return f"Automatyczna aktualizacja zablokowana: trwałe dane współdzieli usługa {other.name}."
        return None

    def _load_compose_project(self, container: Any) -> tuple[ComposeProject | None, str | None]:
        """Read Compose's resolved model without modifying any project files."""
        labels = ((container.attrs.get("Config") or {}).get("Labels") or {})
        project = str(labels.get(COMPOSE_PROJECT_LABEL) or "")
        if not project:
            return None, None
        service = str(labels.get(COMPOSE_SERVICE_LABEL) or "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,127}", project) or not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", service
        ):
            return None, "Etykiety Compose nie zawierają prawidłowej nazwy projektu lub usługi."

        raw_files = str(labels.get(COMPOSE_CONFIG_FILES_LABEL) or "")
        if not raw_files:
            return None, "Brak ścieżki pliku Compose w etykietach kontenera; updater nie może bezpiecznie odtworzyć usługi."
        raw_file_values = [value.strip() for value in raw_files.split(",") if value.strip()]
        if not raw_file_values:
            return None, "Etykiety Compose nie zawierają prawidłowej ścieżki pliku."
        raw_working_dir = str(labels.get(COMPOSE_WORKING_DIR_LABEL) or "").strip()
        try:
            if raw_working_dir:
                working_dir = Path(raw_working_dir).resolve(strict=True)
            elif Path(raw_file_values[0]).is_absolute():
                working_dir = Path(raw_file_values[0]).resolve(strict=True).parent
            else:
                return None, "Compose nie podał katalogu projektu, a ścieżka pliku jest względna."
            files = tuple(
                (Path(value) if Path(value).is_absolute() else working_dir / value).resolve(strict=True)
                for value in raw_file_values
            )
        except (OSError, RuntimeError) as exc:
            return None, f"Plik Compose nie jest dostępny wewnątrz updatera ({type(exc).__name__}). Dodaj jego katalog jako montowanie tylko do odczytu."
        if not files or any(not path.is_file() for path in files):
            return None, "Nie znaleziono pliku Compose; dodaj jego katalog jako montowanie tylko do odczytu."
        if any(not self._path_is_under(path, self.compose_roots) for path in files):
            return None, "Plik Compose leży poza katalogami udostępnionymi updaterowi tylko do odczytu."

        if not working_dir.is_dir() or not self._path_is_under(working_dir, self.compose_roots):
            return None, "Katalog projektu Compose nie jest dostępny w bezpiecznych montowaniach tylko do odczytu."

        cache_key = (project, str(working_dir), *(str(path) for path in files))
        if cache_key in self._compose_cache:
            payload, error = self._compose_cache[cache_key]
            if payload is None:
                return None, error
            parsed = payload
        else:
            args = [self.compose_bin, "--project-name", project, "--project-directory", str(working_dir)]
            for path in files:
                args.extend(("--file", str(path)))
            args.extend(("config", "--format", "json"))
            try:
                completed = subprocess.run(
                    args,
                    cwd=str(working_dir),
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=COMPOSE_TIMEOUT,
                )
            except FileNotFoundError:
                error = "W obrazie updatera brakuje Docker Compose CLI. Zainstaluj nowszy obraz updatera."
                self._compose_cache[cache_key] = (None, error)
                return None, error
            except subprocess.TimeoutExpired:
                error = "Odczyt konfiguracji Compose przekroczył limit czasu; plików nie zmieniono."
                self._compose_cache[cache_key] = (None, error)
                return None, error
            except OSError as exc:
                error = f"Nie można uruchomić Docker Compose ({type(exc).__name__})."
                self._compose_cache[cache_key] = (None, error)
                return None, error
            if completed.returncode != 0:
                detail = (completed.stderr or "").strip().replace("\r", " ").replace("\n", " ")
                if re.search(r"is not set|defaulting to a blank string", detail, re.IGNORECASE):
                    error = "Compose nie ma wszystkich zmiennych środowiskowych projektu. Zamontuj plik .env lub uzupełnij konfigurację środowiska."
                else:
                    excerpt = detail[:260] or f"kod wyjścia {completed.returncode}"
                    error = f"Nie udało się odczytać konfiguracji Compose: {excerpt}"
                self._compose_cache[cache_key] = (None, error)
                return None, error
            if re.search(r"is not set|defaulting to a blank string", completed.stderr or "", re.IGNORECASE):
                error = "Compose nie ma wszystkich zmiennych środowiskowych projektu. Zamontuj plik .env lub uzupełnij konfigurację środowiska."
                self._compose_cache[cache_key] = (None, error)
                return None, error
            try:
                parsed = json.loads(completed.stdout)
            except (TypeError, json.JSONDecodeError):
                error = "Docker Compose zwrócił nieczytelny model konfiguracji."
                self._compose_cache[cache_key] = (None, error)
                return None, error
            if not isinstance(parsed, dict) or not isinstance(parsed.get("services"), dict):
                error = "Model Compose nie zawiera listy usług."
                self._compose_cache[cache_key] = (None, error)
                return None, error
            self._compose_cache[cache_key] = (parsed, None)

        if service not in (parsed.get("services") or {}):
            return None, f"Usługa {service} nie występuje w aktualnym pliku Compose."
        return ComposeProject(project, service, working_dir, files, parsed), None

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

    @staticmethod
    def _compose_depends_on(service_config: dict[str, Any]) -> set[str]:
        raw = service_config.get("depends_on") or []
        if isinstance(raw, dict):
            return {str(name) for name in raw}
        if isinstance(raw, list):
            return {str(name) for name in raw}
        return set()

    @classmethod
    def _compose_references_service(cls, service_config: dict[str, Any], target: str) -> bool:
        if target in cls._compose_depends_on(service_config):
            return True
        links = service_config.get("links") or []
        if any(str(value).split(":", 1)[0] == target for value in links):
            return True
        volumes_from = service_config.get("volumes_from") or []
        if any(str(value).split(":", 1)[0] == target for value in volumes_from):
            return True
        network_mode = str(service_config.get("network_mode") or "")
        return network_mode == f"service:{target}"

    def _compose_port_conflict(
        self,
        container: Any,
        service_config: dict[str, Any],
        all_containers: list[Any] | None,
    ) -> str | None:
        proposed: list[tuple[str, str, str]] = []
        for port in service_config.get("ports") or []:
            if not isinstance(port, dict):
                continue
            host_port = str(port.get("published") or "").strip()
            if not host_port or host_port == "0":
                continue
            proposed.append((
                str(port.get("host_ip") or "").strip().lower(),
                host_port,
                str(port.get("protocol") or "tcp").lower(),
            ))
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
                        name = str(getattr(other, "name", "nieznany")).lstrip("/")
                        return (
                            f"Konfiguracja Compose zajmuje port {proposed_address or '*'}:{proposed_port}/{proposed_protocol}, "
                            f"który jest już przypisany do kontenera {name}. Zwolnij port przed aktualizacją."
                        )
        return None

    def _compose_update_blocker(
        self,
        container: Any,
        target_image: str,
        all_containers: list[Any] | None,
    ) -> tuple[ComposeProject | None, str | None]:
        project, error = self._load_compose_project(container)
        if error or project is None:
            return None, error or "Nie udało się odczytać konfiguracji Compose."

        services = project.config.get("services") or {}
        service_config = services.get(project.service) or {}
        env_files = service_config.get("env_file") or []
        if isinstance(env_files, (str, dict)):
            env_files = [env_files]
        for env_file in env_files:
            path_value = env_file.get("path") if isinstance(env_file, dict) else env_file
            if path_value and not self._path_is_under(Path(str(path_value)), self.compose_roots):
                return project, (
                    f"Plik env_file {path_value} nie znajduje się w katalogach zamontowanych tylko do odczytu. "
                    "Dodaj jego katalog do montowań updatera."
                )
        for section in ("configs", "secrets"):
            resources = project.config.get(section) or {}
            if not isinstance(resources, dict):
                continue
            for resource in resources.values():
                if isinstance(resource, dict) and resource.get("file"):
                    path_value = str(resource["file"])
                    if not self._path_is_under(Path(path_value), self.compose_roots):
                        return project, (
                            f"Plik {section} {path_value} nie znajduje się w katalogach zamontowanych tylko do odczytu. "
                            "Dodaj jego katalog do montowań updatera."
                        )
        compose_image = str(service_config.get("image") or "").strip()
        if not compose_image:
            return project, "Usługa Compose nie deklaruje pola image; updater nie buduje obrazów ze źródeł."
        if not same_image_reference(compose_image, target_image):
            return project, (
                f"Plik Compose wskazuje obraz {compose_image}, a wykryta aktualizacja to {target_image}. "
                f"Zmień pole image usługi w pliku Compose na {target_image}; updater nie edytuje plików projektu."
            )
        for volume in service_config.get("volumes") or []:
            if not isinstance(volume, dict) or volume.get("type") != "bind":
                continue
            source = Path(str(volume.get("source") or ""))
            if not source.is_absolute() or not self._path_is_under(source, self.compose_roots):
                return project, (
                    f"Bind mount {source or '(brak ścieżki)'} leży poza katalogami udostępnionymi updaterowi tylko do odczytu. "
                    "Dodaj jego katalog do montowań DCC lub aktualizuj projekt ręcznie."
                )

        replicas = []
        for item in all_containers or []:
            item_labels = ((getattr(item, "attrs", {}).get("Config") or {}).get("Labels") or {})
            if (
                item_labels.get(COMPOSE_PROJECT_LABEL) == project.project
                and item_labels.get(COMPOSE_SERVICE_LABEL) == project.service
            ):
                replicas.append(item)
        if len(replicas) != 1:
            return project, (
                f"Usługa Compose ma {len(replicas)} kontenerów/replik. Aktualizator obsługuje tylko pojedynczą replikę, "
                "aby nie zatrzymać kilku instancji naraz."
            )
        state = (container.attrs.get("State") or {}).get("Status")
        if state != "running":
            return project, "Kontener Compose nie działa. Aktualizator nie uruchamia usług, które były wcześniej zatrzymane."

        dependents = sorted(
            str(name)
            for name, other_config in services.items()
            if name != project.service
            and self._compose_references_service(
                other_config if isinstance(other_config, dict) else {},
                project.service,
            )
        )
        if dependents:
            return project, (
                "Usługi Compose zależne od tego kontenera: " + ", ".join(dependents)
                + ". Aktualizacja mogłaby przerwać ich pracę; najpierw zaktualizuj je razem w pliku Compose."
            )

        service_volumes = {
            (str(volume.get("type")), str(volume.get("source")))
            for volume in service_config.get("volumes") or []
            if isinstance(volume, dict)
            and volume.get("type") in {"volume", "bind"}
            and volume.get("source")
        }
        shared_volumes = []
        for name, other_config in services.items():
            if name == project.service or not isinstance(other_config, dict):
                continue
            other_volumes = {
                (str(volume.get("type")), str(volume.get("source")))
                for volume in other_config.get("volumes") or []
                if isinstance(volume, dict)
                and volume.get("type") in {"volume", "bind"}
                and volume.get("source")
            }
            shared_volumes.extend(sorted(source for _kind, source in service_volumes & other_volumes))
        if shared_volumes:
            return project, (
                "Usługa współdzieli wolumen lub bind mount Compose z inną usługą ("
                + ", ".join(sorted(set(shared_volumes)))
                + "); aktualizację należy wykonać wspólnie dla całego projektu."
            )

        own_networks = set(
            str(name)
            for name in ((container.attrs.get("NetworkSettings") or {}).get("Networks") or {})
            if name
        )
        own_network_mode = str((container.attrs.get("HostConfig") or {}).get("NetworkMode") or "")
        if own_network_mode == "host":
            own_networks.add("host")
        for other in all_containers or []:
            if str(getattr(other, "id", "")) == str(getattr(container, "id", "")):
                continue
            other_attrs = getattr(other, "attrs", {}) or {}
            other_networks = set(
                str(name)
                for name in ((other_attrs.get("NetworkSettings") or {}).get("Networks") or {})
                if name
            )
            other_network_mode = str((other_attrs.get("HostConfig") or {}).get("NetworkMode") or "")
            if other_network_mode == "host":
                other_networks.add("host")
            shared_networks = sorted(own_networks & other_networks)
            if shared_networks:
                name = str(getattr(other, "name", "nieznany")).lstrip("/")
                return project, (
                    f"Kontener {name} współdzieli sieć Docker {', '.join(shared_networks)}. "
                    "Nie można bezpiecznie wykluczyć zależności; aktualizacja pojedynczej usługi została zablokowana. "
                    "Zaktualizuj cały projekt Compose ręcznie."
                )

        conflict = self._compose_port_conflict(container, service_config, all_containers)
        if conflict:
            return project, conflict
        return project, None

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
        if not same_image_reference(target, image):
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
        local_attrs = getattr(local_image, "attrs", {}) or {}
        local_os = str(local_attrs.get("Os") or "linux").lower()
        local_arch = str(local_attrs.get("Architecture") or "").lower()
        local_digests = tuple(sorted(
            value.rsplit("@", 1)[1]
            for value in local_attrs.get("RepoDigests") or []
            if "@" in value
        ))
        cache_key = (image, local_os, local_arch, local_digests)
        if cache_key in self._registry_cache:
            return self._registry_cache[cache_key]

        for attempt in range(len(REGISTRY_RETRY_DELAYS) + 1):
            try:
                auth = self.registry_auth_loader(image) if self.registry_auth_loader else None
                distribution = self.client.api.inspect_distribution(image, **({'auth_config':auth} if auth else {}))
                platforms = distribution.get("Platforms") or []
                supported_platforms = set()
                for platform in platforms:
                    if not isinstance(platform, dict):
                        continue
                    # The Engine API returns OCI platform fields in lowercase.
                    # Platforms describe compatibility; only Descriptor has a digest.
                    platform_os = str(platform.get("os") or platform.get("OS") or "").lower()
                    platform_arch = str(platform.get("architecture") or platform.get("Architecture") or "").lower()
                    if platform_os and platform_arch and "unknown" not in {platform_os, platform_arch}:
                        supported_platforms.add((platform_os, platform_arch))
                if supported_platforms and local_arch and (local_os, local_arch) not in supported_platforms:
                    available_platforms = ", ".join(f"{os_name}/{arch}" for os_name, arch in sorted(supported_platforms))
                    result = (
                        None,
                        f"Obraz w rejestrze nie zawiera wariantu {local_os}/{local_arch}. Dostępne platformy: {available_platforms}.",
                    )
                    self._registry_cache[cache_key] = result
                    return result
                descriptor = distribution.get("Descriptor") or {}
                remote_digest = str(descriptor.get("digest") or "")
                if not remote_digest or not local_digests:
                    result = (None, "Rejestr nie udostępnił porównywalnego digestu obrazu.")
                else:
                    result = (remote_digest not in local_digests, "Porównano digest obrazu z rejestrem.")
                self._registry_cache[cache_key] = result
                return result
            except Exception as exc:
                if attempt < len(REGISTRY_RETRY_DELAYS) and _is_transient_registry_error(exc):
                    time.sleep(REGISTRY_RETRY_DELAYS[attempt])
                    continue
                result = (None, friendly_registry_error(exc, "Sprawdzanie rejestru"))
                self._registry_cache[cache_key] = result
                return result
        return None, "Sprawdzanie rejestru nie powiodło się."

    def _local_image(self, container: Any) -> Any:
        image_id = container.attrs.get("Image")
        try:
            return self.client.images.get(image_id) if image_id else container.image
        except Exception:
            # Docker SDK's image property performs another daemon lookup. A
            # running container can outlive deleted image metadata, so this
            # fallback may raise ImageNotFound too. Keep inventory readable;
            # never substitute the current tag for the missing original image.
            try:
                return getattr(container, "image", None)
            except Exception:
                return None

    @staticmethod
    def _named_local_image(container: Any, local_image: Any) -> tuple[str, str | None]:
        current = str(((container.attrs.get("Config") or {}).get("Image")) or "").strip()
        if current and not current.startswith("sha256:"):
            return current, None
        tags = sorted({
            str(tag).strip()
            for tag in ((getattr(local_image, "attrs", {}) or {}).get("RepoTags") or [])
            if tag and tag != "<none>:<none>"
        })
        if len(tags) == 1:
            return tags[0], None
        if not tags:
            return "", "Obraz kontenera ma tylko digest; lokalny obraz nie zawiera tagu, który można sprawdzić ani pobrać."
        return "", "Obraz kontenera ma kilka tagów i updater nie może bezpiecznie ustalić, którego użyć."

    def _compose_candidate(
        self,
        current_image: str,
        compose_image: str,
    ) -> UpdateCandidate | None:
        desired = str(compose_image or "").strip()
        if not desired or desired == current_image:
            return None
        if normalized_repository(desired) != normalized_repository(current_image):
            return None
        _repo, current_tag = image_reference(current_image)
        _repo, desired_tag = image_reference(desired)
        current_version = version_tuple(current_tag)
        desired_version = version_tuple(desired_tag)
        if current_version and desired_version and compare_versions(desired_version, current_version) > 0:
            return UpdateCandidate(True, desired, "plik Compose", f"Plik Compose wskazuje nowszy obraz {desired}.")
        return None

    def inspect_container(
        self,
        container: Any,
        apps: list[dict[str, Any]],
        catalog_error: str | None = None,
        all_containers: list[Any] | None = None,
    ) -> dict[str, Any]:
        attrs = container.attrs
        config = attrs.get("Config") or {}
        local_image = self._local_image(container)
        current, image_error = self._named_local_image(container, local_image)
        compose = self._is_compose(container)
        compose_project: ComposeProject | None = None
        compose_error: str | None = None
        if compose:
            compose_project, compose_error = self._load_compose_project(container)
            if compose_project:
                service_config = compose_project.config["services"][compose_project.service]
                compose_image = str(service_config.get("image") or "").strip()
                if image_error and compose_image:
                    current, image_error = compose_image, None
        result: dict[str, Any] = {
            "id": str(container.id),
            "name": str(getattr(container, "name", container.id)).lstrip("/"),
            "current_image": current,
            "target_image": current,
            "update_available": False,
            "supported": True,
            "auto_update_supported": not compose,
            "source": "",
            "status": str((attrs.get("State") or {}).get("Status") or getattr(container, "status", "unknown")),
            "message": "",
            "check_error": False,
            "is_panel": self._is_self(container),
            "is_compose": compose,
            "persistent_mounts": sorted({
                str(mount.get("Destination") or "")
                for mount in attrs.get("Mounts") or []
                if mount.get("Type") in {"volume", "bind"}
                and mount.get("Destination") and mount.get("Destination") != "/var/run/docker.sock"
            }),
            "has_update_instructions": bool(self._catalog_update_instructions(current, apps)) if current else False,
        }
        if self._is_self(container):
            result.update(supported=False, auto_update_supported=False, message="To jest panel aktualizujący; pominięto aktualizację samego panelu.")
            return result
        runtime_blocker = self._unsupported_reason(container)
        if not current:
            result.update(
                supported=False,
                auto_update_supported=False,
                message=runtime_blocker or image_error or "Kontener nie przechowuje nazwy obrazu, której można użyć do pobrania aktualizacji.",
            )
            return result

        candidate = self._catalog_candidate(current, apps)
        if compose and compose_project:
            service_config = compose_project.config["services"][compose_project.service]
            compose_image = str(service_config.get("image") or "").strip()
            file_candidate = self._compose_candidate(current, compose_image)
            if file_candidate and file_candidate.available:
                catalog_version = version_tuple(image_reference(candidate.target_image)[1]) if candidate and candidate.available else None
                file_version = version_tuple(image_reference(file_candidate.target_image)[1])
                if (
                    not (candidate and candidate.available)
                    or file_candidate.target_image == candidate.target_image
                    or (catalog_version and file_version and compare_versions(file_version, catalog_version) > 0)
                ):
                    candidate = file_candidate

        if candidate and candidate.available:
            blocker = runtime_blocker
            if compose:
                _project, compose_blocker = self._compose_update_blocker(container, candidate.target_image, all_containers)
                blocker = blocker or compose_blocker
            else:
                port_blocker = self._port_conflict_reason(container, candidate.update_instructions, all_containers)
                if port_blocker and not runtime_blocker:
                    result.update(
                        supported=False,
                        auto_update_supported=False,
                        source=candidate.source,
                        message=port_blocker,
                    )
                    return result
                blocker = blocker or port_blocker
            result.update(
                update_available=True,
                target_image=candidate.target_image,
                source=candidate.source,
                message=f"{candidate.message} {blocker}" if blocker else candidate.message,
                has_update_instructions=bool(candidate.update_instructions) and not compose,
                supported=not bool(blocker),
                auto_update_supported=not compose and not bool(blocker),
            )
            return result
        if candidate:
            result.update(source=candidate.source, message=candidate.message)
        available, digest_message = self._registry_digest(current, local_image)
        if available is True:
            target = current
            source = "digest rejestru"
            message = "Ten sam tag wskazuje w rejestrze nowszy obraz."
            if compose and compose_project:
                service_config = compose_project.config["services"][compose_project.service]
                file_image = str(service_config.get("image") or "").strip()
                file_candidate = self._compose_candidate(current, file_image)
                if file_candidate and file_candidate.available:
                    target, source, message = file_candidate.target_image, file_candidate.source, file_candidate.message
            if compose:
                _project, blocker = self._compose_update_blocker(container, target, all_containers)
            else:
                instructions = self._catalog_update_instructions(current, apps)
                blocker = self._port_conflict_reason(container, instructions, all_containers)
            blocker = runtime_blocker or blocker
            result.update(
                update_available=True,
                target_image=target,
                source=source,
                message=f"{message} {blocker}" if blocker else message,
                supported=not bool(blocker),
                auto_update_supported=not compose and not bool(blocker),
                check_error=bool(catalog_error),
            )
            if catalog_error:
                result["message"] = f"{result['message']} Nie udało się zweryfikować nowszego taga w katalogu DCC: {catalog_error}"
        elif available is False:
            blocker = runtime_blocker or compose_error
            if catalog_error:
                detail = "Nie można potwierdzić, czy aplikacja ma nowszy tag, ponieważ katalog DCC jest niedostępny."
                if blocker:
                    detail = f"{blocker} {detail}"
                result.update(
                    source=result["source"] or "digest rejestru",
                    message=f"{detail} Digest bieżącego taga nie wykazuje nowego obrazu. {catalog_error}",
                    supported=False,
                    auto_update_supported=False,
                    check_error=True,
                )
                return result
            result.update(
                source=result["source"] or "digest rejestru",
                message=blocker or "Obraz jest aktualny.",
                supported=not bool(blocker),
                auto_update_supported=not compose and not bool(blocker),
            )
        else:
            blocker = runtime_blocker or compose_error
            result.update(
                source=result["source"] or "rejestr",
                message=" ".join(value for value in (blocker, catalog_error or digest_message) if value),
                supported=not bool(blocker or catalog_error),
                auto_update_supported=not compose and not bool(blocker or catalog_error),
                check_error=True,
            )
        return result

    def inventory(self) -> list[dict[str, Any]]:
        """List local containers without loading the catalog or contacting registries."""
        results = []
        for container in self.client.containers.list(all=True, ignore_removed=True):
            if self._is_self_update_helper(container):
                continue
            attrs = container.attrs
            image = str((attrs.get("Config") or {}).get("Image") or "")
            panel = self._is_self(container)
            results.append({
                "id": str(container.id),
                "name": str(getattr(container, "name", container.id)).lstrip("/"),
                "current_image": image,
                "target_image": "",
                "status": str((attrs.get("State") or {}).get("Status") or getattr(container, "status", "unknown")),
                "is_panel": panel,
                "is_compose": self._is_compose(container),
                "supported": False,
                "auto_update_supported": False,
                "update_available": False,
                "check_error": False,
                "scan_pending": not panel,
                "checked_at": None,
                "message": "To jest panel aktualizujący; pominięto aktualizację samego panelu." if panel
                           else "Nie sprawdzono jeszcze aktualizacji tego kontenera.",
            })
        return results

    def scan(
        self, progress: Callable[[str], None] | None = None, *, container_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self._compose_cache.clear()
        self._registry_cache.clear()
        containers = [
            container for container in self.client.containers.list(all=True, ignore_removed=True)
            if not self._is_self_update_helper(container)
        ]
        # Keep all local metadata for dependency/port checks, but inspect remote
        # images only for the explicitly requested, exact container IDs.
        by_id = {str(container.id): container for container in containers}
        selected_ids = list(dict.fromkeys(container_ids)) if container_ids is not None else list(by_id)
        if not selected_ids:
            return []
        apps, catalog_error = self._catalog() if any(value in by_id for value in selected_ids) else ([], None)
        results = []
        for index, container_id in enumerate(selected_ids, start=1):
            container = by_id.get(container_id)
            if container is None:
                results.append({
                    "id": container_id, "name": container_id, "status": "error",
                    "supported": False, "auto_update_supported": False, "update_available": False,
                    "check_error": True, "missing": True, "scan_pending": False, "checked_at": time.time(),
                    "message": "Kontener nie jest już dostępny. Odśwież skan.",
                })
                continue
            if progress:
                progress(f"Sprawdzanie kontenera {index}/{len(selected_ids)}: {getattr(container, 'name', container.id)}")
            try:
                item = self.inspect_container(container, apps, catalog_error, containers)
                reason = self.automatic_dependency_blocker(container, containers)
                if reason:
                    item.update(auto_update_supported=False, auto_update_reason=reason)
                results.append(item)
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
                    "check_error": True,
                    "auto_update_supported": False,
                })
            results[-1].update(checked_at=time.time(), scan_pending=False)
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
        healthcheck = (container.attrs.get("Config") or {}).get("Healthcheck") or {}
        has_healthcheck = bool(healthcheck and healthcheck.get("Test") != ["NONE"])
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

    def _pull_image_with_retry(self, image: str, *, platform: str | None = None) -> None:
        for attempt in range(len(REGISTRY_RETRY_DELAYS) + 1):
            try:
                auth = self.registry_auth_loader(image) if self.registry_auth_loader else None
                options = {'auth_config':auth} if auth else {}
                if platform:
                    options['platform'] = platform
                self.client.images.pull(image, **options)
                return
            except Exception as exc:
                if attempt < len(REGISTRY_RETRY_DELAYS) and _is_transient_registry_error(exc):
                    time.sleep(REGISTRY_RETRY_DELAYS[attempt])
                    continue
                raise RuntimeError(friendly_registry_error(exc, f"Pobieranie obrazu {image}")) from exc

    @staticmethod
    def _compose_base_args(project: ComposeProject, extra_files: tuple[Path, ...] = ()) -> list[str]:
        args = [
            os.environ.get("DCC_UPDATER_COMPOSE_BIN", "docker-compose"),
            "--project-name", project.project,
            "--project-directory", str(project.working_dir),
        ]
        for path in (*project.config_files, *extra_files):
            args.extend(("--file", str(path)))
        return args

    def _compose_command(
        self,
        project: ComposeProject,
        arguments: list[str],
        timeout: int,
    ) -> tuple[int, str]:
        try:
            completed = subprocess.run(
                self._compose_base_args(project) + arguments,
                cwd=str(project.working_dir),
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("W obrazie updatera brakuje Docker Compose CLI. Zainstaluj nowszy obraz updatera.") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Docker Compose przekroczył limit czasu. Pliku Compose ani wolumenów nie usunięto.") from exc
        except OSError as exc:
            raise RuntimeError(f"Nie można uruchomić Docker Compose ({type(exc).__name__}).") from exc
        output = "\n".join(part for part in (completed.stderr, completed.stdout) if part).strip()
        return completed.returncode, output

    def _compose_pull(self, project: ComposeProject) -> None:
        model = (project.config.get('services') or {}).get(project.service) or {}
        image = str(model.get('image') or '')
        if image and self.registry_auth_loader and self.registry_auth_loader(image):
            self._pull_image_with_retry(image, platform=str(model.get('platform') or '') or None)
            return
        for attempt in range(len(REGISTRY_RETRY_DELAYS) + 1):
            try:
                code, output = self._compose_command(project, ["pull", project.service], COMPOSE_PULL_TIMEOUT)
            except Exception as exc:
                output = str(exc)
                if attempt < len(REGISTRY_RETRY_DELAYS) and _is_transient_registry_error(output):
                    time.sleep(REGISTRY_RETRY_DELAYS[attempt])
                    continue
                raise RuntimeError(output) from exc
            if code == 0:
                return
            if attempt < len(REGISTRY_RETRY_DELAYS) and _is_transient_registry_error(output):
                time.sleep(REGISTRY_RETRY_DELAYS[attempt])
                continue
            raise RuntimeError(friendly_registry_error(output or f"kod wyjścia {code}", "Pobieranie obrazu przez Compose"))

    def _update_compose(
        self,
        container: Any,
        target_image: str,
        all_containers: list[Any] | None,
    ) -> str:
        project, blocker = self._compose_update_blocker(container, target_image, all_containers)
        if blocker or project is None:
            raise RuntimeError(blocker or "Nie udało się odczytać projektu Compose.")

        local_image = self._local_image(container)
        if local_image is None:
            raise RuntimeError("Nie znaleziono lokalnego obrazu; nie można przygotować kopii do wycofania zmiany.")
        rollback_suffix = f"{str(container.id)[:12]}-{int(time.time())}"
        rollback_tag = f"dcc-updater-rollback:{rollback_suffix}"
        if not local_image.tag("dcc-updater-rollback", tag=rollback_suffix):
            raise RuntimeError("Nie udało się zachować lokalnego obrazu do bezpiecznego wycofania aktualizacji.")

        try:
            self._compose_pull(project)
        except Exception:
            try:
                self.client.images.remove(rollback_tag)
            except Exception:
                pass
            raise

        arguments = [
            "up", "--detach", "--no-deps", "--no-build", "--pull", "never",
            "--wait", "--wait-timeout", str(self.wait_seconds), project.service,
        ]
        try:
            code, output = self._compose_command(project, arguments, self.wait_seconds + 60)
        except Exception as exc:
            code, output = 1, str(exc)
        if code == 0:
            try:
                self.client.images.remove(rollback_tag)
            except Exception:
                pass
            return (
                f"Zaktualizowano usługę Compose do {target_image}; użyto wyłącznie tej usługi "
                "(--no-deps), zależności i wolumeny projektu pozostawiono bez zmian."
            )

        with tempfile.TemporaryDirectory(prefix="dcc-updater-rollback-") as temp_dir:
            override_path = Path(temp_dir) / "rollback.json"
            override_path.write_text(
                json.dumps({"services": {project.service: {"image": rollback_tag}}}),
                encoding="utf-8",
            )
            rollback_args = self._compose_base_args(project, (override_path,)) + [
                "up", "--detach", "--no-deps", "--no-build", "--pull", "never",
                "--wait", "--wait-timeout", str(self.wait_seconds), project.service,
            ]
            try:
                restored = subprocess.run(
                    rollback_args,
                    cwd=str(project.working_dir),
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self.wait_seconds + 60,
                )
                restored_ok = restored.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                restored_ok = False

        if not restored_ok:
            raise RuntimeError(
                "Nowy kontener Compose nie przeszedł kontroli, a automatyczne przywrócenie nie powiodło się. "
                f"Poprzedni obraz zachowano lokalnie jako {rollback_tag}; sprawdź projekt Compose."
            )
        try:
            self.client.images.remove(rollback_tag)
        except Exception:
            pass
        detail = output.replace("\r", " ").replace("\n", " ")[:220]
        raise RuntimeError(
            "Compose zgłosił problem po podmianie usługi; przywrócono poprzedni obraz. "
            + (f"Szczegóły: {detail}" if detail else "Sprawdź logi usługi.")
        )

    def update_one(
        self,
        container: Any,
        target_image: str,
        update_instructions: dict[str, Any] | None = None,
        *,
        _allow_self: bool = False,
        _image_already_pulled: bool = False,
        _expected_image_id: str | None = None,
    ) -> str:
        if self._is_self(container) and not _allow_self:
            raise RuntimeError("Aktualizacja samego panelu nie jest obsługiwana.")
        if self._is_compose(container):
            raise RuntimeError("Usługi Compose należy aktualizować przez kontrolowany tryb Compose.")
        reason = self._unsupported_reason(container)
        if reason:
            raise RuntimeError(reason)

        # Validate and build the replacement config while the original is still running.
        raw_config = self._create_config(container, target_image, update_instructions)
        # Pull first: a registry or network failure leaves the running service untouched.
        if not _image_already_pulled:
            self._pull_image_with_retry(target_image)
        original_name = str(getattr(container, "name", "")).lstrip("/")
        was_running = str((container.attrs.get("State") or {}).get("Status")) == "running"
        existing_names = {
            str(getattr(item, "name", "")).lstrip("/")
            for item in self.client.containers.list(all=True, ignore_removed=True)
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
            if _expected_image_id and str(replacement.attrs.get("Image") or "") != _expected_image_id:
                raise RuntimeError("Nowy kontener nie używa przypiętego obrazu aktualizacji; wycofano podmianę.")
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
        *, automatic: bool = False,
    ) -> list[dict[str, Any]]:
        self._compose_cache.clear()
        self._registry_cache.clear()
        apps, catalog_error = self._catalog()
        output = []
        for index, container_id in enumerate(container_ids, start=1):
            display_name = str(container_id)[:12]
            try:
                container = self.client.containers.get(container_id)
                display_name = str(getattr(container, "name", display_name)).lstrip("/")
                all_containers = self.client.containers.list(all=True, ignore_removed=True)
                current = self.inspect_container(container, apps, catalog_error, all_containers)
                display_name = current["name"]
                if automatic:
                    blocker = ("Automatyczna aktualizacja Compose jest wyłączona. Usługi Compose aktualizuj ręcznie po sprawdzeniu zależności i konfiguracji."
                               if self._is_compose(container) else self.automatic_dependency_blocker(container, all_containers))
                    if blocker:
                        output.append({"name": display_name, "ok": False, "result": blocker})
                        continue
                if not current["supported"] or not current["update_available"]:
                    output.append({
                        "name": current["name"],
                        "result": current["message"] or "Brak dostępnej aktualizacji.",
                        "ok": False,
                    })
                    continue
                if progress:
                    progress(f"Aktualizowanie {index}/{len(container_ids)}: {current['name']}")
                if self._is_compose(container):
                    message = self._update_compose(container, current["target_image"], all_containers)
                else:
                    instructions = self._catalog_update_instructions(current["current_image"], apps)
                    message = self.update_one(container, current["target_image"], instructions)
                output.append({"name": current["name"], "result": message, "ok": True})
            except Exception as exc:
                output.append({"name": display_name, "result": str(exc), "ok": False})
        return output
