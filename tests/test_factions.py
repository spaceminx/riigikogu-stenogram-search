"""Tests for the faction rosters built from member faction periods."""

import json

from fastapi.testclient import TestClient

from src.api.factions import NO_FACTION, build_factions_overview, normalize_periods
from src.api.main import app
from src.load.database import SessionLocal
from src.load.loader import create_tables
from src.load.models import Person

REFORM = "Eesti Reformierakonna fraktsioon"
E200 = "Eesti 200 fraktsioon"
EKRE = "Eesti Konservatiivse Rahvaerakonna fraktsioon"

XV = ("2023-04-10", "2099-12-31")
XIV = ("2019-04-04", "2023-04-09")
TODAY = "2026-10-27"


def _person(uuid, first, last, active=True):
    return {
        "uuid": uuid,
        "full_name": f"{first} {last}",
        "first_name": first,
        "last_name": last,
        "electoral_district": "Valimisringkond nr 1",
        "photo_url": None,
        "active": active,
    }


def _build(persons, periods, membership=XV, active_only=False, by_name=None):
    return build_factions_overview(
        persons,
        periods,
        by_name or {},
        membership[0],
        membership[1],
        TODAY,
        active_only=active_only,
    )


def _faction(overview, name):
    return next(f for f in overview["factions"] if f["faction"] == name)


def test_current_and_former_members_of_current_membership():
    persons = [
        _person("a", "Anna", "Aas"),
        _person("b", "Boris", "Bänk"),
        _person("c", "Cecilia", "Cee", active=False),
    ]
    periods = {
        "a": [{"faction": REFORM, "start": "2023-04-10", "end": "2099-12-31"}],
        # Moved from EKRE to the non-affiliated members
        "b": [
            {"faction": EKRE, "start": "2023-04-10", "end": "2025-04-01"},
            {"faction": NO_FACTION, "start": "2025-04-01", "end": "2099-12-31"},
        ],
        # Mandate suspended, the period has ended
        "c": [{"faction": REFORM, "start": "2023-04-10", "end": "2023-04-18"}],
    }

    overview = _build(persons, periods)

    assert overview["is_current_membership"] is True
    assert overview["date"] == TODAY
    reform = _faction(overview, REFORM)
    assert [(m["uuid"], m["current"]) for m in reform["members"]] == [("a", True), ("c", False)]
    assert reform["current_count"] == 1
    assert reform["members"][0]["periods"] == [{"start": "2023-04-10", "end": None}]
    assert reform["members"][1]["periods"] == [{"start": "2023-04-10", "end": "2023-04-18"}]

    ekre = _faction(overview, EKRE)
    assert [(m["uuid"], m["current"]) for m in ekre["members"]] == [("b", False)]
    assert [(m["uuid"], m["current"]) for m in _faction(overview, NO_FACTION)["members"]] == [
        ("b", True)
    ]


def test_active_only_keeps_current_members_and_drops_empty_factions():
    persons = [_person("a", "Anna", "Aas"), _person("b", "Boris", "Bänk")]
    periods = {
        "a": [{"faction": REFORM, "start": "2023-04-10", "end": "2099-12-31"}],
        "b": [
            {"faction": EKRE, "start": "2023-04-10", "end": "2025-04-01"},
            {"faction": NO_FACTION, "start": "2025-04-01", "end": "2099-12-31"},
        ],
    }

    overview = _build(persons, periods, active_only=True)

    assert [f["faction"] for f in overview["factions"]] == [REFORM, NO_FACTION]
    assert all(m["current"] for f in overview["factions"] for m in f["members"])


def test_inactive_member_with_open_period_is_not_current():
    persons = [_person("a", "Anna", "Aas", active=False)]
    periods = {"a": [{"faction": REFORM, "start": "2023-04-10", "end": "2099-12-31"}]}

    assert _faction(_build(persons, periods), REFORM)["members"][0]["current"] is False
    assert _build(persons, periods, active_only=True)["factions"] == []


