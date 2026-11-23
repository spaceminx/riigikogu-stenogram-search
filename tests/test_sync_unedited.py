"""An unedited sitting in the database follows its re-fetched file (audit A-1)."""

import json

import pytest

from scripts.sync_database import sync_current_year_speeches
from src.load.database import SessionLocal
from src.load.loader import create_tables
from src.load.models import Speech, SpeechAlias, SpeechTerm

SOURCE = "2026-08-05_1000.api"


def _speech(i, text=None, video_url=None, status="UNEDITED"):
    return {
        "date": "2026-08-05",
        "time": "1000",
        "source_file": SOURCE,
        "source_url": "https://stenogrammid.riigikogu.ee/et/202608051000",
        "agenda_title": "Ootamatu päevakorrapunkt",
        "video_url": video_url,
        "speaker": f"Kõneleja {i}",
        "speaker_uuid": f"sync-unedited-{i}",
        "speech_type": "SPEECH",
        "external_id": 77000 + i,
        "start_time": f"2026-08-05T10:0{i}:00.000",
        "end_time": f"2026-08-05T10:0{i}:30.000",
        "speech_key": f"sync-unedited-key-{i}",
        "text": text or f"esialgne tekst {i}",
        "status": status,
    }


@pytest.fixture
def sync(tmp_path, monkeypatch):
    create_tables()
    monkeypatch.setattr("scripts.sync_database.OUTPUT_DIR_PROCESSED", str(tmp_path))
    session = SessionLocal()

    def cleanup():
        ids = [r[0] for r in session.query(Speech.id).filter(Speech.source_file == SOURCE)]
        if ids:
            session.query(SpeechTerm).filter(SpeechTerm.speech_id.in_(ids)).delete()
            session.query(SpeechAlias).filter(SpeechAlias.speech_id.in_(ids)).delete()
            session.query(Speech).filter(Speech.id.in_(ids)).delete()
        session.commit()

    def run(speeches):
        (tmp_path / "2026.jsonl").write_text(
            "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in speeches), encoding="utf-8"
        )
        assert sync_current_year_speeches("2026") == []
        session.expire_all()
        return session.query(Speech).filter(Speech.source_file == SOURCE).order_by(Speech.id).all()

    cleanup()
    try:
        yield run
    finally:
        cleanup()
        session.close()


def test_unchanged_file_leaves_rows_alone(sync):
    first = sync([_speech(i) for i in range(5)])
    ids = [r.id for r in first]
    again = sync([_speech(i) for i in range(5)])
    assert [r.id for r in again] == ids


def test_video_link_and_text_correction_reach_the_database(sync):
    sync([_speech(i) for i in range(5)])
    rows = sync(
        [_speech(i, text=f"parandatud tekst {i}", video_url=f"https://v/{i}") for i in range(5)]
    )
    assert [r.status for r in rows] == ["UNEDITED"] * 5
    assert [r.video_url for r in rows] == [f"https://v/{i}" for i in range(5)]
    assert [r.text for r in rows] == [f"parandatud tekst {i}" for i in range(5)]


def test_removed_speech_is_removed(sync):
    sync([_speech(i) for i in range(5)])
    rows = sync([_speech(i) for i in range(4)])
    assert [r.speech_key for r in rows] == [f"sync-unedited-key-{i}" for i in range(4)]


def test_much_shorter_file_does_not_replace(sync, capsys):
    first = sync([_speech(i) for i in range(5)])
    rows = sync([_speech(i, video_url="https://v") for i in range(3)])
    assert [r.id for r in rows] == [r.id for r in first]
    assert all(r.video_url is None for r in rows)
    assert "Not replacing unedited session" in capsys.readouterr().out


def test_edited_sitting_is_final(sync):
    sync([_speech(i, status="EDITED") for i in range(3)])
    rows = sync([_speech(i, status="EDITED", video_url="https://v") for i in range(3)])
    assert all(r.video_url is None for r in rows)
