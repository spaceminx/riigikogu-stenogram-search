"""Request parameters that used to create a new cache entry (and a full query) per distinct value."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func

from src.api.main import app
from src.api.search import (
    _ACTIVITY_DENOMINATOR_CACHE,
    build_speech_filters,
    clear_activity_denominator_cache,
    get_activity_denominator,
    week_key_to_monday,
)
from src.api.votings import _VOTE_PARTICIPATION_CACHE
from src.load.database import SessionLocal, engine
from src.load.loader import create_tables
from src.load.models import Speech

client = TestClient(app)

FIRST_ID = 889_001
# Dates across a year boundary (week 00), months of different length and two speeches on a day
DATES = [
    "2022-12-30",
    "2022-12-31",
    "2023-01-01",
    "2023-01-02",
    "2023-01-02",
    "2023-02-28",
    "2023-03-01",
    "2023-06-15",
    "2024-02-29",
    "2024-12-31",
]


@pytest.fixture(scope="module")
def speeches():
    create_tables()
    session = SessionLocal()
    for i, date in enumerate(DATES):
        session.merge(
            Speech(
                id=FIRST_ID + i,
                date=date,
                time="10:00",
                source_file=f"{date}_1000.api",
                source_url="https://stenogrammid.riigikogu.ee/et/x",
                speaker="Nimetaja Kontroll" if i % 2 else "Teine Kõneleja",
                text="tekst",
                text_lemmas="tekst",
            )
        )
    session.commit()
    session.close()
    clear_activity_denominator_cache()
    yield
    session = SessionLocal()
    session.query(Speech).filter(Speech.id.in_([FIRST_ID + i for i in range(len(DATES))])).delete()
    session.commit()
    session.close()
    clear_activity_denominator_cache()


def reference_denominator(session, interval, start_date, end_date, speaker=None):
    """The previous implementation: one SQL aggregate per interval and date range."""
    if interval == "daily":
        group = Speech.date
    elif interval == "monthly":
        group = func.strftime("%Y-%m", Speech.date)
    else:
        group = func.strftime("%Y-%W", Speech.date)
    filters = build_speech_filters(speaker=speaker, start_date=start_date, end_date=end_date)
    rows = session.query(group, func.count(Speech.id)).filter(*filters).group_by(group).all()
    if interval != "weekly":
        return {period: int(count) for period, count in rows}
    out: dict[str, int] = {}
    for period, count in rows:
        monday = week_key_to_monday(period).isoformat()
        out[monday] = out.get(monday, 0) + int(count)
    return out


@pytest.mark.parametrize("interval", ["daily", "weekly", "monthly"])
@pytest.mark.parametrize(
    "start_date,end_date",
    [
        (None, None),
        ("2023-01-01", None),
        (None, "2023-01-02"),
        ("2023-01-02", "2023-03-01"),
        ("1900-01-01", "2099-12-31"),
        ("2023-02-01", "2023-02-27"),
    ],
)
@pytest.mark.parametrize("speaker", [None, "Nimetaja"])
def test_denominator_matches_per_range_sql(speeches, interval, start_date, end_date, speaker):
    session = SessionLocal()
    try:
        got = get_activity_denominator(
            session, interval=interval, start_date=start_date, end_date=end_date, speaker=speaker
        )
        assert got == reference_denominator(session, interval, start_date, end_date, speaker)
    finally:
        session.close()


def test_date_range_does_not_add_cache_entries(speeches):
    clear_activity_denominator_cache()
    cache = _ACTIVITY_DENOMINATOR_CACHE["denominators"]
    session = SessionLocal()
    try:
        for day in range(1, 29):
            get_activity_denominator(session, interval="daily", start_date=f"1901-01-{day:02d}")
        get_activity_denominator(session, interval="monthly", end_date="2023-06-30")
        get_activity_denominator(session, interval="weekly")
        assert len(cache) == 1
    finally:
        session.close()


def test_unknown_faction_answers_without_a_query():
    statements = []

    def capture(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    client.get("/attendance/stats?faction=Isamaa fraktsioon")  # warms the faction list
    entries_before = len(_VOTE_PARTICIPATION_CACHE["members"])
    event.listen(engine, "before_cursor_execute", capture)
    try:
        res = client.get("/attendance/stats?membership=all&faction=audit-olematu-fraktsioon")
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert res.status_code == 200
    assert res.json() == []
    assert not [s for s in statements if "FROM votes" in s or "FROM attendance" in s]
    assert len(_VOTE_PARTICIPATION_CACHE["members"]) == entries_before


def test_known_faction_still_filters():
    res = client.get("/attendance/stats?faction=Isamaa fraktsioon")
    assert res.status_code == 200
    assert all(row.get("faction") in (None, "Isamaa fraktsioon") for row in res.json())


def test_overlong_faction_is_rejected():
    assert client.get("/attendance/stats?faction=" + "a" * 121).status_code == 422
