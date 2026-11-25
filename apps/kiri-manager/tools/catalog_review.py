"""Validate the offline DCC Store candidate and prepare a one-entry publication patch."""
import argparse
import json
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent.parent
sys.path.insert(0, str(REPO))

from dcc_catalog import validate_catalog_uniqueness  # noqa: E402


def candidate():
    return json.loads((ROOT / "release" / "catalog-entry.json").read_text(encoding="utf-8"))


def entry_text(entry):
    return "\n".join("    " + line for line in json.dumps(entry, ensure_ascii=False, indent=2).splitlines())


def prepare(original):
    document = json.loads(original)
    app = candidate()
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if (document["schema_version"] != 1 or app["category"] != "DCC"
            or app["category_en"] != "DCC" or app["version"] != version):
        raise ValueError("Application catalog schema or version differs")
    if app["image"] != f"ghcr.io/hattimon/dcc-kiri-manager:{version}":
        raise ValueError("Image and release version differ")
    if app["engines"] != ["docker"] or set(app["archs"]) != {"amd64", "arm64"}:
        raise ValueError("The Store candidate targets Docker on the two built architectures")
    extras = shlex.split(app["extra"])
    if ("127.0.0.1:8796:8796" not in extras or "dcc_kiri_manager_data:/data" not in extras
            or any(".sock" in x or x == "--privileged" for x in extras)
            or app["host_port"] or app["container_port"] != "8796"):
        raise ValueError("The Store candidate requires loopback, a dedicated volume and no engine socket")
    apps = document["apps"]
    validate_catalog_uniqueness(apps)
    existing = next((index for index, item in enumerate(apps) if item["name"] == app["name"]), None)
    if any(item.get("host_port") == "8796" for index, item in enumerate(apps) if index != existing):
        raise ValueError("Port 8796 is already reserved by another catalog entry")
    if existing is None:
        position = original.rfind("\n  ]\n}")
        if position < 0:
            raise ValueError("Unexpected catalog formatting; review the candidate manually")
        updated = original[:position] + ",\n" + entry_text(app) + original[position:]
        apps.append(app)
    else:
        current = apps[existing]
        if current == app:
            return original
        if (current.get("default_name") != app["default_name"]
                or current["image"].rsplit(":", 1)[0] != app["image"].rsplit(":", 1)[0]
                or tuple(map(int, current["version"].split("."))) >= tuple(map(int, version.split(".")))):
            raise ValueError("Expected a newer release of the same Kiri Manager application")
        old_text = entry_text(current)
        if original.count(old_text) != 1:
            raise ValueError("Unexpected catalog formatting; review the candidate manually")
        updated = original.replace(old_text, entry_text(app), 1)
        apps[existing] = app
    validate_catalog_uniqueness(apps)
    if json.loads(updated) != document:
        raise ValueError("Expected a single application change in the catalog")
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write a preview of the catalog to a new file")
    args = parser.parse_args()
    rendered = prepare((REPO / "dcc-catalog.json").read_text(encoding="utf-8"))
    if args.output:
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
    print("DCC Store candidate valid")


if __name__ == "__main__":
    main()
