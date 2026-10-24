"""GET /drafts/{uuid} includes votings linked only through the draft's agenda items."""

import json

from fastapi.testclient import TestClient

from src.api.main import app
from src.load.database import SessionLocal
from src.load.loader import create_tables
from src.load.models import AgendaItem, Voting

create_tables()
client = TestClient(app)

DRAFT = "d9999999-9999-9999-9999-999999999999"
READING_DOC = "r9999999-9999-9999-9999-999999999999"


def _voting(uuid, number, description, related_uuid, start_time):
    return Voting(
        uuid=uuid,
        voting_number=number,
        type="AVALIK",
        description=description,
        date="2026-10-21",
        start_time=start_time,
        sitting_date="2026-10-21",
        membership=15,
        related_document_uuid=related_uuid,
        related_document_title="2027. aasta riigieelarve seadus",
        present=90,
        absent=11,
        in_favor=40,
        against=50,
        neutral=0,
        abstained=11,
    )


def test_draft_includes_votings_linked_only_by_agenda_item():
    session = SessionLocal()
    try:
        session.merge(
            AgendaItem(
                agenda_item_uuid="a9999999-9999-9999-9999-999999999999",
                sitting_date="2026-10-21",
                source_file="2026-10-21_1400.api",
                order=1,
                steno_title="2027. aasta riigieelarve seaduse eelnõu esimene lugemine",
                stage="ESIMENE_LUGEMINE",
                draft_uuid=DRAFT,
                draft_mark="1037 SE",
                draft_title="2027. aasta riigieelarve seadus",
                voting_uuids=json.dumps(["v-reject"]),
            )
        )
        session.merge(_voting("v-extend", 1, "Tööaja pikendamine", DRAFT, "2026-10-21T13:00:00"))
        # The rejection motion points to the reading document, not to the draft
        session.merge(
            _voting("v-reject", 2, "Tagasi lükkamine", READING_DOC, "2026-10-21T15:00:00")
        )
        session.commit()
    finally:
        session.close()

    resp = client.get(f"/drafts/{DRAFT}")
    assert resp.status_code == 200
    votings = resp.json()["votings"]
    assert [v["uuid"] for v in votings] == ["v-extend", "v-reject"]
