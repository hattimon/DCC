"""Qt-free catalog semantics shared by DCC Desktop and DCC Web."""
import json
import re

DCC_CATEGORY = "DCC"


def image_repository(image):
    value=str(image or '').split('@',1)[0]
    colon,slash=value.rfind(':'),value.rfind('/')
    return value[:colon] if colon>slash else value


def catalog_application_key(name, image, default_name=""):
    """Tags select versions; distinct default container names preserve variants."""
    name = str(name or '').strip().casefold()
    target = str(default_name or re.sub(r"[^a-z0-9_.-]+", "-", name).strip("-") or "app").strip().casefold()
    return name, image_repository(image).strip().casefold(), target


def catalog_image_is_older(candidate, current):
    """Compare stable numeric tags only; moving tags/digests follow source priority."""
    if image_repository(candidate).casefold() != image_repository(current).casefold():
        return False
    versions = []
    for image in (candidate, current):
        value = str(image or '').strip()
        tag = value[len(image_repository(value)):]
        match = re.fullmatch(r":v?(\d+(?:\.\d+)*)", tag)
        if not match:
            return False
        versions.append(tuple(int(part) for part in match[1].split('.')))
    width = max(map(len, versions))
    candidate_version, current_version = [v + (0,) * (width - len(v)) for v in versions]
    return candidate_version < current_version


def validate_catalog_uniqueness(apps):
    """A published catalog defines each application/explicit variant once."""
    seen = {}
    for app in apps:
        key = catalog_application_key(app.get('name'), app.get('image'), app.get('default_name') or app.get('container_name'))
        if key in seen:
            raise ValueError(f"Duplicate catalog application: {app.get('name')} ({seen[key]} / {app.get('image')}); update the existing entry instead of adding a version")
        seen[key] = app.get('image')


def localized_categories(category, category_en="", categories=None, categories_en=None, lang="PL"):
    primary = category_en if lang == "EN" and category_en else category
    extras = categories_en if lang == "EN" and categories_en else categories
    result, seen = [], set()
    for value in [primary, *(extras or [])]:
        value = str(value or "").strip()
        if value and value.casefold() not in seen:
            result.append(value)
            seen.add(value.casefold())
    return result


def category_group(category):
    raw = str(category or "")
    head = re.split(r"\s*[›/]\s*", raw, maxsplit=1)[0].strip()
    while head and not head[-1].isalnum():
        head = head[:-1].rstrip()
    return head or raw


def catalog_category_sort_key(category: str) -> tuple[int, str]:
    text = str(category or "").strip()
    normalized = text.casefold()
    priorities = [
        ("ai", 0),
        ("autom", 1),
        ("low-code", 2),
        ("administr", 3),
        ("monitor", 4),
        ("narz", 5),
        ("tools", 5),
        ("aplikacje www", 6),
        ("web apps", 6),
        ("www", 7),
        ("web /", 7),
        ("devops", 8),
        ("smart home", 9),
        ("media", 10),
        ("network", 11),
        ("sie", 11),
        ("bazy", 12),
        ("databases", 12),
        ("messaging", 13),
        ("cache", 14),
        ("runtime", 15),
        ("baza /", 16),
        ("base /", 16),
        ("balena", 17),
    ]
    for prefix, priority in priorities:
        if normalized.startswith(prefix):
            return priority, normalized
    return 50, normalized


