"""Tests for /sitemap.xml and related SEO backend endpoints."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routes import _SITEMAP_CACHE
from src.load.database import SessionLocal
from src.load.loader import create_tables
from src.load.models import AgendaItem, Person, Speech, SystemMeta, Voting

client = TestClient(app)


def test_sitemap_xml_endpoint():
    """Verify sitemap.xml returns valid XML, contains required routes, and excludes speeches."""
    create_tables()
    session = SessionLocal()
    try:
        # Seed test entities if not already existing
        person = session.query(Person).first()
        if not person:
            person = Person(
                uuid="test-person-123",
                first_name="Jüri",
                last_name="Tamm",
                full_name="Jüri Tamm",
            )
            session.add(person)

        speech = session.query(Speech).first()
        if not speech:
            speech = Speech(
                external_id=99999,
                speaker="Jüri Tamm",
                date="2024-03-15",
                time="10:00:00",
                source_url="https://example.com/test",
                text="Tere päevast",
                source_file="test.json",
            )
            session.add(speech)

        voting = session.query(Voting).filter(Voting.in_favor > 0).first()
        if not voting:
            voting = Voting(
                uuid="test-voting-456",
                date="2024-03-15",
                description="Seaduseelnõu hääletus",
                sitting_date="2024-03-15",
                type="AVALIK",
                in_favor=55,
                against=10,
            )
            session.add(voting)

        agenda_item = session.query(AgendaItem).filter(AgendaItem.draft_uuid.isnot(None)).first()
        if not agenda_item:
            agenda_item = AgendaItem(
                agenda_item_uuid="item-uuid-1",
                draft_uuid="test-draft-789",
                sitting_date="2024-03-15",
                draft_title="Maksuseaduse muutmise seadus",
            )
            session.add(agenda_item)

        # Non-draft related document should NOT be included in sitemap
        non_draft_voting = (
            session.query(Voting)
            .filter(Voting.related_document_uuid == "non-draft-other-doc")
            .first()
        )
        if not non_draft_voting:
            non_draft_voting = Voting(
                uuid="voting-with-non-draft-doc",
                date="2024-03-15",
                description="Muu küsimuse hääletus",
                sitting_date="2024-03-15",
                type="AVALIK",
                in_favor=50,
                against=5,
                related_document_uuid="non-draft-other-doc",
                related_document_type="otherQuestionDocument",
            )
            session.add(non_draft_voting)

        # Draft voting with related_document_type = 'DRAFT' should be included
        draft_voting = (
            session.query(Voting)
            .filter(Voting.related_document_uuid == "test-draft-via-voting")
            .first()
        )
        if not draft_voting:
            draft_voting = Voting(
                uuid="voting-with-draft-doc",
                date="2024-03-15",
                description="Eelnõu hääletus",
                sitting_date="2024-03-15",
                type="AVALIK",
                in_favor=50,
                against=5,
                related_document_uuid="test-draft-via-voting",
                related_document_type="DRAFT",
            )
            session.add(draft_voting)

        session.commit()
        person_uuid = person.uuid
        speech_date = speech.date
        voting_uuid = voting.uuid
        draft_uuid = agenda_item.draft_uuid
    finally:
        session.close()

    # Clear cache to force fresh generation
    _SITEMAP_CACHE["xml"] = None
    _SITEMAP_CACHE["last_sync_at"] = object()

    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert "application/xml" in response.headers.get("content-type", "")

    content = response.text
    assert '<?xml version="1.0" encoding="UTF-8"?>' in content
    assert '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' in content

    # Check static routes
    assert "<loc>https://www.riigivaade.me/</loc>" in content
    assert "<loc>https://www.riigivaade.me/haaletused</loc>" in content
    assert "<loc>https://www.riigivaade.me/kohalolek</loc>" in content
    assert "<loc>https://www.riigivaade.me/fraktsioonid</loc>" in content
    assert "<loc>https://www.riigivaade.me/andmed</loc>" in content

    # Check dynamic routes exist
    assert f"<loc>https://www.riigivaade.me/saadik/{person_uuid}</loc>" in content
    assert f"<loc>https://www.riigivaade.me/istung/{speech_date}</loc>" in content
    assert f"<loc>https://www.riigivaade.me/eelnou/{draft_uuid}</loc>" in content
    assert "<loc>https://www.riigivaade.me/eelnou/test-draft-via-voting</loc>" in content
    assert "<loc>https://www.riigivaade.me/eelnou/non-draft-other-doc</loc>" not in content
    assert f"<loc>https://www.riigivaade.me/haaletus/{voting_uuid}</loc>" in content

    # Crucial rule: no speeches (209k) in sitemap
    assert "/kone/" not in content

    # Check caching
    second_response = client.get("/sitemap.xml")
    assert second_response.status_code == 200
    assert second_response.text == content

    # Check cache invalidation on last_sync_at update
    session = SessionLocal()
    try:
        row = session.query(SystemMeta).filter_by(key="last_sync_at").first()
        if not row:
            session.add(SystemMeta(key="last_sync_at", value="2024-03-15T12:00:00Z"))
        else:
            row.value = "2024-03-15T12:00:00Z"
        session.commit()
    finally:
        session.close()

    third_response = client.get("/sitemap.xml")
    assert third_response.status_code == 200
    assert _SITEMAP_CACHE["last_sync_at"] == "2024-03-15T12:00:00Z"
