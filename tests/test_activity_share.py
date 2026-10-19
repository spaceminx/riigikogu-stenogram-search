import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.search import clear_activity_denominator_cache, keyword_activity
from src.load.database import SessionLocal
from src.load.loader import create_tables
from src.load.models import Lemma, Speech, SpeechTerm, SystemMeta

client = TestClient(app)


@pytest.fixture(autouse=True, scope="session")
def setup_test_database():
    """Ensure database schema and test data exist in test environment."""
    create_tables()


def test_activity_share_monthly():
    """Verify share = count/total rounded to 4 decimals for a month."""
    clear_activity_denominator_cache()
    session = SessionLocal()
    lemma = Lemma(id=888001, lemma="rohepööre")
    session.merge(lemma)

    # 4 speeches in 2024-05: 2 matching "rohepööre", 2 non-matching
    s1 = Speech(
        id=888001,
        date="2024-05-10",
        time="1000",
        source_file="2024-05-10_1000.api",
        source_url="https://stenogrammid.riigikogu.ee/et/888001",
        speaker="Speaker A",
        text="Rohepööre on vajalik.",
        text_lemmas="rohepööre olema vajalik",
    )
    s2 = Speech(
        id=888002,
        date="2024-05-15",
        time="1000",
        source_file="2024-05-15_1000.api",
        source_url="https://stenogrammid.riigikogu.ee/et/888002",
        speaker="Speaker B",
        text="Teine rohepööre teema.",
        text_lemmas="teine rohepööre teema",
    )
    s3 = Speech(
        id=888003,
        date="2024-05-20",
        time="1000",
        source_file="2024-05-20_1000.api",
        source_url="https://stenogrammid.riigikogu.ee/et/888003",
        speaker="Speaker C",
        text="Muu teema eelarvest.",
        text_lemmas="muu teema eelarve",
    )
    s4 = Speech(
        id=888004,
        date="2024-05-25",
        time="1000",
        source_file="2024-05-25_1000.api",
        source_url="https://stenogrammid.riigikogu.ee/et/888004",
        speaker="Speaker D",
        text="Veel üks teema.",
        text_lemmas="veel üks teema",
    )
    st1 = SpeechTerm(speech_id=888001, lemma_id=888001, count=1)
    st2 = SpeechTerm(speech_id=888002, lemma_id=888001, count=1)

    for obj in (s1, s2, s3, s4, st1, st2):
        session.merge(obj)
    session.commit()
    session.close()

    try:
        res = client.get("/search/activity?q=rohepööre&interval=monthly")
        assert res.status_code == 200
        data = res.json()
        item = next((x for x in data["activity"] if x["month"] == "2024-05"), None)
        assert item is not None
        assert item["count"] == 2
        assert item["total"] == 4
        assert item["share"] == 0.5
    finally:
        session = SessionLocal()
        session.query(SpeechTerm).filter(SpeechTerm.speech_id.in_([888001, 888002])).delete()
        session.query(Speech).filter(Speech.id.in_([888001, 888002, 888003, 888004])).delete()
        session.query(Lemma).filter(Lemma.id == 888001).delete()
        session.commit()
        session.close()
        clear_activity_denominator_cache()


def test_activity_gap_period_total_zero_share_null():
    """Verify gap periods with 0 total speeches return total 0 and share null."""
    clear_activity_denominator_cache()
    session = SessionLocal()
    lemma = Lemma(id=888002, lemma="julgeolek")
    session.merge(lemma)

    # 1 speech in 2024-01 and 1 speech in 2024-03; 2024-02 has 0 speeches
    s1 = Speech(
        id=888011,
        date="2024-01-10",
        time="1000",
        source_file="2024-01-10_1000.api",
        source_url="https://stenogrammid.riigikogu.ee/et/888011",
        speaker="Speaker A",
        text="Julgeolek on tähtis.",
        text_lemmas="julgeolek olema tähtis",
    )
    s2 = Speech(
        id=888012,
        date="2024-03-10",
        time="1000",
        source_file="2024-03-10_1000.api",
        source_url="https://stenogrammid.riigikogu.ee/et/888012",
        speaker="Speaker B",
        text="Julgeolek ja kaitse.",
        text_lemmas="julgeolek ja kaitse",
    )
    st1 = SpeechTerm(speech_id=888011, lemma_id=888002, count=1)
    st2 = SpeechTerm(speech_id=888012, lemma_id=888002, count=1)

    for obj in (s1, s2, st1, st2):
        session.merge(obj)
    session.commit()
    session.close()

    try:
        res = client.get("/search/activity?q=julgeolek&interval=monthly")
        assert res.status_code == 200
        data = res.json()
        item_feb = next((x for x in data["activity"] if x["month"] == "2024-02"), None)
        assert item_feb is not None
        assert item_feb["count"] == 0
        assert item_feb["total"] == 0
        assert item_feb["share"] is None
    finally:
        session = SessionLocal()
        session.query(SpeechTerm).filter(SpeechTerm.speech_id.in_([888011, 888012])).delete()
        session.query(Speech).filter(Speech.id.in_([888011, 888012])).delete()
        session.query(Lemma).filter(Lemma.id == 888002).delete()
        session.commit()
        session.close()
        clear_activity_denominator_cache()


