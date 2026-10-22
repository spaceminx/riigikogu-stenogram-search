"""Tests for Pydantic models validating upstream Riigikogu API responses."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.fetch_agenda import process_agenda_and_verbatims
from scripts.fetch_factions import extract_electoral_district, extract_photo_url
from scripts.fetch_memberships import roman_numeral
from scripts.fetch_stenograms_api import parse_meeting_speeches
from scripts.fetch_votes import parse_and_validate_voting
from src.fetch_models import (
    AgendaPlenary,
    MeetingSpeech,
    MemberPhoto,
    MembershipItem,
    PlenaryMember,
    RichMeeting,
    UpstreamSchemaError,
    VerbatimAgendaItem,
    VerbatimEvent,
    VerbatimSitting,
    Voter,
    VotingDetail,
    VotingsSitting,
    validate_response,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "riigikogu_api"
GOLDENS_DIR = FIXTURES_DIR / "goldens"


# ---------------------------------------------------------------------------
# 1. All real fixtures validate
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("model", "filename", "endpoint"),
    [
        (MembershipItem, "memberships.json", "/api/memberships"),
        (PlenaryMember, "plenary_members_recent.json", "/api/plenary-members"),
        (PlenaryMember, "plenary_members_2019.json", "/api/plenary-members"),
        (VotingsSitting, "votings_recent.json", "/api/votings"),
        (VotingsSitting, "votings_2019.json", "/api/votings"),
        (VotingDetail, "voting_detail_recent.json", "/api/votings/{uuid}"),
        (VotingDetail, "voting_detail_2019.json", "/api/votings/{uuid}"),
        (VerbatimSitting, "verbatims_recent.json", "/api/steno/verbatims"),
        (VerbatimSitting, "verbatims_2019.json", "/api/steno/verbatims"),
        (RichMeeting, "meeting_recent.json", "stenogrammid.riigikogu.ee/api/meeting/{code}"),
        (RichMeeting, "meeting_2019.json", "stenogrammid.riigikogu.ee/api/meeting/{code}"),
        (AgendaPlenary, "agenda_recent.json", "/api/agenda/plenary"),
        (AgendaPlenary, "agenda_2019.json", "/api/agenda/plenary"),
    ],
)
def test_fixtures_validate_successfully(model, filename, endpoint):
    fixture_path = FIXTURES_DIR / filename
    assert fixture_path.exists(), f"Fixture {filename} missing"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)
    validate_response(model, data, endpoint=endpoint, ref=filename)


# ---------------------------------------------------------------------------
# 2. Removing required field or changing type raises UpstreamSchemaError with field path
# ---------------------------------------------------------------------------
def test_missing_required_field_raises():
    with pytest.raises(UpstreamSchemaError) as exc_info:
        validate_response(
            MembershipItem,
            [{"endDate": "2023-01-01"}],
            endpoint="/api/memberships",
            ref="test_missing",
        )
    msg = str(exc_info.value)
    assert "0.number" in msg
    assert "0.startDate" in msg
    assert "api.riigikogu.ee response shape changed" in msg


def test_invalid_field_type_raises():
    with pytest.raises(UpstreamSchemaError) as exc_info:
        validate_response(
            MembershipItem,
            [{"number": 15, "startDate": 12345}],
            endpoint="/api/memberships",
            ref="test_type",
        )
    msg = str(exc_info.value)
    assert "0.startDate" in msg
    assert "api.riigikogu.ee response shape changed" in msg


def test_nested_missing_required_field_raises():
    with pytest.raises(UpstreamSchemaError) as exc_info:
        validate_response(
            VotingsSitting,
            [{"title": "Istung", "votings": [{"description": "Missing UUID"}]}],
            endpoint="/api/votings",
            ref="test_nested",
        )
    msg = str(exc_info.value)
    assert "0.votings.0.uuid" in msg
    assert "api.riigikogu.ee response shape changed" in msg


def test_member_photo_invalid_links_raises():
    with pytest.raises(UpstreamSchemaError) as exc_info:
        validate_response(
            MemberPhoto,
            {"uuid": "photo-uuid", "_links": "invalid_links_type"},
            endpoint="/api/plenary-members",
            ref="test_photo_links",
        )
    msg = str(exc_info.value)
    assert "_links" in msg
    assert "api.riigikogu.ee response shape changed" in msg


@pytest.mark.parametrize(
    ("model", "base_payload", "field_name"),
    [
        # PlenaryMember: uuid, firstName, lastName, fullName, factions
        (
            PlenaryMember,
            {
                "uuid": "u1",
                "firstName": "Jaan",
                "lastName": "Tamm",
                "fullName": "Jaan Tamm",
                "factions": [],
            },
            "uuid",
        ),
        (
            PlenaryMember,
            {
                "uuid": "u1",
                "firstName": "Jaan",
                "lastName": "Tamm",
                "fullName": "Jaan Tamm",
                "factions": [],
            },
            "firstName",
        ),
        (
            PlenaryMember,
            {
                "uuid": "u1",
                "firstName": "Jaan",
                "lastName": "Tamm",
                "fullName": "Jaan Tamm",
                "factions": [],
            },
            "lastName",
        ),
        (
            PlenaryMember,
            {
                "uuid": "u1",
                "firstName": "Jaan",
                "lastName": "Tamm",
                "fullName": "Jaan Tamm",
                "factions": [],
            },
            "fullName",
        ),
        (
            PlenaryMember,
            {
                "uuid": "u1",
                "firstName": "Jaan",
                "lastName": "Tamm",
                "fullName": "Jaan Tamm",
                "factions": [],
            },
            "factions",
        ),
        # VotingDetail: uuid, votingNumber, startDateTime, type, voters
        (
            VotingDetail,
            {
                "uuid": "v1",
                "votingNumber": 1,
                "startDateTime": "2026-10-01T10:00:00",
                "type": {"code": "AVALIK"},
                "voters": [],
            },
            "uuid",
        ),
        (
            VotingDetail,
            {
                "uuid": "v1",
                "votingNumber": 1,
                "startDateTime": "2026-10-01T10:00:00",
                "type": {"code": "AVALIK"},
                "voters": [],
            },
            "votingNumber",
        ),
        (
            VotingDetail,
            {
                "uuid": "v1",
                "votingNumber": 1,
                "startDateTime": "2026-10-01T10:00:00",
                "type": {"code": "AVALIK"},
                "voters": [],
            },
            "startDateTime",
        ),
        (
            VotingDetail,
            {
                "uuid": "v1",
                "votingNumber": 1,
                "startDateTime": "2026-10-01T10:00:00",
                "type": {"code": "AVALIK"},
                "voters": [],
            },
            "type",
        ),
        (
            VotingDetail,
            {
                "uuid": "v1",
                "votingNumber": 1,
                "startDateTime": "2026-10-01T10:00:00",
                "type": {"code": "AVALIK"},
                "voters": [],
            },
            "voters",
        ),
        # Voter: uuid, fullName, decision, faction
        (
            Voter,
            {
                "uuid": "m1",
                "fullName": "Jaan Tamm",
                "decision": {"code": "POOLT"},
                "faction": {"name": "Fraktsioon"},
            },
            "uuid",
        ),
        (
            Voter,
            {
                "uuid": "m1",
                "fullName": "Jaan Tamm",
                "decision": {"code": "POOLT"},
                "faction": {"name": "Fraktsioon"},
            },
            "fullName",
        ),
        (
            Voter,
            {
                "uuid": "m1",
                "fullName": "Jaan Tamm",
                "decision": {"code": "POOLT"},
                "faction": {"name": "Fraktsioon"},
            },
            "decision",
        ),
        # VerbatimSitting: date, link, edited, agendaItems
        (
            VerbatimSitting,
            {
                "date": "2026-10-01",
                "link": "https://stenogrammid.riigikogu.ee/et/202610011000",
                "edited": False,
                "agendaItems": [],
            },
            "date",
        ),
        (
            VerbatimSitting,
            {
                "date": "2026-10-01",
                "link": "https://stenogrammid.riigikogu.ee/et/202610011000",
                "edited": False,
                "agendaItems": [],
            },
            "link",
        ),
        (
            VerbatimSitting,
            {
                "date": "2026-10-01",
                "link": "https://stenogrammid.riigikogu.ee/et/202610011000",
                "edited": False,
                "agendaItems": [],
            },
            "edited",
        ),
        (
            VerbatimSitting,
            {
                "date": "2026-10-01",
                "link": "https://stenogrammid.riigikogu.ee/et/202610011000",
                "edited": False,
                "agendaItems": [],
            },
            "agendaItems",
        ),
        # VerbatimAgendaItem: events
        (
            VerbatimAgendaItem,
            {"events": []},
            "events",
        ),
        # VerbatimEvent: type
        (
            VerbatimEvent,
            {"type": "SPEECH"},
            "type",
        ),
        # MeetingSpeech: content, speechType
        (
            MeetingSpeech,
            {"content": "<p>Tere</p>", "speechType": "SPEECH"},
            "content",
        ),
        (
            MeetingSpeech,
            {"content": "<p>Tere</p>", "speechType": "SPEECH"},
            "speechType",
        ),
    ],
)
def test_newly_required_fields_raise_on_missing(model, base_payload, field_name):
    payload = dict(base_payload)
    del payload[field_name]
    with pytest.raises(UpstreamSchemaError) as exc_info:
        validate_response(
            model,
            payload,
            endpoint=f"/test/{model.__name__}",
            ref=f"missing_{field_name}",
        )
    msg = str(exc_info.value)
    assert field_name in msg
    assert "api.riigikogu.ee response shape changed" in msg


# ---------------------------------------------------------------------------
# 3. Unknown extra field is tolerated
# ---------------------------------------------------------------------------
def test_unknown_extra_fields_allowed():
    extra_data = [
        {
            "number": 15,
            "startDate": "2023-04-10",
            "endDate": "2027-02-25",
            "completely_new_field": "some_value",
            "nested_unrecognized_struct": {"foo": "bar", "count": 42},
        }
    ]
    # Should not raise
    validate_response(
        MembershipItem,
        extra_data,
        endpoint="/api/memberships",
        ref="extra_fields_test",
    )


# ---------------------------------------------------------------------------
# 4. Golden tests: fetcher transforms produce identical output to master
# ---------------------------------------------------------------------------
def test_memberships_transform_golden():
    with open(FIXTURES_DIR / "memberships.json", encoding="utf-8") as f:
        m_data = json.load(f)

    sorted_items = sorted(
        [it for it in m_data if it.get("number") and it.get("startDate")],
        key=lambda x: int(x["number"]),
    )
    m_map = {}
    for _i, item in enumerate(sorted_items):
        num = int(item["number"])
        start = item["startDate"]
        session_end = item.get("endDate")
        mandate_end = session_end or "2099-12-31"
        roman = roman_numeral(num)
        m_map[str(num)] = {
            "number": num,
            "name": f"{roman} Riigikogu",
            "startDate": start,
            "endDate": mandate_end,
            "sessionEndDate": session_end,
        }

    with open(GOLDENS_DIR / "memberships_transformed.json", encoding="utf-8") as f:
        expected = json.load(f)
    assert m_map == expected


def test_persons_transform_golden():
    with open(FIXTURES_DIR / "plenary_members_recent.json", encoding="utf-8") as f:
        p_data = json.load(f)

    persons = []
    for m in p_data:
        persons.append(
            {
                "uuid": m.get("uuid"),
                "first_name": m.get("firstName"),
                "last_name": m.get("lastName"),
                "photo_url": extract_photo_url(m),
                "electoral_district": extract_electoral_district(m),
            }
        )

    with open(GOLDENS_DIR / "persons_transformed.json", encoding="utf-8") as f:
        expected = json.load(f)
    assert persons == expected


def test_voting_detail_transform_golden():
    with open(FIXTURES_DIR / "voting_detail_recent.json", encoding="utf-8") as f:
        v_data = json.load(f)

    v_parsed = parse_and_validate_voting(v_data)
    with open(GOLDENS_DIR / "voting_detail_transformed.json", encoding="utf-8") as f:
        expected = json.load(f)
    assert v_parsed == expected


def test_speeches_transform_golden():
    with open(FIXTURES_DIR / "meeting_recent.json", encoding="utf-8") as f:
        meeting_data = json.load(f)

    speeches, status = parse_meeting_speeches(
        rich_meeting=meeting_data,
        verbatim=None,
        meeting_code="202610191500",
        verbatim_link="https://stenogrammid.riigikogu.ee/et/202610191500",
        date_formatted="2026-10-19",
        time_formatted="1500",
        source_file_key="2026-10-19_1500.api",
        faction_map={},
    )

    with open(GOLDENS_DIR / "speeches_transformed.json", encoding="utf-8") as f:
        expected = json.load(f)
    assert {"status": status, "speeches": speeches} == expected


def test_agenda_transform_golden():
    with open(FIXTURES_DIR / "agenda_recent.json", encoding="utf-8") as f:
        ag_data = json.load(f)
    with open(FIXTURES_DIR / "verbatims_recent.json", encoding="utf-8") as f:
        vb_data = json.load(f)

    existing_records = {}
    process_agenda_and_verbatims(ag_data, vb_data, existing_records)

    with open(GOLDENS_DIR / "agenda_transformed.json", encoding="utf-8") as f:
        expected = json.load(f)
    assert existing_records == expected
