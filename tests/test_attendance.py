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


def test_vote_participation_helper_and_two_uuids_same_name():
    from src.api.votings import (
        clear_vote_participation_cache,
        get_faction_vote_participation,
        get_member_vote_participation,
    )
    from src.load.models import Vote, Voting

    create_tables()
    clear_vote_participation_cache()
    session = SessionLocal()

    p_a = Person(
        uuid="uuid-mari-1",
        first_name="Mari",
        last_name="Mets",
        full_name="Mari Mets",
        active=1,
    )
    p_b = Person(
        uuid="uuid-mari-2",
        first_name="Mari",
        last_name="Mets",
        full_name="Mari Mets",
        active=1,
    )
    session.add_all([p_a, p_b])

    # v1: public, non-technical, membership 15
    v1 = Voting(
        uuid="v-test-pub-1",
        voting_number=1,
        type="AVALIK",
        date="2023-05-10",
        membership=15,
        in_favor=50,
        against=10,
        neutral=5,
    )
    # v2: technical (AVALIK but in_favor+against+neutral == 0) -> must be EXCLUDED
    v2 = Voting(
        uuid="v-test-tech-1",
        voting_number=2,
        type="AVALIK",
        date="2023-05-10",
        membership=15,
        in_favor=0,
        against=0,
        neutral=0,
    )
    # v3: SALAJANE -> must be EXCLUDED
    v3 = Voting(
        uuid="v-test-sec-1",
        voting_number=3,
        type="SALAJANE",
        date="2023-05-10",
        membership=15,
        in_favor=60,
        against=10,
        neutral=0,
    )
    # v4: KOHALOLEKU_KONTROLL -> must be EXCLUDED
    v4 = Voting(
        uuid="v-test-att-1",
        voting_number=4,
        type="KOHALOLEKU_KONTROLL",
        date="2023-05-10",
        membership=15,
        in_favor=0,
        against=0,
        neutral=0,
    )
    # v5: public, non-technical, membership 14
    v5 = Voting(
        uuid="v-test-mem14-1",
        voting_number=5,
        type="AVALIK",
        date="2021-05-10",
        membership=14,
        in_favor=40,
        against=20,
        neutral=2,
    )
    session.add_all([v1, v2, v3, v4, v5])

    # Ballots on v1
    vote1_a = Vote(
        voting_uuid="v-test-pub-1",
        member_uuid="uuid-mari-1",
        faction="Fraktsioon A",
        decision="POOLT",
    )
    vote1_b = Vote(
        voting_uuid="v-test-pub-1",
        member_uuid="uuid-mari-2",
        faction="Fraktsioon B",
        decision="EI_HAALETANUD",
    )
    # Ballots on v2 (tech), v3 (sec), v4 (att)
    vote2 = Vote(
        voting_uuid="v-test-tech-1",
        member_uuid="uuid-mari-1",
        faction="Fraktsioon A",
        decision="VASTU",
    )
    vote3 = Vote(
        voting_uuid="v-test-sec-1",
        member_uuid="uuid-mari-1",
        faction="Fraktsioon A",
        decision="POOLT",
    )
    vote4 = Vote(
        voting_uuid="v-test-att-1",
        member_uuid="uuid-mari-1",
        faction="Fraktsioon A",
        decision="KOHAL",
    )
    # Ballot on v5 (membership 14)
    vote5 = Vote(
        voting_uuid="v-test-mem14-1",
        member_uuid="uuid-mari-1",
        faction="Fraktsioon A",
        decision="PUUDUB",
    )
    session.add_all([vote1_a, vote1_b, vote2, vote3, vote4, vote5])
    session.commit()

    try:
        # 1. Membership 15 filter
        m15_stats = get_member_vote_participation(session, membership=15)
        mari1 = m15_stats.get("uuid-mari-1")
        mari2 = m15_stats.get("uuid-mari-2")

        assert mari1 is not None
        assert mari1["total"] == 1  # Only v1 counted (v2, v3, v4, v5 excluded)
        assert mari1["voted"] == 1
        assert mari1["not_voted"] == 0
        assert mari1["absent"] == 0
        assert mari1["voted_pct"] == 100.0

        assert mari2 is not None
        assert mari2["total"] == 1
        assert mari2["voted"] == 0
        assert mari2["not_voted"] == 1
        assert mari2["absent"] == 0
        assert mari2["voted_pct"] == 0.0

        # 2. Membership "all" filter
        all_stats = get_member_vote_participation(session, membership="all")
        mari1_all = all_stats.get("uuid-mari-1")
        assert mari1_all["total"] == 2  # v1 + v5
        assert mari1_all["voted"] == 1
        assert mari1_all["not_voted"] == 0
        assert mari1_all["absent"] == 1
        assert mari1_all["voted_pct"] == 50.0

        # 3. Faction vote participation
        f_stats = get_faction_vote_participation(session, membership=15)
        fac_a = f_stats.get("Fraktsioon A")
        fac_b = f_stats.get("Fraktsioon B")
        assert fac_a["total"] == 1
        assert fac_a["voted"] == 1
        assert fac_a["voted_pct"] == 100.0
        assert fac_b["total"] == 1
        assert fac_b["not_voted"] == 1
        assert fac_b["voted_pct"] == 0.0

    finally:
        for obj in [
            vote1_a,
            vote1_b,
            vote2,
            vote3,
            vote4,
            vote5,
            v1,
            v2,
            v3,
            v4,
            v5,
            p_a,
            p_b,
        ]:
            session.delete(obj)
        session.commit()
        session.close()
        clear_vote_participation_cache()


