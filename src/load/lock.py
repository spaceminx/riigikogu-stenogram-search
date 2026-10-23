import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from config import DATABASE_DIR

if os.name == "nt":
    import msvcrt
else:
    import fcntl

LOCK_FILENAME = ".sync.lock"
# Windows locks a byte range, which also blocks reads; lock a byte past the pid/time text.
_WINDOWS_LOCK_OFFSET = 1 << 20


def _try_lock(fd: int) -> bool:
    """Take an exclusive, non-blocking lock on fd. Returns False if another process holds it."""
    try:
        if os.name == "nt":
            os.lseek(fd, _WINDOWS_LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            os.lseek(fd, 0, os.SEEK_SET)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _same_file(fd: int, path: str) -> bool:
    try:
        return os.fstat(fd).st_ino == os.stat(path).st_ino
    except FileNotFoundError:
        return False


@contextmanager
def sync_lock(database_dir: str | None = None):
    """Context manager holding an exclusive lock on database/.sync.lock.

    The lock is a kernel lock (flock; msvcrt.locking on Windows) on the open file, so it is
    released when the holder exits or is killed: a leftover file never blocks the next run.
    The pipeline container and the host deploy job see the same lock through the bind mount.
    If another process holds the lock, prints "Sync already running" and exits with status 1.
    The file contains the holder's pid and start time for humans; it is removed on release.
    """
    db_dir = database_dir if database_dir is not None else DATABASE_DIR
    Path(db_dir).mkdir(parents=True, exist_ok=True)
    lock_file = os.path.join(db_dir, LOCK_FILENAME)

    while True:
        fd = os.open(lock_file, os.O_RDWR | os.O_CREAT, 0o644)
        if not _try_lock(fd):
            os.close(fd)
            print("Sync already running")
            sys.exit(1)
        # The previous holder may have removed the file between our open() and lock.
        if os.name == "nt" or _same_file(fd, lock_file):
            break
        os.close(fd)

    try:
        previous = os.read(fd, 200).decode("utf-8", errors="replace").split()
        if previous:
            print(
                f"Notice: Taking over a leftover lock file (pid {previous[0]}); "
                "its holder is no longer running."
            )
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, f"{os.getpid()}\n{datetime.now(timezone.utc).isoformat()}\n".encode())
        yield lock_file
    finally:
        if os.name == "nt":
            try:
                os.lseek(fd, _WINDOWS_LOCK_OFFSET, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            os.close(fd)
            try:
                os.remove(lock_file)
            except OSError as e:
                print(f"Notice: Could not remove lock file {lock_file}: {e}")
        else:
            # Remove while still holding the lock, so no one locks the old file afterwards.
            try:
                os.remove(lock_file)
            except OSError as e:
                print(f"Notice: Could not remove lock file {lock_file}: {e}")
            os.close(fd)
