"""One-shot helper that replaces the running updater through the Docker socket."""

from __future__ import annotations

import sys

import docker

from updater import UpdateService


def main(arguments: list[str]) -> int:
    if len(arguments) != 2:
        print("Użycie: self_update.py <container-id> <image-id>", file=sys.stderr, flush=True)
        return 2
    try:
        client = docker.from_env(timeout=180)
        service = UpdateService(client)
        result = service.replace_self_from_helper(arguments[0], arguments[1])
    except Exception as exc:
        print(f"Aktualizacja panelu nie powiodła się: {exc}", file=sys.stderr, flush=True)
        return 1
    print(result, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
