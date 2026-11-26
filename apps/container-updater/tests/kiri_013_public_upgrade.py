"""Verify the public 0.1.2 to 0.1.3 upgrade on a disposable runner."""
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

import docker
from docker.errors import NotFound

from image_smoke import PanelHTTP, wait_ready
from updater import DCC_CATALOG_URL, UpdateService, load_catalog


REPO = "ghcr.io/hattimon/dcc-kiri-manager"
OLD = REPO + ":0.1.2"
TARGET = REPO + ":0.1.3"
OLD_DIGEST = "sha256:37404038b896cb9f9ac3a04e2b7b46c37246d6fdb79d38693717e8bffd0faf47"
INDEX = "sha256:02268eb6f8d30bed7bc43529c1bdf4dece978dd2cf42f02629097f052d76757a"
MANIFESTS = {
    "amd64": "sha256:4fdd4add681e6272893ac26ddb4e7bca3a13ff9331546521f86a54ce6941eb12",
    "arm64": "sha256:953586b7e2fe5fcd79175799d7c13e998e0119b1603f7d87cb6d2d1c91ca54bd",
}
NAME = "dcc-kiri-manager"
URL = "http://127.0.0.1:18796"
USER = "ci-panel-operator"
PREFS = {"language": "pl", "theme": "light"}
SOCKETS = '{"offline":"/run/dcc-kiri/fixture.sock"}'


def wait_public_catalog():
    for _ in range(60):
        apps = load_catalog()
        entry = next(app for app in apps if app["name"] == "DCC Kiri Manager")
        if entry["image"] == TARGET:
            assert entry["version"] == "0.1.3" and entry["latest_release"] == "kiri-manager-v0.1.3"
            print(f"Public catalog {DCC_CATALOG_URL} advertises {TARGET}")
            return
        time.sleep(5)
    raise AssertionError("Public catalog did not advertise 0.1.3 before timeout")


def assert_data_mount(container, volume):
    container.reload()
    matches = [mount for mount in container.attrs["Mounts"] if mount["Destination"] == "/data"]
    assert len(matches) == 1 and matches[0]["Name"] == volume and matches[0]["RW"]


def assert_saved_ssh(panel, container):
    with tempfile.TemporaryDirectory() as raw_dir:
        key = Path(raw_dir) / "host_key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        public_key = " ".join(key.with_suffix(".pub").read_text().split()[:2])
    # Only used to test the vault. Real SSH connections are tested by the release workflow.
    password = secrets.token_hex(24)
    profile = panel.request("/api/profiles", {
        "name": "Disposable SSH profile", "host": "linux", "runtime": "docker", "endpoint": "",
        "transport": "ssh", "ssh_cli": "docker", "ssh_host": "127.0.0.1",
        "ssh_port": 22222, "ssh_username": "testuser",
        "ssh_known_hosts": "[127.0.0.1]:22222 " + public_key, "credentials": {"password": password},
    })
    container.restart()
    panel = PanelHTTP(URL)
    wait_ready(panel, seconds=30)
    saved = next(row for row in panel.login(USER)["profiles"] if row["id"] == profile["id"])
    assert saved["transport"] == "ssh" and saved["has_credentials"]
    assert "credentials" not in saved and saved["ssh_known_hosts"].endswith(public_key)
    check = container.exec_run(["python", "-c", """
import sys
from backend.storage import Storage

store = Storage('/data')
profile_id, expected = sys.argv[1:]
with store.connect() as db:
    encrypted = db.execute('SELECT credentials FROM profiles WHERE id = ?', (profile_id,)).fetchone()[0]
assert expected.encode() not in encrypted
assert store.connection_profile(profile_id)['credentials']['password'] == expected
""", profile["id"], password])
    assert check.exit_code == 0, "SSH credential could not be recovered from the original encrypted volume"


def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true"
    assert os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
    wait_public_catalog()
    client = docker.from_env()
    volume = client.volumes.create(name="kiri-upgrade-ci-" + secrets.token_hex(8)).name
    try:
        client.images.pull(REPO + "@" + OLD_DIGEST).tag(REPO, tag="0.1.2")
        old = client.containers.run(
            OLD, name=NAME, detach=True,
            environment={"KIRI_SOCKETS": SOCKETS},
            ports={"8796/tcp": ("127.0.0.1", 18796)},
            volumes={volume: {"bind": "/data", "mode": "rw"}},
            restart_policy={"Name": "unless-stopped"},
            read_only=True, tmpfs={"/tmp": "size=8m,mode=1777"},
            cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
        )
        panel = PanelHTTP(URL)
        wait_ready(panel, seconds=30)
        assert panel.setup(USER)["version"] == "0.1.2"
        panel.request("/api/preferences", PREFS, "PUT")
        legacy = panel.request("/api/profiles", {
            "name": "Previous Kiri profile", "host": "linux", "runtime": "docker", "endpoint": "offline",
        })
        panel.request(f"/api/profiles/{legacy['id']}/active", {}, "PUT")
        assert_data_mount(old, volume)

        service = UpdateService(client, wait_seconds=45)
        candidate, = service.scan(container_ids=[old.id])
        assert candidate["update_available"] and candidate["supported"], candidate
        assert candidate["source"] == "katalog DCC" and candidate["target_image"] == TARGET, candidate
        print(f"DCC Updater scan selected {candidate['target_image']} from the public catalog")
        try:
            client.images.get(TARGET)
        except NotFound:
            pass
        else:
            raise AssertionError("Target must be absent locally before Updater pulls it")

        result, = service.update_selected([old.id])
        assert result["ok"], result
        current = client.containers.get(NAME)
        assert current.id != old.id and current.attrs["Config"]["Image"] == TARGET
        arch = os.environ["IMAGE_ARCH"]
        assert current.image.attrs["Architecture"] == arch
        expected_refs = {REPO + "@" + digest for digest in (INDEX, MANIFESTS[arch])}
        assert expected_refs.intersection(current.image.attrs.get("RepoDigests") or [])
        assert_data_mount(current, volume)
        config = current.attrs["HostConfig"]
        assert config["ReadonlyRootfs"] and config["RestartPolicy"]["Name"] == "unless-stopped"
        assert config["PortBindings"]["8796/tcp"] == [{"HostIp": "127.0.0.1", "HostPort": "18796"}]
        assert "KIRI_SOCKETS=" + SOCKETS in current.attrs["Config"]["Env"]
        panel = PanelHTTP(URL)
        wait_ready(panel, seconds=30)
        state = panel.login(USER)
        assert state["version"] == "0.1.3"
        assert all(state["preferences"][key] == value for key, value in PREFS.items())
        assert state["preferences"]["active"] == legacy["id"]
        migrated = next(row for row in state["profiles"] if row["id"] == legacy["id"])
        assert migrated["transport"] == "socket" and migrated["endpoint"] == legacy["endpoint"]
        print(f"Updater pulled the verified {arch} image and preserved the volume, settings, login and active profile")
        assert_saved_ssh(panel, current)
        latest, = service.scan(container_ids=[current.id])
        assert not latest["update_available"] and not latest.get("check_error"), latest
        print("Encrypted SSH profile survived restart; Updater reports no pending 0.1.3 update")
    finally:
        try:
            client.containers.get(NAME).remove(force=True, v=False)
        except NotFound:
            pass
        client.volumes.get(volume).remove()
        client.close()


if __name__ == "__main__":
    main()
