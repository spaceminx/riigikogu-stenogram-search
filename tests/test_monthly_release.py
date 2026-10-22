import gzip
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.build_open_data_release import build_open_data_release
from scripts.monthly_release import (
    acquire_backup_with_retry,
    cleanup_local_releases,
    run_monthly_release,
    select_releases_to_delete,
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


def test_select_releases_to_delete():
    # 1. <= 12 tags -> nothing deleted
    tags_12 = [f"data-2025-{i:02d}-01" for i in range(1, 13)]
    assert select_releases_to_delete(tags_12, keep_latest=12) == []

    # 2. 14 tags across 2 years (2025 and 2026)
    # 2025: 01..12 (12 tags)
    # 2026: 01, 02 (2 tags)
    # Total: 14 tags.
    # keep_latest=12 keeps: data-2025-03-01 to data-2026-02-01 (12 newest tags).
    # Earliest of each calendar year:
    #   2025: data-2025-01-01
    #   2026: data-2026-01-01 (already in the 12 newest)
    # Deletions: data-2025-02-01
    tags_14 = [f"data-2025-{i:02d}-01" for i in range(1, 13)] + [
        "data-2026-01-01",
        "data-2026-02-01",
    ]
    to_delete = select_releases_to_delete(tags_14, keep_latest=12)
    assert to_delete == ["data-2025-02-01"]

    # 3. Non-matching tags are completely ignored
    mixed_tags = ["v1.0.0", "beta-2025-01-01", "data-2025-01-01", "other"]
    assert select_releases_to_delete(mixed_tags, keep_latest=12) == []

    # 4. Multi-year scenario with multiple deletions
    # 2024: 01, 02, 03
    # 2025: 01..12
    # Total 15 tags. Earliest 2024 kept (2024-01-01). 12 newest kept (2024-04..2025-12 or 2024-03..2025-12).
    tags_multi = [f"data-2024-{i:02d}-01" for i in range(1, 4)] + [
        f"data-2025-{i:02d}-01" for i in range(1, 13)
    ]
    # Total 15 tags.
    # Newest 12: data-2024-04-01 (doesn't exist) -> data-2025-01-01 to data-2025-12-01 (12 tags)
    # Earliest of each year: data-2024-01-01, data-2025-01-01
    # Deletions: data-2024-02-01, data-2024-03-01
    to_del = select_releases_to_delete(tags_multi, keep_latest=12)
    assert to_del == ["data-2024-02-01", "data-2024-03-01"]


def test_safety_guard_aborts_on_excessive_deletions(
    sample_sqlite_db: Path, tmp_path: Path, monkeypatch
):
    # If more than 3 releases would be deleted, abort with exit 1
    monkeypatch.setenv("GITHUB_RELEASE_TOKEN", "mock-token")
    mock_releases = [{"id": i, "tag_name": f"data-2024-{i:02d}-01"} for i in range(1, 6)] + [
        {"id": 10 + i, "tag_name": f"data-2025-{i:02d}-01"} for i in range(1, 13)
    ]
    # Total 17 tags -> 4 would be deleted (2024-02, 2024-03, 2024-04, 2024-05)

    with (
        patch("scripts.monthly_release.find_release_by_tag", return_value=None),
        patch("scripts.monthly_release.list_repo_releases", return_value=mock_releases),
        patch("scripts.monthly_release.publish_release"),
        patch("scripts.monthly_release.PROJECT_ROOT", tmp_path),
    ):
        code = run_monthly_release(
            dry_run=False,
            keep_latest=12,
            release_date="2026-10-22",
            source_db=sample_sqlite_db,
        )
        assert code == 1


def test_existing_tag_skips_without_force(sample_sqlite_db: Path, monkeypatch):
    monkeypatch.setenv("GITHUB_RELEASE_TOKEN", "mock-token")
    mock_existing = {"id": 123, "tag_name": "data-2026-10-22", "draft": False}

    with (
        patch("scripts.monthly_release.find_release_by_tag", return_value=mock_existing),
        patch("scripts.monthly_release.acquire_backup_with_retry") as mock_backup,
    ):
        code = run_monthly_release(
            dry_run=False,
            force=False,
            release_date="2026-10-22",
            source_db=sample_sqlite_db,
        )
        assert code == 0
        mock_backup.assert_not_called()


def test_existing_draft_release_triggers_rebuild_and_replace(
    sample_sqlite_db: Path, tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("GITHUB_RELEASE_TOKEN", "mock-token")
    mock_draft_existing = {"id": 456, "tag_name": "data-2026-10-22", "draft": True}

    with (
        patch("scripts.monthly_release.find_release_by_tag", return_value=mock_draft_existing),
        patch("scripts.monthly_release.acquire_backup_with_retry") as mock_backup,
        patch("scripts.monthly_release.build_open_data_release") as mock_build,
        patch("scripts.monthly_release.publish_release") as mock_publish,
        patch("scripts.monthly_release.list_repo_releases", return_value=[]),
    ):
        code = run_monthly_release(
            dry_run=False,
            force=False,  # Note: force is False, but draft triggers replace!
            release_date="2026-10-22",
            source_db=sample_sqlite_db,
        )
        assert code == 0
        assert mock_backup.called
        assert mock_build.called
        assert mock_publish.called
        # Check that replace was passed as True to publish_release
        _, kwargs = mock_publish.call_args
        assert kwargs["replace"] is True


def test_db_copy_removed_on_exception(sample_sqlite_db: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GITHUB_RELEASE_TOKEN", "mock-token")
    backup_db = sample_sqlite_db.parent / "release_copy.sqlite"

    with (
        patch("scripts.monthly_release.find_release_by_tag", return_value=None),
        patch(
            "scripts.monthly_release.build_open_data_release",
            side_effect=ValueError("Build failed"),
        ),
    ):
        code = run_monthly_release(
            dry_run=False,
            release_date="2026-10-22",
            source_db=sample_sqlite_db,
        )
        assert code == 1
        assert not backup_db.exists()


def test_lock_retry_times_out(sample_sqlite_db: Path, tmp_path: Path):
    backup_db = tmp_path / "backup.sqlite"
    # Create active lock
    lock_file = sample_sqlite_db.parent / ".sync.lock"
    lock_file.write_text("12345\n2026-10-22T00:00:00Z\n", encoding="utf-8")

    current_time = [1000.0]

    def mock_time():
        return current_time[0]

    def mock_sleep(seconds):
        current_time[0] += seconds

    with (
        patch("scripts.monthly_release.time.time", side_effect=mock_time),
        patch("scripts.monthly_release.time.sleep", side_effect=mock_sleep) as sleep_spy,
        pytest.raises(RuntimeError, match="Timed out waiting for sync_lock"),
    ):
        acquire_backup_with_retry(
            source_db=sample_sqlite_db,
            backup_db=backup_db,
            max_wait_seconds=600,
            retry_interval_seconds=300,
        )
        assert sleep_spy.call_count >= 2


def test_person_export_normalizes_sentinel_end_date(
    sample_sqlite_db: Path, tmp_path: Path, monkeypatch
):
    # Mock person_factions.json with 2099-12-31 sentinel
    factions_data = {
        "p-1": [
            {"faction": "Fraktsioon A", "start": "2023-04-01", "end": "2023-10-01"},
            {"faction": "Fraktsioon B", "start": "2023-10-01", "end": "2099-12-31"},
        ]
    }
    mock_pf_path = tmp_path / "person_factions.json"
    mock_pf_path.write_text(json.dumps(factions_data), encoding="utf-8")

    with patch("scripts.build_open_data_release.PROJECT_ROOT", tmp_path):
        processed_dir = tmp_path / "data" / "processed"
        processed_dir.mkdir(parents=True)
        (processed_dir / "person_factions.json").write_text(
            json.dumps(factions_data), encoding="utf-8"
        )

        out_dir = tmp_path / "test_out"
        build_open_data_release(sample_sqlite_db, out_dir, release_date="2026-10-22")

        p_file = out_dir / "persons.jsonl.gz"
        assert p_file.exists()

        with gzip.open(p_file, "rt", encoding="utf-8") as f:
            line = f.readline()
            person = json.loads(line)
            factions = person.get("factions", [])
            assert len(factions) == 2
            assert factions[0]["end"] == "2023-10-01"
            assert factions[1]["end"] is None  # Normalized from 2099-12-31 to null!


def test_cleanup_local_releases(tmp_path: Path):
    rel_base = tmp_path / "data" / "release"
    rel_base.mkdir(parents=True)
    d1 = rel_base / "2026-08-01"
    d2 = rel_base / "2026-09-01"
    d3 = rel_base / "2026-10-01"
    d1.mkdir()
    d2.mkdir()
    d3.mkdir()

    cleanup_local_releases(rel_base, keep_dir_name="2026-10-01")
    assert not d1.exists()
    assert not d2.exists()
    assert d3.exists()


def test_build_with_custom_date_sets_version_and_readme_and_publish_tag(
    sample_sqlite_db: Path, tmp_path: Path, monkeypatch
):
    # build with release_date="2026-11-01" -> manifest version, README version and publish dry-run tag are 2026-11-01
    out_dir = tmp_path / "data" / "release" / "2026-11-01"
    manifest = build_open_data_release(sample_sqlite_db, out_dir, release_date="2026-11-01")

    # 1. Manifest version
    assert manifest["version"] == "2026-11-01"

    # 2. Manifest created_at is real time (not midnight f"{date_str}T00:00:00Z")
    created_at = manifest["created_at"]
    assert not created_at.endswith("T00:00:00Z")
    assert "T" in created_at

    # 3. README version
    readme_content = (out_dir / "README.md").read_text(encoding="utf-8")
    assert "**Versioon / kuupäev:** 2026-11-01" in readme_content

    # 4. Publish dry-run derives tag data-2026-11-01
    with patch("builtins.print") as mock_print:
        from scripts.publish_open_data_release import publish_release

        publish_release(release_dir=out_dir, dry_run=True)
        # Check printed tag
        printed_lines = [call[0][0] for call in mock_print.call_args_list if call[0]]
        assert any("[DRY-RUN] Release tag: data-2026-11-01" in line for line in printed_lines)
