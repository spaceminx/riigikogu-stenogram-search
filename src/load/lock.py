import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from config import DATABASE_DIR

LOCK_FILENAME = ".sync.lock"
DEFAULT_STALE_HOURS = 3.0


@contextmanager
def sync_lock(database_dir: str | None = None, stale_hours: float = DEFAULT_STALE_HOURS):
    """Context manager acquiring database/.sync.lock.

    If the lock file exists and is newer than stale_hours (default 3 hours),
    prints "Sync already running" and exits with status 1.
    If the lock file exists and is older, overwrites it with a warning.
    Always releases the lock on exit (unless active lock prevented acquisition).
    """
    db_dir = database_dir if database_dir is not None else DATABASE_DIR
    Path(db_dir).mkdir(parents=True, exist_ok=True)
    lock_file = os.path.join(db_dir, LOCK_FILENAME)
    lock_created = False

    try:
        if os.path.exists(lock_file):
            try:
                mtime = os.path.getmtime(lock_file)
                age = time.time() - mtime
                if age < stale_hours * 3600:
                    print("Sync already running")
                    sys.exit(1)
                else:
                    print(f"Notice: Stale lock file ({age:.0f}s old) found. Overwriting.")
            except SystemExit:
                raise
            except Exception as e:
                print(f"Notice: Could not check lock file: {e}")

        with open(lock_file, "w", encoding="utf-8") as f:
            f.write(f"{os.getpid()}\n{datetime.now(timezone.utc).isoformat()}\n")
        lock_created = True
        yield lock_file
    finally:
        if lock_created and os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except Exception as e:
                print(f"Notice: Could not remove lock file {lock_file}: {e}")
