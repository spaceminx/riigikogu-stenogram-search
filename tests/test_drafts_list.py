"""GET /drafts, drafts without plenary readings, and loading drafts.json into the database."""

import json

import pytest
from fastapi.testclient import TestClient

import src.load.loader as loader
from src.api.drafts import clear_draft_cache, filter_drafts, status_group
from src.api.main import app
from src.load.database import SessionLocal
from src.load.loader import create_tables
from src.load.models import AgendaItem, Draft, Speech, SystemMeta, Voting

create_tables()
client = TestClient(app)

# Every test title carries this word, so drafts added by other test modules stay out
WORD = "Kaardistusseadus"
FINANCE = "c1111111-0000-0000-0000-000000000001"
CULTURE = "c1111111-0000-0000-0000-000000000002"

IN_PROCESS = "dl000001-0000-0000-0000-000000000000"
ADOPTED = "dl000002-0000-0000-0000-000000000000"
NOT_IN_PLENARY = "dl000003-0000-0000-0000-000000000000"
AGENDA_ONLY = "dl000004-0000-0000-0000-000000000000"
UUIDS = [IN_PROCESS, ADOPTED, NOT_IN_PLENARY, AGENDA_ONLY]


DRAFTS = [
    (IN_PROCESS, 919, "SE", "TEINE_LUGEMINE", "IN_PROCESS", "2026-10-20", FINANCE, "2026-05-18"),
    (ADOPTED, 12, "OE", "VASTU_VOETUD", "PROCESSED", "2026-10-28", CULTURE, "2026-03-01"),
    (
        NOT_IN_PLENARY,
        1070,
        "SE",
        "MENETLUSSE_VOETUD",
        "IN_PROCESS",
        "2026-10-01",
        FINANCE,
        "2026-09-30",
    ),
]
COMMITTEE_NAMES = {FINANCE: "Rahanduskomisjon", CULTURE: "Kultuurikomisjon"}


def _insert_drafts(session):
    for uuid, mark, type_code, stage, proceeding, status_date, committee, initiated in DRAFTS:
        session.merge(
            Draft(
                uuid=uuid,
                membership=15,
                mark=mark,
                type_code=type_code,
                title=f"{WORD} nr {mark}",
                stage=stage,
                status=stage,
                status_date=status_date,
                proceeding_status=proceeding,
                initiated=initiated,
                leading_committee_uuid=committee,
                leading_committee=COMMITTEE_NAMES[committee],
            )
        )


def _agenda(uuid, draft_uuid, day, steno_title, voting_uuids=(), mark=None):
    return AgendaItem(
        agenda_item_uuid=uuid,
        sitting_date=day,
        source_file=f"{day}_1000.api",
        order=1,
        steno_title=steno_title,
        stage="ESIMENE_LUGEMINE",
        draft_uuid=draft_uuid,
        draft_mark=mark,
        draft_title=f"{WORD} varasemast koosseisust",
        voting_uuids=json.dumps(list(voting_uuids)),
    )


def _speech(speech_id, day, agenda_title):
    return Speech(
        id=speech_id,
        date=day,
        time="10:00:00",
        source_file=f"{day}_1000.api",
        source_url="http://example.com",
        agenda_title=agenda_title,
        speaker="Kõneleja",
        text="Sisu",
    )


@pytest.fixture(scope="module", autouse=True)
def drafts_data():
    session = SessionLocal()
    try:
        _insert_drafts(session)
        session.merge(
            _agenda(
                "dl-a1",
                IN_PROCESS,
                "2026-09-16",
                "Eelnõu 919 esimene lugemine",
                ["dl-v1", "dl-not-loaded"],
            )
        )
        session.merge(
            _agenda("dl-a2", IN_PROCESS, "2026-10-21", "Eelnõu 919 teine lugemine", ["dl-v1"])
        )
        session.merge(_agenda("dl-a3", ADOPTED, "2026-10-27", "Otsuse 12 arutelu"))
        # Agenda marks are bare numbers, as in the real data
        session.merge(_agenda("dl-a4", AGENDA_ONLY, "2019-05-29", "Eelnõu 783", mark="783"))
        session.merge(
            Voting(
                uuid="dl-v1",
                date="2026-10-21",
                sitting_date="2026-10-21",
                membership=15,
                related_document_uuid=IN_PROCESS,
            )
        )
        session.merge(Voting(uuid="dl-v2", date="2026-10-28", related_document_uuid=ADOPTED))
        session.merge(_speech(95001, "2026-09-16", "Eelnõu 919 esimene lugemine"))
        session.merge(_speech(95002, "2026-09-16", "Eelnõu 919 esimene lugemine"))
        session.merge(_speech(95003, "2026-10-21", "Eelnõu 919 teine lugemine"))
        session.merge(_speech(95004, "2026-09-16", "Muu päevakorrapunkt"))
        session.commit()
    finally:
        session.close()
    clear_draft_cache()
    yield
    session = SessionLocal()
    try:
        session.query(Draft).filter(Draft.uuid.in_(UUIDS)).delete(synchronize_session=False)
        session.query(AgendaItem).filter(AgendaItem.draft_uuid.in_(UUIDS)).delete(
            synchronize_session=False
        )
        session.query(Voting).filter(Voting.uuid.in_(["dl-v1", "dl-v2"])).delete(
            synchronize_session=False
        )
        session.query(Speech).filter(Speech.id.in_([95001, 95002, 95003, 95004])).delete(
            synchronize_session=False
        )
        session.commit()
    finally:
        session.close()
    clear_draft_cache()


