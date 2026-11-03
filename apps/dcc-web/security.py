"""Authentication, profile-scoped authorization and redaction."""
import hashlib
import ipaddress
import re
import secrets
import time
from urllib.parse import urlsplit

from flask import abort, g, request, session

CAPABILITIES = {"host.exec","read", "containers.write", "exec", "images.write", "volumes.write", "networks.write", "compose.write", "install", "update", "destructive"}
ROLES = {"viewer": {"read"}, "operator": {"read", "containers.write", "exec"}, "admin": CAPABILITIES}
SECRET_WORDS = re.compile(r"password|passwd|passphrase|private.?key|token|secret|authorization|api.?key|credential|setup.?code|recovery.?code", re.I)


def trusted_public_https_request(app):
    """Recognize an explicitly configured public HTTPS endpoint."""
    host=(urlsplit("//"+request.host).hostname or "").lower()
    trusted={str(value).lower() for value in app.config.get("TRUSTED_HTTPS_HOSTS",[]) if value}
    public_origin=app.config.get("PUBLIC_ORIGIN") or ""
    parsed=urlsplit(public_origin)
    if parsed.scheme.lower()=="https" and parsed.hostname:
        trusted.add(parsed.hostname.lower())
    return host in trusted


def trusted_https_request(app):
    """Recognize TLS from Flask, a configured public host, or authenticated Caddy."""
    # Direct TLS termination is trustworthy even when the hostname is a private
    # LAN address. Public HSTS is handled separately by trusted_public_https_request.
    if request.is_secure:
        return True
    if trusted_public_https_request(app):
        return True
    if request.headers.get("X-Forwarded-Proto","").split(",",1)[0].strip().lower()!="https":
        return False
    domains=app.extensions.get("dcc_domains")
    return bool(domains and domains.trusts_proxy(request.headers.get("X-DCC-Web-Internal-TLS", "")))


