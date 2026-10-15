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
