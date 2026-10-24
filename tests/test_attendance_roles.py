"""Tests for coalition/opposition role filtering on attendance and vote participation."""

import pytest
from fastapi.testclient import TestClient

from src.api.attendance import (
    get_attendance_stats,
    get_faction_attendance_stats,
    get_person_attendance,
)
from src.api.main import app
from src.api.roles import role_condition, role_expression
from src.api.votings import clear_vote_participation_cache
from src.load.database import SessionLocal
from src.load.loader import create_tables
from src.load.models import Attendance, AttendanceCheck, Person, Vote, Voting

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_roles_test_data():
    create_tables()
    clear_vote_participation_cache()
    session = SessionLocal()
    try:
        # Clear test rows
        session.query(Vote).delete()
        session.query(Voting).delete()
        session.query(AttendanceCheck).delete()
        session.query(Attendance).delete()
        session.query(Person).delete()

        # Create 2 persons:
        # 1) Mari Maasikas (SDE in XV: coalition during Kallas III/Michal I, opposition after 2025-03-11)
        # 2) Jüri Jõgi (Fraktsioonitu)
        p1 = Person(
            uuid="uuid-mari",
            first_name="Mari",
            last_name="Maasikas",
            full_name="Mari Maasikas",
            active=1,
        )
        p2 = Person(
            uuid="uuid-juri",
            first_name="Jüri",
            last_name="Jõgi",
            full_name="Jüri Jõgi",
            active=1,
        )
        session.add_all([p1, p2])

        att_records = [
            Attendance(
                session_date="2024-05-10T10:00:00",
                voting_uuid="chk-1",
                member_uuid="uuid-mari",
                member_name="Mari Maasikas",
                faction="Sotsiaaldemokraatliku Erakonna fraktsioon",
                status="KOHAL",
            ),
            Attendance(
                session_date="2024-05-11T10:00:00",
                voting_uuid="chk-2",
                member_uuid="uuid-mari",
                member_name="Mari Maasikas",
                faction="Sotsiaaldemokraatliku Erakonna fraktsioon",
                status="PUUDUB",
            ),
            Attendance(
                session_date="2025-03-20T10:00:00",
                voting_uuid="chk-3",
                member_uuid="uuid-mari",
                member_name="Mari Maasikas",
                faction="Sotsiaaldemokraatliku Erakonna fraktsioon",
                status="KOHAL",
            ),
            Attendance(
                session_date="2024-05-10T10:00:00",
                voting_uuid="chk-1",
                member_uuid="uuid-juri",
                member_name="Jüri Jõgi",
                faction="Fraktsiooni mittekuuluvad Riigikogu liikmed",
                status="KOHAL",
            ),
        ]
        session.add_all(att_records)

        v1 = Voting(
            uuid="vote-1",
            voting_number=1,
            type="AVALIK",
            date="2024-05-10",
            sitting_date="2024-05-10",
            membership=15,
            in_favor=10,
            against=5,
            neutral=0,
        )
        v2 = Voting(
            uuid="vote-2",
            voting_number=2,
            type="AVALIK",
            date="2025-03-20",
            sitting_date="2025-03-20",
            membership=15,
            in_favor=8,
            against=2,
            neutral=0,
        )
        session.add_all([v1, v2])

        ballots = [
            Vote(
                voting_uuid="vote-1",
                member_uuid="uuid-mari",
                faction="Sotsiaaldemokraatliku Erakonna fraktsioon",
                decision="POOLT",
            ),
            Vote(
                voting_uuid="vote-2",
                member_uuid="uuid-mari",
                faction="Sotsiaaldemokraatliku Erakonna fraktsioon",
                decision="VASTU",
            ),
            Vote(
                voting_uuid="vote-1",
                member_uuid="uuid-juri",
                faction="Fraktsiooni mittekuuluvad Riigikogu liikmed",
                decision="EI_HAALETANUD",
            ),
        ]
        session.add_all(ballots)

        session.commit()
    finally:
        session.close()

    yield

    clear_vote_participation_cache()


def test_get_governments_endpoint():
    """GET /governments returns 200 and government periods."""
    response = client.get("/governments")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 8
    assert data[0]["government"] == "Ratas I"
    assert data[-1]["government"] == "Michal"
    assert data[-1]["to"] is None