def test_periods_outside_the_membership_are_ignored():
    persons = [_person("a", "Anna", "Aas")]
    periods = {
        "a": [
            # Ends on the first day of XV, so it belongs to XIV
            {"faction": EKRE, "start": "2019-04-04", "end": "2023-04-10"},
            {"faction": REFORM, "start": "2023-04-10", "end": "2099-12-31"},
        ]
    }

    xv = _build(persons, periods)
    assert [f["faction"] for f in xv["factions"]] == [REFORM]

    xiv = _build(persons, periods, membership=XIV)
    assert [f["faction"] for f in xiv["factions"]] == [EKRE]


def test_past_membership_uses_its_last_day_and_has_no_current_members():
    persons = [_person("a", "Anna", "Aas"), _person("b", "Boris", "Bänk")]
    periods = {
        "a": [{"faction": REFORM, "start": "2019-04-04", "end": "2023-04-09"}],
        "b": [{"faction": EKRE, "start": "2019-04-04", "end": "2023-04-09"}],
    }

    overview = _build(persons, periods, membership=XIV)

    assert overview["is_current_membership"] is False
    assert overview["date"] == "2023-04-09"
    assert overview["government"]["name"] == "Kallas II"
    assert _faction(overview, REFORM)["role"] == "coalition"
    assert _faction(overview, EKRE)["role"] == "opposition"
    assert all(not m["current"] for f in overview["factions"] for m in f["members"])
    assert _build(persons, periods, membership=XIV, active_only=True)["factions"] == []


def test_roles_follow_the_current_government():
    persons = [
        _person("a", "Anna", "Aas"),
        _person("b", "Boris", "Bänk"),
        _person("c", "Cecilia", "Cee"),
    ]
    periods = {
        "a": [{"faction": E200, "start": "2023-04-10", "end": "2099-12-31"}],
        "b": [{"faction": EKRE, "start": "2023-04-10", "end": "2099-12-31"}],
        "c": [{"faction": None, "start": "2023-04-10", "end": "2099-12-31"}],
    }

    overview = _build(persons, periods)

    assert overview["government"]["from"] == "2025-03-11"
    assert overview["government"]["to"] is None
    assert E200 in overview["government"]["coalition"]
    assert {f["faction"]: f["role"] for f in overview["factions"]} == {
        E200: "coalition",
        EKRE: "opposition",
        NO_FACTION: "none",
    }


def test_factions_sorted_by_current_size_with_non_affiliated_last():
    persons = [_person(str(i), f"Nimi{i}", f"Pere{i}") for i in range(6)]
    periods = {
        "0": [{"faction": NO_FACTION, "start": "2023-04-10", "end": "2099-12-31"}],
        "1": [{"faction": NO_FACTION, "start": "2023-04-10", "end": "2099-12-31"}],
        "2": [{"faction": NO_FACTION, "start": "2023-04-10", "end": "2099-12-31"}],
        "3": [{"faction": E200, "start": "2023-04-10", "end": "2099-12-31"}],
        "4": [{"faction": REFORM, "start": "2023-04-10", "end": "2099-12-31"}],
        "5": [{"faction": REFORM, "start": "2023-04-10", "end": "2099-12-31"}],
    }

    assert [f["faction"] for f in _build(persons, periods)["factions"]] == [
        REFORM,
        E200,
        NO_FACTION,
    ]


def test_normalize_drops_waiting_time_before_joining_a_faction():
    periods = [
        {"faction": NO_FACTION, "start": "2023-04-01", "end": "2023-04-11"},
        {"faction": E200, "start": "2023-04-11", "end": "2099-12-31"},
    ]

    assert normalize_periods(periods) == [
        {"faction": E200, "start": "2023-04-11", "end": "2099-12-31"}
    ]


def test_normalize_drops_same_day_non_affiliated_entry():
    periods = [
        {"faction": REFORM, "start": "2025-03-25", "end": "2099-12-31"},
        {"faction": NO_FACTION, "start": "2025-03-25", "end": "2025-03-25"},
    ]

    assert [p["faction"] for p in normalize_periods(periods)] == [REFORM]