def test_vote_participation_cache_invalidation_on_last_sync_at():
    from src.api.votings import clear_vote_participation_cache, get_member_vote_participation
    from src.load.models import SystemMeta, Vote, Voting

    create_tables()
    clear_vote_participation_cache()
    session = SessionLocal()

    p = Person(
        uuid="uuid-cache-test-1",
        first_name="Kati",
        last_name="Kask",
        full_name="Kati Kask",
        active=1,
    )
    v1 = Voting(
        uuid="v-cache-1",
        type="AVALIK",
        date="2023-06-01",
        membership=15,
        in_favor=50,
        against=5,
        neutral=2,
    )
    vote1 = Vote(
        voting_uuid="v-cache-1",
        member_uuid="uuid-cache-test-1",
        faction="Testfraktsioon",
        decision="POOLT",
    )
    session.add_all([p, v1, vote1])
    session.commit()

    v2 = None
    vote2 = None
    meta_row = None
    try:
        # First query populates cache
        stats1 = get_member_vote_participation(session, membership=15)
        assert stats1["uuid-cache-test-1"]["total"] == 1

        # Add another vote to database directly
        v2 = Voting(
            uuid="v-cache-2",
            type="AVALIK",
            date="2023-06-02",
            membership=15,
            in_favor=50,
            against=5,
            neutral=2,
        )
        vote2 = Vote(
            voting_uuid="v-cache-2",
            member_uuid="uuid-cache-test-1",
            faction="Testfraktsioon",
            decision="VASTU",
        )
        session.add_all([v2, vote2])
        session.commit()

        # Query again without changing last_sync_at -> should return cached data (total == 1)
        stats2 = get_member_vote_participation(session, membership=15)
        assert stats2["uuid-cache-test-1"]["total"] == 1

        # Update last_sync_at in system_meta
        meta_row = session.query(SystemMeta).filter_by(key="last_sync_at").first()
        if not meta_row:
            meta_row = SystemMeta(key="last_sync_at", value="2026-10-17T12:00:00")
            session.add(meta_row)
        else:
            meta_row.value = "2026-10-17T12:00:00"
        session.commit()

        # Query again -> cache invalidated, reloaded from DB (total == 2)
        stats3 = get_member_vote_participation(session, membership=15)
        assert stats3["uuid-cache-test-1"]["total"] == 2
        assert stats3["uuid-cache-test-1"]["voted"] == 2
        assert stats3["uuid-cache-test-1"]["voted_pct"] == 100.0

    finally:
        for obj in [vote1, vote2, v1, v2, p]:
            if obj:
                session.delete(obj)
        session.commit()
        session.close()
        clear_vote_participation_cache()


def test_api_attendance_stats_returns_both_metrics():
    from fastapi.testclient import TestClient

    from src.api.main import app

    client = TestClient(app)
    res = client.get("/attendance/stats?membership=all")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    if len(data) > 0:
        first = data[0]
        # Group 1 (registered presence checks)
        assert "total_sessions" in first
        assert "present_sessions" in first
        assert "attendance_percentage" in first
        assert "registered_checks" in first
        assert "total_checks" in first
        assert "registered_pct" in first
        assert first["registered_checks"] == first["present_sessions"]
        assert first["total_checks"] == first["total_sessions"]
        assert first["registered_pct"] == first["attendance_percentage"]

        # Group 2 (votes)
        assert "votes_voted" in first
        assert "votes_not_voted" in first
        assert "votes_absent" in first
        assert "votes_total" in first
        assert "votes_voted_pct" in first


def test_api_attendance_factions_returns_both_metrics():
    from fastapi.testclient import TestClient

    from src.api.main import app

    client = TestClient(app)
    res = client.get("/attendance/factions?membership=all")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    if len(data) > 0:
        first = data[0]
        # Group 1
        assert "total_sessions" in first
        assert "present_sessions" in first
        assert "attendance_percentage" in first
        assert "registered_checks" in first
        assert "total_checks" in first
        assert "registered_pct" in first
        assert first["registered_checks"] == first["present_sessions"]
        assert first["total_checks"] == first["total_sessions"]
        assert first["registered_pct"] == first["attendance_percentage"]

        # Group 2
        assert "votes_voted" in first
        assert "votes_not_voted" in first
        assert "votes_absent" in first
        assert "votes_total" in first
        assert "votes_voted_pct" in first


def test_api_person_attendance_votes_in_both_places():
    from fastapi.testclient import TestClient

    from src.api.main import app
    from src.load.models import Person

    session = SessionLocal()
    person = session.query(Person).first()
    p_uuid = person.uuid if person else None
    session.close()

    if not p_uuid:
        return

    client = TestClient(app)
    res = client.get(f"/persons/{p_uuid}/attendance")
    assert res.status_code == 200
    data = res.json()

    # Top-level votes object
    assert "votes" in data
    v = data["votes"]
    for k in ["voted", "not_voted", "absent", "total", "voted_pct"]:
        assert k in v

    # By membership votes object
    for item in data.get("by_membership", []):
        assert "votes" in item
        mv = item["votes"]
        for k in ["voted", "not_voted", "absent", "total", "voted_pct"]:
            assert k in mv


def test_methodology_attendance_two_metrics_text():
    from fastapi.testclient import TestClient

    from src.api.main import app

    client = TestClient(app)
    res = client.get("/system/status")
    assert res.status_code == 200
    att_methodology = res.json()["methodology"]["attendance"]
    assert "Kohalolekut näidatakse kahe mõõdikuna." in att_methodology
    assert "Registreerus kohalolekukontrollis" in att_methodology
    assert "Osales hääletustel" in att_methodology
