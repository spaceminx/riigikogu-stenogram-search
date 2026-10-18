"""Tests for agenda fetching, database loading, coverage check, and draft API endpoints."""

import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.agenda_coverage import compute_agenda_coverage, print_coverage_report
from scripts.fetch_agenda import (
    clean_html,
    fetch_agenda_items,
    is_valid_uuid,
    load_existing_agenda_items,
    map_verbatim_to_source_file,
    process_agenda_and_verbatims,
    write_agenda_items_atomic,
)
from scripts.fetch_stenograms_api import clean_html as base_clean_html
from src.api.main import app
from src.load.database import SessionLocal
from src.load.loader import create_tables, load_agenda_items_to_database
from src.load.migrations import apply_migrations
from src.load.models import AgendaItem, Speech, Voting

client = TestClient(app)


@pytest.fixture(autouse=True, scope="module")
def setup_test_db():
    create_tables()
    apply_migrations()


def test_clean_html_matches_existing_agenda_title_normalisation():
    """clean_html in fetch_agenda is identical to fetch_stenograms_api and strips HTML/normalises spaces."""
    assert clean_html is base_clean_html

    raw_html = "<p>Otsuse &quot;Eelnõu algatamine&quot; arutelu &amp; vastuvõtmine</p>"
    expected = 'Otsuse "Eelnõu algatamine" arutelu & vastuvõtmine'
    assert clean_html(raw_html) == expected

    html_with_nbsp = "<span>414 SE III</span>&nbsp;&nbsp;&nbsp;arutelu\n\t"
    assert clean_html(html_with_nbsp) == "414 SE III arutelu"


def test_is_valid_uuid():
    """UUID validator recognizes standard 36-char hyphenated UUIDs."""
    assert is_valid_uuid("b9fab890-fa21-4a69-9039-171a0015bc84") is True
    assert is_valid_uuid("B9FAB890-FA21-4A69-9039-171A0015BC84") is True
    assert is_valid_uuid("") is False
    assert is_valid_uuid(None) is False
    assert is_valid_uuid("invalid-uuid") is False
    assert is_valid_uuid("12345") is False


def test_verbatim_mapping_and_sittings_on_same_day():
    """Two sittings on same day map to correct source files (YYYY-MM-DD_HHMM.api)."""
    sitting_morning = {
        "date": "2026-10-14T10:00:00",
        "title": "Täiskogu hommikune istung",
        "link": "https://stenogrammid.riigikogu.ee/202610141000",
    }
    sitting_afternoon = {
        "date": "2026-10-14T14:00:00",
        "title": "Täiskogu pärastlõunane istung",
        "link": "https://stenogrammid.riigikogu.ee/202610141400",
    }
    assert map_verbatim_to_source_file(sitting_morning) == "2026-10-14_1000.api"
    assert map_verbatim_to_source_file(sitting_afternoon) == "2026-10-14_1400.api"

    # Fallback when time is missing
    sitting_notime = {
        "date": "2026-10-14",
        "title": "Istung ilma ajata",
        "link": "",
    }
    assert map_verbatim_to_source_file(sitting_notime) == "2026-10-14_0000.api"


