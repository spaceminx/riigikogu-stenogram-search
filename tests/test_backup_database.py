"""Tests for scripts/backup_database.py."""

import gzip
import sqlite3

import pytest

from scripts.backup_database import backup_database


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE speeches (id INTEGER PRIMARY KEY, text TEXT)")
    conn.executemany("INSERT INTO speeches (text) VALUES (?)", [("kõne",), ("teine kõne",)])
    conn.commit()
    conn.close()


def test_backup_is_gzipped_valid_copy(tmp_path):
    db = tmp_path / "riigikogu.sqlite"
    _make_db(db)
    dest = tmp_path / "backups"

    target = backup_database(db, dest, keep=4, tmp_dir=tmp_path, backup_date="2026-10-25")

    assert target == dest / "riigikogu-2026-10-25.sqlite.gz"
    restored = tmp_path / "restored.sqlite"
    with gzip.open(target, "rb") as f_in:
        restored.write_bytes(f_in.read())
    conn = sqlite3.connect(restored)
    assert conn.execute("SELECT COUNT(*) FROM speeches").fetchone()[0] == 2
    conn.close()
    # No temp or partial files are left behind
    assert sorted(p.name for p in dest.iterdir()) == ["riigikogu-2026-10-25.sqlite.gz"]
    assert not list(tmp_path.glob("riigikogu-backup-*"))


def test_backup_rotation_keeps_newest(tmp_path):
    db = tmp_path / "riigikogu.sqlite"
    _make_db(db)
    dest = tmp_path / "backups"
    dest.mkdir()
    (dest / "notes.txt").write_text("keep me", encoding="utf-8")

    for day in ["2026-10-04", "2026-10-11", "2026-10-18", "2026-10-25", "2026-11-01"]:
        backup_database(db, dest, keep=3, tmp_dir=tmp_path, backup_date=day)

    assert sorted(p.name for p in dest.iterdir()) == [
        "notes.txt",
        "riigikogu-2026-10-18.sqlite.gz",
        "riigikogu-2026-10-25.sqlite.gz",
        "riigikogu-2026-11-01.sqlite.gz",
    ]


def test_backup_missing_database_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        backup_database(tmp_path / "missing.sqlite", tmp_path / "backups")
