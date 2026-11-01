"""Qt-free catalog semantics shared by DCC Desktop and DCC Web."""
import re

DCC_CATEGORY = "DCC"


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