def test_methodology_text_appended():
    """Verify that /system/status methodology.attendance contains the expected role explanation."""
    response = client.get("/system/status")
    assert response.status_code == 200
    att_methodology = response.json().get("methodology", {}).get("attendance", "")
    expected = (
        "Koalitsiooni ja opositsiooni jaotus põhineb valitsuste ametiaegadel "
        "(allikad: valitsus.ee, ERR ja Wikipedia; perioodid on avaandmete failis governments.json); "
        "iga hääl ja kohalolekukontroll "
        "arvestatakse selle fraktsiooni rolli järgi, kuhu saadik sel päeval kuulus. "
        "Tagasi astunud valitsuse ajutine ametiaeg loetakse selle valitsuse koalitsiooni alla. "
        "Fraktsiooni mittekuuluvad saadikud ei kuulu kumbagi rühma."
    )
    assert expected in att_methodology


def test_attendance_stats_role_param_validation():
    """Invalid role value should return 422."""
    response = client.get("/attendance/stats?role=invalid")
    assert response.status_code == 422

    response_f = client.get("/attendance/factions?role=invalid")
    assert response_f.status_code == 422

    response_p = client.get("/persons/uuid-mari/attendance?role=invalid")
    assert response_p.status_code == 422


def test_role_filter_coalition_plus_opposition_equals_total_minus_none():
    """SQL filter: coalition + opposition + none must equal total count."""
    session = SessionLocal()
    try:
        from sqlalchemy import func

        date_col = func.substr(Attendance.session_date, 1, 10)
        tot_att = session.query(func.count(Attendance.id)).scalar()
        coal_att = (
            session.query(func.count(Attendance.id))
            .filter(role_condition(Attendance.faction, date_col, "coalition"))
            .scalar()
        )
        opp_att = (
            session.query(func.count(Attendance.id))
            .filter(role_condition(Attendance.faction, date_col, "opposition"))
            .scalar()
        )
        none_att = (
            session.query(func.count(Attendance.id))
            .filter(role_expression(Attendance.faction, date_col) == "none")
            .scalar()
        )
        assert tot_att == coal_att + opp_att + none_att
        assert coal_att + opp_att == tot_att - none_att
        assert coal_att == 2
        assert opp_att == 1
        assert none_att == 1

        # Also for votes
        tot_votes = (
            session.query(func.count(Vote.voting_uuid))
            .join(Voting, Vote.voting_uuid == Voting.uuid)
            .scalar()
        )
        base_v = session.query(func.count(Vote.voting_uuid)).join(
            Voting, Vote.voting_uuid == Voting.uuid
        )
        coal_v = base_v.filter(
            role_condition(Vote.faction, Voting.sitting_date, "coalition")
        ).scalar()
        opp_v = base_v.filter(
            role_condition(Vote.faction, Voting.sitting_date, "opposition")
        ).scalar()
        none_v = base_v.filter(
            role_expression(Vote.faction, Voting.sitting_date) == "none"
        ).scalar()
        assert tot_votes == coal_v + opp_v + none_v
        assert coal_v + opp_v == tot_votes - none_v
        assert coal_v == 1
        assert opp_v == 1
        assert none_v == 1
    finally:
        session.close()


def test_person_role_breakdown_sums_to_overall():
    """Person attendance role_breakdown (coalition + opposition + none) sums to overall figures."""
    data = get_person_attendance("uuid-mari")
    assert "role_breakdown" in data
    assert "coalition" in data["role_breakdown"]
    assert "opposition" in data["role_breakdown"]

    c_data = data["role_breakdown"]["coalition"]
    o_data = data["role_breakdown"]["opposition"]

    # Mari had 2 coalition checks (1 present, 1 absent) and 1 opposition check (1 present)
    assert c_data["total_sessions"] == 2
    assert c_data["present_sessions"] == 1
    assert c_data["absent_sessions"] == 1
    assert c_data["attendance_percentage"] == 50.0

    assert o_data["total_sessions"] == 1
    assert o_data["present_sessions"] == 1
    assert o_data["absent_sessions"] == 0
    assert o_data["attendance_percentage"] == 100.0

    assert c_data["total_sessions"] + o_data["total_sessions"] == data["total_sessions"]
    assert c_data["present_sessions"] + o_data["present_sessions"] == data["present_sessions"]

    # Votes: 1 coalition vote (POOLT), 1 opposition vote (VASTU)
    assert c_data["votes"]["total"] == 1
    assert c_data["votes"]["voted"] == 1
    assert o_data["votes"]["total"] == 1
    assert o_data["votes"]["voted"] == 1

    assert c_data["votes"]["total"] + o_data["votes"]["total"] == data["votes"]["total"]
    assert c_data["votes"]["voted"] + o_data["votes"]["voted"] == data["votes"]["voted"]


