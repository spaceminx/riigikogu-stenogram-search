import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.attendance import (
    get_attendance_stats,
    get_faction_attendance_stats,
    get_person_attendance,
)
from src.load.database import SessionLocal
from src.load.loader import (
    classify_sitting_type,
    load_attendance_checks_to_database,
    upsert_attendance_checks_jsonl,
)
from src.load.models import Attendance, AttendanceCheck, Base, Person, Vote, Voting


def test_classify_sitting_type():
    assert classify_sitting_type("Infotund kolmapäev, 14.10.2026 12:00") == "infotund"
    assert classify_sitting_type("infotund 12.05.2021") == "infotund"
    assert (
        classify_sitting_type("Täiskogu korraline istung kolmapäev, 14.10.2026 14:00")
        == "korraline"
    )
    assert classify_sitting_type("Täiskogu lisaistung reede, 16.10.2026") == "lisaistung"
    assert classify_sitting_type("Riigikogu erakorraline istungjärk teisipäev") == "erakorraline"
    assert classify_sitting_type("Pidulik istung 24.02.2025") == "muu"
    assert classify_sitting_type(None) == "muu"
    assert classify_sitting_type("") == "muu"


def test_upsert_attendance_checks_jsonl(tmp_path):
    jsonl_path = tmp_path / "attendance_checks.jsonl"
    records_1 = [
        {
            "voting_uuid": "v-1",
            "sitting_uuid": "s-1",
            "sitting_title": "Infotund",
            "sitting_datetime": "2024-01-01T12:00:00",
            "sitting_type": "infotund",
        },
        {
            "voting_uuid": "v-2",
            "sitting_uuid": "s-2",
            "sitting_title": "Täiskogu korraline istung",
            "sitting_datetime": "2024-01-01T14:00:00",
            "sitting_type": "korraline",
        },
    ]
    upsert_attendance_checks_jsonl(records_1, filepath=jsonl_path)

    # Update v-2 and add v-3
    records_2 = [
        {
            "voting_uuid": "v-2",
            "sitting_uuid": "s-2-updated",
            "sitting_title": "Täiskogu korraline istung (muudetud)",
            "sitting_datetime": "2024-01-01T14:00:00",
            "sitting_type": "korraline",
        },
        {
            "voting_uuid": "v-3",
            "sitting_uuid": "s-3",
            "sitting_title": "Erakorraline istung",
            "sitting_datetime": "2024-01-02T10:00:00",
            "sitting_type": "erakorraline",
        },
    ]
    upsert_attendance_checks_jsonl(records_2, filepath=jsonl_path)

    loaded = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                loaded.append(json.loads(line))

    assert len(loaded) == 3
    by_uuid = {r["voting_uuid"]: r for r in loaded}
    assert by_uuid["v-1"]["sitting_type"] == "infotund"
    assert by_uuid["v-2"]["sitting_uuid"] == "s-2-updated"
    assert by_uuid["v-3"]["sitting_type"] == "erakorraline"


def test_missing_attendance_checks_file_warning(tmp_path, monkeypatch, capsys):
    import src.load.loader

    monkeypatch.setattr(src.load.loader, "OUTPUT_DIR_PROCESSED", str(tmp_path / "non_existent"))

    count = load_attendance_checks_to_database()
    assert count == 0
    captured = capsys.readouterr()
    assert "does not exist. Skipping attendance checks loading" in captured.out


