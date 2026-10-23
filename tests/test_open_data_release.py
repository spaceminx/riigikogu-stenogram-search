import gzip
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.build_open_data_release import build_open_data_release
from scripts.publish_open_data_release import (
    load_env_pipeline,
    publish_release,
)


@pytest.fixture
def sample_sqlite_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test_riigikogu.sqlite"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE persons (
            uuid TEXT PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            full_name TEXT NOT NULL,
            gender TEXT,
            date_of_birth TEXT,
            email TEXT,
            photo_url TEXT,
            electoral_district TEXT,
            seniority_days INTEGER,
            active INTEGER
        )
        """
    )
    cur.execute(
        """
        INSERT INTO persons VALUES (
            'p-1', 'Jüri', 'Ratas', 'Jüri Ratas', 'M', '1978-07-02', 'jyri@example.com',
            'https://example.com/jyri.jpg', 'Harju ja Rapla', 3000, 1
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE speeches (
            id INTEGER PRIMARY KEY,
            date TEXT,
            time TEXT,
            source_file TEXT,
            source_url TEXT,
            agenda_title TEXT,
            video_url TEXT,
            speaker TEXT,
            speaker_role TEXT,
            speaker_faction TEXT,
            speaker_uuid TEXT,
            ems_id TEXT,
            speech_type TEXT,
            external_id TEXT,
            start_time TEXT,
            end_time TEXT,
            duration_seconds INTEGER,
            speech_key TEXT,
            text TEXT,
            text_lemmas TEXT,
            status TEXT
        )
        """
    )
    cur.execute(
        """
        INSERT INTO speeches VALUES (
            1, '2023-05-15', '10:00:00', 'steno-1.html', 'https://example.com/s/1',
            'Päevakord 1', 'https://youtube.com/watch?v=abc12345678', 'Jüri Ratas',
            'Esimees', 'Isamaa', 'p-1', 'ems-1', 'kõne', 'ext-1', '10:00:00',
            '10:05:00', 300, 'sk-1', 'Tere päevast, austatud kolleegid!',
            'tere päev austatud kolleeg', 'FINAL'
        )
        """
    )
    cur.execute(
        """
        INSERT INTO speeches VALUES (
            2, '2024-02-10', '11:00:00', 'steno-2.html', 'https://example.com/s/2',
            'Päevakord 2', NULL, 'Jüri Ratas', 'Liige', 'Isamaa', 'p-1', 'ems-1',
            'kõne', 'ext-2', '11:00:00', '11:02:00', 120, 'sk-2',
            'Teine kõne tekst.', 'teine kõne tekst', 'FINAL'
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE votings (
            uuid TEXT PRIMARY KEY,
            voting_number INTEGER,
            type TEXT,
            description TEXT,
            date TEXT,
            start_time TEXT,
            end_time TEXT,
            membership TEXT,
            sitting_uuid TEXT,
            sitting_title TEXT,
            related_document_uuid TEXT,
            related_document_reference TEXT,
            related_document_title TEXT,
            related_document_type TEXT,
            chairman_uuid TEXT,
            present INTEGER,
            absent INTEGER,
            in_favor INTEGER,
            against INTEGER,
            neutral INTEGER,
            abstained INTEGER,
            sitting_date TEXT,
            sitting_datetime TEXT
        )
        """
    )
    cur.execute(
        """
        INSERT INTO votings VALUES (
            'v-1', 1, 'AVALIK', 'Hääletus eelnõu kohta', '2023-05-15', '12:00:00', '12:01:00',
            'XV', 'sit-1', 'Istung 1', 'draft-1', '123 SE', 'Eelnõu 1', 'DRAFT',
            'chair-1', 87, 10, 55, 30, 2, 4, '2023-05-15', '2023-05-15T12:00:00'
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE votes (
            voting_uuid TEXT,
            member_uuid TEXT,
            faction TEXT,
            decision TEXT,
            PRIMARY KEY (voting_uuid, member_uuid)
        )
        """
    )
    cur.execute(
        """
        INSERT INTO votes VALUES (
            'v-1', 'p-1', 'Isamaa', 'POOLT'
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE attendance (
            id INTEGER PRIMARY KEY,
            session_date TEXT,
            voting_uuid TEXT,
            member_uuid TEXT,
            member_name TEXT,
            faction TEXT,
            status TEXT
        )
        """
    )
    cur.execute(
        """
        INSERT INTO attendance VALUES (
            1, '2023-05-15', 'att-v-1', 'p-1', 'Jüri Ratas', 'Isamaa', 'KOHAL'
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE attendance_checks (
            voting_uuid TEXT PRIMARY KEY,
            sitting_uuid TEXT,
            sitting_title TEXT,
            sitting_datetime TEXT,
            sitting_type TEXT
        )
        """
    )
    cur.execute(
        """
        INSERT INTO attendance_checks VALUES (
            'att-v-1', 'sit-1', 'Istung 1', '2023-05-15T10:00:00', 'REGULAR'
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE agenda_items (
            agenda_item_uuid TEXT PRIMARY KEY,
            sitting_uuid TEXT,
            sitting_date TEXT,
            sitting_datetime TEXT,
            source_file TEXT,
            "order" INTEGER,
            steno_title TEXT,
            api_title TEXT,
            document_type TEXT,
            type_code TEXT,
            stage TEXT,
            decision_code TEXT,
            decision_value TEXT,
            draft_uuid TEXT,
            draft_mark TEXT,
            draft_title TEXT,
            voting_uuids TEXT,
            match_method TEXT
        )
        """
    )
    cur.execute(
        """
        INSERT INTO agenda_items VALUES (
            'item-1', 'sit-1', '2023-05-15', '2023-05-15T10:00:00', 'steno-1.html',
            1, 'Päevakord 1', 'Päevakord 1', 'Eelnõu', 'EELNOU', '1',
            'OTSUSTATUD', 'Vastu võetud', 'draft-1', '123 SE', 'Eelnõu 1', '["v-1"]', 'title_exact'
        )
        """
    )

    conn.commit()
    conn.close()
    return db_path


def test_build_open_data_release(sample_sqlite_db: Path, tmp_path: Path):
    out_dir = tmp_path / "release_1"
    summary = build_open_data_release(sample_sqlite_db, out_dir, release_date="2026-10-22")

    files = summary["files"]
    assert files["speeches_2023.jsonl.gz"]["count"] == 1
    assert files["speeches_2024.jsonl.gz"]["count"] == 1
    assert files["votings.jsonl.gz"]["count"] == 1
    assert files["votes.jsonl.gz"]["count"] == 1
    assert files["attendance.jsonl.gz"]["count"] == 1
    assert files["attendance_checks.jsonl.gz"]["count"] == 1
    assert files["persons.jsonl.gz"]["count"] == 1
    assert files["agenda_items.jsonl.gz"]["count"] == 1

    # Check that speech files by year exist
    s2023 = out_dir / "speeches_2023.jsonl.gz"
    s2024 = out_dir / "speeches_2024.jsonl.gz"
    assert s2023.exists()
    assert s2024.exists()

    with gzip.open(s2023, "rt", encoding="utf-8") as f:
        line = f.readline()
        data = json.loads(line)
        assert data["speech_key"] == "sk-1"
        assert "text_lemmas" not in data  # text_lemmas must be omitted
        assert data["speaker"] == "Jüri Ratas"

    # Check persons: birth_year present, date_of_birth and email omitted
    persons_file = out_dir / "persons.jsonl.gz"
    assert persons_file.exists()
    with gzip.open(persons_file, "rt", encoding="utf-8") as f:
        line = f.readline()
        person = json.loads(line)
        assert person["uuid"] == "p-1"
        assert person["full_name"] == "Jüri Ratas"
        assert person["birth_year"] == 1978
        assert "date_of_birth" not in person
        assert "email" not in person

    # Check votes: has member_name
    votes_file = out_dir / "votes.jsonl.gz"
    assert votes_file.exists()
    with gzip.open(votes_file, "rt", encoding="utf-8") as f:
        vote = json.loads(f.readline())
        assert vote["member_uuid"] == "p-1"
        assert vote["member_name"] == "Jüri Ratas"
        assert vote["decision"] == "POOLT"

    # Check votings: has is_technical
    votings_file = out_dir / "votings.jsonl.gz"
    assert votings_file.exists()
    with gzip.open(votings_file, "rt", encoding="utf-8") as f:
        voting = json.loads(f.readline())
        assert voting["uuid"] == "v-1"
        assert "is_technical" in voting
        assert voting["is_technical"] is False

    # Check SHA256SUMS file
    checksums_file = out_dir / "SHA256SUMS"
    assert checksums_file.exists()
    checksums = checksums_file.read_text(encoding="utf-8")
    assert "speeches_2023.jsonl.gz" in checksums
    assert "persons.jsonl.gz" in checksums
    assert "manifest.json" in checksums

    # Check determinism: with fixed created_at time mock, run build again to another dir and verify identical SHA256SUMS
    out_dir_2 = tmp_path / "release_2"
    fixed_time = "2026-10-22T12:00:00.000000+00:00"
    with patch("scripts.build_open_data_release.datetime") as mock_dt:
        mock_dt.now.return_value.isoformat.return_value = fixed_time
        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
        build_open_data_release(sample_sqlite_db, out_dir, release_date="2026-10-22")
        checksums = (out_dir / "SHA256SUMS").read_text(encoding="utf-8")
        build_open_data_release(sample_sqlite_db, out_dir_2, release_date="2026-10-22")
        checksums_2 = (out_dir_2 / "SHA256SUMS").read_text(encoding="utf-8")
    assert checksums == checksums_2


def test_build_open_data_release_duplicate_agenda_items(sample_sqlite_db: Path, tmp_path: Path):
    conn = sqlite3.connect(sample_sqlite_db)
    cur = conn.cursor()
    # Add a duplicate agenda item for steno-1.html and Päevakord 1
    cur.execute(
        """
        INSERT INTO agenda_items VALUES (
            'item-dup-2', 'sit-1', '2023-05-15', '2023-05-15T11:00:00', 'steno-1.html',
            2, 'Päevakord 1', 'Päevakord 1 Teine', 'Eelnõu', 'EELNOU', '2',
            'OTSUSTATUD', 'Vastu võetud', 'draft-2', '124 SE', 'Eelnõu 2', '["v-2"]', 'title_exact'
        )
        """
    )
    conn.commit()
    conn.close()

    out_dir = tmp_path / "dup_release"
    summary = build_open_data_release(
        sample_sqlite_db,
        out_dir,
        release_date="2026-10-22",
        commit_override="abc12345",
    )
    assert summary["git_commit"] == "abc12345"

    s2023 = out_dir / "speeches_2023.jsonl.gz"
    assert s2023.exists()

    with gzip.open(s2023, "rt", encoding="utf-8") as f:
        lines = f.readlines()
        # Must appear exactly once despite duplicate agenda items!
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["id"] == 1
        assert data["speech_key"] == "sk-1"
        assert data["agenda_item_uuid"] == "item-1"  # MIN(agenda_item_uuid)


def test_publish_open_data_release_helpers(tmp_path: Path, monkeypatch):
    release_dir = tmp_path / "2026-10-22"
    release_dir.mkdir()
    (release_dir / "speeches_2023.jsonl.gz").write_bytes(b"test-speech-bytes")
    (release_dir / "SHA256SUMS").write_text("dummy sha256", encoding="utf-8")

    # Test load_env_pipeline
    env_pipeline = tmp_path / ".env.pipeline"
    env_pipeline.write_text(
        "GITHUB_RELEASE_TOKEN=test-token-123\nOTHER_VAR='abc'\n", encoding="utf-8"
    )
    monkeypatch.delenv("GITHUB_RELEASE_TOKEN", raising=False)
    load_env_pipeline(tmp_path)
    import os

    assert os.environ.get("GITHUB_RELEASE_TOKEN") == "test-token-123"

    # Test publish_release in dry_run mode
    publish_release(release_dir=release_dir, token="mock-token", dry_run=True)


def test_publish_open_data_release_mock_api(tmp_path: Path):
    release_dir = tmp_path / "2026-10-22"
    release_dir.mkdir()
    (release_dir / "data.jsonl.gz").write_bytes(b"data")
    (release_dir / "manifest.json").write_text("{}", encoding="utf-8")
    (release_dir / "SHA256SUMS").write_text("hash data.jsonl.gz\n", encoding="utf-8")

    # 1. list_repo_releases -> []
    mock_list_cm = MagicMock()
    mock_list_cm.__enter__.return_value.read.return_value = b"[]"

    # 2. create_release (draft=True) -> id 9999
    mock_create_cm = MagicMock()
    mock_create_cm.__enter__.return_value.read.return_value = json.dumps(
        {
            "id": 9999,
            "tag_name": "data-2026-10-22",
            "upload_url": "https://uploads.github.com/repos/spaceminx/riigikogu-stenogram-search/releases/9999/assets{?name,label}",
            "assets": [],
            "draft": True,
        }
    ).encode("utf-8")

    # 3..5 upload_asset x3
    mock_upload_cm = MagicMock()
    mock_upload_cm.__enter__.return_value.read.return_value = b"{}"

    # 6. verify_release_assets (GET assets) -> names and sizes match the local files
    mock_assets_cm = MagicMock()
    mock_assets_cm.__enter__.return_value.read.return_value = json.dumps(
        [{"name": f.name, "size": f.stat().st_size} for f in release_dir.iterdir()]
    ).encode("utf-8")

    # 7. publish_draft_release (PATCH draft=False)
    mock_patch_cm = MagicMock()
    mock_patch_cm.__enter__.return_value.read.return_value = json.dumps(
        {"id": 9999, "draft": False}
    ).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [
            mock_list_cm,
            mock_create_cm,
            mock_upload_cm,
            mock_upload_cm,
            mock_upload_cm,
            mock_assets_cm,
            mock_patch_cm,
        ]
        publish_release(
            release_dir=release_dir,
            token="ghp_testtoken",
            dry_run=False,
        )
        assert mock_urlopen.call_count == 7
        assert all(call.kwargs.get("timeout") for call in mock_urlopen.call_args_list)

    # A missing asset keeps the release as a draft (no PATCH)
    mock_short_cm = MagicMock()
    mock_short_cm.__enter__.return_value.read.return_value = json.dumps(
        [{"name": "data.jsonl.gz", "size": 4}]
    ).encode("utf-8")
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [
            mock_list_cm,
            mock_create_cm,
            mock_upload_cm,
            mock_upload_cm,
            mock_upload_cm,
            mock_short_cm,
        ]
        with pytest.raises(RuntimeError, match="do not match the local files"):
            publish_release(release_dir=release_dir, token="ghp_testtoken", dry_run=False)
        assert mock_urlopen.call_count == 6


def test_build_open_data_release_clears_previous_build(sample_sqlite_db: Path, tmp_path: Path):
    """Rebuilding into a release dir removes old files; other non-empty dirs are refused."""
    out_dir = tmp_path / "2026-10-22"
    build_open_data_release(sample_sqlite_db, out_dir, release_date="2026-10-22")
    (out_dir / "speeches_2019.jsonl.gz").write_bytes(b"stale")

    build_open_data_release(sample_sqlite_db, out_dir, release_date="2026-10-22")
    assert not (out_dir / "speeches_2019.jsonl.gz").exists()
    assert (out_dir / "manifest.json").exists()

    other_dir = tmp_path / "not_a_release"
    other_dir.mkdir()
    (other_dir / "notes.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="not a release"):
        build_open_data_release(sample_sqlite_db, other_dir, release_date="2026-10-22")
    assert (other_dir / "notes.txt").exists()
