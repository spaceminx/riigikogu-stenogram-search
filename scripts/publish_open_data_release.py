#!/usr/bin/env python3
"""Publish an open data release directory to GitHub Releases.

Creates a release tagged data-YYYY-MM-DD on spaceminx/riigikogu-stenogram-search
and uploads all files in the release directory using the GitHub REST API.
Token is read from env GITHUB_RELEASE_TOKEN (or from .env.pipeline).
Token is never printed or logged.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO = "spaceminx/riigikogu-stenogram-search"
API_BASE = "https://api.github.com"
UPLOADS_BASE = "https://uploads.github.com"
# Without a timeout a stalled connection would hang the monthly cron indefinitely.
API_TIMEOUT_SECONDS = 60
UPLOAD_TIMEOUT_SECONDS = 300


def load_env_pipeline(root_dir: Path) -> None:
    """Load variables from .env.pipeline into os.environ if present."""
    env_file = root_dir / ".env.pipeline"
    if not env_file.exists():
        return
    try:
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


def github_api_request(
    url: str,
    method: str = "GET",
    token: str | None = None,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = API_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Execute a GitHub API request and return JSON response."""
    req_headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "riigivaade-open-data-publisher",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        req_headers["Authorization"] = f"Bearer {token}"
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read()
            if not resp_body:
                return {}
            return json.loads(resp_body.decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {url} returned HTTP {e.code}: {err_body}") from e


def list_repo_releases(token: str) -> list[dict[str, Any]]:
    """List all releases in the repository with pagination."""
    releases: list[dict[str, Any]] = []
    page = 1
    per_page = 100

    while True:
        url = f"{API_BASE}/repos/{REPO}/releases?per_page={per_page}&page={page}"
        batch = github_api_request(url, token=token)
        if not batch or not isinstance(batch, list):
            break
        releases.extend(batch)
        if len(batch) < per_page:
            break
        page += 1

    return releases


def find_release_by_tag(tag: str, token: str) -> dict[str, Any] | None:
    """Find release by tag name from releases list (includes drafts)."""
    releases = list_repo_releases(token)
    for r in releases:
        if r.get("tag_name") == tag:
            return r
    return None


def create_release(
    tag: str, name: str, body: str, token: str, draft: bool = True
) -> dict[str, Any]:
    """Create a new GitHub release (defaults to draft=True)."""
    url = f"{API_BASE}/repos/{REPO}/releases"
    payload = {
        "tag_name": tag,
        "name": name,
        "body": body,
        "draft": draft,
        "prerelease": False,
    }
    data = json.dumps(payload).encode("utf-8")
    return github_api_request(
        url,
        method="POST",
        token=token,
        data=data,
        headers={"Content-Type": "application/json"},
    )


def publish_draft_release(release_id: int, token: str) -> dict[str, Any]:
    """Publish a draft release by updating draft=False."""
    url = f"{API_BASE}/repos/{REPO}/releases/{release_id}"
    payload = {"draft": False}
    data = json.dumps(payload).encode("utf-8")
    return github_api_request(
        url,
        method="PATCH",
        token=token,
        data=data,
        headers={"Content-Type": "application/json"},
    )


def delete_release(release_id: int, token: str) -> None:
    """Delete an existing release by ID."""
    url = f"{API_BASE}/repos/{REPO}/releases/{release_id}"
    github_api_request(url, method="DELETE", token=token)


def upload_asset(release_id: int, file_path: Path, token: str) -> dict[str, Any]:
    """Upload a file as a release asset."""
    file_name = file_path.name
    content_type, _ = mimetypes.guess_type(file_name)
    if not content_type:
        content_type = "application/octet-stream"

    encoded_name = urllib.parse.quote(file_name)
    url = f"{UPLOADS_BASE}/repos/{REPO}/releases/{release_id}/assets?name={encoded_name}"

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    return github_api_request(
        url,
        method="POST",
        token=token,
        data=file_bytes,
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(file_bytes)),
        },
        timeout=UPLOAD_TIMEOUT_SECONDS,
    )