def test_load_attendance_checks_upsert_in_database(tmp_path, monkeypatch):
    import src.load.loader

    test_proc_dir = tmp_path / "proc"
    test_proc_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = test_proc_dir / "attendance_checks.jsonl"
    monkeypatch.setattr(src.load.loader, "OUTPUT_DIR_PROCESSED", str(test_proc_dir))

    # Initial record
    initial_records = [
        {
            "voting_uuid": "chk-u-1",
            "sitting_uuid": "sit-1",
            "sitting_title": "Infotund",
            "sitting_datetime": "2024-01-01T12:00:00",
            "sitting_type": "infotund",
        }
    ]
    upsert_attendance_checks_jsonl(initial_records, filepath=jsonl_path)

    count1 = load_attendance_checks_to_database()
    assert count1 == 1

    session = SessionLocal()
    c1 = session.query(AttendanceCheck).filter(AttendanceCheck.voting_uuid == "chk-u-1").first()
    assert c1 is not None
    assert c1.sitting_title == "Infotund"
    assert c1.sitting_type == "infotund"
    session.close()

    # Re-run with updated title and a new check
    updated_records = [
        {
            "voting_uuid": "chk-u-1",
            "sitting_uuid": "sit-1",
            "sitting_title": "Infotund muudetud",
            "sitting_datetime": "2024-01-01T12:00:00",
            "sitting_type": "infotund",
        },
        {
            "voting_uuid": "chk-u-2",
            "sitting_uuid": "sit-2",
            "sitting_title": "Täiskogu korraline istung",
            "sitting_datetime": "2024-01-01T14:00:00",
            "sitting_type": "korraline",
        },
    ]
    upsert_attendance_checks_jsonl(updated_records, filepath=jsonl_path)

    count2 = load_attendance_checks_to_database()
    assert count2 == 2

    session = SessionLocal()
    try:
        c1_up = (
            session.query(AttendanceCheck).filter(AttendanceCheck.voting_uuid == "chk-u-1").first()
        )
        c2 = session.query(AttendanceCheck).filter(AttendanceCheck.voting_uuid == "chk-u-2").first()
        assert c1_up.sitting_title == "Infotund muudetud"
        assert c2 is not None
        assert c2.sitting_type == "korraline"
    finally:
        session.query(AttendanceCheck).filter(
            AttendanceCheck.voting_uuid.in_(["chk-u-1", "chk-u-2"])
        ).delete(synchronize_session=False)
        session.commit()
        session.close()


