import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

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


def test_backfill_speaker_uuids_read_only(tmp_path, monkeypatch):
    from src.load.loader import backfill_speaker_uuids

    create_tables()
    session = SessionLocal()
    try:
        # Create person
        p = Person(
            uuid="uuid-unique-mp",
            first_name="Ainulaadne",
            last_name="Saadik",
            full_name="Ainulaadne Saadik",
            active=1,
        )
        session.merge(p)
        # Create speech without speaker_uuid
        sp = Speech(
            date="2024-05-01",
            time="1000",
            source_file="test_session.jsonl:1",
            source_url="https://example.com",
            speaker="Ainulaadne Saadik",
            speaker_uuid=None,
            text="Tere päevast",
            status="EDITED",
        )
        session.add(sp)
        session.commit()
        sp_id = sp.id

        # Run backfill_speaker_uuids
        count = backfill_speaker_uuids()
        assert count >= 1

        # Check that speech speaker_uuid is STILL None in database (read-only audit!)
        reloaded = session.query(Speech).filter(Speech.id == sp_id).first()
        assert reloaded.speaker_uuid is None
    finally:
        session.close()


def test_build_full_database_missing_year_aborts(tmp_path, monkeypatch):
    import pytest

    from scripts.build_full_database import build_full_database

    monkeypatch.setattr("scripts.build_full_database.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("scripts.build_full_database.download_all_from_b2", lambda: False)

    with pytest.raises(SystemExit) as exc_info:
        build_full_database(allow_partial=False)
    assert exc_info.value.code == 1


def test_build_full_database_allow_partial_continues(tmp_path, monkeypatch):
    from scripts.build_full_database import build_full_database

    monkeypatch.setattr("scripts.build_full_database.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("scripts.build_full_database.create_tables", lambda: None)
    monkeypatch.setattr("scripts.build_full_database.load_jsonl_to_database", lambda: None)
    monkeypatch.setattr("scripts.build_full_database.build_missing_lemmas", lambda **kwargs: None)
    monkeypatch.setattr("scripts.build_full_database.build_missing_terms", lambda: None)
    monkeypatch.setattr("scripts.build_full_database.create_indexes", lambda: None)

    # Calling with allow_partial=True should NOT raise SystemExit
    build_full_database(allow_partial=True)


def test_get_expected_dataset_files_attendance_always_expected(tmp_path, monkeypatch):
    from scripts.build_full_database import get_expected_dataset_files

    monkeypatch.setattr("scripts.build_full_database.OUTPUT_DIR_PROCESSED", str(tmp_path))
    files = get_expected_dataset_files()
    assert "attendance.jsonl" in files
    assert "persons.json" in files
    assert "person_factions.json" in files


def test_get_expected_dataset_files_january_cutoff():
    from datetime import datetime

    from scripts.build_full_database import get_expected_dataset_files

    early_jan = datetime(2027, 1, 10)
    files_early = get_expected_dataset_files(now=early_jan)
    assert "2026.jsonl" in files_early
    assert "2027.jsonl" not in files_early
    assert "attendance.jsonl" in files_early

    mid_jan = datetime(2027, 1, 15)
    files_mid = get_expected_dataset_files(now=mid_jan)
    assert "2027.jsonl" in files_mid
    assert "attendance.jsonl" in files_mid

    october = datetime(2026, 10, 13)
    files_oct = get_expected_dataset_files(now=october)
    assert "2026.jsonl" in files_oct


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
    # The newest mandate stays open after its last regular session (2027-02-25)
    assert data["15"]["endDate"] == "2099-12-31"
    assert data["15"]["sessionEndDate"] == "2027-02-25"


def test_fetch_memberships_xv_until_xvi_convenes(tmp_path, monkeypatch):
    import requests

    import config
    from scripts.fetch_memberships import fetch_memberships
    from scripts.fetch_votes import get_membership_for_date

    monkeypatch.setattr("scripts.fetch_memberships.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr(config, "OUTPUT_DIR_PROCESSED", str(tmp_path))
    upstream = [
        {"number": 14, "startDate": "2019-04-04", "endDate": "2023-02-23"},
        {"number": 15, "startDate": "2023-04-10", "endDate": "2027-02-25"},
    ]

    class MockResp:
        status_code = 200

        def json(self):
            return upstream

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: MockResp())

    # Before XVI is listed: a sitting after XV's last regular session still belongs to XV
    assert fetch_memberships() is True
    assert config.latest_membership(today="2027-03-10") == "15"
    assert get_membership_for_date("2027-03-10") == 15

    # XVI listed ahead of convening: XV ends the day before, XVI is not latest yet
    upstream.append({"number": 16, "startDate": "2027-03-30", "endDate": None})
    assert fetch_memberships() is True
    data = json.loads((tmp_path / "memberships.json").read_text(encoding="utf-8"))
    assert data["15"]["endDate"] == "2027-03-29"
    assert data["16"]["endDate"] == "2099-12-31"
    assert config.latest_membership(today="2027-03-29") == "15"
    assert config.latest_membership(today="2027-03-30") == "16"
    assert get_membership_for_date("2027-03-29") == 15
    assert get_membership_for_date("2027-03-30") == 16


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
    from src.load.loader import create_tables
    from src.load.models import Speech, SpeechAlias

    create_tables()
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
    failed_sources = sync_current_year_speeches("2026")
    assert failed_sources == []

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

        def download_file(self, bucket, key, local_path, **kwargs):
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

        def head_object(self, Bucket, Key):
            return {"Metadata": {}, "ContentLength": 100}

        def download_file(self, bucket, key, local_path, **kwargs):
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

        def download_file(self, bucket, key, local_path, **kwargs):
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


def test_resolve_speaker_uuid_tarmo_tamm(capsys):
    uuid_old = "76afbcdc-b41d-4fc6-b5eb-d0cce01e94d5"
    uuid_new = "236e49d6-eecb-4562-8ad4-bedd586bb149"
    known_uuids = {uuid_old, uuid_new}
    uuid_to_name_map = {uuid_old: "Tarmo Tamm", uuid_new: "Tarmo Tamm"}
    person_name_map = {}
    person_factions = {
        uuid_old: [
            {"faction": "Eesti Keskerakonna fraktsioon", "start": "2019-04-04", "end": "2023-04-01"}
        ],
        uuid_new: [{"faction": "Eesti 200 fraktsioon", "start": "2023-04-11", "end": "2099-12-31"}],
    }

    # Tarmo Tamm on 2021-05-04 -> old uuid
    uuid1, method1 = resolve_speaker_uuid(
        speaker_name="Tarmo Tamm",
        ems_id=None,
        date="2021-05-04",
        known_uuids=known_uuids,
        uuid_to_name_map=uuid_to_name_map,
        person_name_map=person_name_map,
        person_factions=person_factions,
    )
    assert uuid1 == uuid_old
    assert method1 == "member_period"

    # Tarmo Tamm on 2024-05-04 -> new uuid
    uuid2, method2 = resolve_speaker_uuid(
        speaker_name="Tarmo Tamm",
        ems_id=None,
        date="2024-05-04",
        known_uuids=known_uuids,
        uuid_to_name_map=uuid_to_name_map,
        person_name_map=person_name_map,
        person_factions=person_factions,
    )
    assert uuid2 == uuid_new
    assert method2 == "member_period"

    # Both covering -> empty + log notice
    both_covering_factions = {
        uuid_old: [{"faction": "Faction A", "start": "2027-01-01", "end": "2027-12-31"}],
        uuid_new: [{"faction": "Faction B", "start": "2027-01-01", "end": "2027-12-31"}],
    }
    capsys.readouterr()  # clear buffer
    uuid_both, method_both = resolve_speaker_uuid(
        speaker_name="Tarmo Tamm",
        ems_id=None,
        date="2027-04-15",
        known_uuids=known_uuids,
        uuid_to_name_map=uuid_to_name_map,
        person_name_map=person_name_map,
        person_factions=both_covering_factions,
        speech_key="speech_both_key",
    )
    assert uuid_both is None
    assert method_both == "unresolved"
    captured_both = capsys.readouterr().out
    assert "Notice: Ambiguous speaker 'Tarmo Tamm'" in captured_both
    assert "speech_both_key" in captured_both

    # Neither covering -> empty + log notice
    neither_covering_factions = {
        uuid_old: [{"faction": "Faction A", "start": "2019-01-01", "end": "2020-01-01"}],
        uuid_new: [{"faction": "Faction B", "start": "2024-01-01", "end": "2025-01-01"}],
    }
    uuid_neither, method_neither = resolve_speaker_uuid(
        speaker_name="Tarmo Tamm",
        ems_id=None,
        date="2022-04-15",
        known_uuids=known_uuids,
        uuid_to_name_map=uuid_to_name_map,
        person_name_map=person_name_map,
        person_factions=neither_covering_factions,
        speech_key="speech_neither_key",
    )
    assert uuid_neither is None
    assert method_neither == "unresolved"
    captured_neither = capsys.readouterr().out
    assert "Notice: Ambiguous speaker 'Tarmo Tamm'" in captured_neither
    assert "speech_neither_key" in captured_neither

    # Non-ambiguous name keeps its UUID
    single_uuid = "single-uuid-kaja"
    uuid_to_name_single = {single_uuid: "Kaja Kallas"}
    person_name_single = {"Kaja Kallas": single_uuid}
    known_single = {single_uuid}
    uuid_single_res, method_single = resolve_speaker_uuid(
        speaker_name="Kaja Kallas",
        ems_id=None,
        date="2024-05-04",
        known_uuids=known_single,
        uuid_to_name_map=uuid_to_name_single,
        person_name_map=person_name_single,
        person_factions=person_factions,
    )
    assert uuid_single_res == single_uuid
    assert method_single == "name"


def test_resolve_speaker_uuid_tarmo_tamm_wrong_ems_id():
    uuid_old = "76afbcdc-b41d-4fc6-b5eb-d0cce01e94d5"
    uuid_new = "236e49d6-eecb-4562-8ad4-bedd586bb149"
    known_uuids = {uuid_old, uuid_new}
    uuid_to_name_map = {uuid_old: "Tarmo Tamm", uuid_new: "Tarmo Tamm"}
    person_name_map = {}
    person_factions = {
        uuid_old: [
            {"faction": "Eesti Keskerakonna fraktsioon", "start": "2019-04-04", "end": "2023-04-01"}
        ],
        uuid_new: [{"faction": "Eesti 200 fraktsioon", "start": "2023-04-11", "end": "2099-12-31"}],
    }

    # Tarmo Tamm speech in 2024 with wrong emsId (uuid_old) must resolve to uuid_new
    resolved_uuid, method = resolve_speaker_uuid(
        speaker_name="Tarmo Tamm",
        ems_id=uuid_old,
        date="2024-05-04",
        known_uuids=known_uuids,
        uuid_to_name_map=uuid_to_name_map,
        person_name_map=person_name_map,
        person_factions=person_factions,
    )
    assert resolved_uuid == uuid_new
    assert method == "member_period"

    # Tarmo Tamm speech in 2021 with valid emsId (uuid_old) resolves to uuid_old
    resolved_uuid2, method2 = resolve_speaker_uuid(
        speaker_name="Tarmo Tamm",
        ems_id=uuid_old,
        date="2021-05-04",
        known_uuids=known_uuids,
        uuid_to_name_map=uuid_to_name_map,
        person_name_map=person_name_map,
        person_factions=person_factions,
    )
    assert resolved_uuid2 == uuid_old
    assert method2 == "ems"


def test_disambiguation_matches_date_rule_for_all_historical_speeches():
    import glob

    from config import PROJECT_ROOT

    data_dir = os.path.join(PROJECT_ROOT, "data", "processed")
    uuid_old = "76afbcdc-b41d-4fc6-b5eb-d0cce01e94d5"
    uuid_new = "236e49d6-eecb-4562-8ad4-bedd586bb149"
    pf_file = os.path.join(data_dir, "person_factions.json")
    if not os.path.exists(pf_file):
        pytest.skip("person_factions.json not found in data/processed")

    with open(pf_file, encoding="utf-8") as f:
        factions = json.load(f)

    from scripts.fetch_stenograms_api import is_member_on_date

    checked = 0
    for fpath in sorted(glob.glob(os.path.join(data_dir, "20*.jsonl"))):
        with open(fpath, encoding="utf-8") as f:
            for line in f:
                if "Tarmo Tamm" not in line:
                    continue
                d = json.loads(line)
                if d.get("speaker") != "Tarmo Tamm":
                    continue
                dt = d.get("date")[:10]
                expected_uuid = uuid_old if dt < "2023-04-10" else uuid_new
                old_active = is_member_on_date(uuid_old, dt, factions)
                new_active = is_member_on_date(uuid_new, dt, factions)
                if old_active and not new_active:
                    resolved = uuid_old
                elif new_active and not old_active:
                    resolved = uuid_new
                else:
                    resolved = None
                assert resolved == expected_uuid, (
                    f"Mismatch on {dt} for speech {d.get('speech_key')}"
                )
                checked += 1

    assert checked > 0


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


def test_repair_speaker_uuids_bak_with_permission_error_fallback(tmp_path, monkeypatch):
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

    def failing_copy(src, dst, *args, **kwargs):
        raise PermissionError("[Errno 1] Operation not permitted (chmod on DrvFS)")

    monkeypatch.setattr(shutil, "copy", failing_copy)

    repair_speaker_uuids(data_dir=str(data_dir), dry_run=False)

    bak_file = data_dir / "2021.jsonl.bak"
    assert bak_file.exists()
    assert "Peaministrikandidaat Kaja Kallas" in bak_file.read_text(encoding="utf-8")


def test_download_from_b2_etag_rules(tmp_path, monkeypatch):
    import hashlib

    from scripts.download_from_b2 import download_from_b2

    monkeypatch.setattr("scripts.download_from_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "dummy_key")
    monkeypatch.setenv("B2_APP_KEY", "dummy_secret")

    # 1. Test active-only download: skipped inactive file does not get ETag, downloaded file gets ETag
    class MockPaginatorActive:
        def paginate(self, Bucket):
            return [
                {
                    "Contents": [
                        {"Key": "2021.jsonl", "Size": 100, "ETag": '"etag-2021-skipped"'},
                        {"Key": "2026.jsonl", "Size": 200, "ETag": '"etag-2026-downloaded"'},
                    ]
                }
            ]

    class MockS3ClientActive:
        def get_paginator(self, operation_name):
            return MockPaginatorActive()

        def download_file(self, bucket, key, local_path, **kwargs):
            Path(local_path).write_text("active-data", encoding="utf-8")

    class MockBoto3Active:
        @staticmethod
        def client(service, **kwargs):
            return MockS3ClientActive()

    monkeypatch.setitem(sys.modules, "boto3", MockBoto3Active)

    ok = download_from_b2(active_year="2026", include_all_history=False)
    assert ok is True

    etags_file = tmp_path / ".b2_etags.json"
    assert etags_file.exists()
    etags = json.loads(etags_file.read_text(encoding="utf-8"))

    # Downloaded file gets ETag
    assert etags.get("2026.jsonl") == "etag-2026-downloaded"
    # Skipped inactive file does NOT get ETag
    assert "2021.jsonl" not in etags

    # 2. Test include_all_history with same-size files and MD5 checks
    hello_bytes = b"hello"
    hello_md5 = hashlib.md5(hello_bytes).hexdigest()

    world_bytes = b"world"  # same size 5 bytes, different md5

    file_match = tmp_path / "match.jsonl"
    file_match.write_bytes(hello_bytes)

    file_diff = tmp_path / "diff.jsonl"
    file_diff.write_bytes(world_bytes)

    file_multipart = tmp_path / "multipart.jsonl"
    file_multipart.write_bytes(hello_bytes)

    class MockPaginatorHistory:
        def paginate(self, Bucket):
            return [
                {
                    "Contents": [
                        # Same size 5, matching MD5 -> should get ETag
                        {"Key": "match.jsonl", "Size": 5, "ETag": f'"{hello_md5}"'},
                        # Same size 5, different MD5 -> downloads and gets ETag
                        {"Key": "diff.jsonl", "Size": 5, "ETag": f'"{hello_md5}"'},
                        # Same size 5, multipart ETag without metadata -> skipped by size, no ETag
                        {"Key": "multipart.jsonl", "Size": 5, "ETag": f'"{hello_md5}-2"'},
                    ]
                }
            ]

    class MockS3ClientHistory:
        def get_paginator(self, operation_name):
            return MockPaginatorHistory()

        def head_object(self, Bucket, Key):
            return {"Metadata": {}, "ContentLength": 5}

        def download_file(self, bucket, key, local_path, **kwargs):
            Path(local_path).write_bytes(hello_bytes)

    class MockBoto3History:
        @staticmethod
        def client(service, **kwargs):
            return MockS3ClientHistory()

    monkeypatch.setitem(sys.modules, "boto3", MockBoto3History)

    # Re-run with include_all_history=True
    ok = download_from_b2(active_year="2026", include_all_history=True)
    assert ok is True

    etags_after = json.loads(etags_file.read_text(encoding="utf-8"))
    # Matching MD5 saved
    assert etags_after.get("match.jsonl") == hello_md5
    # Different MD5 downloaded and saved
    assert etags_after.get("diff.jsonl") == hello_md5
    assert file_diff.read_bytes() == hello_bytes
    # Multipart without metadata not saved
    assert "multipart.jsonl" not in etags_after


def test_fetch_stenograms_rich_none_unedited_fallback(tmp_path, monkeypatch):
    import scripts.fetch_stenograms_api as fsa

    monkeypatch.setattr(fsa, "OUTPUT_DIR_PROCESSED", str(tmp_path))

    # Mock fetch_rich_meeting_data to return None
    monkeypatch.setattr(fsa, "fetch_rich_meeting_data", lambda code: None)

    # Provide factions_map.json and persons.json
    (tmp_path / "factions_map.json").write_text("{}", encoding="utf-8")
    (tmp_path / "persons.json").write_text("[]", encoding="utf-8")

    meeting_code = "202601011000"
    verbatim_item = {
        "link": f"https://stenogrammid.riigikogu.ee/et/{meeting_code}",
        "date": "2026-01-01T10:00:00",
        "title": "Täiskogu erakorraline istung",
        "edited": True,  # Verbatim claims EDITED, but rich is None!
        "agendaItems": [
            {
                "title": "Päevakord 1",
                "events": [
                    {
                        "speaker": "Jaan Tamm",
                        "text": "Austatud esimees, head kolleegid!",
                        "type": "SPEECH",
                    }
                ],
            }
        ],
    }

    class MockResponse:
        status_code = 200

        def json(self):
            return [verbatim_item]

    def mock_requests_get(url, *args, **kwargs):
        return MockResponse()

    monkeypatch.setattr("requests.get", mock_requests_get)
    monkeypatch.setattr("time.sleep", lambda s: None)

    processed_codes = set()
    ok = fsa.fetch_and_process_stenograms(
        start_date="2026-01-01",
        end_date="2026-01-01",
        processed_meeting_codes=processed_codes,
    )

    # Rich data was None -> has_errors must be True, so ok must be False
    assert ok is False

    # Meeting must NOT be added to processed_meeting_codes
    assert meeting_code not in processed_codes

    # Check saved JSONL record: status must be UNEDITED
    jsonl_file = tmp_path / "2026.jsonl"
    assert jsonl_file.exists()
    lines = [
        json.loads(line) for line in jsonl_file.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(lines) == 1
    assert lines[0]["status"] == "UNEDITED"
    assert lines[0]["speaker"] == "Jaan Tamm"


def test_ensure_schema_idempotency(tmp_path):
    from sqlalchemy import create_engine

    from src.load.indexes import create_indexes
    from src.load.migrations import apply_migrations

    db_path = str(tmp_path / "test_schema.sqlite")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE attendance (id INTEGER PRIMARY KEY, session_date TEXT, voting_uuid TEXT, member_name TEXT, faction TEXT, status TEXT);"
    )
    conn.commit()
    conn.close()

    eng = create_engine(f"sqlite:///{db_path}")

    # First call: should add member_uuid column and index
    apply_migrations(eng)
    create_indexes(eng)

    conn = sqlite3.connect(db_path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(attendance)").fetchall()]
    assert "member_uuid" in cols
    indices = [r[1] for r in conn.execute("PRAGMA index_list(attendance)").fetchall()]
    assert "idx_attendance_member_uuid" in indices
    conn.close()

    # Second call: must be idempotent and succeed without error
    apply_migrations(eng)
    create_indexes(eng)


def test_repair_attendance_uuids_logic(tmp_path, monkeypatch):
    from scripts.repair_attendance_uuids import repair_attendance_uuids

    data_dir = str(tmp_path / "processed")
    os.makedirs(data_dir, exist_ok=True)

    db_path = str(tmp_path / "test_att.sqlite")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE speeches (id INTEGER PRIMARY KEY, speaker TEXT, speaker_uuid TEXT, ems_id TEXT);"
    )
    # Map old name Siret Kotka-Repinski to uuid-kotka via ems_id in speeches
    conn.execute(
        "INSERT INTO speeches (id, speaker, ems_id) VALUES (1, 'Siret Kotka-Repinski', 'uuid-siret-kotka');"
    )
    conn.execute(
        "CREATE TABLE attendance (id INTEGER PRIMARY KEY, session_date TEXT, voting_uuid TEXT, member_uuid TEXT, member_name TEXT, faction TEXT, status TEXT);"
    )
    conn.commit()
    conn.close()

    # persons.json
    persons = [
        {"uuid": "76afbcdc-b41d-4fc6-b5eb-d0cce01e94d5", "full_name": "Tarmo Tamm"},
        {"uuid": "236e49d6-eecb-4562-8ad4-bedd586bb149", "full_name": "Tarmo Tamm"},
        {"uuid": "uuid-kaja-kallas", "full_name": "Kaja Kallas"},
        {"uuid": "uuid-siret-kotka", "full_name": "Siret Kotka"},
    ]
    with open(os.path.join(data_dir, "persons.json"), "w", encoding="utf-8") as f:
        json.dump(persons, f)

    person_factions = {
        "76afbcdc-b41d-4fc6-b5eb-d0cce01e94d5": [
            {"faction": "Keskerakond", "start": "2019-04-04", "end": "2023-04-09"}
        ],
        "236e49d6-eecb-4562-8ad4-bedd586bb149": [
            {"faction": "Eesti 200", "start": "2023-04-10", "end": "2099-12-31"}
        ],
    }
    with open(os.path.join(data_dir, "person_factions.json"), "w", encoding="utf-8") as f:
        json.dump(person_factions, f)

    att_file = os.path.join(data_dir, "attendance.jsonl")
    lines = [
        {
            "session_date": "2023-04-09T10:00:00",
            "voting_uuid": "v1",
            "member_name": "Tarmo Tamm",
            "status": "KOHAL",
        },
        {
            "session_date": "2023-04-10T10:00:00",
            "voting_uuid": "v2",
            "member_name": "Tarmo Tamm",
            "status": "KOHAL",
        },
        {
            "session_date": "2023-05-01T10:00:00",
            "voting_uuid": "v3",
            "member_name": "Kaja Kallas",
            "status": "KOHAL",
        },
        {
            "session_date": "2023-05-01T10:00:00",
            "voting_uuid": "v4",
            "member_name": "Siret Kotka-Repinski",
            "status": "KOHAL",
        },
        {
            "session_date": "2023-05-01T10:00:00",
            "voting_uuid": "v5",
            "member_name": "Tundmatu Külaline",
            "status": "KOHAL",
        },
    ]
    with open(att_file, "w", encoding="utf-8") as f:
        for record_dict in lines:
            f.write(json.dumps(record_dict) + "\n")

    # Insert corresponding rows into attendance table
    conn = sqlite3.connect(db_path)
    for idx, record_dict in enumerate(lines, 1):
        conn.execute(
            "INSERT INTO attendance (id, session_date, voting_uuid, member_name, status) VALUES (?, ?, ?, ?, ?)",
            (
                idx,
                record_dict["session_date"],
                record_dict["voting_uuid"],
                record_dict["member_name"],
                record_dict["status"],
            ),
        )
    conn.commit()
    conn.close()

    # 1. Dry run: file must not be modified
    res_dry = repair_attendance_uuids(data_dir=data_dir, dry_run=True, db_path=db_path)
    assert res_dry["needed_repair"] == 5
    assert res_dry["resolved_tarmo_tamm"] == 2
    assert res_dry["resolved_canonical"] == 1
    assert res_dry["resolved_old_names"] == 1
    assert "Tundmatu Külaline" in res_dry["unresolved_names"]
    assert not os.path.exists(att_file + ".bak")

    # 2. Apply run: file must be modified and .bak created
    res_apply = repair_attendance_uuids(data_dir=data_dir, dry_run=False, db_path=db_path)
    assert res_apply["needed_repair"] == 5
    assert os.path.exists(att_file + ".bak")

    # Check updated lines in attendance.jsonl
    with open(att_file, encoding="utf-8") as f:
        updated_lines = [json.loads(line_str) for line_str in f if line_str.strip()]

    assert updated_lines[0]["member_uuid"] == "76afbcdc-b41d-4fc6-b5eb-d0cce01e94d5"
    assert updated_lines[1]["member_uuid"] == "236e49d6-eecb-4562-8ad4-bedd586bb149"
    assert updated_lines[2]["member_uuid"] == "uuid-kaja-kallas"
    assert updated_lines[3]["member_uuid"] == "uuid-siret-kotka"
    assert updated_lines[4]["member_uuid"] is None

    # Check database was updated
    conn = sqlite3.connect(db_path)
    db_u1 = conn.execute("SELECT member_uuid FROM attendance WHERE voting_uuid = 'v1'").fetchone()[
        0
    ]
    db_u2 = conn.execute("SELECT member_uuid FROM attendance WHERE voting_uuid = 'v2'").fetchone()[
        0
    ]
    db_u3 = conn.execute("SELECT member_uuid FROM attendance WHERE voting_uuid = 'v3'").fetchone()[
        0
    ]
    db_u4 = conn.execute("SELECT member_uuid FROM attendance WHERE voting_uuid = 'v4'").fetchone()[
        0
    ]
    db_u5 = conn.execute("SELECT member_uuid FROM attendance WHERE voting_uuid = 'v5'").fetchone()[
        0
    ]
    conn.close()

    assert db_u1 == "76afbcdc-b41d-4fc6-b5eb-d0cce01e94d5"
    assert db_u2 == "236e49d6-eecb-4562-8ad4-bedd586bb149"
    assert db_u3 == "uuid-kaja-kallas"
    assert db_u4 == "uuid-siret-kotka"
    assert db_u5 is None


def test_sync_database_votes_error_does_not_block_lemmas_and_terms(monkeypatch):
    from scripts.sync_database import sync_database
    from src.load.database import SessionLocal
    from src.load.loader import create_tables
    from src.load.models import SystemMeta

    create_tables()

    # Clear last_sync_at
    s = SessionLocal()
    s.query(SystemMeta).filter_by(key="last_sync_at").delete()
    s.commit()
    s.close()

    lemmas_called = []
    terms_called = []

    monkeypatch.setattr("scripts.sync_database.sync_current_year_speeches", lambda: [])
    monkeypatch.setattr(
        "scripts.sync_database.build_missing_lemmas", lambda: lemmas_called.append(True) or 0
    )
    monkeypatch.setattr(
        "scripts.sync_database.build_missing_terms", lambda: terms_called.append(True)
    )
    monkeypatch.setattr("scripts.sync_database.load_attendance_to_database", lambda: None)
    monkeypatch.setattr("scripts.sync_database.load_persons_to_database", lambda: None)

    def failing_votes(*args, **kwargs):
        raise RuntimeError("Vote schema error")

    monkeypatch.setattr("scripts.sync_database.load_votes_to_database", failing_votes)

    result = sync_database(skip_download=True)
    assert result is False
    assert len(lemmas_called) == 1
    assert len(terms_called) == 1

    s = SessionLocal()
    meta = s.query(SystemMeta).filter_by(key="last_sync_at").first()
    assert meta is None
    s.close()


def test_sync_current_year_speeches_one_session_fails_others_loaded(tmp_path, monkeypatch):
    from scripts.sync_database import sync_current_year_speeches, sync_database
    from src.load.database import SessionLocal
    from src.load.loader import create_tables
    from src.load.models import Speech, SystemMeta

    create_tables()
    monkeypatch.setattr("scripts.sync_database.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("scripts.sync_database.active_years", lambda: ["2026"])

    s = SessionLocal()
    s.query(Speech).delete()
    s.query(SystemMeta).filter_by(key="last_sync_at").delete()
    s.commit()
    s.close()

    speeches_2026 = [
        {
            "date": "2026-06-01",
            "time": "1000",
            "source_file": "good_session.api",
            "source_url": "https://stenogrammid.riigikogu.ee/test1",
            "speaker": "Speaker One",
            "text": "Good speech text",
            "status": "EDITED",
        },
        {
            # Missing "date" key triggers KeyError when creating Speech model
            "time": "1100",
            "source_file": "bad_session.api",
            "source_url": "https://stenogrammid.riigikogu.ee/test2",
            "speaker": "Speaker Two",
            "text": "Bad speech text",
            "status": "EDITED",
        },
    ]

    year_file = tmp_path / "2026.jsonl"
    with open(year_file, "w", encoding="utf-8") as f:
        for sp in speeches_2026:
            f.write(json.dumps(sp) + "\n")

    failed = sync_current_year_speeches("2026")
    assert "bad_session.api" in failed

    s = SessionLocal()
    good = s.query(Speech).filter_by(source_file="good_session.api").first()
    bad = s.query(Speech).filter_by(source_file="bad_session.api").first()
    assert good is not None
    assert bad is None
    s.close()

    # Now verify sync_database returns False when speech sync has failures
    monkeypatch.setattr(
        "scripts.sync_database.sync_current_year_speeches", lambda: ["bad_session.api"]
    )
    monkeypatch.setattr("scripts.sync_database.build_missing_lemmas", lambda: 0)
    monkeypatch.setattr("scripts.sync_database.build_missing_terms", lambda: None)
    monkeypatch.setattr("scripts.sync_database.load_attendance_to_database", lambda: None)
    monkeypatch.setattr("scripts.sync_database.load_persons_to_database", lambda: None)
    monkeypatch.setattr("scripts.sync_database.load_votes_to_database", lambda **k: None)

    res = sync_database(skip_download=True)
    assert res is False

    s = SessionLocal()
    meta = s.query(SystemMeta).filter_by(key="last_sync_at").first()
    assert meta is None
    s.close()


def test_sync_database_persons_error_results_in_false(monkeypatch):
    from scripts.sync_database import sync_database
    from src.load.database import SessionLocal
    from src.load.loader import create_tables
    from src.load.models import SystemMeta

    create_tables()

    s = SessionLocal()
    s.query(SystemMeta).filter_by(key="last_sync_at").delete()
    s.commit()
    s.close()

    monkeypatch.setattr("scripts.sync_database.sync_current_year_speeches", lambda: [])
    monkeypatch.setattr("scripts.sync_database.build_missing_lemmas", lambda: 0)
    monkeypatch.setattr("scripts.sync_database.build_missing_terms", lambda: None)
    monkeypatch.setattr("scripts.sync_database.load_attendance_to_database", lambda: None)

    def failing_persons():
        raise RuntimeError("Persons database load error")

    monkeypatch.setattr("scripts.sync_database.load_persons_to_database", failing_persons)
    monkeypatch.setattr("scripts.sync_database.load_votes_to_database", lambda **k: None)

    result = sync_database(skip_download=True)
    assert result is False

    s = SessionLocal()
    meta = s.query(SystemMeta).filter_by(key="last_sync_at").first()
    assert meta is None
    s.close()


def test_sync_database_unlemmatized_speeches_results_in_false(monkeypatch):
    from scripts.sync_database import sync_database
    from src.load.database import SessionLocal
    from src.load.loader import create_tables
    from src.load.models import SystemMeta

    create_tables()

    s = SessionLocal()
    s.query(SystemMeta).filter_by(key="last_sync_at").delete()
    s.commit()
    s.close()

    monkeypatch.setattr("scripts.sync_database.sync_current_year_speeches", lambda: [])
    monkeypatch.setattr("scripts.sync_database.build_missing_lemmas", lambda: 5)
    monkeypatch.setattr("scripts.sync_database.build_missing_terms", lambda: None)
    monkeypatch.setattr("scripts.sync_database.load_attendance_to_database", lambda: None)
    monkeypatch.setattr("scripts.sync_database.load_persons_to_database", lambda: None)
    monkeypatch.setattr("scripts.sync_database.load_votes_to_database", lambda **k: None)

    result = sync_database(skip_download=True)
    assert result is False

    s = SessionLocal()
    meta = s.query(SystemMeta).filter_by(key="last_sync_at").first()
    assert meta is None
    s.close()


def test_verify_pipeline_integrity_report_and_blocked_files(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    import requests

    from scripts.verify_pipeline_integrity import verify_pipeline_integrity

    monkeypatch.setattr("scripts.verify_pipeline_integrity.OUTPUT_DIR_PROCESSED", str(tmp_path))

    today = datetime.now()
    yesterday = today - timedelta(days=1)
    two_days_ago = today - timedelta(days=2)

    # In local JSONL, yesterday's session has 0 speeches (truncated/empty)
    # two_days_ago session is completely missing from local JSONL
    code_truncated = f"{yesterday.strftime('%Y%m%d')}1200"
    file_truncated = f"{yesterday.strftime('%Y-%m-%d')}_1200.api"
    year_file = tmp_path / f"{yesterday.year}.jsonl"
    # An empty session: speech_count 0 can happen if represented with an entry having empty text or mock
    # Wait, load_local_sessions_from_jsonl counts lines per source_file.
    # If a source_file appears with speech_count 0... wait, how does speech_count become 0?
    # In load_local_sessions_from_jsonl, if a line has valid source_file, speech_count += 1.
    # But wait! If local_count is checked against rich meeting API (sample checks) or empty:
    # Notice line 135: if sp_count == 0: truncated.
    # Wait, if speech_count is 0 in local_sessions, or if sample check sees local_count < official_speeches * 0.8:
    # If sample_meeting_checks > 0, rich meeting official_speeches > 5 and local_count < official_speeches * 0.8 -> truncated!

    # Write 1 speech for truncated session
    mock_speech = {
        "source_file": file_truncated,
        "date": yesterday.strftime("%Y-%m-%d"),
        "source_url": f"https://stenogrammid.riigikogu.ee/et/{code_truncated}#PKP-1",
        "text": "Üks kõne",
    }
    year_file.write_text(json.dumps(mock_speech) + "\n", encoding="utf-8")

    code_missing = f"{two_days_ago.strftime('%Y%m%d')}1000"

    class MockResp:
        def __init__(self, url):
            self.url = url
            self.status_code = 200

        def json(self):
            if "meeting" in self.url:
                # Rich meeting for code_truncated has 10 official speeches, but local only has 1 -> truncated!
                return {
                    "stenograph": {
                        "agendaItems": [
                            {
                                "speeches": [
                                    {
                                        "name": f"Kõneleja {i}",
                                        "content": "Kõne sisu",
                                        "speechType": "SPEECH",
                                    }
                                    for i in range(10)
                                ]
                            }
                        ]
                    }
                }
            # Verbatims list
            return [
                {
                    "date": f"{yesterday.strftime('%Y-%m-%d')}T12:00:00.000+00:00",
                    "title": "Kärbitud istung",
                    "link": f"https://stenogrammid.riigikogu.ee/{code_truncated}",
                },
                {
                    "date": f"{two_days_ago.strftime('%Y-%m-%d')}T10:00:00.000+00:00",
                    "title": "Puuduv istung",
                    "link": f"https://stenogrammid.riigikogu.ee/{code_missing}",
                },
            ]

    monkeypatch.setattr(requests, "get", lambda url, *args, **kwargs: MockResp(url))

    ok = verify_pipeline_integrity(days=7, fail_on_missing=True, sample_meeting_checks=1)
    assert ok is False

    report_path = tmp_path / "integrity_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))

    missing_codes = [s["code"] for s in report["missing_sessions"]]
    assert code_missing in missing_codes

    truncated_codes = [s["code"] for s in report["truncated_sessions"]]
    assert code_truncated in truncated_codes

    # blocked_files MUST contain the truncated session's year file, but NOT block missing sessions
    assert f"{yesterday.year}.jsonl" in report["blocked_files"]


def test_verify_pipeline_integrity_skips_ignored_verbatim(tmp_path, monkeypatch):
    import requests

    from config import IGNORED_VERBATIMS
    from scripts.verify_pipeline_integrity import verify_pipeline_integrity

    monkeypatch.setattr("scripts.verify_pipeline_integrity.OUTPUT_DIR_PROCESSED", str(tmp_path))

    ignored_code = next(iter(IGNORED_VERBATIMS.keys()))

    class MockResp:
        def __init__(self, url):
            self.url = url
            self.status_code = 200

        def json(self):
            return [
                {
                    "date": "2021-03-25T00:48:00.000+00:00",
                    "title": "Ignored night verbatim",
                    "link": f"https://stenogrammid.riigikogu.ee/{ignored_code}",
                    "edited": True,
                    "agendaItems": [],
                }
            ]

    monkeypatch.setattr(requests, "get", lambda url, *args, **kwargs: MockResp(url))

    ok = verify_pipeline_integrity(days=60, fail_on_missing=True, sample_meeting_checks=0)
    assert ok is True

    report_path = tmp_path / "integrity_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert len(report["missing_sessions"]) == 0
    assert len(report["truncated_sessions"]) == 0


def test_fetch_stenograms_fetches_20_day_old_missing_verbatim(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    import requests

    from scripts.fetch_stenograms_api import fetch_and_process_stenograms

    monkeypatch.setattr("scripts.fetch_stenograms_api.OUTPUT_DIR_PROCESSED", str(tmp_path))

    today = datetime.now()
    yesterday = today - timedelta(days=1)
    twenty_days_ago = today - timedelta(days=20)

    # Write yesterday's session in local JSONL, so latest_existing_date is yesterday
    code_yesterday = f"{yesterday.strftime('%Y%m%d')}1000"
    file_yesterday = f"{yesterday.strftime('%Y-%m-%d')}_1000.api"
    y_file = tmp_path / f"{yesterday.year}.jsonl"
    mock_existing = {
        "source_file": file_yesterday,
        "date": yesterday.strftime("%Y-%m-%d"),
        "time": "1000",
        "source_url": f"https://stenogrammid.riigikogu.ee/et/{code_yesterday}#PKP-1",
        "text": "Eile toimunud kõne",
        "status": "EDITED",
    }
    y_file.write_text(json.dumps(mock_existing) + "\n", encoding="utf-8")

    code_missing_20d = f"{twenty_days_ago.strftime('%Y%m%d')}1400"
    file_missing_20d = f"{twenty_days_ago.strftime('%Y-%m-%d')}_1400.api"

    fetched_meeting_codes = []

    all_verbatims = [
        {
            "date": f"{yesterday.strftime('%Y-%m-%d')}T10:00:00.000+00:00",
            "title": "Eilne istung",
            "link": f"https://stenogrammid.riigikogu.ee/{code_yesterday}",
            "edited": True,
            "agendaItems": [],
        },
        {
            "date": f"{twenty_days_ago.strftime('%Y-%m-%d')}T14:00:00.000+00:00",
            "title": "20 päeva vana puuduv istung",
            "link": f"https://stenogrammid.riigikogu.ee/{code_missing_20d}",
            "edited": True,
            "agendaItems": [],
        },
    ]

    class MockResp:
        def __init__(self, url, params=None):
            self.url = url
            self.params = params or {}
            self.status_code = 200

        def json(self):
            if "meeting" in self.url:
                code = self.url.rstrip("/").split("/")[-1]
                fetched_meeting_codes.append(code)
                return {
                    "meetingStatus": "EDITED",
                    "stenograph": {
                        "agendaItems": [
                            {
                                "title": "Päevakord",
                                "speeches": [
                                    {
                                        "name": "Kõneleja",
                                        "content": "20 päeva vana kõne sisu",
                                        "speechType": "SPEECH",
                                        "startTime": f"{twenty_days_ago.strftime('%Y-%m-%d')}T14:05:00.000+02:00",
                                        "endTime": f"{twenty_days_ago.strftime('%Y-%m-%d')}T14:10:00.000+02:00",
                                    }
                                ],
                            }
                        ]
                    },
                }
            # Filter verbatims by requested startDate/endDate like the real API
            start = self.params.get("startDate")
            end = self.params.get("endDate")
            filtered = []
            for item in all_verbatims:
                d = item["date"][:10]
                if start and d < start:
                    continue
                if end and d > end:
                    continue
                filtered.append(item)
            return filtered

    monkeypatch.setattr(
        requests, "get", lambda url, *args, **kwargs: MockResp(url, kwargs.get("params"))
    )
    monkeypatch.setattr("time.sleep", lambda *args: None)

    ok = fetch_and_process_stenograms()
    assert ok is True
    assert code_missing_20d in fetched_meeting_codes

    # Check that 20-day-old session was saved into the JSONL file
    target_year_file = tmp_path / f"{twenty_days_ago.year}.jsonl"
    assert target_year_file.exists()
    content = target_year_file.read_text(encoding="utf-8")
    assert file_missing_20d in content
    assert "20 päeva vana kõne sisu" in content


def test_fetch_stenograms_explicit_start_date_skips_missing_check(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    import requests

    from scripts.fetch_stenograms_api import fetch_and_process_stenograms

    monkeypatch.setattr("scripts.fetch_stenograms_api.OUTPUT_DIR_PROCESSED", str(tmp_path))

    today = datetime.now()
    yesterday = today - timedelta(days=1)
    twenty_days_ago = today - timedelta(days=20)

    code_yesterday = f"{yesterday.strftime('%Y%m%d')}1000"
    file_yesterday = f"{yesterday.strftime('%Y-%m-%d')}_1000.api"
    y_file = tmp_path / f"{yesterday.year}.jsonl"
    mock_existing = {
        "source_file": file_yesterday,
        "date": yesterday.strftime("%Y-%m-%d"),
        "time": "1000",
        "source_url": f"https://stenogrammid.riigikogu.ee/et/{code_yesterday}#PKP-1",
        "text": "Eilne kõne",
        "status": "EDITED",
    }
    y_file.write_text(json.dumps(mock_existing) + "\n", encoding="utf-8")

    code_missing_20d = f"{twenty_days_ago.strftime('%Y%m%d')}1400"
    fetched_meeting_codes = []

    all_verbatims = [
        {
            "date": f"{yesterday.strftime('%Y-%m-%d')}T10:00:00.000+00:00",
            "title": "Eilne istung",
            "link": f"https://stenogrammid.riigikogu.ee/{code_yesterday}",
            "edited": True,
            "agendaItems": [],
        },
        {
            "date": f"{twenty_days_ago.strftime('%Y-%m-%d')}T14:00:00.000+00:00",
            "title": "20 päeva vana puuduv istung",
            "link": f"https://stenogrammid.riigikogu.ee/{code_missing_20d}",
            "edited": True,
            "agendaItems": [],
        },
    ]

    class MockResp:
        def __init__(self, url, params=None):
            self.url = url
            self.params = params or {}
            self.status_code = 200

        def json(self):
            if "meeting" in self.url:
                code = self.url.rstrip("/").split("/")[-1]
                fetched_meeting_codes.append(code)
                return {"meetingStatus": "EDITED", "stenograph": {"agendaItems": []}}
            start = self.params.get("startDate")
            end = self.params.get("endDate")
            filtered = []
            for item in all_verbatims:
                d = item["date"][:10]
                if start and d < start:
                    continue
                if end and d > end:
                    continue
                filtered.append(item)
            return filtered

    monkeypatch.setattr(
        requests, "get", lambda url, *args, **kwargs: MockResp(url, kwargs.get("params"))
    )
    monkeypatch.setattr("time.sleep", lambda *args: None)

    # Call with explicit start_date: 60-day check MUST NOT run
    ok = fetch_and_process_stenograms(start_date=yesterday.strftime("%Y-%m-%d"))
    assert ok is True
    assert code_missing_20d not in fetched_meeting_codes


def test_fetch_stenograms_skips_ignored_verbatim(tmp_path, monkeypatch):
    import requests

    from config import IGNORED_VERBATIMS
    from scripts.fetch_stenograms_api import fetch_and_process_stenograms

    monkeypatch.setattr("scripts.fetch_stenograms_api.OUTPUT_DIR_PROCESSED", str(tmp_path))

    ignored_code = next(iter(IGNORED_VERBATIMS.keys()))
    fetched_codes = []

    class MockResp:
        def __init__(self, url):
            self.url = url
            self.status_code = 200

        def json(self):
            if "meeting" in self.url:
                code = self.url.rstrip("/").split("/")[-1]
                fetched_codes.append(code)
                return {}
            return [
                {
                    "date": "2021-03-25T00:48:00.000+00:00",
                    "title": "Ignored night verbatim",
                    "link": f"https://stenogrammid.riigikogu.ee/{ignored_code}",
                    "edited": True,
                    "agendaItems": [],
                }
            ]

    monkeypatch.setattr(requests, "get", lambda url, *args, **kwargs: MockResp(url))
    monkeypatch.setattr("time.sleep", lambda *args: None)

    ok = fetch_and_process_stenograms()
    assert ok is True
    assert ignored_code not in fetched_codes


def test_compute_capped_duration_seconds():
    from src.load.loader import compute_capped_duration_seconds

    # 1. Overlapping end time is capped at next speech start
    dur_overlapping = compute_capped_duration_seconds(
        start_time_str="2026-10-15T10:00:00.000+02:00",
        end_time_str="2026-10-15T10:15:00.000+02:00",
        next_start_time_str="2026-10-15T10:05:00.000+02:00",
    )
    assert dur_overlapping == 300  # 5 minutes, not 15

    # 2. Last speech (no next start time) is unchanged
    dur_last = compute_capped_duration_seconds(
        start_time_str="2026-10-15T10:05:00.000+02:00",
        end_time_str="2026-10-15T10:20:00.000+02:00",
        next_start_time_str=None,
    )
    assert dur_last == 900  # 15 minutes

    # 3. Next speech starting earlier (inverted start time) changes nothing
    dur_inverted = compute_capped_duration_seconds(
        start_time_str="2026-10-15T10:10:00.000+02:00",
        end_time_str="2026-10-15T10:15:00.000+02:00",
        next_start_time_str="2026-10-15T10:05:00.000+02:00",
    )
    assert dur_inverted == 300  # end_time - start_time

    # 4. Missing start or end returns None
    assert compute_capped_duration_seconds(None, "2026-10-15T10:15:00") is None
    assert compute_capped_duration_seconds("2026-10-15T10:10:00", None) is None

    # 5. Implausible duration (> 3 hours = 10,800 s) returns None
    dur_implausible = compute_capped_duration_seconds(
        start_time_str="2026-10-15T10:00:00.000+02:00",
        end_time_str="2026-10-15T14:00:00.000+02:00",  # 4 hours
        next_start_time_str=None,
        speech_id=12345,
    )
    assert dur_implausible is None

    # Exactly 3 hours (10,800 s) is accepted
    dur_exact_3h = compute_capped_duration_seconds(
        start_time_str="2026-10-15T10:00:00.000+02:00",
        end_time_str="2026-10-15T13:00:00.000+02:00",  # 3 hours
        next_start_time_str=None,
    )
    assert dur_exact_3h == 10800

    # 6. Identical next_start_time does not produce 0 s
    dur_same_start = compute_capped_duration_seconds(
        start_time_str="2026-10-15T10:00:00.000+02:00",
        end_time_str="2026-10-15T10:10:00.000+02:00",
        next_start_time_str="2026-10-15T10:00:00.000+02:00",  # Same start time!
    )
    assert dur_same_start == 600  # Not 0!


def test_apply_capped_durations_identical_start_time():
    from src.load.loader import apply_capped_durations_to_session_speeches

    speeches = [
        {
            "id": 1,
            "start_time": "2026-10-15T10:00:00.000+02:00",
            "end_time": "2026-10-15T10:10:00.000+02:00",
        },
        {
            "id": 2,
            "start_time": "2026-10-15T10:00:00.000+02:00",  # identical start
            "end_time": "2026-10-15T10:15:00.000+02:00",
        },
        {
            "id": 3,
            "start_time": "2026-10-15T10:05:00.000+02:00",  # later start
            "end_time": "2026-10-15T10:20:00.000+02:00",
        },
    ]
    apply_capped_durations_to_session_speeches(speeches)
    # Speeches 1 and 2 are capped at next later start (10:05 = 300 s), not 0 s!
    assert speeches[0]["duration_seconds"] == 300
    assert speeches[1]["duration_seconds"] == 300
    # Speech 3 is last so keeps end_time - start_time (900 s)
    assert speeches[2]["duration_seconds"] == 900


def test_recompute_durations_dry_run_and_apply_idempotent(tmp_path, monkeypatch):
    from scripts.recompute_durations import recompute_durations
    from src.load.database import SessionLocal
    from src.load.loader import create_tables
    from src.load.models import Speech

    create_tables()
    session = SessionLocal()

    # Clean existing speeches
    session.query(Speech).filter(Speech.source_file == "test_session_dur.api").delete()
    session.commit()

    sp1 = Speech(
        date="2026-10-15",
        time="1000",
        source_file="test_session_dur.api",
        source_url="https://stenogrammid.riigikogu.ee/et/123#PKP-1",
        speaker="Kõneleja Üks",
        start_time="2026-10-15T10:00:00.000+02:00",
        end_time="2026-10-15T10:30:00.000+02:00",
        duration_seconds=1800,  # Uncapped: 30 minutes
        text="Esimene pikk kõne",
    )
    sp2 = Speech(
        date="2026-10-15",
        time="1005",
        source_file="test_session_dur.api",
        source_url="https://stenogrammid.riigikogu.ee/et/123#PKP-2",
        speaker="Kõneleja Kaks",
        start_time="2026-10-15T10:05:00.000+02:00",
        end_time="2026-10-15T10:15:00.000+02:00",
        duration_seconds=600,  # 10 minutes
        text="Teine kõne",
    )
    session.add_all([sp1, sp2])
    session.commit()
    sp1_id = sp1.id
    sp2_id = sp2.id
    session.close()

    try:
        # 1. Dry run: finds 1 modified row, but database is NOT modified
        stats_dry = recompute_durations(apply=False)
        assert stats_dry["modified_rows"] == 1
        assert len(stats_dry["top_10"]) == 1
        assert stats_dry["top_10"][0]["diff"] == 1500  # 1800 -> 300

        check_s = SessionLocal()
        db_sp1 = check_s.query(Speech).filter(Speech.id == sp1_id).first()
        assert db_sp1.duration_seconds == 1800  # Still old value in DB!
        check_s.close()

        # 2. Apply: updates database
        stats_apply = recompute_durations(apply=True)
        assert stats_apply["modified_rows"] == 1

        check_s = SessionLocal()
        db_sp1 = check_s.query(Speech).filter(Speech.id == sp1_id).first()
        assert db_sp1.duration_seconds == 300  # Capped at 10:05!
        db_sp2 = check_s.query(Speech).filter(Speech.id == sp2_id).first()
        assert db_sp2.duration_seconds == 600  # Last speech unchanged!
        check_s.close()

        # 3. Repeat apply: idempotent (0 modified rows)
        stats_repeat = recompute_durations(apply=True)
        assert stats_repeat["modified_rows"] == 0

    finally:
        clean_s = SessionLocal()
        clean_s.query(Speech).filter(Speech.source_file == "test_session_dur.api").delete()
        clean_s.commit()
        clean_s.close()


def test_sync_database_lock_creates_and_removes(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    import pytest

    import scripts.sync_database as sd

    monkeypatch.setattr(sd, "DATABASE_DIR", str(tmp_path))
    monkeypatch.setattr(sd, "download_from_b2", lambda: True)
    monkeypatch.setattr(sd, "create_tables", lambda: None)
    monkeypatch.setattr(sd, "create_indexes", lambda: None)
    monkeypatch.setattr(sd, "build_missing_lemmas", lambda: 0)
    monkeypatch.setattr(sd, "build_missing_terms", lambda: None)
    monkeypatch.setattr(sd, "load_attendance_to_database", lambda: None)
    monkeypatch.setattr(sd, "load_persons_to_database", lambda: None)
    monkeypatch.setattr(sd, "load_votes_to_database", lambda *a, **kw: None)

    mock_session = MagicMock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = None
    monkeypatch.setattr(sd, "SessionLocal", lambda: mock_session)

    lock_file = tmp_path / ".sync.lock"

    checked_lock = False

    def check_lock_during_execution(*a, **kw):
        nonlocal checked_lock
        assert lock_file.exists()
        content = lock_file.read_text(encoding="utf-8")
        assert str(os.getpid()) in content
        checked_lock = True
        return []

    monkeypatch.setattr(sd, "sync_current_year_speeches", check_lock_during_execution)

    assert sd.sync_database(skip_download=True) is True
    assert checked_lock is True
    assert not lock_file.exists()

    # Verify lock is cleaned up on unhandled exception
    def fatal_err(*a, **kw):
        assert lock_file.exists()
        raise KeyboardInterrupt()

    monkeypatch.setattr(sd, "create_tables", fatal_err)
    with pytest.raises(KeyboardInterrupt):
        sd.sync_database(skip_download=True)
    assert not lock_file.exists()


def test_sync_database_lock_active_exits_1(tmp_path, monkeypatch, capsys):
    import pytest

    import scripts.sync_database as sd
    from src.load.lock import sync_lock

    monkeypatch.setattr(sd, "DATABASE_DIR", str(tmp_path))
    lock_file = tmp_path / ".sync.lock"

    # Another run holds the lock
    with sync_lock(database_dir=str(tmp_path)):
        with pytest.raises(SystemExit) as exc_info:
            sd.sync_database(skip_download=True)
        assert lock_file.exists()
        assert str(os.getpid()) in lock_file.read_text(encoding="utf-8")
    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "Sync already running" in captured.out


def test_sync_database_lock_leftover_file_taken_over(tmp_path, monkeypatch, capsys):
    """A lock file left by a killed run (no process holds the lock) does not block a new run."""
    from unittest.mock import MagicMock

    import scripts.sync_database as sd

    monkeypatch.setattr(sd, "DATABASE_DIR", str(tmp_path))
    monkeypatch.setattr(sd, "download_from_b2", lambda: True)
    monkeypatch.setattr(sd, "create_tables", lambda: None)
    monkeypatch.setattr(sd, "create_indexes", lambda: None)
    monkeypatch.setattr(sd, "sync_current_year_speeches", lambda *a, **kw: [])
    monkeypatch.setattr(sd, "build_missing_lemmas", lambda: 0)
    monkeypatch.setattr(sd, "build_missing_terms", lambda: None)
    monkeypatch.setattr(sd, "load_attendance_to_database", lambda: None)
    monkeypatch.setattr(sd, "load_persons_to_database", lambda: None)
    monkeypatch.setattr(sd, "load_votes_to_database", lambda *a, **kw: None)

    mock_session = MagicMock()
    mock_session.query.return_value.filter_by.return_value.first.return_value = None
    monkeypatch.setattr(sd, "SessionLocal", lambda: mock_session)

    lock_file = tmp_path / ".sync.lock"
    lock_file.write_text("88888\n2026-10-16T00:00:00\n", encoding="utf-8")

    assert sd.sync_database(skip_download=True) is True
    captured = capsys.readouterr()
    assert "Taking over a leftover lock file (pid 88888)" in captured.out
    assert not lock_file.exists()


@pytest.mark.parametrize("failure", ["http_error", "connection_error", "not_a_list"])
def test_verify_pipeline_integrity_unverified_raises(tmp_path, monkeypatch, failure):
    """If the official verbatims cannot be fetched, integrity is unverified, not OK."""
    import requests

    from scripts.verify_pipeline_integrity import (
        IntegrityUnverifiedError,
        verify_pipeline_integrity,
    )

    monkeypatch.setattr("scripts.verify_pipeline_integrity.OUTPUT_DIR_PROCESSED", str(tmp_path))

    class MockResp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.headers = {}

        def json(self):
            return self._payload

    def mock_get(url, *args, **kwargs):
        if failure == "connection_error":
            raise requests.exceptions.ConnectionError("no route to host")
        if failure == "http_error":
            return MockResp(503, None)
        return MockResp(200, {"error": "maintenance"})

    monkeypatch.setattr(requests, "get", mock_get)
    monkeypatch.setattr("scripts.verify_pipeline_integrity.time.sleep", lambda *args: None)

    with pytest.raises(IntegrityUnverifiedError):
        verify_pipeline_integrity(days=7, fail_on_missing=True, sample_meeting_checks=0)


def test_verify_pipeline_integrity_retries_after_429(tmp_path, monkeypatch):
    """A 429 right after the fetchers is retried (honouring Retry-After) before giving up."""
    import requests

    from scripts.verify_pipeline_integrity import (
        IntegrityUnverifiedError,
        verify_pipeline_integrity,
    )

    monkeypatch.setattr("scripts.verify_pipeline_integrity.OUTPUT_DIR_PROCESSED", str(tmp_path))
    sleeps = []
    monkeypatch.setattr("scripts.verify_pipeline_integrity.time.sleep", sleeps.append)

    class MockResp:
        def __init__(self, status_code, headers=None):
            self.status_code = status_code
            self.headers = headers or {}

        def json(self):
            return []

    responses = [MockResp(429, {"Retry-After": "7"}), MockResp(200)]
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: responses.pop(0))

    assert verify_pipeline_integrity(days=7, fail_on_missing=True, sample_meeting_checks=0)
    assert sleeps == [7]

    sleeps.clear()
    responses[:] = [MockResp(429), MockResp(429), MockResp(429)]
    with pytest.raises(IntegrityUnverifiedError, match="HTTP 429 after 3 attempts"):
        verify_pipeline_integrity(days=7, fail_on_missing=True, sample_meeting_checks=0)
    assert sleeps == [15, 30]
