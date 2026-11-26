"""Run only on an isolated CI runner. Each invocation owns a new panel and volume."""
import argparse
import json
import os
import subprocess
import time
from urllib.error import HTTPError
from uuid import uuid4

from backend.config import VERSION
from image_smoke import PanelHTTP, wait_ready


def verify(args):
    name = "dcc-kiri-ci-" + uuid4().hex[:12]
    volume = name + "-data"
    if args.runtime == "kiri":
        cmd = ["sudo", "-n", "docker", "--host", "unix://" + args.socket]
    else:
        cmd = ["docker", "--context", args.docker_context]

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
    username = "ci-panel-operator"
    original_preferences = {"language": "pl", "theme": "light"}
    try:
        docker("volume", "create", "--label", "dev.dcc.kiri-ci=" + name, volume)
        volume_created = True
        if args.previous_image:
            created = docker("create", *params, args.previous_image)
            docker("start", created)
            wait_ready(client, seconds=20)
            evidence = client.setup(username)
            assert evidence["version"] == args.previous_version
            client.request("/api/preferences", original_preferences, "PUT")
            docker("stop", created)
            docker("rm", created)
            created = None
            client = PanelHTTP(client.url)
        created = docker("create", *params, args.image)
        started = time.monotonic()
        docker("start", created)
        wait_ready(client, seconds=20)
        print(f"Readiness {time.monotonic() - started:.3f} s ({args.runtime})")
        assert docker("exec", created, "python", "-c", "import os; print(os.geteuid())") == "10001"
        if args.previous_image:
            assert not client.get("/api/session")["setup_available"]
            evidence = client.login(username)
            assert all(evidence["preferences"][key] == value for key, value in original_preferences.items())
            print(f"Upgrade {args.previous_version} -> {VERSION}: account and preferences preserved")
        else:
            assert "admin / admin" in docker("logs", created, stderr=subprocess.STDOUT)
            evidence = client.setup(username)
        assert not evidence["demo"] and evidence["version"] == VERSION
        assert evidence["endpoints"] == (["test"] if args.socket else [])
        client.request("/api/preferences", original_preferences, "PUT")
        profile = None
        if args.socket:
            configured = {"name": "CI Kiri", "host": "linux", "runtime": args.runtime, "endpoint": "test"}
            try:
                connection = client.request("/api/profiles/test", configured)
            except HTTPError as error:
                with error:
                    detail = error.read(1024).decode("utf-8", errors="replace")
                raise AssertionError(f"{args.runtime} profile test returned HTTP {error.code}: {detail}") from None
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

            # Separate disposable resource on the isolated Kiri CI runner.
            # The shared Compose fixture remains untouched.
            engine_cmd = ["sudo", "-n", "docker", "--host", "unix://" + args.socket]
            def engine(*parts):
                return subprocess.run([*engine_cmd, *parts], check=True, text=True,
                                      stdout=subprocess.PIPE).stdout.strip()

            action_name = name + "-action"
            action_volume = action_name + "-data"
            action_id = None
            engine("volume", "create", "--label", "dev.dcc.kiri-ci=" + name, action_volume)
            try:
                action_id = engine("create", "--name", action_name, "--label", "dev.dcc.kiri-ci=" + name,
                                   "--mount", f"type=volume,src={action_volume},dst=/fixture",
                                   "alpine:3.22", "sleep", "300")
                assert len(action_id) == 64
                route = f"{endpoint}/containers/{action_id}/action"
                for action, state in (("start", "running"), ("pause", "paused"),
                                      ("unpause", "running"), ("restart", "running"),
                                      ("stop", "exited"), ("remove", None)):
                    result = client.request(route, {"action": action, "revision": profile["revision"],
                                                    "confirmation": action_name if action == "remove" else action_id})
                    assert result["ok"]
                    if state:
                        assert engine("inspect", "--format", "{{.State.Status}}", action_id) == state
                    else:
                        assert action_id not in engine("ps", "-aq", "--no-trunc").splitlines()
                        action_id = None
                assert engine("volume", "inspect", "--format", "{{.Name}}", action_volume) == action_volume
                print("Kiri lifecycle: all six actions and volume retention verified")
            finally:
                if action_id:
                    # The API could have applied removal before a response failed.
                    if action_id in engine("ps", "-aq", "--no-trunc").splitlines():
                        engine("rm", "-f", action_id)
                engine("volume", "rm", action_volume)

        docker("restart", created)
        wait_ready(client)
        evidence = client.login(username)
        assert evidence["preferences"]["language"] == "pl" and evidence["preferences"]["theme"] == "light"
        if profile:
            assert evidence["preferences"]["active"] == profile["id"]
            assert client.get(endpoint + "/status")["engine"]["version"] == args.version
        reset_password = "isolated-cli-reset-test-only"
        docker("exec", "-i", created, "python", "-m", "backend.admin", "--reset", "--password-stdin",
               input=reset_password + "\n")
        assert not client.get("/api/session")["authenticated"]
        assert client.login(username, reset_password)["preferences"]["theme"] == "light"
        if args.runtime == "docker":
            sample = json.loads(docker("stats", "--no-stream", "--format", "{{json .}}", created))
            print(json.dumps({key: sample.get(key) for key in ("CPUPerc", "MemUsage", "PIDs")}))
        if args.previous_image:
            client.request("/api/preferences", {"language": "en", "theme": "dark"}, "PUT")
            docker("stop", created)
            docker("rm", created)
            created = None
            # Downgrade requires restoring the pre-migration schema 2 backup.
            # This helper touches only the uniquely owned CI test volume.
            restore = """from pathlib import Path
import os, sqlite3
root = Path('/data')
backups = list(root.glob('config-v2-*.sqlite3'))
assert len(backups) == 1
with sqlite3.connect(backups[0]) as src:
    assert src.execute('PRAGMA user_version').fetchone()[0] == 2
    assert src.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    with sqlite3.connect(root / 'rollback.tmp') as dst:
        src.backup(dst)
os.chmod(root / 'rollback.tmp', 0o600)
for suffix in ('-wal', '-shm', '-journal'):
    (root / ('config.sqlite3' + suffix)).unlink(missing_ok=True)
os.replace(root / 'rollback.tmp', root / 'config.sqlite3')
"""
            docker("run", "--rm", "--network", "none", "--user", "10001:10001",
                   "--mount", f"type=volume,src={volume},dst=/data", "--entrypoint", "python",
                   args.image, "-c", restore)
            created = docker("create", *params, args.previous_image)
            docker("start", created)
            client = PanelHTTP(client.url)
            wait_ready(client, seconds=20)
            assert not client.get("/api/session")["setup_available"]
            evidence = client.login(username)
            assert evidence["version"] == args.previous_version
            assert all(evidence["preferences"][key] == value for key, value in original_preferences.items())
            print(f"Rollback {VERSION} -> {args.previous_version}: pre-migration account and preferences restored")
    finally:
        if created:
            docker("rm", "-f", created)
        if volume_created:
            docker("volume", "rm", volume)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--previous-image")
    parser.add_argument("--previous-version")
    parser.add_argument("--docker-context", default="default")
    parser.add_argument("--runtime", choices=["docker", "kiri"], default="docker")
    parser.add_argument("--socket")
    parser.add_argument("--version", default="0.2.2")
    parser.add_argument("--port", type=int, default=28796)
    args = parser.parse_args()
    if args.runtime == "kiri" and args.socket != "/run/kiri/docker.sock":
        parser.error("Kiri CI requires the dedicated native Linux socket")
    if bool(args.previous_image) != bool(args.previous_version):
        parser.error("Use --previous-image and --previous-version together")
    verify(args)
