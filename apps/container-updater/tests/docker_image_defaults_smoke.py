"""Exercise image-default migration and named-volume retention against Docker."""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import docker
from docker.errors import NotFound

from updater import UpdateService


def _build_image(root: Path, tag: str, filename: str, command: list[str]) -> None:
    context = root / tag.rsplit(":", 1)[-1]
    (context / "app" / "ops").mkdir(parents=True)
    (context / "Dockerfile").write_text(
        "FROM alpine:3.21\n"
        "RUN mkdir -p /app/ops /data\n"
        f"COPY app/ops/{filename} /app/ops/{filename}\n"
        "VOLUME [\"/data\"]\n"
        f"CMD {json.dumps(command)}\n",
        encoding="utf-8",
    )
    marker = "old" if "public" in filename else "new"
    volume_check = (
        "if [ ! -f /data/preserved.txt ]; then printf 'user-data\\n' > /data/preserved.txt; fi\n"
        if marker == "old"
        else "test -f /data/preserved.txt && test \"$(cat /data/preserved.txt)\" = user-data\n"
    )
    script = (
        "#!/bin/sh\n"
        "set -eu\n"
        + volume_check
        + f"printf '{marker}-image-started\\n' > /data/started.txt\n"
        + "exec sleep 300\n"
    )
    (context / "app" / "ops" / filename).write_text(script, encoding="utf-8")
    subprocess.run(
        ["docker", "build", "--quiet", "--tag", tag, str(context)],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )


def main() -> None:
    suffix = uuid.uuid4().hex[:12]
    old_tag = f"dcc-updater-defaults:{suffix}-old"
    target_tag = f"dcc-updater-defaults:{suffix}-new"
    container_name = f"dcc-updater-defaults-{suffix}"
    volume_name = f"dcc-updater-data-{suffix}"
    client = docker.from_env()
    try:
        with tempfile.TemporaryDirectory(prefix="dcc-updater-defaults-") as temp:
            root = Path(temp)
            _build_image(
                root,
                old_tag,
                "public-start.sh",
                ["sh", "/app/ops/public-start.sh"],
            )
            _build_image(
                root,
                target_tag,
                "start.sh",
                ["sh", "/app/ops/start.sh"],
            )

        client.volumes.create(name=volume_name)
        old = client.containers.create(
            old_tag,
            name=container_name,
            detach=True,
            volumes={volume_name: {"bind": "/data", "mode": "rw"}},
            restart_policy={"Name": "unless-stopped"},
        )
        old.start()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            old.reload()
            if old.status != "running":
                raise RuntimeError(f"Old smoke container stopped: {old.status}; {old.logs(tail=20)!r}")
            code, output = old.exec_run(["sh", "-c", "test -f /data/preserved.txt"])
            if code == 0:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("Old smoke container did not initialize its data volume")

        result = UpdateService(client, wait_seconds=15).update_one(
            old,
            target_tag,
            _image_already_pulled=True,
        )
        if "Zaktualizowano" not in result:
            raise RuntimeError(f"Unexpected updater result: {result}")

        replacement = client.containers.get(container_name)
        replacement.reload()
        if replacement.status != "running":
            raise RuntimeError(f"Replacement is not running: {replacement.status}; {replacement.logs(tail=20)!r}")
        code, output = replacement.exec_run(
            ["sh", "-c", "test \"$(cat /data/preserved.txt)\" = user-data && cat /data/started.txt"]
        )
        if code != 0 or output.decode("utf-8", errors="replace").strip() != "new-image-started":
            raise RuntimeError(f"Replacement did not use target defaults or lost volume data: {output!r}")
        mounts = replacement.attrs.get("Mounts") or []
        data_mount = next((mount for mount in mounts if mount.get("Destination") == "/data"), None)
        if not data_mount or data_mount.get("Name") != volume_name:
            raise RuntimeError("The original named data volume is not attached to the replacement")
        print("Image-default update started the replacement and retained the original named data volume.")
    finally:
        try:
            client.containers.get(container_name).remove(force=True, v=False)
        except NotFound:
            pass
        try:
            client.volumes.get(volume_name).remove(force=True)
        except NotFound:
            pass
        for tag in (old_tag, target_tag):
            try:
                client.images.remove(tag, force=True)
            except NotFound:
                pass
        client.close()


if __name__ == "__main__":
    main()
