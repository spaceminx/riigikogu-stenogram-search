from src.api.attendance import get_attendance_stats, get_faction_attendance_stats
from src.load.database import SessionLocal
from src.load.loader import create_tables
from src.load.models import Attendance, Person


def test_attendance_stats_same_name_different_uuids():
    create_tables()
    session = SessionLocal()
    # Create two members with the identical name but distinct UUIDs and factions
    p1 = Person(
        uuid="uuid-tammo-inactive",
        first_name="Tarmo",
        last_name="Tamm",
        full_name="Tarmo Tamm",
        active=0,
    )
    p2 = Person(
        uuid="uuid-tammo-active",
        first_name="Tarmo",
        last_name="Tamm",
        full_name="Tarmo Tamm",
        active=1,
    )
    session.add_all([p1, p2])

    a1 = Attendance(
        session_date="2021-05-01T10:00:00",
        voting_uuid="vote-tamm-1",
        member_uuid="uuid-tammo-inactive",
        member_name="Tarmo Tamm",
        faction="Eesti Keskerakonna fraktsioon",
        status="KOHAL",
    )
    a2 = Attendance(
        session_date="2023-05-01T10:00:00",
        voting_uuid="vote-tamm-2",
        member_uuid="uuid-tammo-active",
        member_name="Tarmo Tamm",
        faction="Eesti 200 fraktsioon",
        status="KOHAL",
    )
    session.add_all([a1, a2])
    session.commit()

    try:
        # 1. membership=all gives two rows with correct factions and session counts
        stats_all = get_attendance_stats(membership="all", active_only=False)
        tamms = [s for s in stats_all if s["member_name"] == "Tarmo Tamm"]
        assert len(tamms) == 2
        u_inactive = next(s for s in tamms if s["member_uuid"] == "uuid-tammo-inactive")
        u_active = next(s for s in tamms if s["member_uuid"] == "uuid-tammo-active")

        assert u_inactive["faction"] == "Eesti Keskerakonna fraktsioon"
        assert u_inactive["total_sessions"] == 1
        assert u_inactive["present_sessions"] == 1

        assert u_active["faction"] == "Eesti 200 fraktsioon"
        assert u_active["total_sessions"] == 1
        assert u_active["present_sessions"] == 1

        # 2. active_only gives only the active member
        stats_active = get_attendance_stats(membership="all", active_only=True)
        tamms_active = [s for s in stats_active if s["member_name"] == "Tarmo Tamm"]
        assert len(tamms_active) == 1
        assert tamms_active[0]["member_uuid"] == "uuid-tammo-active"
        assert tamms_active[0]["faction"] == "Eesti 200 fraktsioon"

        # 3. Faction statistics counts two members
        faction_stats = get_faction_attendance_stats(membership="all", active_only=False)
        kesk = next(f for f in faction_stats if f["faction"] == "Eesti Keskerakonna fraktsioon")
        e200 = next(f for f in faction_stats if f["faction"] == "Eesti 200 fraktsioon")
        assert kesk["member_count"] >= 1
        assert e200["member_count"] >= 1

    finally:
        session.delete(a1)
        session.delete(a2)
        session.delete(p1)
        session.delete(p2)
        session.commit()
        session.close()


