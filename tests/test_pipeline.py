import json
import sys
from pathlib import Path

from scripts.fetch_stenograms_api import (
    compute_duration_seconds,
    get_faction_for_date,
    parse_meeting_speeches,
    resolve_speaker_uuid,
    save_session_to_jsonl,
    split_speaker_role,
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


def test_slugify_estonian():
    from scripts.fetch_stenograms_api import slugify_estonian

    assert slugify_estonian("Jüri Ratas") == "juri-ratas"
    assert slugify_estonian("Õnne Pillak") == "onne-pillak"
    assert slugify_estonian("Kaja Kallas") == "kaja-kallas"
    assert slugify_estonian("Urmas Reinsalu (välisminister)") == "urmas-reinsalu-valisminister"


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
            ] * 105

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

    create_tables()
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
        def __init__(self, is_steno: bool):
            self.status_code = 200
            self.is_steno = is_steno

        def json(self):
            data = {
                "uuid": "test-uuid-stats",
                "fullName": "Ants Kask",
                "speeches": 1,
                "questions": 0,
                "procedural": 0,
                "total": 1,
            }
            return [data] if self.is_steno else data

    def mock_get(url, *args, **kwargs):
        return MockResp(is_steno="steno" in url)

    monkeypatch.setattr(requests, "get", mock_get)

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

    # 1. Test steno source (default)
    report_path_steno = tmp_path / "steno_report.json"
    ok_steno = verify_statistics(
        start_date="2026-07-01",
        end_date="2026-07-02",
        sample_size=1,
        delay=0.0,
        output_path=str(report_path_steno),
        source="steno",
    )
    assert ok_steno is True
    assert report_path_steno.exists()
    steno_data = json.loads(report_path_steno.read_text(encoding="utf-8"))
    assert steno_data["source"] == "steno"
    assert steno_data["summary"]["passed"] == 1
    assert steno_data["summary"]["discrepancies"] == 0

    # 2. Test statistics source
    report_path_stats = tmp_path / "stats_report.json"
    ok_stats = verify_statistics(
        start_date="2026-07-01",
        end_date="2026-07-02",
        sample_size=1,
        delay=0.0,
        output_path=str(report_path_stats),
        source="statistics",
    )
    assert ok_stats is True
    assert report_path_stats.exists()
    stats_data = json.loads(report_path_stats.read_text(encoding="utf-8"))
    assert stats_data["source"] == "statistics"
    assert stats_data["summary"]["passed"] == 1
    assert stats_data["summary"]["discrepancies"] == 0