def test_activity_speaker_uuid_filter_applied_to_denominator():
    """Verify speaker_uuid filter filters both numerator and denominator."""
    clear_activity_denominator_cache()
    session = SessionLocal()
    lemma = Lemma(id=888003, lemma="haridus")
    session.merge(lemma)

    u_target = "uuid-speaker-target"
    u_other = "uuid-speaker-other"

    # Target speaker has 2 speeches: 1 matching, 1 not matching
    s1 = Speech(
        id=888021,
        date="2024-06-10",
        time="1000",
        source_file="2024-06-10_1000.api",
        source_url="https://stenogrammid.riigikogu.ee/et/888021",
        speaker="Target Speaker",
        speaker_uuid=u_target,
        text="Haridus on tulevik.",
        text_lemmas="haridus olema tulevik",
    )
    s2 = Speech(
        id=888022,
        date="2024-06-11",
        time="1000",
        source_file="2024-06-11_1000.api",
        source_url="https://stenogrammid.riigikogu.ee/et/888022",
        speaker="Target Speaker",
        speaker_uuid=u_target,
        text="Teine kõne muul teemal.",
        text_lemmas="teine kõne muu teema",
    )
    # Other speaker has 2 speeches, none matching
    s3 = Speech(
        id=888023,
        date="2024-06-12",
        time="1000",
        source_file="2024-06-12_1000.api",
        source_url="https://stenogrammid.riigikogu.ee/et/888023",
        speaker="Other Speaker",
        speaker_uuid=u_other,
        text="Kolmas kõne muul teemal.",
        text_lemmas="kolmas kõne muu teema",
    )
    s4 = Speech(
        id=888024,
        date="2024-06-13",
        time="1000",
        source_file="2024-06-13_1000.api",
        source_url="https://stenogrammid.riigikogu.ee/et/888024",
        speaker="Other Speaker",
        speaker_uuid=u_other,
        text="Neljas kõne muul teemal.",
        text_lemmas="neljas kõne muu teema",
    )
    st1 = SpeechTerm(speech_id=888021, lemma_id=888003, count=1)

    for obj in (s1, s2, s3, s4, st1):
        session.merge(obj)
    session.commit()
    session.close()

    try:
        res = client.get(f"/search/activity?q=haridus&interval=monthly&speaker_uuid={u_target}")
        assert res.status_code == 200
        data = res.json()
        item = next((x for x in data["activity"] if x["month"] == "2024-06"), None)
        assert item is not None
        assert item["count"] == 1
        assert item["total"] == 2  # Only target speaker's speeches, not 4
        assert item["share"] == 0.5
    finally:
        session = SessionLocal()
        session.query(SpeechTerm).filter(SpeechTerm.speech_id == 888021).delete()
        session.query(Speech).filter(Speech.id.in_([888021, 888022, 888023, 888024])).delete()
        session.query(Lemma).filter(Lemma.id == 888003).delete()
        session.commit()
        session.close()
        clear_activity_denominator_cache()


