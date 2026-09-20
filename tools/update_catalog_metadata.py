#!/usr/bin/env python3
"""Maintain DCC's public deployment catalog from GitHub metadata.

The live catalog is intentionally conservative: upstream release metadata may be
updated automatically, but newly discovered projects are written only to the
candidate file. They are not installable by DCC until a maintainer reviews and
moves them into dcc-catalog.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


GITHUB_API = "https://api.github.com"
USER_AGENT = "DCC-catalog-maintainer/1.0"


def github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def github_json(path: str) -> Any:
    request = Request(f"{GITHUB_API}{path}", headers=github_headers())
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def github_repo_from_url(value: str) -> str:
    match = re.match(r"^https?://github\.com/([^/]+)/([^/#?]+)", str(value or "").strip(), re.IGNORECASE)
    if not match:
        return ""
    owner = match.group(1).strip()
    repo = match.group(2).strip()
    if repo.lower().endswith(".git"):
        repo = repo[:-4]
    return f"{owner}/{repo}" if owner and repo else ""


def app_repo(app: dict[str, Any]) -> str:
    explicit = str(app.get("upstream_repo") or "").strip()
    if re.match(r"^[^/\s]+/[^/\s]+$", explicit):
        return explicit
    for key in ("source_url", "homepage_url", "docs_url"):
        repo = github_repo_from_url(str(app.get(key) or ""))
        if repo:
            return repo
    return ""


def latest_release(repo: str) -> tuple[str, str]:
    try:
        payload = github_json(f"/repos/{repo}/releases/latest")
        tag = str(payload.get("tag_name") or payload.get("name") or "").strip()
        url = str(payload.get("html_url") or "").strip()
        if tag:
            return tag, url
    except HTTPError as exc:
        if exc.code != 404:
            raise

    tags = github_json(f"/repos/{repo}/tags?per_page=1")
    if isinstance(tags, list) and tags:
        tag = str(tags[0].get("name") or "").strip()
        if tag:
            return tag, f"https://github.com/{repo}/releases/tag/{quote(tag)}"
    return "", ""


def update_release_metadata(catalog_path: Path) -> tuple[int, int]:
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    apps = payload.get("apps", [])
    changed = 0
    checked = 0
    for app in apps:
        if not isinstance(app, dict):
            continue
        repo = app_repo(app)
        if not repo:
            continue
        checked += 1
        try:
            version, release_url = latest_release(repo)
        except Exception as exc:
            print(f"WARN {repo}: {exc}")
            continue
        before = (
            app.get("upstream_repo"),
            app.get("latest_release"),
            app.get("latest_release_url"),
        )
        app["upstream_repo"] = repo
        if version:
            app["latest_release"] = version
        if release_url:
            app["latest_release_url"] = release_url
        after = (
            app.get("upstream_repo"),
            app.get("latest_release"),
            app.get("latest_release_url"),
        )
        if before != after:
            changed += 1

    if changed:
        catalog_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return checked, changed


def load_existing_candidates(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    items = payload.get("candidates", []) if isinstance(payload, dict) else []
    return {
        str(item.get("full_name") or "").casefold(): item
        for item in items
        if isinstance(item, dict) and item.get("full_name")
    }


def discover_candidates(catalog_path: Path, candidates_path: Path, limit: int) -> tuple[int, int]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    existing_repos = {
        repo.casefold()
        for app in catalog.get("apps", [])
        if isinstance(app, dict)
        for repo in [app_repo(app)]
        if repo
    }
    previous = load_existing_candidates(candidates_path)
    queries = [
        "topic:self-hosted stars:>300 archived:false fork:false",
        "topic:docker-compose stars:>300 archived:false fork:false",
    ]
    found: dict[str, dict[str, Any]] = {}
    for query in queries:
        result = github_json(f"/search/repositories?q={quote(query)}&sort=updated&order=desc&per_page=50")
        for repo in result.get("items", []) if isinstance(result, dict) else []:
            full_name = str(repo.get("full_name") or "").strip()
            key = full_name.casefold()
            if not full_name or key in existing_repos:
                continue
            previous_item = previous.get(key, {})
            found[key] = {
                "full_name": full_name,
                "name": str(repo.get("name") or ""),
                "source_url": str(repo.get("html_url") or ""),
                "description": str(repo.get("description") or ""),
                "stars": int(repo.get("stargazers_count") or 0),
                "language": str(repo.get("language") or ""),
                "topics": sorted(str(topic) for topic in (repo.get("topics") or [])),
                "updated_at": str(repo.get("updated_at") or ""),
                "first_seen": previous_item.get("first_seen") or str(repo.get("created_at") or ""),
                "review_status": previous_item.get("review_status") or "candidate",
            }

    ordered = sorted(found.values(), key=lambda item: (-int(item.get("stars") or 0), item["full_name"].casefold()))[:limit]
    output = {
        "schema_version": 1,
        "note": "Discovery only. Entries are not published to DCC until reviewed and copied into dcc-catalog.json.",
        "candidates": ordered,
    }
    previous_text = candidates_path.read_text(encoding="utf-8") if candidates_path.exists() else ""
    new_text = json.dumps(output, indent=2, ensure_ascii=False) + "\n"
    if new_text != previous_text:
        candidates_path.parent.mkdir(parents=True, exist_ok=True)
        candidates_path.write_text(new_text, encoding="utf-8")
    return len(ordered), sum(1 for item in ordered if item["full_name"].casefold() not in previous)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="dcc-catalog.json")
    parser.add_argument("--candidates", default="catalog/candidates.json")
    parser.add_argument("--skip-metadata", action="store_true")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--discover-limit", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog_path = Path(args.catalog)
    if not args.skip_metadata:
        checked, changed = update_release_metadata(catalog_path)
        print(f"release metadata: checked={checked} changed={changed}")
    if args.discover:
        total, new = discover_candidates(catalog_path, Path(args.candidates), max(1, args.discover_limit))
        print(f"discovery candidates: total={total} new={new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
