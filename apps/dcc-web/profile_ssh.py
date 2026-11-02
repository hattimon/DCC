"""Explicit, administrator-managed SSH files; never read browser-host paths."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import threading

import paramiko

SETTINGS_ID = "__dcc_profile_ssh__"
WORKSPACE_ACTIONS = {"profiles.ssh.directory", "profiles.ssh.files", "profiles.ssh.apply", "profiles.remove.selected"}
MAX_FILE = 128 * 1024
MAX_TOTAL = 1024 * 1024


def key_name(value):
    """Only explicit bulk migration extracts basenames from Windows paths."""
    return str(value or "").replace("\\", "/").rsplit("/", 1)[-1]


def safe_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", value):
        raise ValueError("Use a simple SSH filename without directories")
    # Windows device names, alternate streams, dot names and trailing dots are disallowed on all OSes.
    if value.endswith(".") or value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        raise ValueError("Use a simple SSH filename without directories")
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def reject_symlinks(path):
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError("SSH paths must not contain symbolic links")


def configure_client(client, profile):
    """Shared identity and strict host verification for CLI, SDK and host PTYs."""
    client.load_system_host_keys()
    known = profile.get("known_hosts_path")
    if profile.get("key_scope") == "shared":
        if not known or not Path(known).is_file():
            raise ValueError("Copy a trusted known_hosts file into the shared SSH directory first")
        if profile.get("key_path") and not Path(profile["key_path"]).is_file():
            raise ValueError("The SSH key is missing from the shared directory; upload it in Profiles")
        reject_symlinks(Path(known))
        if profile.get("key_path"):
            reject_symlinks(Path(profile["key_path"]))
    if known:
        client.load_system_host_keys(str(known))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())


def inspect_file(name, content):
    safe_name(name)
    if not content or len(content) > MAX_FILE or b"\0" in content:
        raise ValueError("SSH files must be nonempty text files no larger than 128 KiB")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("SSH files must contain UTF-8 text") from None
    fingerprints = []
    if name == "known_hosts":
        count = 0
        for line in text.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                entry = paramiko.hostkeys.HostKeyEntry.from_line(line)
                if entry is None or entry.key is None:
                    raise ValueError()
            except Exception:
                raise ValueError("Invalid known_hosts entry; copy verified entries from a trusted SSH client") from None
            count += 1
            fingerprints.append("SHA256:" + base64.b64encode(hashlib.sha256(entry.key.asbytes()).digest()).decode().rstrip("="))
        if not count:
            raise ValueError("known_hosts must contain at least one verified host key")
        kind = "known_hosts"
    elif name.endswith(".pub"):
        try:
            parts = text.strip().split()
            paramiko.PKey.from_type_string(parts[0], base64.b64decode(parts[1], validate=True))
        except Exception:
            raise ValueError("Invalid SSH public key") from None
        kind = "public key"
    else:
        if not text.startswith(("-----BEGIN OPENSSH PRIVATE KEY-----", "-----BEGIN RSA PRIVATE KEY-----", "-----BEGIN EC PRIVATE KEY-----")):
            raise ValueError("Only SSH private keys, public keys and known_hosts can be uploaded")
        accepted = False
        for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
            try:
                cls.from_private_key(io.StringIO(text))
                accepted = True
                break
            except paramiko.PasswordRequiredException:
                accepted = True
                break
            except Exception:
                continue
        if not accepted:
            raise ValueError("Invalid or unsupported SSH private key")
        kind = "private key"
    return {"name": name, "size": len(content), "kind": kind, "sha256": hashlib.sha256(content).hexdigest(), "fingerprints": sorted(set(fingerprints))}


class ProfileSSH:
    def __init__(self, state):
        self.state = state
        self.managed = state.directory / "ssh"
        self.lock = threading.RLock()

    def directory(self):
        rows = self.state.rows("SELECT data FROM settings WHERE user_id=?", (SETTINGS_ID,))
        return Path(json.loads(rows[0]["data"])["directory"]) if rows else self.managed

    def validate_directory(self, value):
        if not isinstance(value, str) or not value.strip() or len(value) > 500 or "\0" in value:
            raise ValueError("Provide an absolute directory on the DCC Web server")
        path = Path(value)
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("Provide an absolute directory on the DCC Web server")
        reject_symlinks(path)
        path = path.resolve()
        if path != self.managed and (not path.is_dir() or not os.access(path, os.R_OK | os.X_OK)):
            raise ValueError("The external SSH directory must already exist and be readable by DCC Web")
        return path

    def settings(self):
        root = self.validate_directory(str(self.directory()))
        files = []
        if root.is_dir():
            for path in sorted(root.iterdir()):
                if len(files) >= 100:
                    break
                if path.is_file() and not path.is_symlink():
                    files.append({"name": path.name, "size": path.stat().st_size})
        return {"directory": str(root), "managed_directory": str(self.managed), "uploads_allowed": root == self.managed, "files": files}

    def resolve(self, profile):
        if profile.get("kind") in {"ssh", "balena"} and profile.get("key_scope") == "shared":
            root = self.validate_directory(str(self.directory()))
            profile = dict(profile, key_path=str(root / safe_name(profile["key_path"])) if profile.get("key_path") else "", known_hosts_path=str(root / "known_hosts"))
        return profile

    def directory_plan(self, value):
        root = self.validate_directory(value)
        affected = [p for p in self.state.profiles() if p.get("key_scope") == "shared" and p.get("kind") in {"ssh", "balena"}]
        target = digest({"directory": str(root), "previous": str(self.directory()), "profiles": affected})
        return {"target": target, "directory": str(root), "profiles": [{"id": p["id"], "name": p["name"]} for p in affected]}

    def set_directory(self, value):
        root = self.validate_directory(value)
        self.state.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (SETTINGS_ID, json.dumps({"directory": str(root)})))

    def bulk_plan(self, action, identifiers):
        if action not in {"profiles.ssh.apply", "profiles.remove.selected"} or not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 100 or not all(isinstance(v, str) for v in identifiers):
            raise ValueError("Select between 1 and 100 profiles")
        ids = sorted(set(identifiers))
        values = {p["id"]: p for p in self.state.profiles()}
        if any(i not in values for i in ids):
            raise ValueError("A selected profile no longer exists; refresh the list")
        selected = [values[i] for i in ids]
        changes, skipped = [], []
        root = str(self.validate_directory(str(self.directory())))
        for p in selected:
            if action == "profiles.ssh.apply":
                if p.get("kind") not in {"ssh", "balena"}:
                    skipped.append({"id": p["id"], "name": p["name"]})
                    continue
                filename = safe_name(key_name(p["key_path"])) if p.get("key_path") else ""
                changes.append({"id": p["id"], "name": p["name"], "key_path": filename, "resolved_path": str(Path(root) / filename) if filename else ""})
            else:
                changes.append({"id": p["id"], "name": p["name"]})
        return {"target": digest({"action": action, "profiles": selected, "directory": root}), "changes": changes, "skipped": skipped, "directory": root}

    def apply_bulk(self, action, plan):
        with self.state.connect() as db:
            for item in plan["changes"]:
                if action == "profiles.remove.selected":
                    db.execute("DELETE FROM profiles WHERE id=?", (item["id"],))
                else:
                    row = db.execute("SELECT public FROM profiles WHERE id=?", (item["id"],)).fetchone()
                    value = dict(json.loads(row["public"]), key_scope="shared", key_path=item["key_path"])
                    value.pop("known_hosts_path", None)
                    # Update only public configuration; the encrypted credential blob stays byte-for-byte intact.
                    db.execute("UPDATE profiles SET public=? WHERE id=?", (json.dumps(value), item["id"]))

    def file_plan(self, files, replace=False):
        root = self.validate_directory(str(self.directory()))
        if root != self.managed:
            raise ValueError("Browser uploads are allowed only in the managed private SSH directory")
        if not 1 <= len(files) <= 20 or sum(len(v) for _, v in files) > MAX_TOTAL:
            raise ValueError("Select at most 20 SSH files with a total size of 1 MiB")
        names = [name.casefold() for name, _ in files]
        if len(set(names)) != len(names):
            raise ValueError("Duplicate SSH filenames are not allowed")
        manifest = []
        for name, content in files:
            item = inspect_file(name, content)
            destination = root / name
            reject_symlinks(destination)
            exists = destination.exists()
            if exists and (not destination.is_file() or destination.stat().st_size > MAX_FILE):
                raise ValueError("The target SSH file cannot be replaced")
            if exists and not replace:
                raise ValueError("A file already exists; explicitly enable replacement to continue")
            item.update(replacing=exists, previous=hashlib.sha256(destination.read_bytes()).hexdigest() if exists else None)
            manifest.append(item)
        return {"target": digest({"directory": str(root), "files": manifest, "replace": bool(replace)}), "directory": str(root), "files": manifest}

    def write_files(self, files):
        root = self.validate_directory(str(self.directory()))
        if root != self.managed:
            raise ValueError("Browser uploads are allowed only in the managed private SSH directory")
        root.mkdir(mode=0o700, exist_ok=True)
        root.chmod(0o700)
        staged = []
        try:
            for name, content in files:
                temp = root / ("upload-" + secrets.token_hex(16))
                with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as handle:
                    handle.write(content)
                temp.chmod(0o600)
                staged.append((temp, root / safe_name(name)))
            for source, destination in staged:
                reject_symlinks(destination)
                os.replace(source, destination)
        finally:
            for source, _ in staged:
                source.unlink(missing_ok=True)
