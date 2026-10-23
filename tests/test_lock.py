"""Tests for the kernel-held sync lock (src/load/lock.py)."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.load.lock import sync_lock

PROJECT_ROOT = Path(__file__).resolve().parent.parent

HOLDER = """
import sys, time
from src.load.lock import sync_lock
with sync_lock(database_dir=sys.argv[1]):
    print("locked", flush=True)
    time.sleep(60)
"""


def test_lock_held_by_other_process_then_released_when_it_is_killed(tmp_path):
    env = dict(os.environ, PYTHONPATH=str(PROJECT_ROOT))
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(tmp_path)],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "locked"

        with pytest.raises(SystemExit) as exc_info:
            with sync_lock(database_dir=str(tmp_path)):
                pass
        assert exc_info.value.code == 1
    finally:
        holder.kill()
        holder.wait(timeout=30)
        holder.stdout.close()

    # The killed holder could not clean up, but the kernel released its lock
    # (Windows may release it shortly after the process has exited).
    assert (tmp_path / ".sync.lock").exists()
    for _ in range(50):
        try:
            with sync_lock(database_dir=str(tmp_path)):
                break
        except SystemExit:
            time.sleep(0.1)
    else:
        pytest.fail("lock was not released after the holder was killed")
    assert not (tmp_path / ".sync.lock").exists()
