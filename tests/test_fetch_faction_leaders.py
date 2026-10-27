"""Tests for fetching faction chairs and vice-chairs from the Riigikogu API."""

import json
from pathlib import Path

import pytest

import scripts.fetch_faction_leaders as fl
from src.fetch_models import UpstreamSchemaError

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "riigikogu_api"
GROUPS = json.loads((FIXTURES_DIR / "usergroups_factions.json").read_text(encoding="utf-8"))
DETAIL = json.loads((FIXTURES_DIR / "usergroup_detail.json").read_text(encoding="utf-8"))

PILLAK = "8d9daaeb-dbaf-4887-8311-881b29bedfa9"
KELDO = "bdcec844-b004-4caf-bfc1-6a74c9fbd76f"
ALENDER = "90074aa2-4938-41a9-8275-3a6efa1cee31"
MICHAL = "84bf9004-a454-44c9-8696-5337c74ff486"


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_extracts_only_chairs_and_vice_chairs_from_xiii_on():
    roles = fl.extract_leader_roles(DETAIL)

    assert roles[PILLAK] == [
        {
            "faction": "Eesti Reformierakonna fraktsioon",
            "role": "esimees",
            "start": "2024-07-23",
            "end": None,
        }
    ]
    assert roles[KELDO][0]["end"] == "2024-07-23"
    # Alender is listed as a member too; only the vice-chair row is kept
    assert [r["role"] for r in roles[ALENDER]] == ["aseesimees"]
    # Michal chaired the faction in XII, before the site's range
    assert MICHAL not in roles
    # Ordinary members and staff are left out
    assert "00000000-0000-0000-0000-000000000000" not in roles
    assert len(roles) == 6


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(fl.time, "sleep", lambda *_: None)


def _route(responses):
    def fake_get(url, timeout=None):
        for key, response in responses.items():
            if key in url:
                return response
        raise AssertionError(f"Unexpected request {url}")

    return fake_get


def test_writes_roles_of_every_active_faction(tmp_path, monkeypatch, no_sleep):
    monkeypatch.setattr(fl, "OUTPUT_DIR_PROCESSED", str(tmp_path))
    requested = []

    def fake_get(url, timeout=None):
        requested.append(url)
        if "typeCode=FRAKTSIOON" in url:
            return FakeResponse(200, GROUPS[:2])
        return FakeResponse(200, DETAIL)

    monkeypatch.setattr(fl.requests, "get", fake_get)

    assert fl.fetch_faction_leaders() is True
    saved = json.loads((tmp_path / "faction_roles.json").read_text(encoding="utf-8"))
    assert saved[PILLAK][0]["role"] == "esimees"
    assert len(requested) == 3
    assert all("email" not in json.dumps(v) for v in saved.values())


def test_keeps_the_previous_file_when_a_faction_fails(tmp_path, monkeypatch, no_sleep):
    monkeypatch.setattr(fl, "OUTPUT_DIR_PROCESSED", str(tmp_path))
    previous = tmp_path / "faction_roles.json"
    previous.write_text('{"kept": []}', encoding="utf-8")
    second = GROUPS[1]["uuid"]
    monkeypatch.setattr(
        fl.requests,
        "get",
        _route(
            {
                "typeCode=FRAKTSIOON": FakeResponse(200, GROUPS[:2]),
                second: FakeResponse(429),
                "/usergroups/": FakeResponse(200, DETAIL),
            }
        ),
    )

    assert fl.fetch_faction_leaders() is False
    assert previous.read_text(encoding="utf-8") == '{"kept": []}'


def test_keeps_the_previous_file_when_no_chairs_come_back(tmp_path, monkeypatch, no_sleep):
    monkeypatch.setattr(fl, "OUTPUT_DIR_PROCESSED", str(tmp_path))
    previous = tmp_path / "faction_roles.json"
    previous.write_text('{"kept": []}', encoding="utf-8")
    empty = {**DETAIL, "members": []}
    monkeypatch.setattr(
        fl.requests,
        "get",
        _route(
            {
                "typeCode=FRAKTSIOON": FakeResponse(200, GROUPS[:1]),
                "/usergroups/": FakeResponse(200, empty),
            }
        ),
    )

    assert fl.fetch_faction_leaders() is False
    assert previous.read_text(encoding="utf-8") == '{"kept": []}'


def test_a_changed_response_shape_raises(tmp_path, monkeypatch, no_sleep):
    monkeypatch.setattr(fl, "OUTPUT_DIR_PROCESSED", str(tmp_path))
    broken = {**DETAIL, "members": [{"fullName": "Ilma UUID-ta"}]}
    monkeypatch.setattr(
        fl.requests,
        "get",
        _route(
            {
                "typeCode=FRAKTSIOON": FakeResponse(200, GROUPS[:1]),
                "/usergroups/": FakeResponse(200, broken),
            }
        ),
    )

    with pytest.raises(UpstreamSchemaError):
        fl.fetch_faction_leaders()
    assert not (tmp_path / "faction_roles.json").exists()
