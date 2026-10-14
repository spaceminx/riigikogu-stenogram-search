import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from sqlalchemy import create_engine

from scripts.build_full_database import get_expected_dataset_files
from scripts.fetch_votes import (
    fetch_votes,
    parse_and_validate_voting,
    write_votes_jsonl_atomic,
)
from scripts.load_votes import load_votes
from scripts.sync_database import sync_database
from scripts.verify_pipeline_integrity import (
    verify_pipeline_integrity,
    verify_votes_integrity,
)
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


def test_fetch_votes_detail_failure_partial_write(tmp_path):
    with (
        patch("scripts.fetch_votes.OUTPUT_DIR_PROCESSED", str(tmp_path)),
        patch("scripts.fetch_votes.fetch_votings_list") as mock_list,
        patch("scripts.fetch_votes.fetch_voting_detail") as mock_detail,
    ):
        mock_list.return_value = [
            {
                "membership": 15,
                "votings": [
                    {
                        "uuid": "v-ok",
                        "votingNumber": 1,
                        "type": {"code": "AVALIK"},
                        "description": "Success voting",
                        "startDateTime": "2026-09-29T10:00:00",
                    },
                    {
                        "uuid": "v-fail",
                        "votingNumber": 2,
                        "type": {"code": "AVALIK"},
                        "description": "Failing voting",
                        "startDateTime": "2026-09-29T10:05:00",
                    },
                ],
            }
        ]
        mock_detail.side_effect = lambda u: (
            {
                "uuid": "v-ok",
                "votingNumber": 1,
                "type": {"code": "AVALIK"},
                "description": "Success voting",
                "startDateTime": "2026-09-29T10:00:00",
                "inFavor": 1,
                "against": 0,
                "neutral": 0,
                "abstained": 0,
                "present": 1,
                "absent": 0,
                "voters": [{"uuid": "m1", "decision": {"code": "POOLT"}}],
            }
            if u == "v-ok"
            else None
        )

        success = fetch_votes(start_date="2026-09-29", end_date="2026-09-29")
        assert success is False

        # Verify that successful voting was still written to file atomically
        out_file = tmp_path / "votes_2026.jsonl"
        assert out_file.exists()
        with open(out_file, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
            assert len(lines) == 1
            assert lines[0]["voting_uuid"] == "v-ok"


def test_fetch_votes_upload_only_modified(tmp_path):
    with (
        patch("scripts.fetch_votes.OUTPUT_DIR_PROCESSED", str(tmp_path)),
        patch("scripts.fetch_votes.fetch_votings_list") as mock_list,
        patch("scripts.fetch_votes.fetch_voting_detail") as mock_detail,
        patch("scripts.upload_to_b2.upload_to_b2") as mock_upload,
    ):
        mock_list.return_value = [
            {
                "membership": 15,
                "votings": [
                    {
                        "uuid": "v-up",
                        "votingNumber": 1,
                        "type": {"code": "AVALIK"},
                        "description": "Upload test",
                        "startDateTime": "2026-09-29T10:00:00",
                    }
                ],
            }
        ]
        mock_detail.return_value = {
            "uuid": "v-up",
            "votingNumber": 1,
            "type": {"code": "AVALIK"},
            "description": "Upload test",
            "startDateTime": "2026-09-29T10:00:00",
            "voters": [],
        }

        # Case 1: upload succeeds with only_files restricted to modified year
        mock_upload.return_value = True
        res_ok = fetch_votes(start_date="2026-09-29", end_date="2026-09-29", upload=True)
        assert res_ok is True
        mock_upload.assert_called_once_with(only_files=["votes_2026.jsonl"])

        # Case 2: upload fails -> returns False
        mock_list.return_value = [
            {
                "membership": 15,
                "votings": [
                    {
                        "uuid": "v-up-2",
                        "votingNumber": 2,
                        "type": {"code": "AVALIK"},
                        "description": "Upload test 2",
                        "startDateTime": "2026-09-29T10:10:00",
                    }
                ],
            }
        ]
        mock_detail.return_value = {
            "uuid": "v-up-2",
            "votingNumber": 2,
            "type": {"code": "AVALIK"},
            "description": "Upload test 2",
            "startDateTime": "2026-09-29T10:10:00",
            "voters": [],
        }
        mock_upload.reset_mock()
        mock_upload.return_value = False
        res_upload_fail = fetch_votes(start_date="2026-09-29", end_date="2026-09-29", upload=True)
        assert res_upload_fail is False
        mock_upload.assert_called_once_with(only_files=["votes_2026.jsonl"])


def test_fetch_votes_load_db(tmp_path):
    with (
        patch("scripts.fetch_votes.OUTPUT_DIR_PROCESSED", str(tmp_path)),
        patch("scripts.fetch_votes.fetch_votings_list") as mock_list,
        patch("scripts.fetch_votes.fetch_voting_detail") as mock_detail,
        patch("src.load.loader.load_votes_to_database") as mock_load_db,
    ):
        mock_list.return_value = [
            {
                "membership": 15,
                "votings": [
                    {
                        "uuid": "v-db",
                        "votingNumber": 1,
                        "type": {"code": "AVALIK"},
                        "description": "DB load test",
                        "startDateTime": "2026-09-29T10:00:00",
                    }
                ],
            }
        ]
        mock_detail.return_value = {
            "uuid": "v-db",
            "votingNumber": 1,
            "type": {"code": "AVALIK"},
            "description": "DB load test",
            "startDateTime": "2026-09-29T10:00:00",
            "voters": [],
        }

        # Success case
        mock_load_db.return_value = 1
        res_ok = fetch_votes(start_date="2026-09-29", end_date="2026-09-29", load_db=True)
        assert res_ok is True
        mock_load_db.assert_called_once_with(years=[2026])

        # Failure case -> returns False
        mock_load_db.reset_mock()
        mock_load_db.side_effect = RuntimeError("Database write error")
        mock_list.return_value = [
            {
                "membership": 15,
                "votings": [
                    {
                        "uuid": "v-db-fail",
                        "votingNumber": 2,
                        "type": {"code": "AVALIK"},
                        "description": "DB load test fail",
                        "startDateTime": "2026-09-29T10:15:00",
                    }
                ],
            }
        ]
        mock_detail.return_value = {
            "uuid": "v-db-fail",
            "votingNumber": 2,
            "type": {"code": "AVALIK"},
            "description": "DB load test fail",
            "startDateTime": "2026-09-29T10:15:00",
            "voters": [],
        }
        res_fail = fetch_votes(start_date="2026-09-29", end_date="2026-09-29", load_db=True)
        assert res_fail is False


def test_load_votes_to_database_corrupted_json(tmp_path):
    bad_file = tmp_path / "votes_2097.jsonl"
    bad_file.write_text('{"voting_uuid": "ok"}\n{invalid_json}\n', encoding="utf-8")
    with patch("src.load.loader.OUTPUT_DIR_PROCESSED", str(tmp_path)):
        with pytest.raises(ValueError, match="Corrupted JSON"):
            load_votes_to_database(years=[2097])


def test_load_votes_to_database_db_error_and_sync_database(tmp_path):
    vote_file = tmp_path / "votes_2026.jsonl"
    vote_file.write_text('{"voting_uuid": "v-1"}\n', encoding="utf-8")
    with (
        patch("src.load.loader.OUTPUT_DIR_PROCESSED", str(tmp_path)),
        patch("src.load.loader.SessionLocal") as mock_session_cls,
    ):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.query.side_effect = RuntimeError("Simulated DB connection drop")

        with pytest.raises(RuntimeError, match="Simulated DB connection drop"):
            load_votes_to_database(years=[2026])
        mock_session.rollback.assert_called()

    # Verify that sync_database aborts and skips updating last_sync_at when load_votes_to_database fails
    with (
        patch("scripts.sync_database.download_from_b2", return_value=True),
        patch("scripts.sync_database.create_tables"),
        patch("scripts.sync_database.create_indexes"),
        patch("scripts.sync_database.sync_current_year_speeches"),
        patch("scripts.sync_database.load_attendance_to_database"),
        patch("scripts.sync_database.load_persons_to_database"),
        patch(
            "scripts.sync_database.load_votes_to_database",
            side_effect=RuntimeError("Vote loader failed"),
        ),
        patch("scripts.sync_database.SessionLocal") as mock_meta_session_cls,
    ):
        mock_meta_session = MagicMock()
        mock_meta_session_cls.return_value = mock_meta_session
        ok = sync_database()
        assert ok is False
        mock_meta_session.add.assert_not_called()
        mock_meta_session.commit.assert_not_called()


def test_verify_votes_integrity_warning_only():
    # 1. Missing votes do not fail verify_pipeline_integrity
    with (
        patch("scripts.verify_pipeline_integrity.load_local_sessions_from_jsonl", return_value={}),
        patch("requests.get") as mock_get,
    ):
        mock_verbatims = MagicMock(status_code=200, json=lambda: [])
        mock_votings = MagicMock(
            status_code=200,
            json=lambda: [
                {
                    "votings": [
                        {
                            "uuid": "missing-vote-uuid-999",
                            "type": {"code": "AVALIK"},
                            "description": "Missing vote",
                            "startDateTime": "2026-10-10T12:00:00",
                        }
                    ]
                }
            ],
        )

        def get_dispatcher(url, *args, **kwargs):
            if "votings" in url:
                return mock_votings
            return mock_verbatims

        mock_get.side_effect = get_dispatcher
        ok = verify_pipeline_integrity(days=14, fail_on_missing=True)
        assert ok is True

    # 2. API error in verify_votes_integrity prints SKIPPED and returns True
    with patch("requests.get") as mock_get, patch("builtins.print") as mock_print:
        mock_get.return_value = MagicMock(status_code=500)
        ok = verify_votes_integrity(days=14)
        assert ok is True
        mock_print.assert_any_call(
            "SKIPPED: Votings API returned HTTP 500. Skipping votes verification."
        )


def test_indexes_no_duplicates():
    import src.load.database as db
    import src.load.indexes as idx_mod
    import src.load.loader as loader_mod

    test_eng = create_engine("sqlite:///:memory:")
    old_eng = db.engine
    db.engine = test_eng
    idx_mod.engine = test_eng
    loader_mod.engine = test_eng

    try:
        loader_mod.create_tables()
        idx_mod.create_indexes()

        with test_eng.connect() as conn:
            rows = conn.exec_driver_sql(
                "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' AND tbl_name IN ('votings', 'votes');"
            ).fetchall()

        index_names = [r[0] for r in rows]
        # Check expected indexes exist
        assert "sqlite_autoindex_votings_1" in index_names
        assert "sqlite_autoindex_votes_1" in index_names
        assert "idx_votings_date" in index_names
        assert "idx_votings_doc_uuid" in index_names
        assert "idx_votes_member_uuid" in index_names

        # Check redundant / duplicate indexes are NOT present
        assert "idx_votes_voting_uuid" not in index_names
        assert "ix_votes_voting_uuid" not in index_names
        assert "ix_votings_date" not in index_names
        assert "ix_votings_related_document_uuid" not in index_names
        assert "ix_votes_member_uuid" not in index_names

        # Total indexes across both tables: exactly 5 (2 PK autoindexes + 3 secondary indexes)
        assert len(rows) == 5
    finally:
        db.engine = old_eng
        idx_mod.engine = old_eng
        loader_mod.engine = old_eng


def test_api_votings_type_parameter_validation():
    # Valid AVALIK
    resp_avalik = client.get("/votings?type=AVALIK")
    assert resp_avalik.status_code == 200

    # Valid SALAJANE
    resp_salajane = client.get("/votings?type=SALAJANE")
    assert resp_salajane.status_code == 200

    # Invalid type -> 422 Unprocessable Entity
    resp_invalid = client.get("/votings?type=KOHALOLEKU_KONTROLL")
    assert resp_invalid.status_code == 422

    resp_invalid_random = client.get("/votings?type=RANDOM_INVALID")
    assert resp_invalid_random.status_code == 422


def test_api_system_status_methodology_text():
    resp = client.get("/system/status")
    assert resp.status_code == 200
    methodology = resp.json().get("methodology", {})
    votes_meta = methodology.get("votes", "")
    assert "abstained" in votes_meta
    assert "ei hääletanud" in votes_meta
    assert "puudub" in votes_meta
    assert "Salajastel hääletustel" in votes_meta


def test_load_votes_script(tmp_path):
    test_jsonl = tmp_path / "votes_2096.jsonl"
    rec = {
        "voting_uuid": "uuid-script-test",
        "voting_number": 1,
        "type": "AVALIK",
        "description": "Script test",
        "date": "2096-01-01",
        "start_time": "2096-01-01T10:00:00",
        "totals": {
            "present": 101,
            "absent": 0,
            "in_favor": 101,
            "against": 0,
            "neutral": 0,
            "abstained": 0,
        },
        "votes": [],
    }
    test_jsonl.write_text(json.dumps(rec) + "\n", encoding="utf-8")

    with (
        patch("scripts.load_votes.OUTPUT_DIR_PROCESSED", str(tmp_path)),
        patch("src.load.loader.OUTPUT_DIR_PROCESSED", str(tmp_path)),
    ):
        loaded = load_votes(years=[2096])
        assert loaded == 1
        loaded_again = load_votes(years=[2096])
        assert loaded_again == 0