def test_process_agenda_and_verbatims_join_and_skipped_uuids():
    """Agenda items join with verbatims by agendaItemUuid; invalid UUIDs skipped."""
    valid_uuid_1 = "11111111-1111-1111-1111-111111111111"
    valid_uuid_2 = "22222222-2222-2222-2222-222222222222"
    draft_uuid = "b9fab890-fa21-4a69-9039-171a0015bc84"
    voting_uuid = "33333333-3333-3333-3333-333333333333"

    agenda_data = {
        "sittings": [
            {
                "uuid": "sitting-uuid-1",
                "sittingDateTime": "2026-10-14T14:00:00",
                "agendaItems": [
                    {
                        "uuid": valid_uuid_1,
                        "order": 1,
                        "title": "(414 SE III)",
                        "documentType": "SEADUSE_EELNOU",
                        "type": {"code": "EELNOU"},
                        "stage": "KOLMAS_LUGEMINE",
                        "decision": {"code": "VASTU_VOETUD", "value": "Vastu võetud"},
                        "relatedDraft": {
                            "uuid": draft_uuid,
                            "mark": "414 SE",
                            "title": "Liiklusseaduse muutmise seadus",
                        },
                        "votings": [{"uuid": voting_uuid}],
                    },
                    {
                        "uuid": valid_uuid_2,
                        "order": 2,
                        "title": "Arupärimine",
                        "type": {"code": "ARUPARIMINE"},
                    },
                    {
                        "uuid": "not-a-valid-uuid",
                        "title": "Vigane kirje",
                    },
                    {
                        "title": "Ilma UUID-ta kirje",
                    },
                ],
            }
        ]
    }

    verbatims_data = [
        {
            "date": "2026-10-14T14:00:00",
            "title": "Täiskogu korraline istung",
            "link": "https://stenogrammid.riigikogu.ee/202610141400",
            "agendaItems": [
                {
                    "agendaItemUuid": valid_uuid_1,
                    "title": "<b>Liiklusseaduse muutmise seaduse eelnõu (414 SE) kolmas lugemine</b>",
                },
                {
                    "agendaItemUuid": "no-agenda-match-uuid-9999",
                    "title": "Infotund",
                },
            ],
        }
    ]

    records = {}
    added, updated = process_agenda_and_verbatims(agenda_data, verbatims_data, records)
    assert added == 2
    assert updated == 0
    assert len(records) == 2

    # Check first item joined with verbatim
    r1 = records[valid_uuid_1]
    assert r1["agenda_item_uuid"] == valid_uuid_1
    assert r1["sitting_date"] == "2026-10-14"
    assert r1["source_file"] == "2026-10-14_1400.api"
    assert r1["steno_title"] == "Liiklusseaduse muutmise seaduse eelnõu (414 SE) kolmas lugemine"
    assert r1["stage"] == "KOLMAS_LUGEMINE"
    assert r1["decision_value"] == "Vastu võetud"
    assert r1["draft_uuid"] == draft_uuid
    assert r1["draft_mark"] == "414 SE"
    assert r1["draft_title"] == "Liiklusseaduse muutmise seadus"
    assert r1["voting_uuids"] == [voting_uuid]

    # Check second item has no verbatim match, falls back to source_file from sittingDateTime
    r2 = records[valid_uuid_2]
    assert r2["steno_title"] is None
    assert r2["source_file"] == "2026-10-14_1400.api"


def test_upsert_re_run_no_duplicates(tmp_path):
    """Re-running agenda processing updates existing records without creating duplicates."""
    item_uuid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    records = {
        item_uuid: {
            "agenda_item_uuid": item_uuid,
            "stage": "ESIMENE_LUGEMINE",
            "decision_value": "Pooleli",
        }
    }

    agenda_update = {
        "sittings": [
            {
                "sittingDateTime": "2026-10-14T10:00:00",
                "agendaItems": [
                    {
                        "uuid": item_uuid,
                        "stage": "TEINE_LUGEMINE",
                        "decision": {"value": "Lõpetatud"},
                    }
                ],
            }
        ]
    }

    added, updated = process_agenda_and_verbatims(agenda_update, [], records)
    assert added == 0
    assert updated == 1
    assert len(records) == 1
    assert records[item_uuid]["stage"] == "TEINE_LUGEMINE"
    assert records[item_uuid]["decision_value"] == "Lõpetatud"

    # Test file-level atomic read/write
    jsonl_file = tmp_path / "test_agenda_items.jsonl"
    write_agenda_items_atomic(jsonl_file, records)
    loaded = load_existing_agenda_items(jsonl_file)
    assert len(loaded) == 1
    assert loaded[item_uuid]["stage"] == "TEINE_LUGEMINE"


def test_load_agenda_items_missing_file_warns_only(monkeypatch):
    """Missing agenda_items.jsonl logs warning and returns 0 without failing."""
    import scripts.sync_database
    import src.load.loader

    monkeypatch.setattr(src.load.loader, "OUTPUT_DIR_PROCESSED", "/non/existent/dir")
    monkeypatch.setattr(scripts.sync_database, "OUTPUT_DIR_PROCESSED", "/non/existent/dir")

    count = load_agenda_items_to_database()
    assert count == 0