def _list(**params):
    resp = client.get("/drafts", params={"q": WORD, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_lists_drafts_with_their_plenary_activity_latest_first():
    data = _list()
    assert [d["uuid"] for d in data["results"]] == [
        ADOPTED,
        IN_PROCESS,
        NOT_IN_PLENARY,
        AGENDA_ONLY,
    ]

    in_process = data["results"][1]
    assert in_process["mark"] == 919
    assert in_process["type_code"] == "SE"
    assert in_process["status_group"] == "in_process"
    assert in_process["leading_committee"] == {"uuid": FINANCE, "name": "Rahanduskomisjon"}
    assert in_process["reading_count"] == 2
    # One voting listed by both readings and by the voting itself counts once; a voting that is
    # not in the database is left out
    assert in_process["voting_count"] == 1
    # Speeches of both readings; a speech under another agenda item on the same day is not counted
    assert in_process["speech_count"] == 3
    assert in_process["first_plenary_date"] == "2026-09-16"
    assert in_process["last_plenary_date"] == "2026-10-21"
    assert in_process["last_activity"] == "2026-10-21"

    not_in_plenary = data["results"][2]
    assert not_in_plenary["reading_count"] == 0
    assert not_in_plenary["speech_count"] == 0
    assert not_in_plenary["last_plenary_date"] is None


def test_a_draft_known_only_from_the_agenda_takes_its_mark_and_membership_from_the_agenda():
    data = _list(membership="14")
    assert [d["uuid"] for d in data["results"]] == [AGENDA_ONLY]
    item = data["results"][0]
    assert (item["mark"], item["type_code"], item["membership"]) == (783, None, 14)
    assert item["status_group"] is None
    assert item["title"] == f"{WORD} varasemast koosseisust"


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"status": "adopted"}, [ADOPTED]),
        ({"status": "in_process"}, [IN_PROCESS, NOT_IN_PLENARY]),
        ({"type": "OE"}, [ADOPTED]),
        ({"committee": FINANCE}, [IN_PROCESS, NOT_IN_PLENARY]),
        ({"membership": "15", "sort": "initiated"}, [NOT_IN_PLENARY, IN_PROCESS, ADOPTED]),
    ],
)
def test_filters_and_sort(params, expected):
    assert [d["uuid"] for d in _list(**params)["results"]] == expected


@pytest.mark.parametrize("q", ["919", "919 SE", "919se"])
def test_query_finds_a_draft_by_its_mark(q):
    resp = client.get("/drafts", params={"q": q, "membership": "15"})
    assert IN_PROCESS in [d["uuid"] for d in resp.json()["results"]]


@pytest.mark.parametrize("q", ["783", "783 SE"])
def test_a_typed_mark_finds_a_draft_whose_type_is_unknown(q):
    resp = client.get("/drafts", params={"q": q, "membership": "14"})
    assert AGENDA_ONLY in [d["uuid"] for d in resp.json()["results"]]


def test_a_typed_mark_skips_a_draft_of_another_type():
    resp = client.get("/drafts", params={"q": "919 OE", "membership": "15"})
    assert IN_PROCESS not in [d["uuid"] for d in resp.json()["results"]]


def test_query_words_may_come_in_any_order():
    data = client.get("/drafts", params={"q": f"1070 {WORD.lower()}"}).json()
    assert [d["uuid"] for d in data["results"]] == [NOT_IN_PLENARY]


def test_facets_count_each_filter_under_the_others():
    data = _list(status="adopted")
    assert data["total"] == 1
    # The status facet ignores the status filter itself
    assert data["facets"]["status"] == {"in_process": 2, "adopted": 1}
    assert data["facets"]["type"] == {"OE": 1}
    assert data["facets"]["committee"] == [
        {"uuid": CULTURE, "name": "Kultuurikomisjon", "count": 1}
    ]


def test_pages():
    data = _list(limit=2, offset=1)
    assert data["total"] == 4
    assert [d["uuid"] for d in data["results"]] == [IN_PROCESS, NOT_IN_PLENARY]


@pytest.mark.parametrize(
    "params",
    [{"status": "passed"}, {"type": "se"}, {"sort": "mark"}, {"membership": "99"}, {"limit": 0}],
)
def test_rejects_unknown_parameters(params):
    assert client.get("/drafts", params=params).status_code == 422


