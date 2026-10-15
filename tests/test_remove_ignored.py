import json
import os
from unittest.mock import MagicMock, patch

import pytest

from config import IGNORED_VERBATIMS
from scripts.remove_ignored_sessions import remove_ignored_sessions
from src.load.database import SessionLocal
from src.load.loader import create_tables
from src.load.models import Lemma, Speech, SpeechAlias, SpeechTerm


@pytest.fixture
def test_env(tmp_path, monkeypatch):
    """Setup isolated test directory and test database for ignored session tests."""
    data_dir = tmp_path / "processed"
    data_dir.mkdir(parents=True, exist_ok=True)
    create_tables()
    return data_dir


def test_remove_ignored_sessions_dry_run_leaves_data_untouched(test_env, monkeypatch):
    data_dir = str(test_env)
    session = SessionLocal()

    # Create dummy speeches in DB
    s_valid = Speech(
        speech_key="202103241400_1",
        date="2021-03-24",
        time="1400",
        source_file="2021-03-24_1400.api",
        source_url="https://stenogrammid.riigikogu.ee/test1",
        speaker="Speaker A",
        text="Normal speech",
    )
    s_ignored = Speech(
        speech_key="202103250048_1",
        date="2021-03-24",
        time="0048",
        source_file="2021-03-24_0048.api",
        source_url="https://stenogrammid.riigikogu.ee/test2",
        speaker="Speaker B",
        text="Duplicate speech",
    )
    session.add_all([s_valid, s_ignored])
    session.flush()

    lemma = Lemma(lemma="testlemma")
    session.add(lemma)
    session.flush()

    term = SpeechTerm(speech_id=s_ignored.id, lemma_id=lemma.id, count=1)
    alias = SpeechAlias(alias_speech_key="old_key_1", speech_id=s_ignored.id)
    session.add_all([term, alias])
    session.commit()

    # Create 2021.jsonl
    jsonl_file = os.path.join(data_dir, "2021.jsonl")
    speeches = [
        {"speech_key": "202103241400_1", "source_file": "2021-03-24_1400.api", "text": "Normal"},
        {"speech_key": "202103250048_1", "source_file": "2021-03-24_0048.api", "text": "Duplicate"},
    ]
    with open(jsonl_file, "w", encoding="utf-8") as f:
        for s in speeches:
            f.write(json.dumps(s) + "\n")

    try:
        # Dry-run
        ret = remove_ignored_sessions(year="2021", apply=False, data_dir=data_dir)
        assert ret == 0

        # Assert JSONL file still has 2 speeches
        with open(jsonl_file, encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        assert len(lines) == 2

        # Assert DB rows still exist
        assert session.query(Speech).filter(Speech.id == s_ignored.id).count() == 1
        assert session.query(SpeechTerm).filter(SpeechTerm.speech_id == s_ignored.id).count() == 1
        assert session.query(SpeechAlias).filter(SpeechAlias.speech_id == s_ignored.id).count() == 1

    finally:
        session.query(SpeechTerm).filter(
            SpeechTerm.speech_id.in_([s_valid.id, s_ignored.id])
        ).delete(synchronize_session=False)
        session.query(SpeechAlias).filter(
            SpeechAlias.speech_id.in_([s_valid.id, s_ignored.id])
        ).delete(synchronize_session=False)
        session.query(Speech).filter(Speech.id.in_([s_valid.id, s_ignored.id])).delete(
            synchronize_session=False
        )
        session.query(Lemma).filter(Lemma.id == lemma.id).delete(synchronize_session=False)
        session.commit()
        session.close()


def test_remove_ignored_sessions_apply_removes_rows_and_is_idempotent(test_env, monkeypatch):
    data_dir = str(test_env)
    session = SessionLocal()

    s_valid = Speech(
        speech_key="202103241400_10",
        date="2021-03-24",
        time="1400",
        source_file="2021-03-24_1400.api",
        source_url="https://stenogrammid.riigikogu.ee/test10",
        speaker="Speaker A",
        text="Normal speech",
    )
    s_ignored = Speech(
        speech_key="202103250048_10",
        date="2021-03-24",
        time="0048",
        source_file="2021-03-24_0048.api",
        source_url="https://stenogrammid.riigikogu.ee/test11",
        speaker="Speaker B",
        text="Duplicate speech",
    )
    session.add_all([s_valid, s_ignored])
    session.flush()

    lemma = Lemma(lemma="testlemma2")
    session.add(lemma)
    session.flush()

    term = SpeechTerm(speech_id=s_ignored.id, lemma_id=lemma.id, count=1)
    alias = SpeechAlias(alias_speech_key="old_key_10", speech_id=s_ignored.id)
    session.add_all([term, alias])
    session.commit()

    valid_id = s_valid.id
    ignored_id = s_ignored.id
    lemma_id = lemma.id

    jsonl_file = os.path.join(data_dir, "2021.jsonl")
    speeches = [
        {
            "speech_key": "202103241400_10",
            "source_file": "2021-03-24_1400.api",
            "text": "Normal",
        },
        {
            "speech_key": "202103250048_10",
            "source_file": "2021-03-24_0048.api",
            "text": "Duplicate",
        },
    ]
    with open(jsonl_file, "w", encoding="utf-8") as f:
        for s in speeches:
            f.write(json.dumps(s) + "\n")

    try:
        # Mock upload_to_b2
        mock_upload = MagicMock(return_value=True)
        monkeypatch.setattr("scripts.remove_ignored_sessions.upload_to_b2", mock_upload)

        # Apply
        ret = remove_ignored_sessions(year="2021", apply=True, data_dir=data_dir)
        assert ret == 0
        mock_upload.assert_called_once_with(only_files=["2021.jsonl"])

        # Assert JSONL file now has only 1 speech
        with open(jsonl_file, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        assert len(lines) == 1
        assert lines[0]["speech_key"] == "202103241400_10"

        # Assert DB rows for ignored speech were deleted
        session.close()
        check_session = SessionLocal()
        assert check_session.query(Speech).filter(Speech.id == ignored_id).count() == 0
        assert (
            check_session.query(SpeechTerm).filter(SpeechTerm.speech_id == ignored_id).count() == 0
        )
        assert (
            check_session.query(SpeechAlias).filter(SpeechAlias.speech_id == ignored_id).count()
            == 0
        )

        # Assert valid speech still exists
        assert check_session.query(Speech).filter(Speech.id == valid_id).count() == 1
        check_session.close()

        # Idempotency check: second run should report no ignored rows found and return 0
        ret_second = remove_ignored_sessions(year="2021", apply=True, data_dir=data_dir)
        assert ret_second == 0

    finally:
        cleanup_session = SessionLocal()
        cleanup_session.query(Speech).filter(Speech.id == valid_id).delete(
            synchronize_session=False
        )
        cleanup_session.query(Lemma).filter(Lemma.id == lemma_id).delete(synchronize_session=False)
        cleanup_session.commit()
        cleanup_session.close()


def test_remove_ignored_refuses_mixed_source_file(test_env, monkeypatch):
    data_dir = str(test_env)
    jsonl_file = os.path.join(data_dir, "2021.jsonl")
    speeches = [
        {"speech_key": "202103241400_1", "source_file": "same_file.api", "text": "Normal"},
        {"speech_key": "202103250048_1", "source_file": "same_file.api", "text": "Duplicate"},
    ]
    with open(jsonl_file, "w", encoding="utf-8") as f:
        for s in speeches:
            f.write(json.dumps(s) + "\n")

    ret = remove_ignored_sessions(year="2021", apply=True, data_dir=data_dir)
    assert ret == 1

    # Ensure file was not modified
    with open(jsonl_file, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    assert len(lines) == 2


def test_remove_ignored_missing_file_suggests_download(test_env, capsys):
    data_dir = str(test_env)
    ret = remove_ignored_sessions(year="1999", apply=False, data_dir=data_dir)
    assert ret == 1
    captured = capsys.readouterr()
    assert "download_from_b2.py --year 1999" in captured.out
    assert "--all" not in captured.out


def test_fetchers_skip_ignored_verbatim(tmp_path, monkeypatch, capsys):

    # Test main fetcher skipping logic
    ignored_code = list(IGNORED_VERBATIMS.keys())[0]
    assert ignored_code == "202103250048"

    # Seed required metadata for backfill_history
    (tmp_path / "factions_map.json").write_text(
        json.dumps({"Jüri Ratas": [{"faction": "KESK"}]}), encoding="utf-8"
    )
    (tmp_path / "persons.json").write_text(
        json.dumps([{"uuid": "u1", "full_name": "Jüri Ratas"}]), encoding="utf-8"
    )

    # Verify backfill_history skips ignored verbatim
    mock_resp = [
        {
            "link": f"https://stenogrammid.riigikogu.ee/{ignored_code}",
            "date": "2021-03-25T00:48:00",
        }
    ]
    with (
        patch("scripts.backfill_history.fetch_month_verbatims", return_value=mock_resp),
        patch("scripts.backfill_history.fetch_rich_meeting_data") as mock_fetch,
    ):
        from scripts.backfill_history import run_backfill

        run_backfill(
            start_date="2021-03-01",
            end_date="2021-03-31",
            year="2021",
            processed_dir=str(tmp_path),
        )
        mock_fetch.assert_not_called()
    captured = capsys.readouterr()
    assert f"Skipping ignored verbatim {ignored_code}" in captured.out
