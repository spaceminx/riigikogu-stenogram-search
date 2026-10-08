import json

from scripts.fetch_stenograms_api import get_faction_for_date, save_session_to_jsonl
from src.load.database import SessionLocal
from src.load.loader import create_tables, load_jsonl_to_database
from src.load.models import Speech, SpeechTerm


def test_save_session_to_jsonl_replacement(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.fetch_stenograms_api.OUTPUT_DIR_PROCESSED", str(tmp_path))

    session_key = "2026-03-01_1500.api"
    initial_speeches = [
        {"date": "2026-03-01", "source_file": session_key, "text": "Draft 1", "status": "UNEDITED"},
        {"date": "2026-03-01", "source_file": session_key, "text": "Draft 2", "status": "UNEDITED"},
    ]

    save_session_to_jsonl("2026", session_key, initial_speeches)

    target_file = tmp_path / "2026.jsonl"
    assert target_file.exists()
    with open(target_file, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 2
    assert "Draft 1" in lines[0]

    # Now save EDITED speeches for the same session
    edited_speeches = [
        {
            "date": "2026-03-01",
            "source_file": session_key,
            "text": "Final edited speech",
            "status": "EDITED",
        },
    ]

    save_session_to_jsonl("2026", session_key, edited_speeches)

    with open(target_file, encoding="utf-8") as f:
        updated_lines = f.readlines()
    assert len(updated_lines) == 1
    assert "Final edited speech" in updated_lines[0]
    assert "Draft 1" not in updated_lines[0]


def test_get_faction_for_date_lookup():
    faction_map = {
        "Jaak Aab": [
            {
                "faction": "Eesti Keskerakonna fraktsioon",
                "start": "2019-04-04",
                "end": "2023-04-01",
            },
            {
                "faction": "Fraktsiooni mittekuuluvad Riigikogu liikmed",
                "start": "2024-01-05",
                "end": "2099-12-31",
            },
        ]
    }

    assert (
        get_faction_for_date(faction_map, "Jaak Aab", "2020-05-01")
        == "Eesti Keskerakonna fraktsioon"
    )
    assert (
        get_faction_for_date(faction_map, "Jaak Aab", "2024-06-01")
        == "Fraktsiooni mittekuuluvad Riigikogu liikmed"
    )
    # Date in gap
    assert get_faction_for_date(faction_map, "Jaak Aab", "2023-08-01") is None
    # Unknown member
    assert get_faction_for_date(faction_map, "Tundmatu Liige", "2020-05-01") is None


def test_loader_replaces_unedited_session(tmp_path, monkeypatch):
    create_tables()
    monkeypatch.setattr("src.load.loader.OUTPUT_DIR_PROCESSED", str(tmp_path))

    session_key = "2026-05-10_1000.api"
    session_file = tmp_path / "2026.jsonl"

    # 1. Write unedited session JSONL
    unedited_data = [
        {
            "date": "2026-05-10",
            "time": "1000",
            "source_file": session_key,
            "source_url": "https://stenogrammid.riigikogu.ee/202605101000",
            "speaker": "Mihkel Tamm",
            "text": "Toimetamata kõne tekst.",
            "text_lemmas": "toimetama kõne tekst",
            "status": "UNEDITED",
        }
    ]
    with open(session_file, "w", encoding="utf-8") as f:
        for d in unedited_data:
            f.write(json.dumps(d) + "\n")

    load_jsonl_to_database()

    db_session = SessionLocal()
    speeches = db_session.query(Speech).filter(Speech.source_file == session_key).all()
    assert len(speeches) == 1
    assert speeches[0].status == "UNEDITED"
    unedited_speech_id = speeches[0].id

    # Create dummy term for this speech
    term = SpeechTerm(speech_id=unedited_speech_id, lemma_id=1, count=1)
    db_session.add(term)
    db_session.commit()

    # Verify term exists
    assert (
        db_session.query(SpeechTerm).filter(SpeechTerm.speech_id == unedited_speech_id).count() == 1
    )
    db_session.close()

    # 2. Overwrite JSONL with EDITED session
    edited_data = [
        {
            "date": "2026-05-10",
            "time": "1000",
            "source_file": session_key,
            "source_url": "https://stenogrammid.riigikogu.ee/202605101000",
            "speaker": "Mihkel Tamm",
            "text": "Lõplik toimetatud kõne tekst.",
            "text_lemmas": "lõplik toimetatud kõne tekst",
            "status": "EDITED",
        }
    ]
    with open(session_file, "w", encoding="utf-8") as f:
        for d in edited_data:
            f.write(json.dumps(d) + "\n")

    # Load again
    load_jsonl_to_database()

    db_session = SessionLocal()
    updated_speeches = db_session.query(Speech).filter(Speech.source_file == session_key).all()
    assert len(updated_speeches) == 1
    assert updated_speeches[0].status == "EDITED"
    assert "Lõplik toimetatud" in updated_speeches[0].text
    # Old speech terms were removed
    assert (
        db_session.query(SpeechTerm).filter(SpeechTerm.speech_id == unedited_speech_id).count() == 0
    )
    db_session.close()


def test_save_session_to_jsonl_empty_speeches_guard(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.fetch_stenograms_api.OUTPUT_DIR_PROCESSED", str(tmp_path))
    session_key = "2026-04-01_1000.api"
    speeches = [{"date": "2026-04-01", "source_file": session_key, "text": "Original text"}]

    save_session_to_jsonl("2026", session_key, speeches)
    target_file = tmp_path / "2026.jsonl"
    assert target_file.exists()

    # Try saving empty list - should be rejected and file retained
    save_session_to_jsonl("2026", session_key, [])
    with open(target_file, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1
    assert "Original text" in lines[0]


def test_parse_meeting_speeches_edited():
    from scripts.fetch_stenograms_api import parse_meeting_speeches

    mock_rich_meeting = {
        "meetingStatus": "EDITED",
        "stenograph": {
            "agendaItems": [
                {
                    "id": 101,
                    "name": "Päevakorrapunkt 1",
                    "speeches": [
                        {
                            "name": "Jüri Ratas",
                            "speechType": "SPEECH",
                            "content": "<p>Tere päevast, austatud kolleegid!</p>",
                            "startTime": "2026-04-01T10:15:00.000",
                            "parsedVideoLink": "https://youtu.be/test?t=15",
                        }
                    ],
                }
            ]
        },
    }

    speeches, status = parse_meeting_speeches(
        rich_meeting=mock_rich_meeting,
        verbatim=None,
        meeting_code="202604011000",
        verbatim_link="https://stenogrammid.riigikogu.ee/et/202604011000",
        date_formatted="2026-04-01",
        time_formatted="1000",
        source_file_key="2026-04-01_1000.api",
        faction_map={},
    )

    assert status == "EDITED"
    assert len(speeches) == 1
    assert speeches[0]["speaker"] == "Jüri Ratas"
    assert speeches[0]["time"] == "1015"
    assert speeches[0]["agenda_title"] == "Päevakorrapunkt 1"
    assert speeches[0]["video_url"] == "https://youtu.be/test?t=15"
    assert "austatud kolleegid" in speeches[0]["text"]