def test_get_local_speech_counts_filters():
    from scripts.verify_statistics import get_local_speech_counts

    create_tables()
    session = SessionLocal()

    test_uuid = "test-uuid-counts-mp"
    try:
        session.query(Speech).filter(Speech.speaker_uuid == test_uuid).delete()

        speeches_data = [
            # speaker_role IS NULL -> categorized
            {"id": 990001, "speech_type": "SPEECH", "speaker_role": None},
            {"id": 990002, "speech_type": "SPEECH_CONTINUE", "speaker_role": None},
            {"id": 990003, "speech_type": "SMALL_SPEECH", "speaker_role": None},
            {"id": 990004, "speech_type": "SMALL_SPEECH", "speaker_role": None},
            {"id": 990005, "speech_type": "PROCEDURAL", "speaker_role": None},
            {"id": 990006, "speech_type": "DIRECTOR", "speaker_role": None},
            # non-null roles
            {"id": 990007, "speech_type": "SPEECH", "speaker_role": "Esimees"},
            {"id": 990008, "speech_type": "SMALL_SPEECH", "speaker_role": "Aseesimees"},
            {"id": 990009, "speech_type": "SPEECH", "speaker_role": "Kaitseminister"},
            {"id": 990010, "speech_type": "SPEECH", "speaker_role": "Peaminister"},
            {"id": 990011, "speech_type": "SPEECH", "speaker_role": "Erikomisjoni esimees"},
        ]

        for data in speeches_data:
            sp = Speech(
                id=data["id"],
                date="2026-01-15",
                time="1200",
                source_file="2026-01-15_1200.api",
                source_url="https://example.com/test",
                speaker="Test MP",
                speaker_uuid=test_uuid,
                speech_type=data["speech_type"],
                speaker_role=data["speaker_role"],
                text="Test speech text",
            )
            session.merge(sp)
        session.commit()

        # Test source="statistics"
        counts_stats = get_local_speech_counts(
            session=session,
            uuid=test_uuid,
            full_name="Test MP",
            start_date="2026-01-01",
            end_date="2026-01-31",
            source="statistics",
        )
        assert counts_stats["speeches"] == 2  # 1 SPEECH + 1 SPEECH_CONTINUE
        assert counts_stats["questions"] == 2  # 2 SMALL_SPEECH
        assert counts_stats["procedural"] == 1  # 1 PROCEDURAL
        assert counts_stats["director"] == 1  # 1 DIRECTOR
        assert counts_stats["total"] == 5  # speeches + questions + procedural
        assert counts_stats["chair"] == 2  # Esimees + Aseesimees
        assert counts_stats["minister"] == 2  # Kaitseminister + Peaminister
        assert counts_stats["other_roles"] == 1  # Erikomisjoni esimees

        # Test source="steno" (default)
        counts_steno = get_local_speech_counts(
            session=session,
            uuid=test_uuid,
            full_name="Test MP",
            start_date="2026-01-01",
            end_date="2026-01-31",
            source="steno",
        )
        assert counts_steno["speeches"] == 3  # (1 SPEECH + 1 CONTINUE) + 1 Esimees SPEECH
        assert counts_steno["questions"] == 3  # 2 SMALL_SPEECH + 1 Aseesimees SMALL_SPEECH
        assert counts_steno["procedural"] == 1  # 1 PROCEDURAL
        assert counts_steno["director"] == 1  # 1 DIRECTOR (non-chair)
        assert counts_steno["total"] == 7  # 3 speeches + 3 questions + 1 procedural
        assert counts_steno["chair"] == 2
        assert counts_steno["minister"] == 2
        assert counts_steno["other_roles"] == 1
    finally:
        session.query(Speech).filter(Speech.speaker_uuid == test_uuid).delete()
        session.commit()
        session.close()


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
    from datetime import datetime, timedelta

    import requests

    from scripts.verify_pipeline_integrity import verify_pipeline_integrity

    monkeypatch.setattr("scripts.verify_pipeline_integrity.OUTPUT_DIR_PROCESSED", str(tmp_path))

    today = datetime.now()
    yesterday = today - timedelta(days=1)
    two_days_ago = today - timedelta(days=2)

    curr_year = today.year
    year_file = tmp_path / f"{curr_year}.jsonl"

    code_existing = f"{yesterday.strftime('%Y%m%d')}1200"
    file_existing = f"{yesterday.strftime('%Y-%m-%d')}_1200.api"
    mock_speech = {
        "source_file": file_existing,
        "date": yesterday.strftime("%Y-%m-%d"),
        "source_url": f"https://stenogrammid.riigikogu.ee/et/{code_existing}#PKP-1",
        "text": "Näidiskõne",
    }
    year_file.write_text(json.dumps(mock_speech) + "\n", encoding="utf-8")

    class MockRespSuccess:
        status_code = 200

        def json(self):
            return [
                {
                    "date": f"{yesterday.strftime('%Y-%m-%d')}T12:00:00.000+00:00",
                    "title": "Täiskogu istung",
                    "link": f"https://stenogrammid.riigikogu.ee/{code_existing}",
                    "edited": False,
                }
            ]

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: MockRespSuccess())

    ok = verify_pipeline_integrity(days=7, fail_on_missing=True, sample_meeting_checks=0)
    assert ok is True

    # Test failure when official session is missing
    code_missing = f"{two_days_ago.strftime('%Y%m%d')}1000"

    class MockRespMissing:
        status_code = 200

        def json(self):
            return [
                {
                    "date": f"{yesterday.strftime('%Y-%m-%d')}T12:00:00.000+00:00",
                    "title": "Olemasolev istung",
                    "link": f"https://stenogrammid.riigikogu.ee/{code_existing}",
                },
                {
                    "date": f"{two_days_ago.strftime('%Y-%m-%d')}T10:00:00.000+00:00",
                    "title": "Puuduv istung",
                    "link": f"https://stenogrammid.riigikogu.ee/{code_missing}",
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
        "previous_external_ids": [19414011],
        "previous_speech_keys": ["194140_20260923T120010_hanno-pevkur"],
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


def test_download_from_b2_active_only(tmp_path, monkeypatch):
    from scripts.download_from_b2 import download_from_b2

    monkeypatch.setattr("scripts.download_from_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "dummy_key")
    monkeypatch.setenv("B2_APP_KEY", "dummy_secret")

    downloaded = []

    class MockPaginator:
        def paginate(self, Bucket):
            return [
                {
                    "Contents": [
                        {"Key": "2021.jsonl", "Size": 50000000},
                        {"Key": "2026.jsonl", "Size": 45000000},
                        {"Key": "attendance.jsonl", "Size": 25000000},
                        {"Key": "memberships.json", "Size": 1000},
                        {"Key": "notes.txt", "Size": 50},
                    ]
                }
            ]

    class MockS3Client:
        def get_paginator(self, operation_name):
            return MockPaginator()

        def download_file(self, bucket, key, local_path):
            downloaded.append(key)
            Path(local_path).write_text("dummy", encoding="utf-8")

    class MockBoto3:
        @staticmethod
        def client(service, **kwargs):
            return MockS3Client()

    monkeypatch.setitem(sys.modules, "boto3", MockBoto3)

    ok = download_from_b2(active_year="2026", include_all_history=False)
    assert ok is True
    # Only active files should be downloaded (2026.jsonl, attendance.jsonl, memberships.json)
    assert set(downloaded) == {"2026.jsonl", "attendance.jsonl", "memberships.json"}
    # Historical 2021.jsonl and non-jsonl notes.txt should NOT be downloaded
    assert "2021.jsonl" not in downloaded
    assert "notes.txt" not in downloaded


def test_download_from_b2_include_all(tmp_path, monkeypatch):
    from scripts.download_from_b2 import download_from_b2

    monkeypatch.setattr("scripts.download_from_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "dummy_key")
    monkeypatch.setenv("B2_APP_KEY", "dummy_secret")

    # Create a pre-existing 2021.jsonl with matching size 100 bytes
    pre_existing = tmp_path / "2021.jsonl"
    pre_existing.write_bytes(b"x" * 100)

    downloaded = []

    class MockPaginator:
        def paginate(self, Bucket):
            return [
                {
                    "Contents": [
                        {"Key": "2021.jsonl", "Size": 100},  # Exactly matches local size -> skip!
                        {"Key": "2022.jsonl", "Size": 200},  # Not local -> download!
                        {"Key": "2026.jsonl", "Size": 300},
                        {"Key": "attendance.jsonl", "Size": 400},
                    ]
                }
            ]

    class MockS3Client:
        def get_paginator(self, operation_name):
            return MockPaginator()

        def download_file(self, bucket, key, local_path):
            downloaded.append(key)
            Path(local_path).write_text("dummy", encoding="utf-8")

    class MockBoto3:
        @staticmethod
        def client(service, **kwargs):
            return MockS3Client()

    monkeypatch.setitem(sys.modules, "boto3", MockBoto3)

    ok = download_from_b2(active_year="2026", include_all_history=True)
    assert ok is True
    # 2021.jsonl was skipped because size matches!
    assert "2021.jsonl" not in downloaded
    assert "2022.jsonl" in downloaded
    assert "2026.jsonl" in downloaded
    assert "attendance.jsonl" in downloaded


def test_active_years_boundaries():
    from datetime import datetime

    from config import active_years

    assert active_years(datetime(2026, 1, 15)) == ["2025", "2026"]
    assert active_years(datetime(2026, 3, 1)) == ["2025", "2026"]
    assert active_years(datetime(2026, 3, 2)) == ["2026"]
    assert active_years(datetime(2026, 10, 9)) == ["2026"]


def test_sync_current_year_speeches_active_years_only(tmp_path, monkeypatch):
    from scripts.sync_database import sync_current_year_speeches
    from src.load.loader import create_tables
    from src.load.models import Speech

    create_tables()

    monkeypatch.setattr("scripts.sync_database.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("scripts.sync_database.active_years", lambda: ["2026"])

    file_2019 = tmp_path / "2019.jsonl"
    file_2026 = tmp_path / "2026.jsonl"

    speech_2019 = {
        "date": "2019-05-01",
        "time": "1000",
        "source_file": "2019-05-01_1000.api",
        "source_url": "https://stenogrammid.riigikogu.ee/201905011000",
        "speaker": "Test Speaker 2019",
        "text": "Tekst 2019",
        "status": "EDITED",
    }
    speech_2026 = {
        "date": "2026-05-01",
        "time": "1000",
        "source_file": "2026-05-01_1000.api",
        "source_url": "https://stenogrammid.riigikogu.ee/202605011000",
        "speaker": "Test Speaker 2026",
        "text": "Tekst 2026",
        "status": "EDITED",
    }

    file_2019.write_text(json.dumps(speech_2019) + "\n", encoding="utf-8")
    file_2026.write_text(json.dumps(speech_2026) + "\n", encoding="utf-8")

    sync_current_year_speeches()

    session = SessionLocal()
    try:
        s_2026 = session.query(Speech).filter(Speech.source_file == "2026-05-01_1000.api").first()
        s_2019 = session.query(Speech).filter(Speech.source_file == "2019-05-01_1000.api").first()
        assert s_2026 is not None
        assert s_2019 is None
    finally:
        session.close()


def test_download_from_b2_default_active_window(tmp_path, monkeypatch):
    import config
    from scripts.download_from_b2 import download_from_b2

    monkeypatch.setattr("scripts.download_from_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "dummy_key")
    monkeypatch.setenv("B2_APP_KEY", "dummy_secret")

    downloaded = []

    class MockPaginator:
        def paginate(self, Bucket):
            return [
                {
                    "Contents": [
                        {"Key": "2025.jsonl", "Size": 100},
                        {"Key": "2026.jsonl", "Size": 200},
                        {"Key": "2027.jsonl", "Size": 300},
                    ]
                }
            ]

    class MockS3Client:
        def get_paginator(self, operation_name):
            return MockPaginator()

        def download_file(self, bucket, key, local_path):
            downloaded.append(key)
            Path(local_path).write_text("dummy", encoding="utf-8")

    class MockBoto3:
        @staticmethod
        def client(service, **kwargs):
            return MockS3Client()

    monkeypatch.setitem(sys.modules, "boto3", MockBoto3)

    # 1. On 2026-10-09, active_years() is ["2026"] -> only 2026.jsonl downloaded
    monkeypatch.setattr(config, "active_years", lambda: ["2026"])
    ok = download_from_b2()
    assert ok is True
    assert downloaded == ["2026.jsonl"]

    # 2. On 2027-01-15, active_years() is ["2026", "2027"] -> both downloaded
    downloaded.clear()
    monkeypatch.setattr(config, "active_years", lambda: ["2026", "2027"])
    ok = download_from_b2()
    assert ok is True
    assert set(downloaded) == {"2026.jsonl", "2027.jsonl"}


def test_resolve_speaker_uuid_name_change():
    known_uuids = {"17d27ea5-b5e6-43e0-86db-ebc15bdd5788"}
    uuid_to_name = {"17d27ea5-b5e6-43e0-86db-ebc15bdd5788": "Luisa Värk"}
    name_map = {"Luisa Värk": "17d27ea5-b5e6-43e0-86db-ebc15bdd5788"}
    faction_map = {
        "Luisa Värk": [
            {
                "start": "2023-04-10",
                "end": "2027-03-01",
                "faction": "Eesti Reformierakonna fraktsioon",
            }
        ]
    }

    resolved_uuid, method = resolve_speaker_uuid(
        speaker_name="Luisa Rõivas",
        ems_id="17d27ea5-b5e6-43e0-86db-ebc15bdd5788",
        date="2023-05-18",
        known_uuids=known_uuids,
        uuid_to_name_map=uuid_to_name,
        person_name_map=name_map,
    )
    assert resolved_uuid == "17d27ea5-b5e6-43e0-86db-ebc15bdd5788"
    assert method == "ems_name_change"

    canonical_name = uuid_to_name.get(resolved_uuid)
    faction = get_faction_for_date(faction_map, canonical_name, "2023-05-18")
    assert faction == "Eesti Reformierakonna fraktsioon"


def test_resolve_speaker_uuid_same_first_name_canonical_mismatch():
    uuid1 = "11111111-1111-1111-1111-111111111111"
    uuid2 = "22222222-2222-2222-2222-222222222222"
    known_uuids = {uuid1, uuid2}
    uuid_to_name = {uuid1: "Tarmo Tamm", uuid2: "Tarmo Kallas"}
    name_map = {"Tarmo Tamm": uuid1, "Tarmo Kallas": uuid2}

    resolved_uuid, method = resolve_speaker_uuid(
        speaker_name="Tarmo Kallas",
        ems_id=uuid1,
        date="2024-01-01",
        known_uuids=known_uuids,
        uuid_to_name_map=uuid_to_name,
        person_name_map=name_map,
    )
    assert method != "ems_name_change"
    assert resolved_uuid != uuid1
    assert resolved_uuid == uuid2
    assert method == "name"


def test_resolve_speaker_uuid_tarmo_tamm():
    uuid_old = "76afbcdc-b41d-4fc6-b5eb-d0cce01e94d5"
    uuid_new = "236e49d6-eecb-4562-8ad4-bedd586bb149"

    uuid1, method1 = resolve_speaker_uuid(
        speaker_name="Tarmo Tamm",
        ems_id=None,
        date="2023-04-09",
        known_uuids=None,
        uuid_to_name_map=None,
        person_name_map=None,
    )
    assert uuid1 == uuid_old
    assert method1 == "tarmo_tamm_date"

    uuid2, method2 = resolve_speaker_uuid(
        speaker_name="Tarmo Tamm",
        ems_id=None,
        date="2023-04-10",
        known_uuids=None,
        uuid_to_name_map=None,
        person_name_map=None,
    )
    assert uuid2 == uuid_new
    assert method2 == "tarmo_tamm_date"


def test_repair_speaker_uuids_dry_run_and_apply(tmp_path):
    import sqlite3

    from scripts.repair_speaker_uuids import repair_speaker_uuids

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    luisa_uuid = "17d27ea5-b5e6-43e0-86db-ebc15bdd5788"
    persons_data = [{"uuid": luisa_uuid, "full_name": "Luisa Värk"}]
    (data_dir / "persons.json").write_text(json.dumps(persons_data), encoding="utf-8")

    factions_data = {
        "Luisa Värk": [
            {
                "start": "2023-04-10",
                "end": "2027-03-01",
                "faction": "Eesti Reformierakonna fraktsioon",
            }
        ]
    }
    (data_dir / "factions_map.json").write_text(json.dumps(factions_data), encoding="utf-8")

    speech_raw = {
        "date": "2023-05-18",
        "time": "1000",
        "source_file": "2023-05-18_1000.api",
        "source_url": "https://example.com",
        "speaker": "Luisa Rõivas",
        "speaker_role": None,
        "speaker_faction": None,
        "speaker_uuid": None,
        "ems_id": luisa_uuid,
        "speech_type": "SPEECH",
        "external_id": 99901,
        "speech_key": "202305181000_luisa",
        "text": "Tere",
        "text_lemmas": "tere",
        "status": "EDITED",
    }
    jsonl_file = data_dir / "2023.jsonl"
    jsonl_file.write_text(json.dumps(speech_raw) + "\n", encoding="utf-8")

    # Set up test sqlite database
    db_file = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db_file)
    conn.execute(
        "CREATE TABLE speeches (id INTEGER PRIMARY KEY, external_id INTEGER, speech_key TEXT, speaker TEXT, speaker_role TEXT, speaker_faction TEXT, speaker_uuid TEXT)"
    )
    conn.execute(
        "INSERT INTO speeches (id, external_id, speech_key, speaker, speaker_role, speaker_faction, speaker_uuid) VALUES (1, 99901, '202305181000_luisa', 'Luisa Rõivas', NULL, NULL, NULL)"
    )
    conn.commit()
    conn.close()

    # 1. Run dry-run
    res_dry = repair_speaker_uuids(
        data_dir=str(data_dir),
        dry_run=True,
        db_path=str(db_file),
    )
    assert res_dry["needed_repair"] == 1
    # Verify file was not modified, no .bak file created
    assert not (data_dir / "2023.jsonl.bak").exists()
    content_after_dry = json.loads(jsonl_file.read_text(encoding="utf-8"))
    assert content_after_dry["speaker_uuid"] is None
    assert content_after_dry["speaker_faction"] is None

    # Verify db was not modified
    conn = sqlite3.connect(db_file)
    row = conn.execute("SELECT speaker_uuid, speaker_faction FROM speeches WHERE id = 1").fetchone()
    conn.close()
    assert row[0] is None
    assert row[1] is None

    # 2. Run apply
    res_apply = repair_speaker_uuids(
        data_dir=str(data_dir),
        dry_run=False,
        db_path=str(db_file),
    )
    assert res_apply["needed_repair"] == 1
    # Verify file was modified
    content_after_apply = json.loads(jsonl_file.read_text(encoding="utf-8"))
    assert content_after_apply["speaker_uuid"] == luisa_uuid
    assert content_after_apply["speaker_faction"] == "Eesti Reformierakonna fraktsioon"
    assert content_after_apply["text"] == "Tere"

    # Verify .bak backup exists with original null content
    assert (data_dir / "2023.jsonl.bak").exists()
    bak_content = json.loads((data_dir / "2023.jsonl.bak").read_text(encoding="utf-8"))
    assert bak_content["speaker_uuid"] is None
    assert bak_content["speaker_faction"] is None

    # Verify SQLite was updated
    conn = sqlite3.connect(db_file)
    row = conn.execute("SELECT speaker_uuid, speaker_faction FROM speeches WHERE id = 1").fetchone()
    conn.close()
    assert row[0] == luisa_uuid
    assert row[1] == "Eesti Reformierakonna fraktsioon"


def test_split_speaker_role_candidates_and_suffix():
    assert split_speaker_role("Peaministrikandidaat Kaja Kallas") == (
        "Kaja Kallas",
        "Peaministrikandidaat",
    )
    assert split_speaker_role("Presidendikandidaat Ülle Madise") == (
        "Ülle Madise",
        "Presidendikandidaat",
    )
    assert split_speaker_role("Jürgen Ligi rahandusminister") == (
        "Jürgen Ligi",
        "Rahandusminister",
    )
    assert split_speaker_role("Riigikohtu liikme kandidaat X Y") == (
        "X Y",
        "Riigikohtu liikme kandidaat",
    )
    assert split_speaker_role("Rahandusminister Martin Helme") == (
        "Martin Helme",
        "Rahandusminister",
    )
    assert split_speaker_role("Aseesimees Arvo Aller") == (
        "Arvo Aller",
        "Aseesimees",
    )
    assert split_speaker_role("Tarmo Tamm") == ("Tarmo Tamm", None)
    assert split_speaker_role("Riigikogu koor") == ("Riigikogu koor", None)


def test_repair_speaker_uuids_candidate_role(tmp_path):
    import sqlite3

    from scripts.repair_speaker_uuids import repair_speaker_uuids

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    kaja_uuid = "c7d52089-6129-468f-8789-9c4cf742b908"
    persons_data = [{"uuid": kaja_uuid, "full_name": "Kaja Kallas"}]
    (data_dir / "persons.json").write_text(json.dumps(persons_data), encoding="utf-8")

    factions_data = {
        "Kaja Kallas": [
            {
                "start": "2019-04-04",
                "end": "2021-01-26",
                "faction": "Eesti Reformierakonna fraktsioon",
            }
        ]
    }
    (data_dir / "factions_map.json").write_text(json.dumps(factions_data), encoding="utf-8")

    speech_raw = {
        "date": "2021-01-25",
        "time": "1500",
        "source_file": "2021-01-25_1500.api",
        "source_url": "https://example.com",
        "speaker": "Peaministrikandidaat Kaja Kallas",
        "speaker_role": None,
        "speaker_faction": None,
        "speaker_uuid": None,
        "ems_id": None,
        "speech_type": "SPEECH",
        "external_id": 88801,
        "speech_key": "202101251500_kaja-kallas-permanent",
        "text": "Austatud Riigikogu",
        "text_lemmas": "austatud riigikogu",
        "status": "EDITED",
    }
    jsonl_file = data_dir / "2021.jsonl"
    jsonl_file.write_text(json.dumps(speech_raw) + "\n", encoding="utf-8")

    db_file = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db_file)
    conn.execute(
        "CREATE TABLE speeches (id INTEGER PRIMARY KEY, external_id INTEGER, speech_key TEXT, speaker TEXT, speaker_role TEXT, speaker_faction TEXT, speaker_uuid TEXT)"
    )
    conn.execute(
        "INSERT INTO speeches (id, external_id, speech_key, speaker, speaker_role, speaker_faction, speaker_uuid) VALUES (1, 88801, '202101251500_kaja-kallas-permanent', 'Peaministrikandidaat Kaja Kallas', NULL, NULL, NULL)"
    )
    conn.commit()
    conn.close()

    res = repair_speaker_uuids(
        data_dir=str(data_dir),
        dry_run=False,
        db_path=str(db_file),
    )
    assert res["needed_repair"] == 1
    assert res["db_updated_count"] == 1

    content = json.loads(jsonl_file.read_text(encoding="utf-8"))
    assert content["speaker"] == "Kaja Kallas"
    assert content["speaker_role"] == "Peaministrikandidaat"
    assert content["speaker_uuid"] == kaja_uuid
    assert content["speaker_faction"] == "Eesti Reformierakonna fraktsioon"
    assert content["speech_key"] == "202101251500_kaja-kallas-permanent"

    conn = sqlite3.connect(db_file)
    row = conn.execute(
        "SELECT speaker, speaker_role, speaker_uuid, speaker_faction, speech_key FROM speeches WHERE id = 1"
    ).fetchone()
    conn.close()
    assert row[0] == "Kaja Kallas"
    assert row[1] == "Peaministrikandidaat"
    assert row[2] == kaja_uuid
    assert row[3] == "Eesti Reformierakonna fraktsioon"
    assert row[4] == "202101251500_kaja-kallas-permanent"


def test_repair_speaker_uuids_db_when_jsonl_already_repaired(tmp_path):
    import sqlite3

    from scripts.repair_speaker_uuids import repair_speaker_uuids

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    kaja_uuid = "c7d52089-6129-468f-8789-9c4cf742b908"
    persons_data = [{"uuid": kaja_uuid, "full_name": "Kaja Kallas"}]
    (data_dir / "persons.json").write_text(json.dumps(persons_data), encoding="utf-8")

    factions_data = {
        "Kaja Kallas": [
            {
                "start": "2019-04-04",
                "end": "2021-01-26",
                "faction": "Eesti Reformierakonna fraktsioon",
            }
        ]
    }
    (data_dir / "factions_map.json").write_text(json.dumps(factions_data), encoding="utf-8")

    # JSONL is ALREADY repaired
    speech_repaired = {
        "date": "2021-01-25",
        "time": "1500",
        "source_file": "2021-01-25_1500.api",
        "source_url": "https://example.com",
        "speaker": "Kaja Kallas",
        "speaker_role": "Peaministrikandidaat",
        "speaker_faction": "Eesti Reformierakonna fraktsioon",
        "speaker_uuid": kaja_uuid,
        "ems_id": None,
        "speech_type": "SPEECH",
        "external_id": 88801,
        "speech_key": "202101251500_kaja",
        "text": "Austatud Riigikogu",
        "text_lemmas": "austatud riigikogu",
        "status": "EDITED",
    }
    jsonl_file = data_dir / "2021.jsonl"
    jsonl_file.write_text(json.dumps(speech_repaired) + "\n", encoding="utf-8")

    # Database has OLD values
    db_file = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db_file)
    conn.execute(
        "CREATE TABLE speeches (id INTEGER PRIMARY KEY, external_id INTEGER, speech_key TEXT, speaker TEXT, speaker_role TEXT, speaker_faction TEXT, speaker_uuid TEXT)"
    )
    conn.execute(
        "INSERT INTO speeches (id, external_id, speech_key, speaker, speaker_role, speaker_faction, speaker_uuid) VALUES (1, 88801, '202101251500_kaja', 'Peaministrikandidaat Kaja Kallas', NULL, NULL, NULL)"
    )
    conn.commit()
    conn.close()

    res = repair_speaker_uuids(
        data_dir=str(data_dir),
        dry_run=False,
        db_path=str(db_file),
    )
    # JSONL had 0 needed repairs
    assert res["needed_repair"] == 0
    # But DB was updated
    assert res["db_updated_count"] == 1
    assert res["db_diff_fields"]["speaker"] == 1
    assert res["db_diff_fields"]["speaker_role"] == 1
    assert res["db_diff_fields"]["speaker_uuid"] == 1
    assert res["db_diff_fields"]["speaker_faction"] == 1

    conn = sqlite3.connect(db_file)
    row = conn.execute(
        "SELECT speaker, speaker_role, speaker_uuid, speaker_faction FROM speeches WHERE id = 1"
    ).fetchone()
    conn.close()
    assert row[0] == "Kaja Kallas"
    assert row[1] == "Peaministrikandidaat"
    assert row[2] == kaja_uuid
    assert row[3] == "Eesti Reformierakonna fraktsioon"


def test_repair_speaker_uuids_upload_failure_aborts_db(tmp_path, monkeypatch):
    import sqlite3

    import pytest

    from scripts.repair_speaker_uuids import repair_speaker_uuids

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    kaja_uuid = "c7d52089-6129-468f-8789-9c4cf742b908"
    (data_dir / "persons.json").write_text(
        json.dumps([{"uuid": kaja_uuid, "full_name": "Kaja Kallas"}]), encoding="utf-8"
    )
    (data_dir / "factions_map.json").write_text(
        json.dumps(
            {
                "Kaja Kallas": [
                    {
                        "start": "2019-04-04",
                        "end": "2021-01-26",
                        "faction": "Eesti Reformierakonna fraktsioon",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    speech_raw = {
        "date": "2021-01-25",
        "time": "1500",
        "source_file": "2021-01-25_1500.api",
        "source_url": "https://example.com",
        "speaker": "Peaministrikandidaat Kaja Kallas",
        "speaker_role": None,
        "speaker_faction": None,
        "speaker_uuid": None,
        "ems_id": None,
        "speech_type": "SPEECH",
        "external_id": 88801,
        "speech_key": "202101251500_kaja",
        "text": "Austatud Riigikogu",
        "text_lemmas": "austatud riigikogu",
        "status": "EDITED",
    }
    jsonl_file = data_dir / "2021.jsonl"
    jsonl_file.write_text(json.dumps(speech_raw) + "\n", encoding="utf-8")

    db_file = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db_file)
    conn.execute(
        "CREATE TABLE speeches (id INTEGER PRIMARY KEY, external_id INTEGER, speech_key TEXT, speaker TEXT, speaker_role TEXT, speaker_faction TEXT, speaker_uuid TEXT)"
    )
    conn.execute(
        "INSERT INTO speeches (id, external_id, speech_key, speaker, speaker_role, speaker_faction, speaker_uuid) VALUES (1, 88801, '202101251500_kaja', 'Peaministrikandidaat Kaja Kallas', NULL, NULL, NULL)"
    )
    conn.commit()
    conn.close()

    # Mock upload_to_b2 to fail
    import scripts.upload_to_b2

    monkeypatch.setattr(scripts.upload_to_b2, "upload_to_b2", lambda **kwargs: False)

    with pytest.raises(SystemExit) as exc_info:
        repair_speaker_uuids(
            data_dir=str(data_dir),
            dry_run=False,
            upload=True,
            db_path=str(db_file),
        )
    assert exc_info.value.code == 1

    # Database must NOT have been updated!
    conn = sqlite3.connect(db_file)
    row = conn.execute(
        "SELECT speaker, speaker_role, speaker_uuid FROM speeches WHERE id = 1"
    ).fetchone()
    conn.close()
    assert row[0] == "Peaministrikandidaat Kaja Kallas"
    assert row[1] is None
    assert row[2] is None


def test_repair_speaker_uuids_bak_with_shutil_copy(tmp_path, monkeypatch):
    import shutil

    from scripts.repair_speaker_uuids import repair_speaker_uuids

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    kaja_uuid = "c7d52089-6129-468f-8789-9c4cf742b908"
    (data_dir / "persons.json").write_text(
        json.dumps([{"uuid": kaja_uuid, "full_name": "Kaja Kallas"}]), encoding="utf-8"
    )
    (data_dir / "factions_map.json").write_text("{}", encoding="utf-8")

    speech_raw = {
        "date": "2021-01-25",
        "time": "1500",
        "source_file": "2021-01-25_1500.api",
        "source_url": "https://example.com",
        "speaker": "Peaministrikandidaat Kaja Kallas",
        "speaker_role": None,
        "speaker_faction": None,
        "speaker_uuid": None,
        "ems_id": None,
        "speech_type": "SPEECH",
        "external_id": 88801,
        "speech_key": "202101251500_kaja",
        "text": "Austatud Riigikogu",
        "text_lemmas": "austatud riigikogu",
        "status": "EDITED",
    }
    jsonl_file = data_dir / "2021.jsonl"
    jsonl_file.write_text(json.dumps(speech_raw) + "\n", encoding="utf-8")

    copy_calls = []
    real_copy = shutil.copy

    def tracked_copy(src, dst, *args, **kwargs):
        copy_calls.append((src, dst))
        return real_copy(src, dst, *args, **kwargs)

    def forbid_copy2(src, dst, *args, **kwargs):
        raise AssertionError("shutil.copy2 must not be called!")

    monkeypatch.setattr(shutil, "copy", tracked_copy)
    monkeypatch.setattr(shutil, "copy2", forbid_copy2)

    repair_speaker_uuids(data_dir=str(data_dir), dry_run=False)

    assert len(copy_calls) == 1
    assert copy_calls[0][1].endswith(".bak")
    assert (data_dir / "2021.jsonl.bak").exists()
