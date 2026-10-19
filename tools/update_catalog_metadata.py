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
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


GITHUB_API = "https://api.github.com"
GHCR_API = "https://ghcr.io"
USER_AGENT = "DCC-catalog-maintainer/1.0"
MANIFEST_ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)


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


def registry_json(url: str, headers: dict[str, str] | None = None) -> Any:
    request_headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    request_headers.update(headers or {})
    request = Request(url, headers=request_headers)
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


def latest_release(repo: str, tag_pattern: str = "") -> tuple[str, str]:
    if tag_pattern:
        pattern = re.compile(tag_pattern)
        for page in range(1, 6):
            releases = github_json(f"/repos/{repo}/releases?per_page=100&page={page}")
            if not isinstance(releases, list):
                break
            for release in releases:
                if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
                    continue
                tag = str(release.get("tag_name") or "").strip()
                if tag and pattern.fullmatch(tag):
                    return tag, str(release.get("html_url") or f"https://github.com/{repo}/releases/tag/{quote(tag)}")
            if len(releases) < 100:
                break
        return "", ""

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


def image_for_release(image: str, version: str, strategy: str) -> str:
    image = str(image or "").strip()
    version = str(version or "").strip()
    if not image or not version or "@" in image:
        return ""
    if strategy == "strip-v":
        tag = version[1:] if version.startswith("v") else version
    elif strategy == "exact":
        tag = version
    else:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag):
        return ""
    last_slash = image.rfind("/")
    last_colon = image.rfind(":")
    if last_colon > last_slash:
        return f"{image[:last_colon]}:{tag}"
    return f"{image}:{tag}"


def registry_image_platforms(image: str) -> set[tuple[str, str]]:
    image = str(image or "").strip()
    if not image.startswith("ghcr.io/") or "@" in image:
        return set()
    reference = image[len("ghcr.io/"):]
    last_slash = reference.rfind("/")
    last_colon = reference.rfind(":")
    if last_colon <= last_slash:
        return set()
    repository, tag = reference[:last_colon], reference[last_colon + 1:]
    if not repository or not tag:
        return set()

    token_url = f"{GHCR_API}/token?{urlencode({'service': 'ghcr.io', 'scope': f'repository:{repository}:pull'})}"
    token_payload = registry_json(token_url)
    token = str(token_payload.get("token") or token_payload.get("access_token") or "").strip()
    if not token:
        return set()
    manifest_url = f"{GHCR_API}/v2/{quote(repository, safe='/')}/manifests/{quote(tag, safe='')}"
    try:
        manifest = registry_json(
            manifest_url,
            {"Accept": MANIFEST_ACCEPT, "Authorization": f"Bearer {token}"},
        )
    except HTTPError as exc:
        if exc.code == 404:
            return set()
        raise

    platforms: set[tuple[str, str]] = set()
    for entry in manifest.get("manifests", []) if isinstance(manifest, dict) else []:
        platform = entry.get("platform") or {}
        os_name = str(platform.get("os") or "").lower()
        architecture = str(platform.get("architecture") or "").lower()
        if os_name and architecture and os_name != "unknown":
            platforms.add((os_name, architecture))
    if isinstance(manifest, dict) and manifest.get("architecture"):
        platforms.add((str(manifest.get("os") or "linux").lower(), str(manifest["architecture"]).lower()))
    return platforms


def registry_image_supports_architectures(image: str, architectures: list[str]) -> bool:
    available = registry_image_platforms(image)
    if not available:
        return False
    aliases = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
        "armv7l": "arm",
        "armv7": "arm",
        "armhf": "arm",
        "arm": "arm",
        "i386": "386",
        "i686": "386",
        "x86": "386",
    }
    required = {aliases[item.lower()] for item in architectures if item.lower() in aliases}
    available_linux = {architecture for os_name, architecture in available if os_name == "linux"}
    return required.issubset(available_linux)


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
            release_pattern = str(app.get("release_tag_pattern") or "").strip()
            version, release_url = latest_release(repo, release_pattern)
        except Exception as exc:
            print(f"WARN {repo}: {exc}")
            continue

        current_image = str(app.get("image") or "").strip()
        image_strategy = str(app.get("image_tag_from_release") or "").strip()
        if image_strategy:
            if not release_pattern or not re.fullmatch(release_pattern, version):
                print(f"WARN {repo}: release tag does not match the configured image-tag rule; keeping catalog entry unchanged")
                continue
            new_image = image_for_release(current_image, version, image_strategy)
            if not new_image:
                print(f"WARN {repo}: cannot derive an image tag from {version}; keeping catalog entry unchanged")
                continue
            if new_image != current_image:
                try:
                    image_ready = registry_image_supports_architectures(new_image, list(app.get("archs") or []))
                except Exception as exc:
                    print(f"WARN {repo}: could not verify {new_image}: {exc}; keeping catalog entry unchanged")
                    continue
                if not image_ready:
                    print(f"WARN {repo}: {new_image} is not published for the catalog architectures; keeping catalog entry unchanged")
                    continue

        before = (
            app.get("upstream_repo"),
            app.get("latest_release"),
            app.get("latest_release_url"),
            app.get("image"),
        )
        app["upstream_repo"] = repo
        if version:
            app["latest_release"] = version
        if release_url:
            app["latest_release_url"] = release_url
        if image_strategy:
            app["image"] = new_image
        after = (
            app.get("upstream_repo"),
            app.get("latest_release"),
            app.get("latest_release_url"),
            app.get("image"),
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