def test_exclude_infotund_filters_numerator_and_denominator_and_leaves_votes(tmp_path, monkeypatch):
    db_path = tmp_path / "attendance_infotund_test.sqlite"
    eng = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(eng)
    TestingSession = sessionmaker(bind=eng)

    import src.api.attendance as att_module

    monkeypatch.setattr(att_module, "SessionLocal", TestingSession)

    session = TestingSession()
    person_uuid = "p-100"
    person = Person(
        uuid=person_uuid,
        first_name="Mari",
        last_name="Mets",
        full_name="Mari Mets",
        active=1,
    )
    session.add(person)

    # 3 attendance checks:
    # 1. infotund check, present
    # 2. infotund check, absent
    # 3. korraline check, present
    chk_info_1 = AttendanceCheck(
        voting_uuid="chk-info-1",
        sitting_uuid="sit-1",
        sitting_title="Infotund 1",
        sitting_datetime="2024-02-01T12:00:00",
        sitting_type="infotund",
    )
    chk_info_2 = AttendanceCheck(
        voting_uuid="chk-info-2",
        sitting_uuid="sit-2",
        sitting_title="Infotund 2",
        sitting_datetime="2024-02-08T12:00:00",
        sitting_type="infotund",
    )
    chk_korr = AttendanceCheck(
        voting_uuid="chk-korr-1",
        sitting_uuid="sit-3",
        sitting_title="Täiskogu korraline istung",
        sitting_datetime="2024-02-01T14:00:00",
        sitting_type="korraline",
    )
    session.add_all([chk_info_1, chk_info_2, chk_korr])

    att_1 = Attendance(
        session_date="2024-02-01T12:00:00",
        voting_uuid="chk-info-1",
        member_uuid=person_uuid,
        member_name="Mari Mets",
        faction="Test fraktsioon",
        status="KOHAL",
    )
    att_2 = Attendance(
        session_date="2024-02-08T12:00:00",
        voting_uuid="chk-info-2",
        member_uuid=person_uuid,
        member_name="Mari Mets",
        faction="Test fraktsioon",
        status="PUUDUB",
    )
    att_3 = Attendance(
        session_date="2024-02-01T14:00:00",
        voting_uuid="chk-korr-1",
        member_uuid=person_uuid,
        member_name="Mari Mets",
        faction="Test fraktsioon",
        status="KOHAL",
    )
    session.add_all([att_1, att_2, att_3])

    # 1 regular voting (not a presence check)
    v_regular = Voting(
        uuid="vote-reg-1",
        voting_number=1,
        type="AVALIK",
        description="Eelnõu hääletus",
        date="2024-02-01",
        start_time="14:30:00",
        membership=15,
        present=1,
        absent=0,
        in_favor=1,
        against=0,
        neutral=0,
        abstained=0,
    )
    session.add(v_regular)

    vr_1 = Vote(
        voting_uuid="vote-reg-1",
        member_uuid=person_uuid,
        decision="POOLT",
        faction="Test fraktsioon",
    )
    session.add(vr_1)
    session.commit()

    # 1. Test get_person_attendance
    # With exclude_infotund=False:
    # total_sessions = 3, present_sessions = 2, rate = 66.7
    # vote_count = 1, participated_votes = 1, vote_rate = 100.0
    res_with_infotund = get_person_attendance(person_uuid, exclude_infotund=False)
    assert res_with_infotund["total_sessions"] == 3
    assert res_with_infotund["present_sessions"] == 2
    assert res_with_infotund["attendance_percentage"] == 66.7
    assert res_with_infotund["votes"]["total"] == 1
    assert res_with_infotund["votes"]["voted"] == 1
    assert res_with_infotund["votes"]["voted_pct"] == 100.0

    # With exclude_infotund=True:
    # only chk-korr-1 remains:
    # total_sessions = 1, present_sessions = 1, rate = 100.0
    # vote participation MUST remain unchanged: total = 1, voted = 1, voted_pct = 100.0
    res_no_infotund = get_person_attendance(person_uuid, exclude_infotund=True)
    assert res_no_infotund["total_sessions"] == 1
    assert res_no_infotund["present_sessions"] == 1
    assert res_no_infotund["attendance_percentage"] == 100.0
    assert res_no_infotund["votes"]["total"] == 1
    assert res_no_infotund["votes"]["voted"] == 1
    assert res_no_infotund["votes"]["voted_pct"] == 100.0

    # 2. Test get_attendance_stats
    stats_all = get_attendance_stats(membership="all", exclude_infotund=False)
    p_stat_all = next(s for s in stats_all if s["member_uuid"] == person_uuid)
    assert p_stat_all["total_sessions"] == 3
    assert p_stat_all["present_sessions"] == 2
    assert p_stat_all["registered_pct"] == 66.7
    assert p_stat_all["votes_total"] == 1
    assert p_stat_all["votes_voted"] == 1
    assert p_stat_all["votes_voted_pct"] == 100.0

    stats_no_info = get_attendance_stats(membership="all", exclude_infotund=True)
    p_stat_no_info = next(s for s in stats_no_info if s["member_uuid"] == person_uuid)
    assert p_stat_no_info["total_sessions"] == 1
    assert p_stat_no_info["present_sessions"] == 1
    assert p_stat_no_info["registered_pct"] == 100.0
    assert p_stat_no_info["votes_total"] == 1
    assert p_stat_no_info["votes_voted"] == 1
    assert p_stat_no_info["votes_voted_pct"] == 100.0

    # 3. Test get_faction_attendance_stats
    f_stats_all = get_faction_attendance_stats(membership="all", exclude_infotund=False)
    f_all = next(f for f in f_stats_all if f["faction"] == "Test fraktsioon")
    assert f_all["registered_pct"] == 66.7
    assert f_all["votes_voted_pct"] == 100.0

    f_stats_no_info = get_faction_attendance_stats(membership="all", exclude_infotund=True)
    f_no_info = next(f for f in f_stats_no_info if f["faction"] == "Test fraktsioon")
    assert f_no_info["registered_pct"] == 100.0
    assert f_no_info["votes_voted_pct"] == 100.0

    session.close()
