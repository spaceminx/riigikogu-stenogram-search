#!/usr/bin/env python3
"""Monthly open data release automation with retention.

Executes in-process:
1. Checks if release tag data-YYYY-MM-DD already exists on GitHub (skips unless --force).
2. Acquires sync_lock, creates SQLite backup database/release_copy.sqlite, releases lock immediately.
3. Builds open data release into data/release/<YYYY-MM-DD> using build_open_data_release.
4. Publishes release to GitHub using publish_release.
5. Performs retention: keeps newest 12 releases + earliest release of each calendar year.
   Deletes obsolete releases and tag refs (safety guard: aborts if >3 deletions).
6. Cleanup: deletes database/release_copy.sqlite; on success keeps only the newest local dir in data/release/.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.build_open_data_release import build_open_data_release
from scripts.publish_open_data_release import (
    API_BASE,
    REPO,
    find_release_by_tag,
    github_api_request,
    list_repo_releases,
    load_env_pipeline,
    publish_release,
)
from src.load.lock import sync_lock

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_TAG_REGEX = re.compile(r"^data-\d{4}-\d{2}-\d{2}$")


def select_releases_to_delete(tags: list[str], keep_latest: int = 12) -> list[str]:
    """Select release tags to delete according to retention policy.

    Retention rule:
    - Only tags matching ^data-\\d{4}-\\d{2}-\\d{2}$ are considered.
    - If total matching tags <= keep_latest, nothing is deleted.
    - Keep the newest `keep_latest` tags.
    - Keep the earliest-dated release of each calendar year.
    - Return sorted list of tags to delete.
    """
    matching = [t for t in tags if DATA_TAG_REGEX.match(t)]
    if len(matching) <= keep_latest:
        return []

    sorted_tags = sorted(matching)
    keep = set(sorted_tags[-keep_latest:])

    earliest_by_year: dict[str, str] = {}
    for t in sorted_tags:
        # tag format: data-YYYY-MM-DD
        year = t.split("-")[1]
        if year not in earliest_by_year:
            earliest_by_year[year] = t

    for t in earliest_by_year.values():
        keep.add(t)

    return [t for t in sorted_tags if t not in keep]


def acquire_backup_with_retry(
    source_db: Path,
    backup_db: Path,
    max_wait_seconds: int = 3600,
    retry_interval_seconds: int = 300,
) -> None:
    """Acquire sync_lock and copy database using sqlite3 backup API.

    Retries every retry_interval_seconds for up to max_wait_seconds if sync_lock is held.
    """
    start_time = time.time()
    db_dir = str(source_db.parent)

    while True:
        try:
            with sync_lock(database_dir=db_dir):
                print(f"Acquired sync_lock. Backing up {source_db} -> {backup_db}...")
                backup_db.parent.mkdir(parents=True, exist_ok=True)
                if backup_db.exists():
                    backup_db.unlink()

                src_uri = f"file:{source_db.resolve()}?mode=ro"
                src_conn = sqlite3.connect(src_uri, uri=True)
                dest_conn = sqlite3.connect(str(backup_db.resolve()))

                try:
                    src_conn.backup(dest_conn)
                finally:
                    dest_conn.close()
                    src_conn.close()

                print("Database backup completed successfully. Released sync_lock.")
                return
        except SystemExit as e:
            # sync_lock exits with status 1 when lock is held
            elapsed = time.time() - start_time
            if elapsed + retry_interval_seconds > max_wait_seconds:
                print(
                    f"Error: sync_lock held continuously for {elapsed:.0f}s. Exceeded {max_wait_seconds}s timeout.",
                    file=sys.stderr,
                )
                raise RuntimeError("Timed out waiting for sync_lock") from e

            print(
                f"Notice: sync_lock currently held. Retrying in {retry_interval_seconds}s "
                f"({elapsed:.0f}s / {max_wait_seconds}s elapsed)..."
            )
            time.sleep(retry_interval_seconds)


def delete_tag_ref(tag: str, token: str) -> None:
    """Delete git tag reference from GitHub."""
    url = f"{API_BASE}/repos/{REPO}/git/refs/tags/{tag}"
    github_api_request(url, method="DELETE", token=token)


def cleanup_local_releases(release_base_dir: Path, keep_dir_name: str) -> None:
    """Keep only the newest directory in data/release/, removing older ones."""
    if not release_base_dir.exists():
        return

    for entry in release_base_dir.iterdir():
        if entry.is_dir() and entry.name != keep_dir_name:
            print(f"Cleaning up older local release dir: {entry}")
            shutil.rmtree(entry, ignore_errors=True)


def run_monthly_release(
    dry_run: bool = False,
    force: bool = False,
    keep_latest: int = 12,
    release_date: str | None = None,
    source_db: Path | None = None,
) -> int:
    """Run monthly open data release and retention workflow.

    Returns exit code (0 for success/skip, non-zero for error).
    """
    load_env_pipeline(PROJECT_ROOT)
    token = os.environ.get("GITHUB_RELEASE_TOKEN")

    today_str = release_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tag = f"data-{today_str}"
    print(f"Target release tag: {tag}")

    src_db = source_db or (PROJECT_ROOT / "database" / "riigikogu.sqlite")
    backup_db = src_db.parent / "release_copy.sqlite"
    release_dir = PROJECT_ROOT / "data" / "release" / today_str

    # 1. Check if release already exists on GitHub
    should_replace = force
    if not dry_run:
        if not token:
            print("Error: GITHUB_RELEASE_TOKEN is not set.", file=sys.stderr)
            return 1

        existing = find_release_by_tag(tag, token)
        if existing:
            if existing.get("draft", False):
                print(
                    f"Notice: Release {tag} exists as an incomplete draft. Rebuilding and replacing..."
                )
                should_replace = True
            elif not force:
                print(
                    f"Notice: Release {tag} already exists on GitHub. Skipping build (use --force to overwrite)."
                )
                return 0

    try:
        # 2. Acquire lock & backup DB
        print(f"Initiating database backup from {src_db} to {backup_db}...")
        acquire_backup_with_retry(src_db, backup_db)

        # 3. Build open data release
        print(f"Building open data release into {release_dir}...")
        build_open_data_release(
            db_path=backup_db,
            out_dir=release_dir,
            release_date=today_str,
        )

        # 4. Publish release
        print(f"Publishing release {tag}...")
        publish_release(
            release_dir=release_dir,
            replace=should_replace,
            dry_run=dry_run,
            token=token,
        )

        # 5. Retention policy
        print("Checking release retention policy...")
        if dry_run:
            if token:
                all_releases = list_repo_releases(token)
                all_tags = [r["tag_name"] for r in all_releases if "tag_name" in r]
            else:
                all_tags = [tag]
            to_delete = select_releases_to_delete(all_tags, keep_latest=keep_latest)
            print(f"[DRY-RUN] Retention plan: {len(to_delete)} release(s) to delete: {to_delete}")
        else:
            all_releases = list_repo_releases(token)  # type: ignore[arg-type]
            release_map = {r["tag_name"]: r["id"] for r in all_releases if "tag_name" in r}
            all_tags = list(release_map.keys())

            to_delete = select_releases_to_delete(all_tags, keep_latest=keep_latest)
            print(
                f"Retention evaluated: {len(to_delete)} release(s) selected for deletion: {to_delete}"
            )

            if len(to_delete) > 3:
                print(
                    f"Error: Safety guard triggered: {len(to_delete)} releases selected for deletion (maximum 3 allowed). "
                    "Aborting deletion to prevent accidental data loss.",
                    file=sys.stderr,
                )
                return 1

            for tag_to_del in to_delete:
                rel_id = release_map.get(tag_to_del)
                if rel_id:
                    print(f"Deleting release {tag_to_del} (ID {rel_id})...")
                    delete_release_from_github(rel_id, token)  # type: ignore[arg-type]
                print(f"Deleting git tag ref for {tag_to_del}...")
                try:
                    delete_tag_ref(tag_to_del, token)  # type: ignore[arg-type]
                except Exception as e:
                    print(f"Warning: Failed to delete git tag ref {tag_to_del}: {e}")

        # 6. Local directory cleanup on success
        cleanup_local_releases(release_dir.parent, today_str)
        print("Monthly release completed successfully.")
        return 0

    except Exception as e:
        print(f"Error during monthly release: {e}", file=sys.stderr)
        return 1
    finally:
        # Always remove release_copy.sqlite
        if backup_db.exists():
            try:
                print(f"Removing temporary backup {backup_db}...")
                backup_db.unlink()
            except Exception as e:
                print(
                    f"Warning: Could not remove temporary backup {backup_db}: {e}", file=sys.stderr
                )


def delete_release_from_github(release_id: int, token: str) -> None:
    """Helper to delete release by ID."""
    url = f"{API_BASE}/repos/{REPO}/releases/{release_id}"
    github_api_request(url, method="DELETE", token=token)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automate monthly Riigivaade open data release with backup and retention."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build release, simulate publish and retention without modifying GitHub.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing release if today's tag already exists.",
    )
    parser.add_argument(
        "--keep-latest",
        type=int,
        default=12,
        help="Number of newest releases to keep in retention (default: 12).",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to source SQLite database (default: database/riigikogu.sqlite).",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Override release date in YYYY-MM-DD format (default: today).",
    )
    args = parser.parse_args()

    exit_code = run_monthly_release(
        dry_run=args.dry_run,
        force=args.force,
        keep_latest=args.keep_latest,
        release_date=args.date,
        source_db=args.db,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