def test_load_agenda_items_upsert_in_database(tmp_path, monkeypatch):
    """Loader inserts new agenda items and updates existing ones on re-run."""
    import src.load.loader

    test_proc_dir = tmp_path / "proc"
    test_proc_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = test_proc_dir / "agenda_items.jsonl"
    monkeypatch.setattr(src.load.loader, "OUTPUT_DIR_PROCESSED", str(test_proc_dir))

    u = "55555555-5555-5555-5555-555555555555"
    d_uuid = "draft-uuid-555"
    record = {
        "agenda_item_uuid": u,
        "sitting_uuid": "sit-555",
        "sitting_date": "2026-10-10",
        "sitting_datetime": "2026-10-10T10:00:00",
        "source_file": "2026-10-10_1000.api",
        "order": 1,
        "steno_title": "Test eelnõu arutelu",
        "api_title": "(555 SE)",
        "document_type": "SEADUSE_EELNOU",
        "type_code": "EELNOU",
        "stage": "ESIMENE_LUGEMINE",
        "decision_code": "POOLELI",
        "decision_value": "Pooleli",
        "draft_uuid": d_uuid,
        "draft_mark": "555 SE",
        "draft_title": "Test eelnõu",
        "voting_uuids": ["v-555-1"],
    }
    with open(jsonl_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    try:
        added = load_agenda_items_to_database()
        assert added == 1

        session = SessionLocal()
        row = session.query(AgendaItem).filter(AgendaItem.agenda_item_uuid == u).first()
        assert row is not None
        assert row.stage == "ESIMENE_LUGEMINE"
        session.close()

        # Update record
        record["stage"] = "TEINE_LUGEMINE"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        load_agenda_items_to_database()
        session = SessionLocal()
        row = session.query(AgendaItem).filter(AgendaItem.agenda_item_uuid == u).first()
        assert row is not None
        assert row.stage == "TEINE_LUGEMINE"
        session.close()
    finally:
        clean_sess = SessionLocal()
        try:
            clean_sess.query(AgendaItem).filter(AgendaItem.agenda_item_uuid == u).delete(
                synchronize_session=False
            )
            clean_sess.commit()
        finally:
            clean_sess.close()


def test_api_draft_and_speeches_endpoints():
    """Test GET /drafts/{uuid}, GET /drafts/{uuid}/speeches, and /sessions/{date}."""
    session = SessionLocal()

    draft_uuid = "d1111111-1111-1111-1111-111111111111"
    agenda_uuid_1 = "a1111111-1111-1111-1111-111111111111"
    agenda_uuid_2 = "a2222222-2222-2222-2222-222222222222"
    voting_uuid_1 = "v1111111-1111-1111-1111-111111111111"

    try:
        # Add agenda items
        item1 = AgendaItem(
            agenda_item_uuid=agenda_uuid_1,
            sitting_date="2026-10-14",
            sitting_datetime="2026-10-14T10:00:00",
            source_file="2026-10-14_1000.api",
            order=1,
            steno_title="Eelnõu 100 SE esimene lugemine",
            api_title="(100 SE I)",
            stage="ESIMENE_LUGEMINE",
            decision_value="Lõpetatud",
            draft_uuid=draft_uuid,
            draft_mark="100 SE",
            draft_title="Maksuseaduse muutmise seadus",
            voting_uuids=json.dumps([voting_uuid_1]),
        )
        item2 = AgendaItem(
            agenda_item_uuid=agenda_uuid_2,
            sitting_date="2026-10-15",
            sitting_datetime="2026-10-15T14:00:00",
            source_file="2026-10-15_1400.api",
            order=2,
            steno_title="Eelnõu 100 SE teine lugemine",
            api_title="(100 SE II)",
            stage="TEINE_LUGEMINE",
            decision_value="Lõpetatud",
            draft_uuid=draft_uuid,
            draft_mark="100 SE",
            draft_title="Maksuseaduse muutmise seadus",
            voting_uuids="[]",
        )
        session.merge(item1)
        session.merge(item2)

        # Add voting for this draft
        v1 = Voting(
            uuid=voting_uuid_1,
            voting_number=42,
            type="AVALIK",
            description="Eelnõu 100 SE I lugemise lõpetamine",
            date="2026-10-14",
            start_time="10:30:00",
            end_time="10:31:00",
            sitting_date="2026-10-14",
            sitting_datetime="2026-10-14T10:00:00",
            membership=15,
            related_document_uuid=draft_uuid,
            related_document_reference="100 SE",
            related_document_title="Maksuseaduse muutmise seadus",
            related_document_type="SEADUSE_EELNOU",
            present=101,
            absent=0,
            in_favor=80,
            against=10,
            neutral=5,
            abstained=6,
        )
        session.merge(v1)

        # Add speeches matching item 1
        sp1 = Speech(
            id=90001,
            date="2026-10-14",
            time="10:10:00",
            start_time="10:10:00",
            source_file="2026-10-14_1000.api",
            source_url="http://example.com/s1",
            speaker="Kõneleja Üks",
            text="Esimese lugemise arutelu kõne.",
            agenda_title="Eelnõu 100 SE esimene lugemine",
        )
        sp2 = Speech(
            id=90002,
            date="2026-10-14",
            time="10:15:00",
            start_time="10:15:00",
            source_file="2026-10-14_1000.api",
            source_url="http://example.com/s2",
            speaker="Kõneleja Kaks",
            text="Teine kõne esimesel lugemisel.",
            agenda_title="Eelnõu 100 SE esimene lugemine",
        )
        # Add speech matching item 2
        sp3 = Speech(
            id=90003,
            date="2026-10-15",
            time="14:10:00",
            start_time="14:10:00",
            source_file="2026-10-15_1400.api",
            source_url="http://example.com/s3",
            speaker="Kõneleja Kolm",
            text="Teise lugemise kõne.",
            agenda_title="Eelnõu 100 SE teine lugemine",
        )
        # Add unlinked speech
        sp4 = Speech(
            id=90004,
            date="2026-10-14",
            time="09:00:00",
            start_time="09:00:00",
            source_file="2026-10-14_1000.api",
            source_url="http://example.com/s4",
            speaker="Juhataja",
            text="Istungi rakendamine.",
            agenda_title="Istungi rakendamine",
        )
        session.merge(sp1)
        session.merge(sp2)
        session.merge(sp3)
        session.merge(sp4)
        session.commit()
        session.close()

        # 1. GET /drafts/{draft_uuid}
        resp = client.get(f"/drafts/{draft_uuid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["uuid"] == draft_uuid
        assert data["mark"] == "100 SE"
        assert data["title"] == "Maksuseaduse muutmise seadus"
        assert len(data["readings"]) == 2
        assert data["readings"][0]["agenda_item_uuid"] == agenda_uuid_1
        assert data["readings"][0]["speech_count"] == 2
        assert data["readings"][0]["voting_uuids"] == [voting_uuid_1]
        assert data["readings"][1]["agenda_item_uuid"] == agenda_uuid_2
        assert data["readings"][1]["speech_count"] == 1
        assert len(data["votings"]) == 1
        assert data["votings"][0]["uuid"] == voting_uuid_1
        assert data["votings"][0]["totals"]["in_favor"] == 80

        # 2. GET /drafts/{unknown_uuid} -> 404
        resp_404 = client.get("/drafts/00000000-0000-0000-0000-000000000000")
        assert resp_404.status_code == 404
        assert resp_404.json()["detail"] == "Eelnõud ei leitud."

        # 3. GET /drafts/{draft_uuid}/speeches
        resp_sp = client.get(f"/drafts/{draft_uuid}/speeches?limit=50&offset=0")
        assert resp_sp.status_code == 200
        sp_data = resp_sp.json()
        assert sp_data["total"] == 3
        assert len(sp_data["results"]) == 3
        assert sp_data["results"][0]["id"] == 90001
        assert sp_data["results"][0]["agenda_item_uuid"] == agenda_uuid_1
        assert sp_data["results"][0]["draft_uuid"] == draft_uuid
        assert sp_data["results"][2]["id"] == 90003
        assert sp_data["results"][2]["agenda_item_uuid"] == agenda_uuid_2

        # Pagination test
        resp_page = client.get(f"/drafts/{draft_uuid}/speeches?limit=1&offset=1")
        assert resp_page.status_code == 200
        page_data = resp_page.json()
        assert page_data["total"] == 3
        assert len(page_data["results"]) == 1
        assert page_data["results"][0]["id"] == 90002

        # Filter by agenda_item_uuid
        resp_filter = client.get(f"/drafts/{draft_uuid}/speeches?agenda_item_uuid={agenda_uuid_2}")
        assert resp_filter.status_code == 200
        filter_data = resp_filter.json()
        assert filter_data["total"] == 1
        assert len(filter_data["results"]) == 1
        assert filter_data["results"][0]["id"] == 90003

        # 4. /sessions/{date} has agenda_item_uuid and draft_uuid
        resp_sess = client.get("/sessions/2026-10-14")
        assert resp_sess.status_code == 200
        sess_data = resp_sess.json()
        sess_speeches = {s["id"]: s for s in sess_data["results"]}
        assert sess_speeches[90001]["agenda_item_uuid"] == agenda_uuid_1
        assert sess_speeches[90001]["draft_uuid"] == draft_uuid
        assert sess_speeches[90004]["agenda_item_uuid"] is None
        assert sess_speeches[90004]["draft_uuid"] is None
    finally:
        clean_sess = SessionLocal()
        try:
            clean_sess.query(AgendaItem).filter(
                AgendaItem.agenda_item_uuid.in_([agenda_uuid_1, agenda_uuid_2])
            ).delete(synchronize_session=False)
            clean_sess.query(Voting).filter(Voting.uuid == voting_uuid_1).delete(
                synchronize_session=False
            )
            clean_sess.query(Speech).filter(Speech.id.in_([90001, 90002, 90003, 90004])).delete(
                synchronize_session=False
            )
            clean_sess.commit()
        finally:
            clean_sess.close()


def test_fetch_agenda_script_mocked_http(tmp_path, monkeypatch):
    """fetch_agenda_items coordinates requests, parses data, and writes JSONL."""
    test_proc_dir = tmp_path / "processed_test"
    test_proc_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("scripts.fetch_agenda.OUTPUT_DIR_PROCESSED", str(test_proc_dir))

    fake_agenda = {
        "sittings": [
            {
                "uuid": "sit-1",
                "sittingDateTime": "2026-10-14T10:00:00",
                "agendaItems": [
                    {
                        "uuid": "77777777-7777-7777-7777-777777777777",
                        "order": 1,
                        "title": "(777 SE)",
                        "stage": "ESIMENE_LUGEMINE",
                    }
                ],
            }
        ]
    }
    fake_verbatims = [
        {
            "date": "2026-10-14T10:00:00",
            "title": "Täiskogu",
            "link": "https://stenogrammid.riigikogu.ee/202610141000",
            "agendaItems": [
                {
                    "agendaItemUuid": "77777777-7777-7777-7777-777777777777",
                    "title": "777 SE arutelu",
                }
            ],
        }
    ]

    def mock_fetch(url, params, **kwargs):
        if "agenda" in url:
            return fake_agenda
        if "verbatims" in url:
            return fake_verbatims
        return None

    monkeypatch.setattr("scripts.fetch_agenda.fetch_api_with_retry", mock_fetch)

    ok = fetch_agenda_items(start_date="2026-10-14", end_date="2026-10-14", upload=False)
    assert ok is True

    jsonl_file = test_proc_dir / "agenda_items.jsonl"
    assert jsonl_file.exists()
    records = load_existing_agenda_items(jsonl_file)
    assert "77777777-7777-7777-7777-777777777777" in records
    assert records["77777777-7777-7777-7777-777777777777"]["steno_title"] == "777 SE arutelu"


def test_agenda_coverage_script():
    """compute_agenda_coverage queries yearly stats and top unlinked titles."""
    session = SessionLocal()
    sp_id = 95555
    ag_uuid = "cov-item-uuid-1"
    try:
        session.add(
            Speech(
                id=sp_id,
                date="2026-05-10",
                time="10:00:00",
                source_file="2026-05-10_1000.api",
                source_url="http://example.com/cov",
                speaker="Coverage Kõneleja",
                text="Coverage kõne sisu",
                agenda_title="Coverage Päevakorrapunkt",
            )
        )
        session.add(
            AgendaItem(
                agenda_item_uuid=ag_uuid,
                sitting_date="2026-05-10",
                source_file="2026-05-10_1000.api",
                steno_title="Coverage Päevakorrapunkt",
                draft_uuid="cov-draft-uuid",
            )
        )
        session.commit()

        data = compute_agenda_coverage(session)
        assert "yearly" in data
        assert "unlinked_titles" in data
        assert len(data["yearly"]) > 0

        # Run report formatting without error
        print_coverage_report(data)
    finally:
        session.query(AgendaItem).filter(AgendaItem.agenda_item_uuid == ag_uuid).delete(
            synchronize_session=False
        )
        session.query(Speech).filter(Speech.id == sp_id).delete(synchronize_session=False)
        session.commit()
        session.close()