def test_activity_weekly_year_boundary_week_00_merged():
    """Verify week '00' across year boundary is merged identically for count and total."""
    clear_activity_denominator_cache()
    session = SessionLocal()
    lemma = Lemma(id=888004, lemma="aastavahetus")
    session.merge(lemma)

    # In 2025: Jan 1 is Wednesday (strftime('%Y-%W') is '2025-00').
    # Monday of that week is 2024-12-30.
    # 2024-12-30 is Monday (strftime('%Y-%W') is '2024-52').
    s1 = Speech(
        id=888031,
        date="2024-12-30",
        time="1000",
        source_file="2024-12-30_1000.api",
        source_url="https://stenogrammid.riigikogu.ee/et/888031",
        speaker="Speaker A",
        text="Aastavahetuse eelne kõne.",
        text_lemmas="aastavahetus eelne kõne",
    )
    s2 = Speech(
        id=888032,
        date="2025-01-01",
        time="1000",
        source_file="2025-01-01_1000.api",
        source_url="https://stenogrammid.riigikogu.ee/et/888032",
        speaker="Speaker B",
        text="Uue aasta esimene kõne aastavahetusel.",
        text_lemmas="uus aasta esimene kõne aastavahetus",
    )
    s3 = Speech(
        id=888033,
        date="2025-01-01",
        time="1100",
        source_file="2025-01-01_1100.api",
        source_url="https://stenogrammid.riigikogu.ee/et/888033",
        speaker="Speaker C",
        text="Uue aasta muu teema.",
        text_lemmas="uus aasta muu teema",
    )
    st1 = SpeechTerm(speech_id=888031, lemma_id=888004, count=1)
    st2 = SpeechTerm(speech_id=888032, lemma_id=888004, count=1)

    for obj in (s1, s2, s3, st1, st2):
        session.merge(obj)
    session.commit()
    session.close()

    try:
        res = client.get("/search/activity?q=aastavahetus&interval=weekly")
        assert res.status_code == 200
        data = res.json()
        item = next((x for x in data["activity"] if x.get("week_start") == "2024-12-30"), None)
        assert item is not None
        # 2 matching speeches (s1 and s2)
        assert item["count"] == 2
        # 3 total speeches (s1, s2, and s3)
        assert item["total"] == 3
        assert item["share"] == round(2 / 3, 4)
    finally:
        session = SessionLocal()
        session.query(SpeechTerm).filter(SpeechTerm.speech_id.in_([888031, 888032])).delete()
        session.query(Speech).filter(Speech.id.in_([888031, 888032, 888033])).delete()
        session.query(Lemma).filter(Lemma.id == 888004).delete()
        session.commit()
        session.close()
        clear_activity_denominator_cache()


def test_activity_denominator_cache_invalidates_on_last_sync_at():
    """Verify denominator cache is invalidated when system_meta last_sync_at changes."""
    clear_activity_denominator_cache()
    session = SessionLocal()
    lemma = Lemma(id=888005, lemma="vahemälu")
    session.merge(lemma)

    meta = SystemMeta(key="last_sync_at", value="2026-10-19 10:00:00")
    session.merge(meta)

    s1 = Speech(
        id=888041,
        date="2024-08-10",
        time="1000",
        source_file="2024-08-10_1000.api",
        source_url="https://stenogrammid.riigikogu.ee/et/888041",
        speaker="Speaker A",
        text="Vahemälu testkõne 1.",
        text_lemmas="vahemälu testkõne 1",
    )
    st1 = SpeechTerm(speech_id=888041, lemma_id=888005, count=1)
    session.merge(s1)
    session.merge(st1)
    session.commit()
    session.close()

    try:
        # First call: cached with total = 1
        res1 = keyword_activity("vahemälu", interval="monthly")
        item1 = next((x for x in res1 if x["month"] == "2024-08"), None)
        assert item1 is not None
        assert item1["total"] == 1

        # Add a 2nd speech in the same month without changing last_sync_at
        session = SessionLocal()
        s2 = Speech(
            id=888042,
            date="2024-08-15",
            time="1000",
            source_file="2024-08-15_1000.api",
            source_url="https://stenogrammid.riigikogu.ee/et/888042",
            speaker="Speaker B",
            text="Teine kõne.",
            text_lemmas="teine kõne",
        )
        session.merge(s2)
        session.commit()
        session.close()

        # Cache still active: total is still 1
        res2 = keyword_activity("vahemälu", interval="monthly")
        item2 = next((x for x in res2 if x["month"] == "2024-08"), None)
        assert item2 is not None
        assert item2["total"] == 1

        # Now change last_sync_at
        session = SessionLocal()
        meta = session.query(SystemMeta).filter_by(key="last_sync_at").first()
        meta.value = "2026-10-19 11:00:00"
        session.commit()
        session.close()

        # Now cache must invalidate and reflect total = 2
        res3 = keyword_activity("vahemälu", interval="monthly")
        item3 = next((x for x in res3 if x["month"] == "2024-08"), None)
        assert item3 is not None
        assert item3["total"] == 2
        assert item3["count"] == 1
        assert item3["share"] == 0.5
    finally:
        session = SessionLocal()
        session.query(SpeechTerm).filter(SpeechTerm.speech_id == 888041).delete()
        session.query(Speech).filter(Speech.id.in_([888041, 888042])).delete()
        session.query(Lemma).filter(Lemma.id == 888005).delete()
        session.query(SystemMeta).filter_by(key="last_sync_at").delete()
        session.commit()
        session.close()
        clear_activity_denominator_cache()
