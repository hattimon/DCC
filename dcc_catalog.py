"""Qt-free catalog semantics shared by DCC Desktop and DCC Web."""
import re

DCC_CATEGORY = "DCC"


def image_repository(image):
    value=str(image or '').split('@',1)[0]
    colon,slash=value.rfind(':'),value.rfind('/')
    return value[:colon] if colon>slash else value


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


def parse_access_details(log_text, patterns=None, lang="EN"):
    text = str(log_text or "")
    if not text.strip():
        return []
    found: List[tuple[str, str]] = []
    seen = set()

    def add(label: str, value: str):
        clean_value = str(value or "").strip().strip("'\"`.,;[]()")
        clean_label = str(label or "Credential").strip()
        if not clean_value or len(clean_value) > 256:
            return
        key = (clean_label.casefold(), clean_value)
        if key not in seen:
            seen.add(key)
            found.append((clean_label, clean_value))

    for rule in patterns or []:
        try:
            pattern = str(rule.get("regex") or "")
            label = str(rule.get("label_en") if lang == "EN" and rule.get("label_en") else rule.get("label") or "Credential")
            for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                value = match.groupdict().get("value") if match.groupdict() else None
                if value is None and match.lastindex:
                    value = match.group(1)
                if value:
                    add(label, value)
        except re.error:
            continue

    generic_patterns = [
        ("Password" if lang == "EN" else "Hasło", r"(?:web\s+)?(?:admin\s+)?password\s*(?:is|:|=|->)\s*(?P<value>[^\s]+)"),
        ("Username" if lang == "EN" else "Login", r"(?:user(?:name)?|login)\s*(?:is|:|=|->)\s*(?P<value>[^\s]+)"),
        ("Setup code" if lang=="EN" else "Kod konfiguracji", r"DCC_WEB_SETUP_CODE\s*[:=]\s*(?P<value>[A-Za-z0-9_-]{16,})"),
        ("API key" if lang=="EN" else "Klucz API", r"(?:api[_ -]?key|access[_ -]?key)\s*(?:is|:|=|->)\s*(?P<value>[A-Za-z0-9._~+/-]{8,})"),
        ("Token", r"(?:access\s+)?token\s*(?:is|:|=|->)\s*(?P<value>[A-Za-z0-9._~+/-]{8,})"),
    ]
    for label, pattern in generic_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
            add(label, match.group("value"))
    return found[:8]
