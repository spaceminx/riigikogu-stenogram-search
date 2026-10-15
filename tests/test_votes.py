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
from src.load.models import Person, Speech, Vote, Voting

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
        assert "idx_votings_sitting_date" in index_names
        assert "idx_votings_doc_uuid" in index_names
        assert "idx_votes_member_uuid" in index_names

        # Check redundant / duplicate indexes are NOT present
        assert "idx_votes_voting_uuid" not in index_names
        assert "ix_votes_voting_uuid" not in index_names
        assert "ix_votings_date" not in index_names
        assert "ix_votings_sitting_date" not in index_names
        assert "ix_votings_related_document_uuid" not in index_names
        assert "ix_votes_member_uuid" not in index_names

        # Total indexes across both tables: exactly 6 (2 PK autoindexes + 4 secondary indexes)
        assert len(rows) == 6
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
    assert "istungi kuupäevaga" in votes_meta
    assert "öised hääletused" in votes_meta


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


def test_fetch_votes_interrupted_intermediate_save_and_resume(tmp_path):
    sample_votings = [
        {
            "uuid": f"v-{i}",
            "votingNumber": i,
            "type": {"code": "AVALIK"},
            "description": f"Voting {i}",
            "startDateTime": f"2026-09-01T10:{i:02d}:00",
        }
        for i in range(1, 36)
    ]

    def mock_detail_side_effect(u):
        idx = int(u.split("-")[1])
        if idx == 30:
            raise KeyboardInterrupt
        return {
            "uuid": u,
            "votingNumber": idx,
            "type": {"code": "AVALIK"},
            "description": f"Voting {idx}",
            "startDateTime": f"2026-09-01T10:{idx:02d}:00",
            "voters": [],
        }

    # Step 1: Interrupted at 30th detail call -> saves 29 records (>= 25), exits with False (code 1), no upload
    with (
        patch("scripts.fetch_votes.OUTPUT_DIR_PROCESSED", str(tmp_path)),
        patch(
            "scripts.fetch_votes.fetch_votings_list",
            return_value=[{"membership": 15, "votings": sample_votings}],
        ),
        patch("scripts.fetch_votes.fetch_voting_detail", side_effect=mock_detail_side_effect),
        patch("scripts.upload_to_b2.upload_to_b2") as mock_upload,
    ):
        ok = fetch_votes(start_date="2026-09-01", end_date="2026-09-30", upload=True)
        assert ok is False
        mock_upload.assert_not_called()

        out_file = tmp_path / "votes_2026.jsonl"
        assert out_file.exists()
        with open(out_file, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        assert len(lines) == 29
        assert len(lines) >= 25

    # Step 2: Resume after interruption -> fetches only remaining 6 votings, then uploads
    def mock_detail_resume(u):
        idx = int(u.split("-")[1])
        return {
            "uuid": u,
            "votingNumber": idx,
            "type": {"code": "AVALIK"},
            "description": f"Voting {idx}",
            "startDateTime": f"2026-09-01T10:{idx:02d}:00",
            "voters": [],
        }

    with (
        patch("scripts.fetch_votes.OUTPUT_DIR_PROCESSED", str(tmp_path)),
        patch(
            "scripts.fetch_votes.fetch_votings_list",
            return_value=[{"membership": 15, "votings": sample_votings}],
        ),
        patch(
            "scripts.fetch_votes.fetch_voting_detail", side_effect=mock_detail_resume
        ) as mock_detail_resumed,
        patch("scripts.upload_to_b2.upload_to_b2", return_value=True) as mock_upload_resumed,
    ):
        ok_resume = fetch_votes(start_date="2026-09-01", end_date="2026-09-30", upload=True)
        assert ok_resume is True
        # Only 6 missing votings fetched (35 total - 29 already in file)
        assert mock_detail_resumed.call_count == 6
        mock_upload_resumed.assert_called_once_with(only_files=["votes_2026.jsonl"])

        with open(out_file, encoding="utf-8") as f:
            all_lines = [json.loads(line) for line in f if line.strip()]
        assert len(all_lines) == 35


def test_fetch_votes_sigterm_handling(tmp_path):
    import signal

    sample_votings = [
        {
            "uuid": f"v-sig-{i}",
            "votingNumber": i,
            "type": {"code": "AVALIK"},
            "description": f"Voting {i}",
            "startDateTime": f"2026-09-01T10:{i:02d}:00",
        }
        for i in range(1, 10)
    ]

    def mock_detail_sigterm(u):
        idx = int(u.split("-")[-1])
        if idx == 3:
            os.kill(os.getpid(), signal.SIGTERM)
        return {
            "uuid": u,
            "votingNumber": idx,
            "type": {"code": "AVALIK"},
            "description": f"Voting {idx}",
            "startDateTime": f"2026-09-01T10:{idx:02d}:00",
            "voters": [],
        }

    with (
        patch("scripts.fetch_votes.OUTPUT_DIR_PROCESSED", str(tmp_path)),
        patch(
            "scripts.fetch_votes.fetch_votings_list",
            return_value=[{"membership": 15, "votings": sample_votings}],
        ),
        patch("scripts.fetch_votes.fetch_voting_detail", side_effect=mock_detail_sigterm),
        patch("scripts.upload_to_b2.upload_to_b2") as mock_upload,
    ):
        ok = fetch_votes(start_date="2026-09-01", end_date="2026-09-30", upload=True)
        assert ok is False
        mock_upload.assert_not_called()

        out_file = tmp_path / "votes_2026.jsonl"
        assert out_file.exists()
        with open(out_file, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        assert len(lines) == 2


def test_fetch_votes_night_voting(tmp_path):
    sitting_data = {
        "uuid": "s-night-uuid",
        "title": "Täiskogu korraline istung kolmapäev, 14.10.2026 14:00",
        "membership": 15,
        "sittingDateTime": "2026-10-14T14:00:00",
        "votings": [
            {
                "uuid": "68c4372e-209a-4c9d-b6f8-d615e1f3e466",
                "votingNumber": 104323,
                "type": {"code": "AVALIK"},
                "description": "Tagasi lükkamine",
                "startDateTime": "2026-10-15T00:43:21.94",
            }
        ],
    }
    mock_detail = {
        "uuid": "68c4372e-209a-4c9d-b6f8-d615e1f3e466",
        "votingNumber": 104323,
        "type": {"code": "AVALIK"},
        "description": "Tagasi lükkamine",
        "startDateTime": "2026-10-15T00:43:21.94",
        "endDateTime": "2026-10-15T00:43:41.94",
        "sitting": {
            "uuid": "s-night-uuid",
            "title": "Täiskogu korraline istung kolmapäev, 14.10.2026 14:00",
        },
        "voters": [],
    }

    with (
        patch("scripts.fetch_votes.OUTPUT_DIR_PROCESSED", str(tmp_path)),
        patch("scripts.fetch_votes.fetch_votings_list", return_value=[sitting_data]),
        patch("scripts.fetch_votes.fetch_voting_detail", return_value=mock_detail),
    ):
        ok = fetch_votes(start_date="2026-10-12", end_date="2026-10-15")
        assert ok is True

        out_file = tmp_path / "votes_2026.jsonl"
        assert out_file.exists()
        with open(out_file, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        assert len(lines) == 1
        rec = lines[0]
        assert rec["voting_uuid"] == "68c4372e-209a-4c9d-b6f8-d615e1f3e466"
        assert rec["sitting_date"] == "2026-10-14"
        assert rec["date"] == "2026-10-15"
        assert rec["sitting_datetime"] == "2026-10-14T14:00:00"


def test_fetch_votes_new_year_boundary_no_duplicate(tmp_path):
    sitting_data = {
        "uuid": "s-nye-uuid",
        "title": "Täiskogu istung kolmapäev, 31.12.2025 14:00",
        "membership": 15,
        "sittingDateTime": "2025-12-31T14:00:00",
        "votings": [
            {
                "uuid": "v-nye-1",
                "votingNumber": 9999,
                "type": {"code": "AVALIK"},
                "description": "Öine hääletus",
                "startDateTime": "2026-01-01T00:30:00",
            }
        ],
    }
    mock_detail = {
        "uuid": "v-nye-1",
        "votingNumber": 9999,
        "type": {"code": "AVALIK"},
        "description": "Öine hääletus",
        "startDateTime": "2026-01-01T00:30:00",
        "voters": [],
    }

    with (
        patch("scripts.fetch_votes.OUTPUT_DIR_PROCESSED", str(tmp_path)),
        patch("scripts.fetch_votes.fetch_votings_list", return_value=[sitting_data]),
        patch("scripts.fetch_votes.fetch_voting_detail", return_value=mock_detail) as mock_fetch,
    ):
        ok1 = fetch_votes(start_date="2025-12-31", end_date="2026-01-01")
        assert ok1 is True
        assert mock_fetch.call_count == 1

        file_2025 = tmp_path / "votes_2025.jsonl"
        file_2026 = tmp_path / "votes_2026.jsonl"
        assert file_2025.exists()
        with open(file_2025, encoding="utf-8") as f:
            lines_2025 = [json.loads(line) for line in f if line.strip()]
        assert len(lines_2025) == 1
        assert lines_2025[0]["voting_uuid"] == "v-nye-1"
        assert lines_2025[0]["sitting_date"] == "2025-12-31"
        assert lines_2025[0]["date"] == "2026-01-01"

        if file_2026.exists():
            with open(file_2026, encoding="utf-8") as f:
                lines_2026 = [json.loads(line) for line in f if line.strip()]
            assert all(r["voting_uuid"] != "v-nye-1" for r in lines_2026)

        # Run 2 (korduskäivitus): does not re-fetch detail or duplicate in votes_2026
        mock_fetch.reset_mock()
        ok2 = fetch_votes(start_date="2026-01-01", end_date="2026-01-05")
        assert ok2 is True
        assert mock_fetch.call_count == 0
        if file_2026.exists():
            with open(file_2026, encoding="utf-8") as f:
                lines_2026 = [json.loads(line) for line in f if line.strip()]
            assert all(r["voting_uuid"] != "v-nye-1" for r in lines_2026)


def test_fetch_votes_self_healing_existing_record(tmp_path):
    legacy_rec = {
        "voting_uuid": "v-legacy-heal",
        "voting_number": 500,
        "type": "AVALIK",
        "description": "Legacy hääletus",
        "date": "2026-09-02",
        "start_time": "2026-09-02T12:00:00",
        "membership": 15,
        "totals": {"present": 100},
        "votes": [],
    }
    file_2026 = tmp_path / "votes_2026.jsonl"
    with open(file_2026, "w", encoding="utf-8") as f:
        f.write(json.dumps(legacy_rec) + "\n")

    sitting_data = {
        "uuid": "s-new-heal-uuid",
        "title": "Uuendatud istung",
        "membership": 15,
        "sittingDateTime": "2026-09-02T10:00:00",
        "votings": [
            {
                "uuid": "v-legacy-heal",
                "votingNumber": 500,
                "type": {"code": "AVALIK"},
                "description": "Legacy hääletus",
                "startDateTime": "2026-09-02T12:00:00",
            }
        ],
    }

    with (
        patch("scripts.fetch_votes.OUTPUT_DIR_PROCESSED", str(tmp_path)),
        patch("scripts.fetch_votes.fetch_votings_list", return_value=[sitting_data]),
        patch("scripts.fetch_votes.fetch_voting_detail") as mock_detail,
    ):
        ok = fetch_votes(start_date="2026-09-01", end_date="2026-09-05")
        assert ok is True
        # Must be self-healed WITHOUT making detail calls
        assert mock_detail.call_count == 0

        with open(file_2026, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        assert len(lines) == 1
        healed = lines[0]
        assert healed["sitting_date"] == "2026-09-02"
        assert healed["sitting_datetime"] == "2026-09-02T10:00:00"
        assert healed["sitting_uuid"] == "s-new-heal-uuid"
        assert healed["sitting_title"] == "Uuendatud istung"


def test_loader_updates_existing_db_row(tmp_path):
    session = SessionLocal()
    v_uuid = "v-db-update-test"
    try:
        session.query(Vote).filter(Vote.voting_uuid == v_uuid).delete()
        session.query(Voting).filter(Voting.uuid == v_uuid).delete()
        session.commit()

        # Insert old row without sitting_date
        old_v = Voting(
            uuid=v_uuid,
            voting_number=100,
            type="AVALIK",
            description="Test DB update",
            date="2026-09-02",
            start_time="2026-09-02T12:00:00",
            sitting_date=None,
            sitting_datetime=None,
        )
        old_vote = Vote(
            voting_uuid=v_uuid,
            member_uuid="person-test-uuid-1",
            faction="Testfraktsioon",
            decision="POOLT",
        )
        session.add(old_v)
        session.add(old_vote)
        session.commit()

        # Prepare JSONL with sitting_date and different vote decision in JSON (should be ignored!)
        jsonl_file = tmp_path / "votes_2026.jsonl"
        rec = {
            "voting_uuid": v_uuid,
            "voting_number": 100,
            "type": "AVALIK",
            "description": "Test DB update",
            "date": "2026-09-02",
            "start_time": "2026-09-02T12:00:00",
            "sitting_date": "2026-09-02",
            "sitting_datetime": "2026-09-02T10:00:00",
            "sitting_uuid": "s-db-uuid",
            "votes": [["person-test-uuid-1", "VASTU", "Uusfraktsioon"]],
        }
        with open(jsonl_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

        with patch("src.load.loader.OUTPUT_DIR_PROCESSED", str(tmp_path)):
            load_votes_to_database(years=[2026])

        # Verify DB Voting metadata was updated
        updated_v = session.query(Voting).filter(Voting.uuid == v_uuid).first()
        assert updated_v is not None
        assert updated_v.sitting_date == "2026-09-02"
        assert updated_v.sitting_datetime == "2026-09-02T10:00:00"
        assert updated_v.sitting_uuid == "s-db-uuid"

        # Verify DB Vote row was untouched
        v_rows = session.query(Vote).filter(Vote.voting_uuid == v_uuid).all()
        assert len(v_rows) == 1
        assert v_rows[0].decision == "POOLT"
        assert v_rows[0].faction == "Testfraktsioon"
    finally:
        session.query(Vote).filter(Vote.voting_uuid == v_uuid).delete()
        session.query(Voting).filter(Voting.uuid == v_uuid).delete()
        session.commit()
        session.close()


def test_api_votings_sitting_date_filter_and_session_source_file():
    session = SessionLocal()
    v1_uuid = "v-api-night-1"
    v2_uuid = "v-api-day-2"
    v3_uuid = "v-api-other-3"
    test_uuids = [v1_uuid, v2_uuid, v3_uuid]
    speech_file = "2026-10-14_1400.api"
    try:
        session.query(Vote).filter(Vote.voting_uuid.in_(test_uuids)).delete(
            synchronize_session=False
        )
        session.query(Voting).filter(Voting.uuid.in_(test_uuids)).delete(synchronize_session=False)
        session.query(Speech).filter(Speech.source_file == speech_file).delete()
        session.commit()

        # Add speech for 2026-10-14 14:00
        sp = Speech(
            date="2026-10-14",
            time="14:00",
            source_file=speech_file,
            source_url="https://api.riigikogu.ee/api/stenograms/123",
            speaker="Test Speaker",
            text="Test speech text",
            speaker_faction="Test Faction",
            speech_type="SPEECH",
            duration_seconds=60,
        )
        session.add(sp)

        # Voting 1: night voting on 15.10 belonging to sitting 14.10
        session.add(
            Voting(
                uuid=v1_uuid,
                voting_number=104323,
                type="AVALIK",
                description="Tagasi lükkamine",
                date="2026-10-15",
                start_time="2026-10-15T00:43:21",
                sitting_date="2026-10-14",
                sitting_datetime="2026-10-14T14:00:00",
                membership=15,
            )
        )
        # Voting 2: earlier day voting on sitting 14.10
        session.add(
            Voting(
                uuid=v2_uuid,
                voting_number=104320,
                type="AVALIK",
                description="Päevane hääletus",
                date="2026-10-14",
                start_time="2026-10-14T15:00:00",
                sitting_date="2026-10-14",
                sitting_datetime="2026-10-14T14:00:00",
                membership=15,
            )
        )
        # Voting 3: different sitting on 12.10 (no matching speech source_file)
        session.add(
            Voting(
                uuid=v3_uuid,
                voting_number=104310,
                type="AVALIK",
                description="Muu istungi hääletus",
                date="2026-10-12",
                start_time="2026-10-12T15:30:00",
                sitting_date="2026-10-12",
                sitting_datetime="2026-10-12T15:00:00",
                membership=15,
            )
        )
        session.commit()

        # 1. Test filtering by sitting_date=2026-10-14
        resp = client.get("/votings?sitting_date=2026-10-14")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        items = data["results"]
        assert items[0]["uuid"] == v2_uuid
        assert items[1]["uuid"] == v1_uuid
        assert items[0]["session_source_file"] == speech_file
        assert items[1]["session_source_file"] == speech_file
        assert items[1]["date"] == "2026-10-15"
        assert items[1]["sitting_date"] == "2026-10-14"

        # 2. Test filtering by sitting_date=2026-10-12 where speeches row does NOT exist -> null
        resp_other = client.get("/votings?sitting_date=2026-10-12")
        assert resp_other.status_code == 200
        data_other = resp_other.json()
        assert data_other["total"] == 1
        assert data_other["results"][0]["session_source_file"] is None

        # 3. Test invalid sitting_date regex -> 422
        resp_invalid = client.get("/votings?sitting_date=invalid-date")
        assert resp_invalid.status_code == 422
        resp_invalid_format = client.get("/votings?sitting_date=2026-1-1")
        assert resp_invalid_format.status_code == 422

        # 4. Test detail endpoint returns sitting_date, sitting_datetime, session_source_file
        resp_detail = client.get(f"/votings/{v1_uuid}")
        assert resp_detail.status_code == 200
        detail_data = resp_detail.json()
        assert detail_data["sitting_date"] == "2026-10-14"
        assert detail_data["sitting_datetime"] == "2026-10-14T14:00:00"
        assert detail_data["session_source_file"] == speech_file

        # Detail for v3 has session_source_file=None
        resp_detail_v3 = client.get(f"/votings/{v3_uuid}")
        assert resp_detail_v3.status_code == 200
        assert resp_detail_v3.json()["session_source_file"] is None
    finally:
        session.rollback()
        session.query(Vote).filter(Vote.voting_uuid.in_(test_uuids)).delete(
            synchronize_session=False
        )
        session.query(Voting).filter(Voting.uuid.in_(test_uuids)).delete(synchronize_session=False)
        session.query(Speech).filter(Speech.source_file == speech_file).delete()
        session.commit()
        session.close()