def verify_release_assets(release_id: int, files: list[Path], token: str) -> None:
    """Raise if the draft's assets do not match the local files by name and size."""
    url = f"{API_BASE}/repos/{REPO}/releases/{release_id}/assets?per_page=100"
    assets = github_api_request(url, token=token)
    remote = {a.get("name"): a.get("size") for a in assets if isinstance(a, dict)}
    expected = {f.name: f.stat().st_size for f in files}
    if remote != expected:
        missing = sorted(set(expected) - set(remote))
        wrong_size = sorted(n for n in expected if n in remote and remote[n] != expected[n])
        extra = sorted(set(remote) - set(expected))
        raise RuntimeError(
            f"Draft release {release_id} assets do not match the local files "
            f"(missing={missing}, wrong_size={wrong_size}, extra={extra}); not publishing."
        )


def publish_release(
    release_dir: Path,
    replace: bool = False,
    dry_run: bool = False,
    token: str | None = None,
) -> None:
    """Publish release directory to GitHub Releases."""
    if not release_dir.is_dir():
        print(f"Error: Release directory not found: {release_dir}", file=sys.stderr)
        sys.exit(1)

    # 1. Determine tag name from manifest or directory name
    manifest_file = release_dir / "manifest.json"
    if manifest_file.exists():
        with open(manifest_file, encoding="utf-8") as f:
            manifest_data = json.load(f)
        date_version = manifest_data.get("version", release_dir.name)
    else:
        date_version = release_dir.name

    tag = f"data-{date_version}"
    release_title = f"Riigivaade Open Data ({date_version})"

    # Read README.md for release notes body if present
    readme_file = release_dir / "README.md"
    if readme_file.exists():
        body = readme_file.read_text(encoding="utf-8")
    else:
        body = f"Riigivaade open dataset release for {date_version}."

    files_to_upload = sorted(
        [f for f in release_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
    )

    if dry_run:
        print(f"[DRY-RUN] Target repo: {REPO}")
        print(f"[DRY-RUN] Release tag: {tag}")
        print(f"[DRY-RUN] Title: {release_title}")
        print(f"[DRY-RUN] Found {len(files_to_upload)} files to upload:")
        for f in files_to_upload:
            print(f"  - {f.name} ({f.stat().st_size} bytes)")
        return

    # Check token
    if not token:
        print("Error: GITHUB_RELEASE_TOKEN is not set.", file=sys.stderr)
        sys.exit(1)

    existing = find_release_by_tag(tag, token)
    if existing:
        is_draft = existing.get("draft", False)
        if not replace and not is_draft:
            print(
                f"Error: Release tag {tag} already exists. Use --replace to overwrite.",
                file=sys.stderr,
            )
            sys.exit(1)
        reason = "incomplete draft" if is_draft and not replace else "replace requested"
        print(f"Replacing existing release for tag {tag} (ID {existing['id']}, {reason})...")
        delete_release(existing["id"], token)

    print(f"Creating draft release {tag}...")
    release = create_release(tag, release_title, body, token, draft=True)
    release_id = release["id"]

    print(f"Draft release created (ID {release_id}). Uploading {len(files_to_upload)} assets...")
    for f in files_to_upload:
        print(f"  Uploading {f.name} ({f.stat().st_size} bytes)...")
        upload_asset(release_id, f, token)

    print("Verifying uploaded assets...")
    verify_release_assets(release_id, files_to_upload, token)

    print(f"Publishing release {tag} (updating draft=false)...")
    publish_draft_release(release_id, token)
    print(f"Successfully published open data release {tag}!")


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish open data release to GitHub.")
    parser.add_argument(
        "--dir",
        type=Path,
        required=True,
        help="Path to built release directory.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace existing release if tag already exists.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files and operations without modifying GitHub.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    load_env_pipeline(project_root)

    token = os.environ.get("GITHUB_RELEASE_TOKEN")

    publish_release(
        release_dir=args.dir,
        replace=args.replace,
        dry_run=args.dry_run,
        token=token,
    )


if __name__ == "__main__":
    main()
