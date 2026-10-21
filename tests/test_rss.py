import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.load.database import SessionLocal
from src.load.loader import create_tables
from src.load.models import Lemma, Person, Speech, SpeechTerm, SystemMeta

client = TestClient(app)


@pytest.fixture(autouse=True, scope="session")
def setup_test_database():
    """Ensure database schema and test data exist in CI environment."""
    create_tables()
    session = SessionLocal()
    try:
        # Seed test speech and lemma for search tests
        sp = Speech(
            id=9871101,
            speaker='Jüri "Testija" & Pojad',
            speaker_faction="Eesti Keskerakonna fraktsioon",
            speaker_uuid="00000000-0000-0000-0000-000000000001",
            date="2026-10-15",
            time="1430",
            start_time="2026-10-15T14:30:00",
            agenda_title="Eelarve & Rahandus arutelu <oluline>",
            text='Täna arutame riigi eelarvet ja "suuri" kärpeid & kulusid.',
            text_lemmas="täna arutama riik eelarve ja suur kärbe kulu",
            status="EDITED",
            source_file="test_rss_1.xml",
            source_url="https://api.riigikogu.ee/test/1",
        )
        session.merge(sp)
        session.flush()

        lem = session.query(Lemma).filter_by(lemma="eelarve").first()
        if not lem:
            lem = Lemma(lemma="eelarve")
            session.add(lem)
            session.flush()

        st = session.query(SpeechTerm).filter_by(speech_id=sp.id, lemma_id=lem.id).first()
        if not st:
            st = SpeechTerm(speech_id=sp.id, lemma_id=lem.id, count=1)
            session.add(st)

        session.commit()
    finally:
        session.close()


def test_rss_search_xml_structure_and_escaping():
    """Verify RSS search XML parses, required elements exist, and special chars are escaped."""
    res = client.get("/rss/search?q=eelarve")
    assert res.status_code == 200
    assert "application/rss+xml" in res.headers["content-type"]
    assert "public, max-age=3600" in res.headers["cache-control"]

    root = ET.fromstring(res.text)
    assert root.tag == "rss"
    assert root.attrib.get("version") == "2.0"

    channel = root.find("channel")
    assert channel is not None
    assert "Riigivaade: otsing „eelarve“" in channel.find("title").text
    assert "https://www.riigivaade.me/otsing?q=eelarve" in channel.find("link").text
    assert channel.find("language").text == "et"
    assert channel.find("lastBuildDate") is not None

    atom_link = channel.find("{http://www.w3.org/2005/Atom}link")
    assert atom_link is not None
    assert atom_link.attrib.get("rel") == "self"
    assert "https://www.riigivaade.me/rss/search?q=eelarve" in atom_link.attrib.get("href")

    items = channel.findall("item")
    assert len(items) >= 1

    first_item = items[0]
    title = first_item.find("title").text
    link = first_item.find("link").text
    guid = first_item.find("guid").text
    pub_date = first_item.find("pubDate").text
    desc = first_item.find("description").text
    category = first_item.find("category")

    assert title is not None
    assert link.startswith("https://www.riigivaade.me/kone/")
    assert guid == link
    assert pub_date is not None
    assert "+0300" in pub_date or "+0200" in pub_date
    assert desc is not None
    if category is not None:
        assert len(category.text) > 0


def test_rss_search_filters_passed_through():
    """Verify filters (membership, faction, etc.) are passed through to links and search."""
    res = client.get("/rss/search?q=eelarve&membership=15&exclude_chair=true")
    assert res.status_code == 200
    root = ET.fromstring(res.text)
    channel = root.find("channel")

    link = channel.find("link").text
    assert "membership=15" in link
    assert "exclude_chair=true" in link

    atom_link = channel.find("{http://www.w3.org/2005/Atom}link").attrib.get("href")
    assert "membership=15" in atom_link
    assert "exclude_chair=true" in atom_link


