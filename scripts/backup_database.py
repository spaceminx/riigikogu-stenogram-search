#!/usr/bin/env python3
"""Back up the SQLite database to a gzip file outside the WSL disk, keeping the newest N copies.

Standard library only, so it runs with the host's python3 from root crontab:
the containers mount only ./database and ./data, while the backup goes to /mnt/c/....

Steps: SQLite online backup API (safe while the API reads/writes) into a temp file,
PRAGMA quick_check on the copy, gzip into <dest>/riigikogu-YYYY-MM-DD.sqlite.gz,
then delete the oldest backups beyond --keep.
"""

from __future__ import annotations

import argparse
import gzip
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "database" / "riigikogu.sqlite"
BACKUP_NAME_RE = re.compile(r"^riigikogu-\d{4}-\d{2}-\d{2}\.sqlite\.gz$")


def backup_database(
    db_path: Path,
    dest_dir: Path,
    keep: int = 4,
    tmp_dir: Path | None = None,
    backup_date: str | None = None,
) -> Path:
    """Create a verified, gzip-compressed backup of db_path in dest_dir and rotate old ones."""
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    day = backup_date or date.today().isoformat()
    target = dest_dir / f"riigikogu-{day}.sqlite.gz"

    fd, tmp_name = tempfile.mkstemp(prefix="riigikogu-backup-", suffix=".sqlite", dir=tmp_dir)
    os.close(fd)
    tmp_db = Path(tmp_name)
    partial = target.with_name(target.name + ".partial")
    try:
        src = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
        dst = sqlite3.connect(tmp_db)
        try:
            src.backup(dst)
            result = dst.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            dst.close()
            src.close()
        if result != "ok":
            raise RuntimeError(f"quick_check failed on the backup copy: {result}")

        with open(tmp_db, "rb") as f_in, gzip.open(partial, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out, length=1024 * 1024)
        os.replace(partial, target)
    finally:
        tmp_db.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)

    backups = sorted(p for p in dest_dir.iterdir() if BACKUP_NAME_RE.match(p.name))
    for old in backups[: max(len(backups) - keep, 0)]:
        print(f"Removing old backup {old}")
        old.unlink()

    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up the SQLite database (gzip, rotated).")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Source database path.")
    parser.add_argument("--dest", type=Path, required=True, help="Backup directory.")
    parser.add_argument("--keep", type=int, default=4, help="Number of backups to keep.")
    parser.add_argument(
        "--tmp-dir",
        type=Path,
        default=None,
        help="Directory for the uncompressed temp copy (default: system temp).",
    )
    args = parser.parse_args()

    if args.keep < 1:
        print("Error: --keep must be at least 1.", file=sys.stderr)
        return 1

    t0 = time.time()
    try:
        target = backup_database(args.db, args.dest, keep=args.keep, tmp_dir=args.tmp_dir)
    except Exception as e:
        print(f"Error: database backup failed: {e}", file=sys.stderr)
        return 1

    size_mb = target.stat().st_size / (1024 * 1024)
    print(f"Backup written: {target} ({size_mb:.1f} MB) in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