def test_fetch_attendance_detail_error_exits_1_and_saves_successful(tmp_path, monkeypatch):
    import json

    import requests

    from scripts.fetch_attendance import fetch_attendance

    monkeypatch.setattr("scripts.fetch_attendance.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("time.sleep", lambda *args: None)

    class MockResp:
        def __init__(self, url):
            self.url = url
            self.status_code = 200

        def json(self):
            if "votings?startDate" in self.url:
                return [
                    {
                        "votings": [
                            {
                                "type": {"code": "KOHALOLEKU_KONTROLL"},
                                "uuid": "check-uuid-1",
                                "startDateTime": "2026-10-15T10:00:00",
                            },
                            {
                                "type": {"code": "KOHALOLEKU_KONTROLL"},
                                "uuid": "check-uuid-2-failing",
                                "startDateTime": "2026-10-15T11:00:00",
                            },
                        ]
                    }
                ]
            if "check-uuid-1" in self.url:
                return {
                    "voters": [
                        {
                            "fullName": "Jaan Tamm",
                            "uuid": "m-1",
                            "decision": {"code": "KOHAL"},
                        }
                    ]
                }
            # Failing check returns empty voters / error
            return {"voters": []}

    monkeypatch.setattr(requests, "get", lambda url, *args, **kwargs: MockResp(url))

    success = fetch_attendance(start_date="2026-10-15", end_date="2026-10-15")
    # Returns False because check-uuid-2-failing failed
    assert success is False

    # But check-uuid-1 was saved successfully
    att_file = tmp_path / "attendance.jsonl"
    assert att_file.exists()
    lines = att_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["voting_uuid"] == "check-uuid-1"
    assert rec["member_name"] == "Jaan Tamm"


def test_fetch_attendance_fetches_20_day_missing_check(tmp_path, monkeypatch):
    import json
    from datetime import datetime, timedelta

    import requests

    from scripts.fetch_attendance import fetch_attendance

    monkeypatch.setattr("scripts.fetch_attendance.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("time.sleep", lambda *args: None)

    today = datetime.now()
    yesterday = today - timedelta(days=1)
    twenty_days_ago = today - timedelta(days=20)

    # Local attendance has yesterday's check
    att_file = tmp_path / "attendance.jsonl"
    mock_local = {
        "session_date": f"{yesterday.strftime('%Y-%m-%d')}T10:00:00",
        "voting_uuid": "yesterday-check",
        "member_name": "Jaan Tamm",
        "status": "KOHAL",
    }
    att_file.write_text(json.dumps(mock_local) + "\n", encoding="utf-8")

    called_urls = []

    class MockResp:
        def __init__(self, url):
            self.url = url
            self.status_code = 200

        def json(self):
            called_urls.append(self.url)
            if "votings?startDate" in self.url:
                return [
                    {
                        "votings": [
                            {
                                "type": {"code": "KOHALOLEKU_KONTROLL"},
                                "uuid": "yesterday-check",
                                "startDateTime": f"{yesterday.strftime('%Y-%m-%d')}T10:00:00",
                            },
                            {
                                "type": {"code": "KOHALOLEKU_KONTROLL"},
                                "uuid": "twenty-days-ago-check",
                                "startDateTime": f"{twenty_days_ago.strftime('%Y-%m-%d')}T10:00:00",
                            },
                        ]
                    }
                ]
            if "twenty-days-ago-check" in self.url:
                return {
                    "voters": [
                        {
                            "fullName": "Mari Mets",
                            "uuid": "m-2",
                            "decision": {"code": "PUUDUB"},
                        }
                    ]
                }
            return {"voters": []}

    monkeypatch.setattr(requests, "get", lambda url, *args, **kwargs: MockResp(url))

    # Run without explicit dates: window reaches 30 days back!
    success = fetch_attendance()
    assert success is True

    lines = att_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    rec2 = json.loads(lines[1])
    assert rec2["voting_uuid"] == "twenty-days-ago-check"
    assert rec2["member_name"] == "Mari Mets"


def test_fetch_attendance_no_db_file_created(tmp_path, monkeypatch):
    import requests

    from scripts.fetch_attendance import fetch_attendance

    monkeypatch.setattr("scripts.fetch_attendance.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("time.sleep", lambda *args: None)

    class MockResp:
        def __init__(self, url):
            self.url = url
            self.status_code = 200

        def json(self):
            if "votings?startDate" in self.url:
                return [
                    {
                        "votings": [
                            {
                                "type": {"code": "KOHALOLEKU_KONTROLL"},
                                "uuid": "test-uuid-clean",
                                "startDateTime": "2026-10-15T10:00:00",
                            }
                        ]
                    }
                ]
            return {
                "voters": [
                    {
                        "fullName": "Jaan Tamm",
                        "uuid": "m-1",
                        "decision": {"code": "KOHAL"},
                    }
                ]
            }

    monkeypatch.setattr(requests, "get", lambda url, *args, **kwargs: MockResp(url))

    success = fetch_attendance(start_date="2026-10-15", end_date="2026-10-15")
    assert success is True

    # Verify no database files were created anywhere in tmp_path or root
    db_files = list(tmp_path.glob("*.db")) + list(tmp_path.glob("*.sqlite"))
    assert len(db_files) == 0
