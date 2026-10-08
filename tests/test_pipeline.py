import json

from scripts.fetch_stenograms_api import (
    compute_duration_seconds,
    get_faction_for_date,
    parse_meeting_speeches,
    save_session_to_jsonl,
)
from src.load.database import SessionLocal
from src.load.loader import (
    create_tables,
    load_jsonl_to_database,
    load_persons_to_database,
)
from src.load.models import Person, Speech, SpeechTerm


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
    mock_rich_meeting = {
        "meetingStatus": "EDITED",
        "stenograph": {
            "agendaItems": [
                {
                    "id": 101,
                    "name": "Päevakorrapunkt 1",
                    "speeches": [
                        {
                            "id": 45038588,
                            "emsId": "uuid-ratas-123",
                            "name": "Jüri Ratas",
                            "speechType": "SPEECH",
                            "content": "<p>Tere päevast, austatud kolleegid!</p>",
                            "startTime": "2026-04-01T10:15:00.000",
                            "endTime": "2026-04-01T10:17:30.000",
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
    assert speeches[0]["speaker_uuid"] == "uuid-ratas-123"
    assert speeches[0]["speech_type"] == "SPEECH"
    assert speeches[0]["external_id"] == 45038588
    assert speeches[0]["duration_seconds"] == 150
    assert speeches[0]["time"] == "1015"
    assert speeches[0]["agenda_title"] == "Päevakorrapunkt 1"
    assert speeches[0]["video_url"] == "https://youtu.be/test?t=15"
    assert "austatud kolleegid" in speeches[0]["text"]


def test_parse_meeting_speeches_minister_ems_id_disambiguation():
    mock_rich_meeting = {
        "meetingStatus": "EDITED",
        "stenograph": {
            "agendaItems": [
                {
                    "id": 102,
                    "name": "Päevakorrapunkt 2",
                    "speeches": [
                        {
                            "id": 45038599,
                            "emsId": "minister-role-uuid-63db",
                            "name": "Kaitseminister Hanno Pevkur",
                            "speechType": "SPEECH",
                            "content": "<p>Austatud Riigikogu!</p>",
                            "startTime": "2026-04-01T10:20:00.000",
                            "endTime": "2026-04-01T10:25:00.000",
                        }
                    ],
                }
            ]
        },
    }

    known_uuids = {"canonical-saadik-uuid-cf42"}
    name_map = {"Hanno Pevkur": "canonical-saadik-uuid-cf42"}
    uuid_to_name = {"canonical-saadik-uuid-cf42": "Hanno Pevkur"}

    speeches, _ = parse_meeting_speeches(
        rich_meeting=mock_rich_meeting,
        verbatim=None,
        meeting_code="202604011000",
        verbatim_link="https://stenogrammid.riigikogu.ee/et/202604011000",
        date_formatted="2026-04-01",
        time_formatted="1000",
        source_file_key="2026-04-01_1000.api",
        faction_map={},
        person_name_map=name_map,
        known_person_uuids=known_uuids,
        uuid_to_name_map=uuid_to_name,
    )

    assert len(speeches) == 1
    sp = speeches[0]
    assert sp["speaker"] == "Hanno Pevkur"
    assert sp["speaker_role"] == "Kaitseminister"
    assert sp["ems_id"] == "minister-role-uuid-63db"
    assert sp["speaker_uuid"] == "canonical-saadik-uuid-cf42"
    assert sp["speech_key"] == "202604011000_20260401T102000000_hanno-pevkur"


def test_compute_duration_seconds():
    # Valid ISO strings
    assert compute_duration_seconds("2026-04-01T10:15:00.000", "2026-04-01T10:16:30.000") == 90
    # With UTC Z suffix
    assert compute_duration_seconds("2026-04-01T10:15:00Z", "2026-04-01T10:15:45Z") == 45
    # Missing or invalid timestamps
    assert compute_duration_seconds(None, "2026-04-01T10:16:30") is None
    assert compute_duration_seconds("2026-04-01T10:15:00", None) is None
    assert compute_duration_seconds("invalid", "times") is None


def test_load_persons_to_database(tmp_path, monkeypatch):
    create_tables()
    monkeypatch.setattr("src.load.loader.OUTPUT_DIR_PROCESSED", str(tmp_path))

    mock_persons = [
        {
            "uuid": "test-mp-uuid-1",
            "first_name": "Ants",
            "last_name": "Kask",
            "full_name": "Ants Kask",
            "gender": "MALE",
            "date_of_birth": "1975-01-01",
            "email": "ants.kask@riigikogu.ee",
            "photo_url": "https://api.riigikogu.ee/api/files/test/download",
            "electoral_district": "Võrumaa",
            "seniority_days": 1000,
            "active": True,
        }
    ]
    persons_file = tmp_path / "persons.json"
    with open(persons_file, "w", encoding="utf-8") as f:
        json.dump(mock_persons, f)

    load_persons_to_database()

    session = SessionLocal()
    try:
        person = session.query(Person).filter(Person.uuid == "test-mp-uuid-1").first()
        assert person is not None
        assert person.full_name == "Ants Kask"
        assert person.electoral_district == "Võrumaa"
        assert person.seniority_days == 1000
        assert person.active == 1
    finally:
        session.close()


def test_fetch_factions_and_persons_with_mock(tmp_path, monkeypatch):
    import requests

    from scripts.fetch_factions import fetch_factions

    monkeypatch.setattr("scripts.fetch_factions.OUTPUT_DIR_PROCESSED", str(tmp_path))

    class MockResp:
        status_code = 200

        def json(self):
            return [
                {
                    "uuid": "mock-mp-1",
                    "firstName": "Mari",
                    "lastName": "Maasikas",
                    "fullName": "Mari Maasikas",
                    "gender": "FEMALE",
                    "dateOfBirth": "1985-05-15",
                    "email": "mari.maasikas@riigikogu.ee",
                    "parliamentSeniority": 500,
                    "active": True,
                    "photo": {
                        "uuid": "photo-uuid-1",
                        "_links": {
                            "download": {
                                "href": "https://api.riigikogu.ee/api/files/photo-uuid-1/download"
                            }
                        },
                    },
                    "electoralDistrictHistory": [
                        {
                            "membership": 15,
                            "electoralDistrict": {"code": "TARTU", "value": "Tartu linn"},
                        }
                    ],
                    "factions": [
                        {
                            "name": "Reformierakonna fraktsioon",
                            "membership": {
                                "startDate": "2023-04-10",
                                "endDate": None,
                            },
                        }
                    ],
                }
            ]

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: MockResp())

    ok = fetch_factions()
    assert ok is True

    factions_file = tmp_path / "factions_map.json"
    persons_file = tmp_path / "persons.json"
    assert factions_file.exists()
    assert persons_file.exists()

    p_data = json.loads(persons_file.read_text(encoding="utf-8"))
    assert len(p_data) == 1
    assert p_data[0]["uuid"] == "mock-mp-1"
    assert p_data[0]["full_name"] == "Mari Maasikas"
    assert p_data[0]["electoral_district"] == "Tartu linn"
    assert p_data[0]["photo_url"] == "https://api.riigikogu.ee/api/files/photo-uuid-1/download"
    assert p_data[0]["active"] is True

    f_data = json.loads(factions_file.read_text(encoding="utf-8"))
    assert "Mari Maasikas" in f_data
    assert f_data["Mari Maasikas"][0]["faction"] == "Reformierakonna fraktsioon"


def test_fetch_memberships_with_mock(tmp_path, monkeypatch):
    import requests

    from scripts.fetch_memberships import fetch_memberships

    monkeypatch.setattr("scripts.fetch_memberships.OUTPUT_DIR_PROCESSED", str(tmp_path))

    class MockResp:
        status_code = 200

        def json(self):
            return [
                {"number": 14, "startDate": "2019-04-04", "endDate": "2023-02-23"},
                {"number": 15, "startDate": "2023-04-10", "endDate": "2027-02-25"},
            ]

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: MockResp())

    ok = fetch_memberships()
    assert ok is True
    out_file = tmp_path / "memberships.json"
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert "14" in data
    assert "15" in data
    assert data["14"]["endDate"] == "2023-04-09"
    assert data["15"]["endDate"] == "2027-02-25"


def test_verify_statistics_with_mock(tmp_path, monkeypatch):
    import requests

    from scripts.verify_statistics import verify_statistics

    monkeypatch.setattr("scripts.verify_statistics.OUTPUT_DIR_PROCESSED", str(tmp_path))

    mock_persons = [
        {
            "uuid": "test-uuid-stats",
            "full_name": "Ants Kask",
            "active": True,
        }
    ]
    persons_file = tmp_path / "persons.json"
    with open(persons_file, "w", encoding="utf-8") as f:
        json.dump(mock_persons, f)

    class MockResp:
        status_code = 200

        def json(self):
            return {
                "uuid": "test-uuid-stats",
                "fullName": "Ants Kask",
                "speeches": 1,
                "questions": 0,
                "procedural": 0,
                "total": 1,
            }

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: MockResp())

    session = SessionLocal()
    sp = Speech(
        id=888111,
        date="2026-07-01",
        time="1000",
        source_file="2026-07-01_1000.api",
        source_url="https://stenogrammid.riigikogu.ee/et/test",
        speaker="Ants Kask",
        speaker_uuid="test-uuid-stats",
        speech_type="SPEECH",
        text="Tere kõigile!",
    )
    session.merge(sp)
    session.commit()
    session.close()

    report_path = tmp_path / "stats_report.json"
    ok = verify_statistics(
        start_date="2026-07-01",
        end_date="2026-07-02",
        sample_size=1,
        delay=0.0,
        output_path=str(report_path),
    )
    assert ok is True
    assert report_path.exists()
    report_data = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_data["summary"]["passed"] == 1
    assert report_data["summary"]["alerts"] == 0


def test_dynamic_membership_dates_reload(tmp_path, monkeypatch):
    from config import MEMBERSHIP_DATES

    monkeypatch.setattr("config.OUTPUT_DIR_PROCESSED", str(tmp_path))

    # Without file, has defaults
    assert "15" in MEMBERSHIP_DATES
    assert "99" not in MEMBERSHIP_DATES

    # Create memberships.json with membership 99
    m_file = tmp_path / "memberships.json"
    mock_data = {
        "99": {"startDate": "2030-01-01", "endDate": "2034-01-01"},
    }
    m_file.write_text(json.dumps(mock_data), encoding="utf-8")

    # MEMBERSHIP_DATES should immediately reflect new membership 99 without restart
    assert "99" in MEMBERSHIP_DATES
    assert MEMBERSHIP_DATES["99"] == ("2030-01-01", "2034-01-01")


def test_verify_pipeline_integrity(tmp_path, monkeypatch):
    import requests

    from scripts.verify_pipeline_integrity import verify_pipeline_integrity

    monkeypatch.setattr("scripts.verify_pipeline_integrity.OUTPUT_DIR_PROCESSED", str(tmp_path))

    # Create dummy JSONL file
    year_file = tmp_path / "2026.jsonl"
    mock_speech = {
        "source_file": "2026-09-23_1200.api",
        "date": "2026-09-23",
        "source_url": "https://stenogrammid.riigikogu.ee/et/194151#PKP-1",
        "text": "Näidiskõne",
    }
    year_file.write_text(json.dumps(mock_speech) + "\n", encoding="utf-8")

    class MockRespSuccess:
        status_code = 200

        def json(self):
            return [
                {
                    "date": "2026-09-23T12:00:00.000+00:00",
                    "title": "Täiskogu istung",
                    "link": "https://stenogrammid.riigikogu.ee/202609231200",
                    "edited": False,
                }
            ]

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: MockRespSuccess())

    ok = verify_pipeline_integrity(days=7, fail_on_missing=True, sample_meeting_checks=0)
    assert ok is True

    # Test failure when official session is missing
    class MockRespMissing:
        status_code = 200

        def json(self):
            return [
                {
                    "date": "2026-09-23T12:00:00.000+00:00",
                    "title": "Olemasolev istung",
                    "link": "https://stenogrammid.riigikogu.ee/202609231200",
                },
                {
                    "date": "2026-09-24T10:00:00.000+00:00",
                    "title": "Puuduv istung",
                    "link": "https://stenogrammid.riigikogu.ee/202609241000",
                },
            ]

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: MockRespMissing())

    ok_missing = verify_pipeline_integrity(days=7, fail_on_missing=True, sample_meeting_checks=0)
    assert ok_missing is False


def test_sync_database_replaces_unedited_and_writes_alias(tmp_path, monkeypatch):
    from scripts.sync_database import sync_current_year_speeches
    from src.load.database import SessionLocal
    from src.load.models import Speech, SpeechAlias

    monkeypatch.setattr("scripts.sync_database.OUTPUT_DIR_PROCESSED", str(tmp_path))

    session = SessionLocal()
    # 1. Seed unedited speech in DB
    unedited_sp = Speech(
        id=888999,
        date="2026-09-23",
        time="1200",
        source_file="2026-09-23_1200.api",
        source_url="https://stenogrammid.riigikogu.ee/et/194140",
        speaker="Hanno Pevkur",
        speaker_uuid="uuid-person-2",
        ems_id="ems-pevkur-1",
        speech_type="SPEECH",
        external_id=19414011,
        start_time="2026-09-23T12:00:10.000",
        end_time="2026-09-23T12:02:10.000",
        duration_seconds=120,
        speech_key="194140_20260923T120010_hanno-pevkur",
        text="Esialgne toimetamata kõne.",
        status="UNEDITED",
    )
    session.merge(unedited_sp)
    session.commit()
    session.close()

    # 2. Write updated edited speech in JSONL with new external_id
    year_file = tmp_path / "2026.jsonl"
    edited_data = {
        "date": "2026-09-23",
        "time": "1200",
        "source_file": "2026-09-23_1200.api",
        "source_url": "https://stenogrammid.riigikogu.ee/et/194151",
        "speaker": "Hanno Pevkur",
        "speaker_uuid": "uuid-person-2",
        "ems_id": "ems-pevkur-1",
        "speech_type": "SPEECH",
        "external_id": 19415122,  # New official edited external_id
        "start_time": "2026-09-23T12:00:10.000",
        "end_time": "2026-09-23T12:02:10.000",
        "duration_seconds": 120,
        "speech_key": "194151_20260923T120010_hanno-pevkur",
        "text": "Lõplik toimetatud kõne.",
        "text_lemmas": "lõplik toimetatud kõne",
        "status": "EDITED",
    }
    year_file.write_text(json.dumps(edited_data) + "\n", encoding="utf-8")

    # 3. Sync database
    new_count = sync_current_year_speeches("2026")
    assert new_count == 1

    # 4. Verify speech was updated and alias was created
    session = SessionLocal()
    updated_sp = session.query(Speech).filter(Speech.source_file == "2026-09-23_1200.api").first()
    assert updated_sp is not None
    assert updated_sp.status == "EDITED"
    assert updated_sp.external_id == 19415122
    assert updated_sp.text == "Lõplik toimetatud kõne."

    alias_rec = session.query(SpeechAlias).filter(SpeechAlias.alias_external_id == 19414011).first()
    assert alias_rec is not None
    assert alias_rec.speech_id == updated_sp.id
    session.close()