_ACCESS_PREFIX = (
    r"(?:(?:initial|default|generated|temporary|bootstrap|admin|root|web|panel|app"
    r"|database|db|mysql|mariadb|postgres|pg|tymczasowe|początkowe)[_. -]?){0,3}"
)
_ACCESS_KEYS = {
    "username": _ACCESS_PREFIX + r"(?:user(?:[_. -]?name)?|login|użytkownik)",
    "password": _ACCESS_PREFIX + r"(?:password|passwd|pwd|hasło)",
    "setup_code": r"(?:DCC_WEB_)?(?:setup|activation|pairing|enrollment)[_. -]?code",
    "api_key": r"(?:admin[_. -]?)?(?:api|access)[_. -]?key",
    "token": r"(?:(?:access|auth|api|setup|bootstrap)[_. -]?)?token",
    "message": r"(?:message|msg|log)",
}
_ACCESS_ASSIGNMENT = re.compile(
    r"(?<![\w.\\-])(?P<key_quote>['\"])?(?:"
    + "|".join(f"(?P<{kind}>{pattern})" for kind, pattern in _ACCESS_KEYS.items())
    + r")(?(key_quote)(?P=key_quote))[ \t]*"
      r"(?:(?:is[ \t]+)?(?:provided|generated)[ \t]+for[ \t]+(?:this[ \t]+)?session[ \t]*:"
      r"|=>|->|[:=|]|\b(?:is|to)\b[ \t]*[:=]?|(?=['\"\x60]))[ \t]*"
    + r"""(?P<value>"(?:\\[^\r\n]|[^"\\\r\n])*(?:"|(?=\r?$))"""
      r"""|'(?:\\[^\r\n]|[^'\\\r\n])*(?:'|(?=\r?$))"""
      r"""|\x60[^\x60\r\n]*(?:\x60|(?=\r?$))"""
      r"""|(?(key_quote)[^\s,"'\x60}\]]+|[^\s"'\x60]+))""",
    re.IGNORECASE | re.MULTILINE,
)
_ACCESS_LABELS = {
    "username": ("Username", "Login"),
    "password": ("Password", "Hasło"),
    "setup_code": ("Setup code", "Kod konfiguracji"),
    "api_key": ("API key", "Klucz API"),
    "token": ("Token", "Token"),
}
_UNAVAILABLE_ACCESS = re.compile(
    r"(?:[*•]+|[<\[]?(?:redacted|masked|hidden|unset|unknown|null|none|undefined|n/a|not(?: set)?)[>\]]?)",
    re.IGNORECASE,
)
_ACCESS_QUOTES = "'\"\x60"


def _access_value(raw):
    if raw[0] in _ACCESS_QUOTES:
        if len(raw) < 2 or raw[-1] != raw[0]:
            return None
        if raw[0] == '"':
            try:
                return json.loads(raw)
            except ValueError:
                pass
        return raw[1:-1]
    if raw.startswith(("{", "[")):
        return None
    return raw


def _mask_log_fields(text, collect=None, nested=True):
    def replace(match):
        kind = next(key for key in _ACCESS_KEYS if match[key] is not None)
        raw = match["value"]
        quote = raw[0] if raw[0] in _ACCESS_QUOTES else ""
        if not quote and match["key_quote"] == '"' and raw in {"true", "false", "null"}:
            return match[0]
        value = _access_value(raw)
        if kind == "message":
            if not nested or not quote or not value:
                return match[0]
            clean = _mask_log_fields(value, collect, nested=False)
            if clean == value:
                return match[0]
            replacement = json.dumps(clean, ensure_ascii=False) if quote == '"' else quote + clean + quote
        else:
            if collect is not None and value is not None:
                collect(kind, value)
            if kind == "username" or (value is None and not quote):
                return match[0]
            if not quote and match["key_quote"] == '"':
                quote = '"'
            replacement = quote + "••••" + quote
        start = match.start("value") - match.start()
        return match[0][:start] + replacement

    return _ACCESS_ASSIGNMENT.sub(replace, text)


def redact_log_access_details(log_text):
    """Mask recognized fields in ordinary log views, exports and MCP reads."""
    return _mask_log_fields(log_text)


def parse_access_details(log_text, patterns=None, lang="EN"):
    text = str(log_text or "")
    if not text.strip():
        return []
    found = []
    seen = set()

    def add(label: str, value: str):
        if (not value.strip() or len(value) > 256 or _UNAVAILABLE_ACCESS.fullmatch(value.strip())
                or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            return
        key = (label.casefold(), value)
        if key not in seen:
            seen.add(key)
            found.append((label, value))

    for rule in patterns or []:
        try:
            pattern = str(rule.get("regex") or "")
            if not pattern:
                continue
            label = str(rule.get("label_en") if lang == "EN" and rule.get("label_en") else rule.get("label") or "Credential").strip()
            for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                value = match.groupdict().get("value") if match.groupdict() else None
                if value is None and match.lastindex:
                    value = match.group(1)
                if value:
                    add(label, value.strip().strip(_ACCESS_QUOTES + ".,;[]()"))
        except re.error:
            continue

    def collect(kind, value):
        if kind in {"api_key", "token"} and len(value) < 8:
            return
        add(_ACCESS_LABELS[kind][0 if lang == "EN" else 1], value)

    _mask_log_fields(text, collect)
    return found[:8]