def test_normalize_keeps_real_non_affiliated_periods():
    periods = [
        # Left the faction for longer before joining another one
        {"faction": EKRE, "start": "2023-04-10", "end": "2024-06-13"},
        {"faction": NO_FACTION, "start": "2024-06-13", "end": "2025-01-10"},
        {"faction": E200, "start": "2025-01-10", "end": "2099-12-31"},
    ]
    # A short non-affiliated period that no faction membership follows
    short_stint = [{"faction": NO_FACTION, "start": "2024-07-23", "end": "2024-07-24"}]

    assert [p["faction"] for p in normalize_periods(periods)] == [EKRE, NO_FACTION, E200]
    assert normalize_periods(short_stint) == [
        {"faction": NO_FACTION, "start": "2024-07-23", "end": "2024-07-24"}
    ]


def test_normalize_joins_split_periods_of_one_faction():
    periods = [
        {"faction": E200, "start": "2025-03-26", "end": "2026-10-19"},
        {"faction": E200, "start": "2026-10-19", "end": "2099-12-31"},
        {"faction": None, "start": "2025-03-26", "end": "2025-03-26"},
    ]

    assert normalize_periods(periods) == [
        {"faction": E200, "start": "2025-03-26", "end": "2099-12-31"}
    ]


def test_suspended_and_returned_member_keeps_both_periods():
    persons = [_person("a", "Anna", "Aas")]
    periods = {
        "a": [
            {"faction": REFORM, "start": "2023-04-10", "end": "2024-07-23"},
            {"faction": NO_FACTION, "start": "2025-03-25", "end": "2025-03-25"},
            {"faction": REFORM, "start": "2025-03-25", "end": "2099-12-31"},
        ]
    }

    overview = _build(persons, periods)

    assert [f["faction"] for f in overview["factions"]] == [REFORM]
    assert overview["factions"][0]["members"][0]["periods"] == [
        {"start": "2023-04-10", "end": "2024-07-23"},
        {"start": "2025-03-25", "end": None},
    ]


def test_member_who_left_today_is_not_current():
    persons = [_person("a", "Anna", "Aas")]
    periods = {
        "a": [
            {"faction": EKRE, "start": "2023-04-10", "end": TODAY},
            {"faction": NO_FACTION, "start": TODAY, "end": "2099-12-31"},
        ]
    }

    overview = _build(persons, periods)

    assert _faction(overview, EKRE)["members"][0]["current"] is False
    assert _faction(overview, NO_FACTION)["members"][0]["current"] is True


def test_falls_back_to_periods_by_name():
    persons = [_person("a", "Anna", "Aas")]
    by_name = {"Anna Aas": [{"faction": REFORM, "start": "2023-04-10", "end": "2099-12-31"}]}

    overview = _build(persons, {}, by_name=by_name)

    assert _faction(overview, REFORM)["members"][0]["uuid"] == "a"


def test_factions_endpoint(tmp_path, monkeypatch):
    create_tables()
    session = SessionLocal()
    session.merge(
        Person(uuid="fx-anna", first_name="Anna", last_name="Aas", full_name="Anna Aas", active=1)
    )
    session.merge(
        Person(
            uuid="fx-boris", first_name="Boris", last_name="Bänk", full_name="Boris Bänk", active=0
        )
    )
    session.commit()
    session.close()

    (tmp_path / "person_factions.json").write_text(
        json.dumps(
            {
                "fx-anna": [{"faction": REFORM, "start": "2023-04-10", "end": "2099-12-31"}],
                "fx-boris": [{"faction": REFORM, "start": "2023-04-10", "end": "2024-07-23"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("src.api.factions.OUTPUT_DIR_PROCESSED", str(tmp_path))
    client = TestClient(app)

    res = client.get("/factions?membership=15")
    assert res.status_code == 200
    data = res.json()
    assert data["membership"] == "15"
    assert [f["faction"] for f in data["factions"]] == [REFORM]
    assert [(m["uuid"], m["current"]) for m in data["factions"][0]["members"]] == [
        ("fx-anna", True),
        ("fx-boris", False),
    ]

    active = client.get("/factions?membership=15&active_only=true").json()
    assert [m["uuid"] for m in active["factions"][0]["members"]] == ["fx-anna"]

    assert client.get("/factions").status_code == 200
    assert client.get("/factions?membership=all").status_code == 422
    assert client.get("/factions?membership=99").status_code == 422
