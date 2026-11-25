"""Run only on an isolated CI runner. Each invocation owns a new panel and volume."""
import argparse
import json
import os
import subprocess
import time
from uuid import uuid4

from image_smoke import PASSWORD, PanelHTTP, wait_ready


def verify(args):
    name = "dcc-kiri-ci-" + uuid4().hex[:12]
    volume = name + "-data"
    if args.runtime == "kiri":
        cmd = ["sudo", "-n", "docker", "--host", "unix://" + args.socket]
    else:
        cmd = ["docker", "--context", "default"]

    def docker(*arguments, **options):
        return subprocess.run([*cmd, *arguments], check=True, text=True, stdout=subprocess.PIPE, **options).stdout.strip()

    params = ["--name", name, "--label", "dev.dcc.kiri-ci=" + name,
              "--publish", f"127.0.0.1:{args.port}:8796",
              "--cap-drop=ALL", "--security-opt=no-new-privileges:true", "--read-only",
              "--tmpfs", "/tmp:size=8m,mode=1777", "--restart", "unless-stopped",
              "--mount", f"type=volume,src={volume},dst=/data"]
    if args.socket:
        params += ["--mount", f"type=bind,src={args.socket},dst=/run/dcc-kiri/engine.sock,readonly",
                   "--group-add", str(os.stat(args.socket).st_gid),
                   "--env", 'KIRI_SOCKETS={"test":"/run/dcc-kiri/engine.sock"}']
    created = None
    volume_created = False
    client = PanelHTTP(f"http://127.0.0.1:{args.port}")
    try:
        docker("volume", "create", "--label", "dev.dcc.kiri-ci=" + name, volume)
        volume_created = True
        created = docker("create", *params, args.image)
        started = time.monotonic()
        docker("start", created)
        wait_ready(client, seconds=20)
        print(f"Readiness {time.monotonic() - started:.3f} s ({args.runtime})")
        assert docker("exec", created, "python", "-c", "import os; print(os.geteuid())") == "10001"
        docker("exec", "-i", created, "python", "-m", "backend.admin", "--password-stdin", input=PASSWORD + "\n")
        evidence = client.login()
        assert not evidence["demo"] and evidence["version"] == "0.1.0"
        assert evidence["endpoints"] == (["test"] if args.socket else [])
        client.request("/api/preferences", {"language": "pl", "theme": "light"}, "PUT")
        profile = None
        if args.socket:
            configured = {"name": "CI Kiri", "host": "linux", "runtime": args.runtime, "endpoint": "test"}
            connection = client.request("/api/profiles/test", configured)
            assert connection["engine"]["version"] == args.version
            assert set(connection["checks"].values()) == {"available"}
            profile = client.request("/api/profiles", configured)
            endpoint = f"/api/profiles/{profile['id']}"
            snapshot = client.get(endpoint + "/snapshot")
            assert snapshot["counts"]["compose"] > 0
            assert all(snapshot["counts"][key] > 0 for key in ("images", "volumes", "networks", "containers"))
            fixture = next(p for p in snapshot["values"]["compose"] if p["name"] == "dcc-kiri-fixture")
            container = fixture["services"][0]["containers"][0]
            cid = container["id"]
            assert container["state"] == "running"
            assert client.get(f"{endpoint}/inventory/containers/{cid}")["item"]["id"] == cid
            assert "kiri-integration-fixture" in client.get(f"{endpoint}/containers/{cid}/logs?tail=25")["text"]
            assert client.get(f"{endpoint}/containers/{cid}/stats")["memory_bytes"] is not None

        docker("restart", created)
        wait_ready(client)
        evidence = client.login()
        assert evidence["preferences"]["language"] == "pl" and evidence["preferences"]["theme"] == "light"
        if profile:
            assert evidence["preferences"]["active"] == profile["id"]
            assert client.get(endpoint + "/status")["engine"]["version"] == args.version
        if args.runtime == "docker":
            sample = json.loads(docker("stats", "--no-stream", "--format", "{{json .}}", created))
            print(json.dumps({key: sample.get(key) for key in ("CPUPerc", "MemUsage", "PIDs")}))
    finally:
        if created:
            docker("rm", "-f", created)
        if volume_created:
            docker("volume", "rm", volume)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--runtime", choices=["docker", "kiri"], default="docker")
    parser.add_argument("--socket")
    parser.add_argument("--version", default="0.2.2")
    parser.add_argument("--port", type=int, default=28796)
    args = parser.parse_args()
    if args.runtime == "kiri" and args.socket != "/run/kiri/docker.sock":
        parser.error("Kiri CI requires the dedicated native Linux socket")
    verify(args)