def test_the_index_is_rebuilt_after_a_sync():
    _list()
    session = SessionLocal()
    try:
        session.query(Draft).filter(Draft.uuid == ADOPTED).update({"title": f"{WORD} uus nimi"})
        session.merge(SystemMeta(key="last_sync_at", value="2026-11-02T05:04:29+00:00"))
        session.commit()
        titles = {d["uuid"]: d["title"] for d in _list()["results"]}
        assert titles[ADOPTED] == f"{WORD} uus nimi"
    finally:
        session.query(Draft).filter(Draft.uuid == ADOPTED).update({"title": f"{WORD} nr 12"})
        session.query(SystemMeta).filter(SystemMeta.key == "last_sync_at").delete()
        session.commit()
        session.close()
        clear_draft_cache()


def test_draft_page_works_for_a_draft_that_has_not_reached_the_plenary():
    resp = client.get(f"/drafts/{NOT_IN_PLENARY}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mark"] == 1070
    assert data["type_code"] == "SE"
    assert data["status_group"] == "in_process"
    assert data["leading_committee"]["name"] == "Rahanduskomisjon"
    assert data["readings"] == []
    assert data["votings"] == []

    speeches = client.get(f"/drafts/{NOT_IN_PLENARY}/speeches")
    assert speeches.status_code == 200
    assert speeches.json()["total"] == 0


def test_draft_page_prefers_the_draft_list_title_and_mark():
    data = client.get(f"/drafts/{IN_PROCESS}").json()
    assert (data["mark"], data["title"]) == (919, f"{WORD} nr 919")
    assert len(data["readings"]) == 2


@pytest.mark.parametrize("uuid", [IN_PROCESS, NOT_IN_PLENARY, AGENDA_ONLY])
def test_draft_page_summary_matches_the_list(uuid):
    listed = next(d for d in _list(limit=100)["results"] if d["uuid"] == uuid)
    detail = client.get(f"/drafts/{uuid}").json()
    fields = ["mark", "type_code", "membership", "title", "status_group", "leading_committee"]
    assert {f: detail[f] for f in fields} == {f: listed[f] for f in fields}


def test_sitemap_lists_drafts_that_have_not_reached_the_plenary():
    assert f"/eelnou/{NOT_IN_PLENARY}<" in client.get("/sitemap.xml").text


def test_status_group():
    assert status_group("IN_PROCESS", "TEINE_LUGEMINE") == "in_process"
    assert status_group("PROCESSED", "VASTU_VOETUD") == "adopted"
    assert status_group("PROCESSED", "TAGASI_VOETUD_TAISKOGUL_MENETLEMATA") == "withdrawn"
    assert status_group("PROCESSED", "VALJA_LANGENUD_KOOSEISU_LOPPEMISEGA") == "lapsed"
    assert status_group("PROCESSED", "YHENDATUD") == "other"
    assert status_group(None, None) is None


def test_filter_drafts_keeps_the_mark_order_on_equal_dates():
    items = [
        {
            "uuid": str(mark),
            "membership": 15,
            "mark": mark,
            "type_code": "SE",
            "title": "x",
            "status_group": "adopted",
            "leading_committee": None,
            "initiated": "2026-01-01",
            "last_activity": "2026-02-01",
        }
        for mark in (3, 10, 7)
    ]
    assert [i["mark"] for i in filter_drafts(items)["results"]] == [10, 7, 3]


def test_load_drafts_replaces_the_table(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "OUTPUT_DIR_PROCESSED", str(tmp_path))
    record = {
        "uuid": "dl-loaded",
        "membership": 15,
        "mark": 5,
        "type_code": "SE",
        "title": "Laaditud eelnõu",
        "stage": "VASTU_VOETUD",
        "status": "AVALDATUD_RIIGITEATAJAS",
        "status_date": "2026-01-01",
        "proceeding_status": "PROCESSED",
        "initiated": "2025-12-01",
        "leading_committee_uuid": None,
        "leading_committee": None,
    }
    (tmp_path / "drafts.json").write_text(json.dumps([record]), encoding="utf-8")

    try:
        assert loader.load_drafts_to_database() == 1
        session = SessionLocal()
        try:
            assert [d.uuid for d in session.query(Draft)] == ["dl-loaded"]
            assert session.get(Draft, "dl-loaded").status == "AVALDATUD_RIIGITEATAJAS"
        finally:
            session.close()
    finally:
        # Put back the drafts the other tests use
        session = SessionLocal()
        try:
            session.query(Draft).delete()
            _insert_drafts(session)
            session.commit()
        finally:
            session.close()
        clear_draft_cache()


def test_load_drafts_without_a_file_keeps_the_table(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "OUTPUT_DIR_PROCESSED", str(tmp_path))
    assert loader.load_drafts_to_database() == 0
    session = SessionLocal()
    try:
        assert session.get(Draft, IN_PROCESS) is not None
    finally:
        session.close()
