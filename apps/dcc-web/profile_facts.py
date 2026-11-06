"""Allowlisted Docker-engine facts cached after an authorized info request."""
import hashlib
import json
import time

FIELDS = {"engine_os": "OperatingSystem", "engine_os_type": "OSType", "architecture": "Architecture",
          "engine_kernel": "KernelVersion", "docker_version": "ServerVersion"}


def signature(profile):
    return hashlib.sha256(json.dumps({key: profile.get(key) for key in
        ("kind", "host", "port", "username", "context", "distro", "endpoint")}, sort_keys=True).encode()).hexdigest()


def remember(state, profile, info):
    facts = {key: "".join(c for c in str(info.get(source, ""))[:200] if c.isprintable()) for key, source in FIELDS.items()}
    value = {"signature": signature(profile), "checked": time.time(), "facts": facts}
    state.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", ("__dcc_profile_facts__" + profile["id"],
                  state.vault.encrypt(json.dumps(value).encode()).decode()))
    return facts


def snapshot(state, profile):
    environment = {"connection": profile.get("kind", "local")}
    if profile.get("distro"):
        environment["wsl_distribution"] = profile["distro"]
    rows = state.rows("SELECT data FROM settings WHERE user_id=?", ("__dcc_profile_facts__" + profile["id"],))
    if rows:
        value = json.loads(state.vault.decrypt(rows[0]["data"].encode()))
        if value.get("signature") == signature(profile):
            environment.update({key: value["facts"][key] for key in FIELDS if value["facts"].get(key)})
            environment["observed_at"] = value["checked"]
    return environment