def redact(value):
    if isinstance(value, dict):
        return {key: "••••" if SECRET_WORDS.search(key) else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return ["%s=••••" % item.split("=", 1)[0] if isinstance(item, str) and "=" in item and SECRET_WORDS.search(item.split("=",1)[0]) else redact(item) for item in value]
    if isinstance(value,str):
        value=re.sub(r"(?im)(authorization\s*:\s*)[^\r\n]+",r"\1••••",value)
        return re.sub(r"(?i)((?:password|passwd|token|secret|api[_ -]?key|setup[_ -]?code)\s*(?::|=|\bis\b|->)\s*)\S+",r"\1••••",value)
    return value


def initialize_security(app, state):
    @app.before_request
    def guard():
        host = (urlsplit("//"+request.host).hostname or "").lower()
        if host not in app.config["ALLOWED_HOSTS"]:
            abort(400, "Untrusted Host header")
        session.setdefault("csrf", secrets.token_urlsafe(32))
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("Origin")
            expected_origin=app.config.get("PUBLIC_ORIGIN") or request.host_url.rstrip("/")
            if trusted_https_request(app):
                expected_origin='https://'+request.host
            if origin and origin != expected_origin:
                abort(403, "Origin rejected")
            supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf", "")
            if not secrets.compare_digest(str(supplied), session["csrf"]):
                abort(403, "Invalid CSRF token")
        sid = session.get("sid", "")
        rows = state.rows("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?", (hashlib.sha256(sid.encode()).hexdigest(), time.time())) if sid else []
        g.user = rows[0] if rows else None
        if g.user and getattr(state, 'mfa', None) and state.mfa.enabled(g.user['id']) and not session.get('mfa_verified'):
            g.user = None
        if request.path.startswith("/api/") and request.path != "/api/health" and not g.user:
            abort(401, "Login required")

    @app.after_request
    def headers(response):
        response.headers.update({
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
            "Referrer-Policy": "same-origin", "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Cache-Control": "no-store" if not request.path.startswith("/static/") else "no-cache" if request.path.endswith(('.js','.css')) else "private, max-age=3600",
        })
        if request.path=='/terminal':
            # xterm creates CSS rules for terminal colours and cell geometry; scripts remain self-only.
            response.headers['Content-Security-Policy']=response.headers['Content-Security-Policy'].replace("style-src 'self';","style-src 'self' 'unsafe-inline';")
        if app.config.get("SESSION_COOKIE_SECURE") or trusted_public_https_request(app):
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
            state.audit(g.user["id"] if g.get("user") else "anonymous", request.method + " " + request.path, str(request.view_args or {}), response.status_code)
        return response


def admin():
    if not g.user or g.user["role"] != "admin":
        abort(403, "Administrator permission required")


def authorize(profile, capability="read"):
    allowed_users = profile.get("users", [])
    if allowed_users and g.user["id"] not in allowed_users and g.user["role"] != "admin":
        abort(403, "Profile access denied")
    if capability not in ROLES.get(g.user["role"], set()) or capability not in profile.get("permissions", ["read"]):
        if capability=='install':
            abort(403, "Installation is disabled for this profile. Enable Install applications in Profiles / Permissions. Only an administrator can change this setting.")
        abort(403, "This profile does not permit the operation: "+capability)


def validate_profile(data):
    result = {key: data.get(key) for key in ("name", "kind", "endpoint", "host", "port", "username", "key_path", "key_scope", "ssh_auth", "known_hosts_path", "distro", "cli", "context", "users", "panel_host") if data.get(key) is not None}
    if result.get('ssh_auth', 'auto') not in {'auto', 'key', 'agent'}:
        raise ValueError('Invalid SSH authentication method')
    if result.get("key_scope", "individual") not in {"individual", "shared", "mounted"}:
        raise ValueError("Invalid SSH key scope")
    for key in ("key_path", "known_hosts_path"):
        if key in result and (not isinstance(result[key], str) or len(result[key]) > 500 or "\0" in result[key]):
            raise ValueError("Invalid SSH file path")
    if result.get("key_scope") in {"shared", "mounted"}:
        from profile_ssh import safe_name
        if result.get("key_path"):
            safe_name(result["key_path"])
        result.pop("known_hosts_path", None)
    if result.get('panel_host') and not re.fullmatch(r'[A-Za-z0-9.\-:_]{1,200}',str(result['panel_host'])):
        raise ValueError('Invalid panel hostname or IP')
    if not isinstance(result.get("name"), str) or not 1 <= len(result["name"]) <= 80:
        raise ValueError("Profile name is required")
    kind = result.get("kind", "local")
    if kind not in {"local", "tcp", "ssh", "wsl", "balena", "tunnel"}:
        raise ValueError("Unsupported profile kind")
    result["kind"] = kind
    if result.get('cli') and result['cli'] not in {'docker','balena','balena-engine'}:
        raise ValueError('Unsupported engine CLI')
    if "port" in result:
        result["port"] = int(result["port"] or 22)
        if not 1 <= result["port"] <= 65535:
            raise ValueError("Invalid connection port")
    if kind in {"ssh", "balena"}:
        for field in ("host", "username"):
            if not re.fullmatch(r"[a-zA-Z0-9_.:@-]{1,180}", str(result.get(field, ""))) or str(result[field]).startswith("-"):
                raise ValueError("Invalid SSH host or username")
        result["port"] = int(result.get("port") or 22)
        if not 1 <= result["port"] <= 65535:
            raise ValueError("Invalid SSH port")
    if kind == "tcp":
        endpoint = str(result.get("endpoint", ""))
        if not re.fullmatch(r"(?:tcp|https)://[a-zA-Z0-9.\[\]:_-]+", endpoint):
            raise ValueError("Invalid Docker endpoint")
        if not data.get("tls_verify", True):
            raise ValueError("Remote TCP requires verified TLS")
        result["tls_verify"] = True
    if kind == "tunnel":
        endpoint=str(result.get("endpoint",""))
        if not re.fullmatch(r"tcp://(?:127\.0\.0\.1|localhost):\d{1,5}",endpoint):
            raise ValueError("A tunnel must terminate on localhost; establish it explicitly using SSH")
    if kind == "wsl" and not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", str(result.get("distro", ""))):
        raise ValueError("Invalid WSL distribution")
    permissions = data.get("permissions", ["read"])
    if not isinstance(permissions, list) or set(permissions) - CAPABILITIES:
        raise ValueError("Invalid permissions")
    result["permissions"] = sorted(set(permissions) | {"read"})
    if "users" in result and (not isinstance(result["users"],list) or not all(isinstance(v,str) for v in result["users"])):
        raise ValueError("Profile users must be an array of user identifiers")
    return result