def test_rss_search_validation_errors_plain_text():
    """Validation errors on /rss/search should return plain text, not JSON or XML."""
    # Missing q -> 422 plain text
    res_missing = client.get("/rss/search")
    assert res_missing.status_code == 422
    assert "text/plain" in res_missing.headers["content-type"]
    assert "q" in res_missing.text.lower() or "puuduv" in res_missing.text.lower()

    # Stopword-only query -> 400 plain text
    res_stopword = client.get("/rss/search?q=ja")
    assert res_stopword.status_code == 400
    assert "text/plain" in res_stopword.headers["content-type"]
    assert "stopsõnu" in res_stopword.text

    # Unknown membership -> 422 plain text
    res_mem = client.get("/rss/search?q=eelarve&membership=999")
    assert res_mem.status_code == 422
    assert "text/plain" in res_mem.headers["content-type"]
    assert "Tundmatu koosseis" in res_mem.text


def test_rss_saadik_xml_and_404():
    """Verify /rss/saadik/{uuid} produces valid RSS or 404 for unknown person."""
    session = SessionLocal()
    try:
        p_uuid = "00000000-0000-0000-0000-000000000042"
        person = Person(
            uuid=p_uuid,
            first_name="Mari",
            last_name="Maasikas",
            full_name="Mari Maasikas",
            active=1,
        )
        session.merge(person)

        sp = Speech(
            id=9871102,
            speaker="Mari Maasikas",
            speaker_uuid=p_uuid,
            speaker_faction="Isamaa fraktsioon",
            date="2026-10-18",
            time="1100",
            start_time="2026-10-18T11:00:00",
            agenda_title="Haridusküsimused",
            text="Hariduse rahastamine peab suurenema.",
            status="EDITED",
            source_file="test_rss_2.xml",
            source_url="https://api.riigikogu.ee/test/2",
        )
        session.merge(sp)
        session.commit()

        # 1. Valid person
        res = client.get(f"/rss/saadik/{p_uuid}")
        assert res.status_code == 200
        assert "application/rss+xml" in res.headers["content-type"]
        assert "public, max-age=3600" in res.headers["cache-control"]

        root = ET.fromstring(res.text)
        channel = root.find("channel")
        assert "Riigivaade: Mari Maasikas kõned" in channel.find("title").text
        assert f"https://www.riigivaade.me/saadik/{p_uuid}" == channel.find("link").text
        items = channel.findall("item")
        assert len(items) >= 1
        assert "Mari Maasikas: Haridusküsimused" in items[0].find("title").text

        # 2. Unknown person -> 404 plain text
        res_unknown = client.get("/rss/saadik/nonexistent-person-uuid")
        assert res_unknown.status_code == 404
        assert "text/plain" in res_unknown.headers["content-type"]
        assert res_unknown.text == "Saadikut ei leitud."
    finally:
        session.query(Speech).filter(Speech.id == 9871102).delete()
        session.query(Person).filter(Person.uuid == "00000000-0000-0000-0000-000000000042").delete()
        session.commit()
        session.close()


def test_rss_cache_invalidation_on_last_sync_at():
    """Verify that RSS cache invalidates when system_meta last_sync_at changes."""
    session = SessionLocal()
    try:
        now1 = datetime.now(timezone.utc).isoformat()
        meta = session.query(SystemMeta).filter_by(key="last_sync_at").first()
        if meta:
            meta.value = now1
        else:
            session.add(SystemMeta(key="last_sync_at", value=now1))
        session.commit()

        # Request 1: populate cache
        res1 = client.get("/rss/search?q=kliimamuutus")
        assert res1.status_code == 200

        # Change last_sync_at
        now2 = datetime.now(timezone.utc).isoformat() + "_updated"
        meta = session.query(SystemMeta).filter_by(key="last_sync_at").first()
        meta.value = now2
        session.commit()

        # Request 2: should re-query and re-cache
        res2 = client.get("/rss/search?q=kliimamuutus")
        assert res2.status_code == 200
    finally:
        session.close()
