"""The non-affiliated wait before a faction admits a new member is booked to that faction."""

import json

import pytest
from fastapi.testclient import TestClient

from src.api.factions import joining_windows, normalize_periods
from src.api.main import app
from src.api.roles import NO_FACTION
from src.api.votings import clear_vote_participation_cache
from src.load import loader
from src.load.database import SessionLocal
from src.load.loader import create_tables, load_faction_joining_windows
from src.load.models import Attendance, FactionJoiningWindow, Vote, Voting

client = TestClient(app)

MEMBER = "joining-wait-member"
FACTION = "Ootetesti fraktsioon"
DAYS = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
# Non-affiliated on the first two days, then admitted on 2026-11-04
PERIODS = [
    {"faction": NO_FACTION, "start": "2026-11-02", "end": "2026-11-04"},
    {"faction": FACTION, "start": "2026-11-04", "end": "2099-12-31"},
]


def test_joining_window_covers_the_wait_and_the_day_after_joining():
    assert joining_windows(PERIODS) == [("2026-11-02", "2026-11-05", FACTION)]
    assert [p["faction"] for p in normalize_periods(PERIODS)] == [FACTION]


def test_first_day_of_a_new_stint_is_a_window_without_a_listed_wait():
    """Upstream sometimes lists the member as non-affiliated on the first day of a faction period."""
    periods = [
        {"faction": FACTION, "start": "2019-04-04", "end": "2023-04-01"},
        {"faction": FACTION, "start": "2023-04-18", "end": None},
    ]
    assert joining_windows(periods) == [
        ("2019-04-04", "2019-04-05", FACTION),
        ("2023-04-18", "2023-04-19", FACTION),
    ]


def test_continuing_faction_period_is_not_a_window():
    periods = [
        {"faction": FACTION, "start": "2024-04-15", "end": "2024-07-24"},
        {"faction": FACTION, "start": "2024-07-25", "end": None},
    ]
    assert joining_windows(periods) == [("2024-04-15", "2024-04-16", FACTION)]


@pytest.mark.parametrize(
    "periods",
    [
        # Non-affiliated for longer than the joining window: a real non-affiliated period
        [
            {"faction": NO_FACTION, "start": "2026-01-01", "end": "2026-03-01"},
            {"faction": FACTION, "start": "2026-03-01", "end": "2099-12-31"},
        ],
        # Left a faction: the open-ended non-affiliated period stays
        [
            {"faction": FACTION, "start": "2025-01-01", "end": "2026-03-01"},
            {"faction": NO_FACTION, "start": "2026-03-01", "end": "2099-12-31"},
        ],
    ],
)
def test_lasting_non_affiliated_periods_stay_outside_windows(periods):
    wait = next(p for p in periods if p["faction"] == NO_FACTION)
    for start, end, _ in joining_windows(periods):
        # Only the faction's first day and the day after are covered
        assert not (start <= "2026-02-01" <= end)
        assert not (start <= "2026-06-01" <= end)
    assert wait in periods


def test_renamed_faction_window_keeps_the_name_of_the_time():
    periods = [
        {"faction": NO_FACTION, "start": "2015-03-30", "end": "2015-04-01"},
        {"faction": "Isamaa ja Res Publica Liidu fraktsioon", "start": "2015-04-01", "end": None},
    ]
    assert joining_windows(periods) == [
        ("2015-03-30", "2015-04-02", "Isamaa ja Res Publica Liidu fraktsioon")
    ]


def test_loader_rebuilds_the_table(tmp_path, monkeypatch):
    create_tables()
    monkeypatch.setattr(loader, "OUTPUT_DIR_PROCESSED", str(tmp_path))
    (tmp_path / "person_factions.json").write_text(json.dumps({MEMBER: PERIODS}), encoding="utf-8")
    session = SessionLocal()
    try:
        assert load_faction_joining_windows() == 1
        assert load_faction_joining_windows() == 1
        rows = session.query(FactionJoiningWindow).filter_by(member_uuid=MEMBER).all()
        assert [(r.start_date, r.end_date, r.faction) for r in rows] == [
            ("2026-11-02", "2026-11-05", FACTION)
        ]
    finally:
        session.query(FactionJoiningWindow).delete()
        session.commit()
        session.close()


@pytest.fixture
def seeded():
    create_tables()
    session = SessionLocal()
    uuids = [f"joining-wait-{i}" for i in range(len(DAYS))]

    def cleanup():
        session.query(Attendance).filter(Attendance.member_uuid == MEMBER).delete()
        session.query(Vote).filter(Vote.voting_uuid.in_(uuids)).delete()
        session.query(Voting).filter(Voting.uuid.in_(uuids)).delete()
        session.query(FactionJoiningWindow).delete()
        session.commit()

    cleanup()
    for i, (uuid, day) in enumerate(zip(uuids, DAYS, strict=True)):
        fac = NO_FACTION if day < "2026-11-04" else FACTION
        session.add(
            Attendance(
                session_date=f"{day}T10:00:00",
                voting_uuid=uuid,
                member_uuid=MEMBER,
                member_name="Ootaja Liige",
                faction=fac,
                status="KOHAL",
            )
        )
        session.add(
            Voting(
                uuid=uuid,
                voting_number=900 + i,
                type="AVALIK",
                description="Ootetest",
                date=day,
                start_time=f"{day}T11:00:00",
                sitting_date=day,
                sitting_datetime=f"{day}T10:00:00",
                membership=15,
                in_favor=1,
                against=0,
                neutral=0,
            )
        )
        session.add(Vote(voting_uuid=uuid, member_uuid=MEMBER, faction=fac, decision="POOLT"))
    session.commit()
    clear_vote_participation_cache()
    try:
        yield session
    finally:
        cleanup()
        session.close()
        clear_vote_participation_cache()


def _faction_rows():
    resp = client.get("/attendance/factions?membership=15")
    assert resp.status_code == 200
    return {r["faction"]: r for r in resp.json()}


def test_wait_is_booked_to_the_faction_joined(seeded):
    before = _faction_rows()
    assert before[FACTION]["member_count"] == 1
    assert before[FACTION]["total_checks"] == 3
    assert before[FACTION]["votes_total"] == 3

    seeded.add(
        FactionJoiningWindow(
            member_uuid=MEMBER, start_date="2026-11-02", end_date="2026-11-05", faction=FACTION
        )
    )
    seeded.commit()
    clear_vote_participation_cache()
    after = _faction_rows()

    assert after[FACTION]["member_count"] == 1
    assert after[FACTION]["total_checks"] == 5
    assert after[FACTION]["votes_total"] == 5
    empty = {"member_count": 0, "total_checks": 0, "votes_total": 0}
    no_faction_before = before.get(NO_FACTION, empty)
    no_faction_after = after.get(NO_FACTION, empty)
    assert no_faction_after["member_count"] == no_faction_before["member_count"] - 1
    assert no_faction_after["total_checks"] == no_faction_before["total_checks"] - 2
    assert no_faction_after["votes_total"] == no_faction_before["votes_total"] - 2

    members = client.get(f"/attendance/stats?membership=15&faction={FACTION}").json()
    row = next(r for r in members if r["member_uuid"] == MEMBER)
    assert row["total_checks"] == 5
    assert row["votes_total"] == 5
