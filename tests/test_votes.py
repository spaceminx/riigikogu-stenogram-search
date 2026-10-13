import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from scripts.build_full_database import get_expected_dataset_files
from scripts.fetch_votes import (
    parse_and_validate_voting,
    write_votes_jsonl_atomic,
)
from scripts.verify_pipeline_integrity import verify_votes_integrity
from src.api.main import app
from src.load.database import SessionLocal
from src.load.loader import create_tables, ensure_schema, load_votes_to_database
from src.load.models import Person, Vote, Voting

client = TestClient(app)


@pytest.fixture(autouse=True, scope="module")
def setup_votes_db():
    create_tables()
    ensure_schema()
    session = SessionLocal()

    # Create dummy person if not exists
    test_person_uuid = "person-test-uuid-1"
    existing_p = session.query(Person).filter(Person.uuid == test_person_uuid).first()
    if not existing_p:
        session.add(
            Person(
                uuid=test_person_uuid,
                first_name="Jüri",
                last_name="Näidis",
                full_name="Jüri Näidis",
                active=1,
            )
        )

    # Create test voting
    v_uuid = "voting-test-uuid-1"
    existing_v = session.query(Voting).filter(Voting.uuid == v_uuid).first()
    if not existing_v:
        voting_obj = Voting(
            uuid=v_uuid,
            voting_number=101,
            type="AVALIK",
            description="Seaduseelnõu 123 esimesel lugemisel",
            date="2026-09-15",
            start_time="2026-09-15T10:15:00",
            end_time="2026-09-15T10:17:00",
            membership=15,
            sitting_uuid="sitting-test-uuid-1",
            sitting_title="Täiskogu istung teisipäev, 15.09.2026",
            related_document_uuid="doc-test-uuid-1",
            related_document_reference="123 SE",
            related_document_title="Maksukorralduse seaduse muutmise seadus",
            related_document_type="SEADUSEELNOU",
            chairman_uuid=test_person_uuid,
            present=92,
            absent=9,
            in_favor=55,
            against=30,
            neutral=2,
            abstained=14,
        )
        session.add(voting_obj)
        session.add(
            Vote(
                voting_uuid=v_uuid,
                member_uuid=test_person_uuid,
                faction="Testfraktsioon",
                decision="POOLT",
            )
        )
        session.add(
            Vote(
                voting_uuid=v_uuid,
                member_uuid="person-test-uuid-2",
                faction="Opositsioon",
                decision="VASTU",
            )
        )

    session.commit()
    session.close()


def test_parse_and_validate_voting_public():
    detail = {
        "uuid": "test-v-uuid",
        "votingNumber": 500,
        "type": {"code": "AVALIK", "value": "Avalik"},
        "description": "Eelnõu hääletus",
        "startDateTime": "2026-09-20T11:00:00",
        "endDateTime": "2026-09-20T11:02:00",
        "inFavor": 2,
        "against": 1,
        "neutral": 0,
        "abstained": 1,
        "present": 3,
        "absent": 1,
        "sitting": {"uuid": "s-uuid", "title": "Istung 1"},
        "chairman": {"uuid": "chair-uuid"},
        "relatedDocument": {
            "uuid": "rd-uuid",
            "reference": "999",
            "title": "Eelnõu",
            "documentType": "DRAFT",
        },
        "voters": [
            {"uuid": "m1", "decision": {"code": "POOLT"}, "faction": {"name": "F1"}},
            {"uuid": "m2", "decision": {"code": "POOLT"}, "faction": {"name": "F1"}},
            {"uuid": "m3", "decision": {"code": "VASTU"}, "faction": {"name": "F2"}},
            {"uuid": "m4", "decision": {"code": "EI_HAALETANUD"}, "faction": {"name": "F2"}},
            {"uuid": "m5", "decision": {"code": "PUUDUB"}, "faction": {"name": "F2"}},
        ],
    }
    parsed = parse_and_validate_voting(detail, sitting_membership=15)
    assert parsed["voting_uuid"] == "test-v-uuid"
    assert parsed["voting_number"] == 500
    assert parsed["type"] == "AVALIK"
    assert parsed["membership"] == 15
    assert parsed["related_document"]["uuid"] == "rd-uuid"
    assert len(parsed["votes"]) == 5
    assert parsed["votes"][0] == ["m1", "POOLT", "F1"]
    assert parsed["totals"]["in_favor"] == 2
    assert parsed["totals"]["against"] == 1


