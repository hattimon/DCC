"""Discover only administrator-provisioned endpoints; never probe browser paths."""

from . import resources
from .kiri_client import KiriError


def discover(connector):
    """A configured socket is usable only after Kiri identity and inventory pass."""
    if not connector.sockets:
        return {"status": "unconfigured", "reason": "transport_not_configured"}

    errors = []
    for alias in sorted(connector.sockets):
        try:
            with connector.connect(alias) as kiri:
                # Identifying /version alone does not establish resource access.
                containers = kiri.read("containers")
                resources.rows(containers)
                return {"status": "ready", "endpoint": alias, "engine": kiri.identity}
        except KiriError as error:
            errors.append(error.code)

    priority = ("permission_denied", "bad_engine", "api_version", "socket_invalid",
                "socket_changed", "timeout", "disconnected", "socket_missing")
    reason = next((error for error in priority if error in errors), errors[0] if errors else "disconnected")
    return {"status": "blocked", "reason": reason}