def test_attendance_stats_with_role_filter():
    """get_attendance_stats and get_faction_attendance_stats work with role filter."""
    stats_coal = get_attendance_stats(membership="15", role="coalition")
    assert len(stats_coal) == 1
    assert stats_coal[0]["member_name"] == "Mari Maasikas"
    assert stats_coal[0]["total_sessions"] == 2
    assert stats_coal[0]["present_sessions"] == 1
    assert stats_coal[0]["votes_total"] == 1

    stats_opp = get_attendance_stats(membership="15", role="opposition")
    assert len(stats_opp) == 1
    assert stats_opp[0]["member_name"] == "Mari Maasikas"
    assert stats_opp[0]["total_sessions"] == 1
    assert stats_opp[0]["present_sessions"] == 1
    assert stats_opp[0]["votes_total"] == 1

    factions_coal = get_faction_attendance_stats(membership="15", role="coalition")
    assert len(factions_coal) == 1
    assert factions_coal[0]["faction"] == "Sotsiaaldemokraatliku Erakonna fraktsioon"
    assert factions_coal[0]["total_sessions"] == 2
    assert factions_coal[0]["votes_total"] == 1

    factions_opp = get_faction_attendance_stats(membership="15", role="opposition")
    assert len(factions_opp) == 1
    assert factions_opp[0]["faction"] == "Sotsiaaldemokraatliku Erakonna fraktsioon"
    assert factions_opp[0]["total_sessions"] == 1
    assert factions_opp[0]["votes_total"] == 1


def test_faction_stats_active_only_with_role_skips_members_without_rows():
    """Active members with no rows in the selected role must not form a zero-session bucket."""
    factions_coal = get_faction_attendance_stats(
        membership="15", active_only=True, role="coalition"
    )
    assert [f["faction"] for f in factions_coal] == ["Sotsiaaldemokraatliku Erakonna fraktsioon"]
    assert factions_coal[0]["member_count"] == 1
    assert factions_coal[0]["total_sessions"] == 2
    assert factions_coal[0]["votes_total"] == 1

    factions_all = get_faction_attendance_stats(membership="15", active_only=True)
    by_faction = {f["faction"]: f for f in factions_all}
    assert by_faction["Fraktsiooni mittekuuluvad Riigikogu liikmed"]["member_count"] == 1
    assert by_faction["Fraktsiooni mittekuuluvad Riigikogu liikmed"]["total_sessions"] == 1


def test_attendance_stats_faction_filter_applies_to_votes():
    """With a faction filter, votes count only ballots cast in that faction, like attendance."""
    session = SessionLocal()
    try:
        session.add(
            Person(
                uuid="uuid-mati",
                first_name="Mati",
                last_name="Mägi",
                full_name="Mati Mägi",
                active=0,
            )
        )
        session.add_all(
            [
                Attendance(
                    session_date="2024-05-10T10:00:00",
                    voting_uuid="chk-1",
                    member_uuid="uuid-mati",
                    member_name="Mati Mägi",
                    faction="Isamaa fraktsioon",
                    status="KOHAL",
                ),
                Attendance(
                    session_date="2025-03-20T10:00:00",
                    voting_uuid="chk-3",
                    member_uuid="uuid-mati",
                    member_name="Mati Mägi",
                    faction="Fraktsiooni mittekuuluvad Riigikogu liikmed",
                    status="KOHAL",
                ),
                Vote(
                    voting_uuid="vote-1",
                    member_uuid="uuid-mati",
                    faction="Isamaa fraktsioon",
                    decision="POOLT",
                ),
                Vote(
                    voting_uuid="vote-2",
                    member_uuid="uuid-mati",
                    faction="Fraktsiooni mittekuuluvad Riigikogu liikmed",
                    decision="VASTU",
                ),
            ]
        )
        session.commit()
    finally:
        session.close()
    clear_vote_participation_cache()

    stats = get_attendance_stats(membership="15", faction="Isamaa fraktsioon")
    assert [s["member_name"] for s in stats] == ["Mati Mägi"]
    assert stats[0]["total_sessions"] == 1
    assert stats[0]["votes_total"] == 1
    assert stats[0]["votes_voted"] == 1

    all_stats = {s["member_name"]: s for s in get_attendance_stats(membership="15")}
    assert all_stats["Mati Mägi"]["total_sessions"] == 2
    assert all_stats["Mati Mägi"]["votes_total"] == 2