def test_parse_and_validate_voting_secret():
    detail = {
        "uuid": "test-v-secret",
        "votingNumber": 501,
        "type": {"code": "SALAJANE", "value": "Salajane"},
        "description": "Salajane hääletus",
        "startDateTime": "2026-09-20T12:00:00",
        "inFavor": 70,
        "against": 5,
        "neutral": 0,
        "abstained": 0,
        "present": 75,
        "absent": 26,
        "voters": [],
    }
    parsed = parse_and_validate_voting(detail, sitting_membership=15)
    assert parsed["voting_uuid"] == "test-v-secret"
    assert parsed["type"] == "SALAJANE"
    assert parsed["votes"] == []
    assert parsed["totals"]["in_favor"] == 70


def test_write_votes_jsonl_atomic_and_load(tmp_path):
    year = 2099
    records = {
        "uuid-1": {
            "voting_uuid": "uuid-1",
            "voting_number": 1,
            "type": "AVALIK",
            "description": "Test",
            "date": "2099-01-01",
            "start_time": "2099-01-01T10:00:00",
            "end_time": "2099-01-01T10:02:00",
            "membership": 15,
            "sitting_uuid": "s-1",
            "sitting_title": "S 1",
            "related_document": None,
            "chairman_uuid": None,
            "totals": {
                "present": 100,
                "absent": 1,
                "in_favor": 90,
                "against": 5,
                "neutral": 5,
                "abstained": 6,
            },
            "votes": [["p-1", "POOLT", "F1"], ["p-2", "VASTU", "F2"]],
        }
    }
    with patch("scripts.fetch_votes.OUTPUT_DIR_PROCESSED", str(tmp_path)):
        write_votes_jsonl_atomic(year, records)
        out_file = tmp_path / f"votes_{year}.jsonl"
        assert out_file.exists()
        with open(out_file, encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["voting_uuid"] == "uuid-1"

    # Test loader with the temporary directory
    with patch("src.load.loader.OUTPUT_DIR_PROCESSED", str(tmp_path)):
        loaded = load_votes_to_database(years=[year])
        assert loaded == 1
        # Idempotent second load returns 0
        loaded_again = load_votes_to_database(years=[year])
        assert loaded_again == 0


def test_file_isolation_speech_loader():
    import re

    # Verify regex matches only 4-digit speech jsonls and ignores votes_*.jsonl
    speech_pattern = r"^\d{4}\.jsonl$"
    assert re.match(speech_pattern, "2026.jsonl") is not None
    assert re.match(speech_pattern, "votes_2026.jsonl") is None
    assert re.match(speech_pattern, "attendance.jsonl") is None


def test_api_list_votings():
    resp = client.get("/votings")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "results" in data
    assert len(data["results"]) >= 1

    # Filter by q
    resp_q = client.get("/votings?q=Maksukorralduse")
    assert resp_q.status_code == 200
    assert len(resp_q.json()["results"]) >= 1

    # Filter by invalid membership
    resp_invalid_mem = client.get("/votings?membership=invalid_999")
    assert resp_invalid_mem.status_code == 422


def test_api_get_voting_detail():
    resp = client.get("/votings/voting-test-uuid-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["uuid"] == "voting-test-uuid-1"
    assert data["totals"]["in_favor"] == 55
    assert len(data["votes"]) >= 2
    assert len(data["by_faction"]) >= 1
    assert data["chairman_name"] == "Jüri Näidis"

    # 404 for unknown voting
    resp_404 = client.get("/votings/non-existent-uuid")
    assert resp_404.status_code == 404


def test_api_person_votes():
    resp = client.get("/persons/person-test-uuid-1/votes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["person"]["uuid"] == "person-test-uuid-1"
    assert data["summary"]["in_favor"] >= 1
    assert len(data["results"]) >= 1
    assert data["results"][0]["decision"] == "POOLT"

    # 404 for non-existent person
    resp_404 = client.get("/persons/unknown-person-uuid/votes")
    assert resp_404.status_code == 404

    # 422 for invalid membership
    resp_422 = client.get("/persons/person-test-uuid-1/votes?membership=invalid_mem")
    assert resp_422.status_code == 422


def test_api_system_status():
    resp = client.get("/system/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "votings" in data["totals"]
    assert "votes" in data["methodology"]
    assert "api.riigikogu.ee" in data["methodology"]["votes"]


def test_build_full_database_expected_files():
    files = get_expected_dataset_files(current_year=2026)
    assert "votes_2026.jsonl" in files
    assert "2026.jsonl" in files
    assert "attendance.jsonl" in files


def test_verify_votes_integrity():
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "votings": [
                    {
                        "uuid": "voting-test-uuid-1",
                        "type": {"code": "AVALIK"},
                        "description": "Desc",
                    },
                    {
                        "uuid": "att-check",
                        "type": {"code": "KOHALOLEKU_KONTROLL"},
                        "description": "Att",
                    },
                ]
            }
        ]
        mock_get.return_value = mock_resp
        ok = verify_votes_integrity(days=14, fail_on_missing=False)
        assert ok is True
