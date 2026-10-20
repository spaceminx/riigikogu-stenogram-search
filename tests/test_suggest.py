import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.search import _OVERVIEW_CACHE, get_dashboard_overview
from src.api.suggest import (
    _SUGGEST_CACHE,
    clear_suggest_cache,
    get_prefix_next,
)
from src.load.database import SessionLocal
from src.load.migrations import apply_migrations
from src.load.models import Lemma, Person, Speech, SpeechTerm, SystemMeta
from src.transform.term_builder import update_lemma_df

client = TestClient(app)


@pytest.fixture(autouse=True)
def init_db():
    apply_migrations()


def test_get_prefix_next():
    assert get_prefix_next("ee") == "ef"
    assert get_prefix_next("õp") == "õq"
    assert get_prefix_next("a") == "b"


def test_suggest_prefix_validation():
    # Less than 2 chars
    res = client.get("/suggest?prefix=a")
    assert res.status_code == 422
    assert "Sisesta vähemalt 2 tähemärki." in res.text

    res_empty = client.get("/suggest?prefix= ")
    assert res_empty.status_code == 422
    assert "Sisesta vähemalt 2 tähemärki." in res_empty.text

    # Greater than 40 chars
    res_long = client.get(f"/suggest?prefix={'a' * 41}")
    assert res_long.status_code == 422

    # Limit bounds
    res_limit_0 = client.get("/suggest?prefix=ee&limit=0")
    assert res_limit_0.status_code == 422

    res_limit_large = client.get("/suggest?prefix=ee&limit=25")
    assert res_limit_large.status_code == 422


def test_suggest_headers_and_cache_invalidation():
    session = SessionLocal()
    try:
        # Clear suggest cache
        clear_suggest_cache()

        meta = session.query(SystemMeta).filter_by(key="last_sync_at").first()
        if not meta:
            session.add(SystemMeta(key="last_sync_at", value="2026-10-19T00:00:00"))
        else:
            meta.value = "2026-10-19T00:00:00"
        session.commit()
    finally:
        session.close()

    res = client.get("/suggest?prefix=ee")
    assert res.status_code == 200
    assert "Cache-Control" in res.headers
    assert res.headers["Cache-Control"] == "public, max-age=3600"

    # Check cache was populated
    assert ("ee", 8) in _SUGGEST_CACHE["prefixes"]

    # Invalidate by bumping last_sync_at
    session = SessionLocal()
    try:
        meta = session.query(SystemMeta).filter_by(key="last_sync_at").first()
        meta.value = "2026-10-20T00:00:00"
        session.commit()
    finally:
        session.close()

    client.get("/suggest?prefix=ee")
    assert _SUGGEST_CACHE["last_sync_at"] == "2026-10-20T00:00:00"


def test_suggest_filtering_and_ranking():
    session = SessionLocal()
    try:
        # Create 100 speeches to test df ratio (20% threshold = 20 speeches)
        total_speeches = session.query(Speech).count()
        if total_speeches < 100:
            for i in range(total_speeches, 100):
                session.add(
                    Speech(
                        id=70000 + i,
                        speech_key=f"test-sugg-sp-{i}",
                        date="2026-01-01",
                        time="10:00",
                        speaker="Saadik",
                        text="Test kõne",
                        source_file="test_sugg.api",
                        source_url="https://stenogrammid.riigikogu.ee/et/sugg",
                    )
                )
            session.commit()

        # Add person "Helir-Valdor Seeder"
        p = session.query(Person).filter_by(uuid="test-uuid-seeder").first()
        if not p:
            session.add(
                Person(
                    uuid="test-uuid-seeder",
                    first_name="Helir-Valdor",
                    last_name="Seeder",
                    full_name="Helir-Valdor Seeder",
                    active=1,
                )
            )

        # Set up test lemmas
        lemmas_data = [
            # Person lemma: should be capitalized in term, is_person=True
            ("seeder", 15, None),
            # Regular lemma with good df
            ("seadus", 18, "S"),
            ("seaduseelnõu", 10, "S"),
            # High df > 20% of 100 speeches (e.g. df=25): should be excluded
            ("see", 25, "P"),
            # Low df < 3: should be excluded
            ("seente", 2, "S"),
            # Stopword: should be excluded
            ("sest", 12, "J"),
            # Non-letter: should be excluded
            ("123", 5, "N"),
        ]

        for item in lemmas_data:
            lemma_text = item[0]
            df_val = item[1]
            pos_val = item[2]
            lem = session.query(Lemma).filter_by(lemma=lemma_text).first()
            if not lem:
                lem = Lemma(lemma=lemma_text, df=df_val, pos=pos_val)
                session.add(lem)
            else:
                lem.df = df_val
                lem.pos = pos_val
        session.commit()
    finally:
        session.close()

    # Clear suggest cache
    clear_suggest_cache()

    # Query prefix "se"
    res = client.get("/suggest?prefix=se&limit=10")
    assert res.status_code == 200
    suggestions = res.json()

    lemmas_returned = [s["lemma"] for s in suggestions]

    # Check excluded items
    assert "see" not in lemmas_returned  # > 20%
    assert "seente" not in lemmas_returned  # df < 3
    assert "sest" not in lemmas_returned  # stopword
    assert "123" not in lemmas_returned  # no letters

    # Check included items and ordering (df desc: seadus 18, seeder 15, seaduseelnõu 10)
    assert "seadus" in lemmas_returned
    assert "seeder" in lemmas_returned
    assert "seaduseelnõu" in lemmas_returned

    assert lemmas_returned[0] == "seadus"
    assert lemmas_returned[1] == "seeder"
    assert lemmas_returned[2] == "seaduseelnõu"

    # Check person capitalization & is_person flag
    seeder_entry = next(s for s in suggestions if s["lemma"] == "seeder")
    assert seeder_entry["term"] == "Seeder"
    assert seeder_entry["is_person"] is True

    seadus_entry = next(s for s in suggestions if s["lemma"] == "seadus")
    assert seadus_entry["term"] == "seadus"
    assert seadus_entry["is_person"] is False


def test_suggest_estonian_letters():
    session = SessionLocal()
    try:
        for lemma_text, df_val, pos_val in [
            ("õpetaja", 8, "S"),
            ("õppus", 6, "S"),
            ("õhk", 5, "S"),
        ]:
            lem = session.query(Lemma).filter_by(lemma=lemma_text).first()
            if not lem:
                session.add(Lemma(lemma=lemma_text, df=df_val, pos=pos_val))
            else:
                lem.df = df_val
                lem.pos = pos_val
        session.commit()
    finally:
        session.close()

    clear_suggest_cache()
    res = client.get("/suggest?prefix=õp")
    assert res.status_code == 200
    items = res.json()
    returned = [i["lemma"] for i in items]
    assert "õpetaja" in returned
    assert "õppus" in returned
    assert "õhk" not in returned


def test_update_lemma_df():
    session = SessionLocal()
    try:
        # Create clean test lemma and speech_terms
        lem = session.query(Lemma).filter_by(lemma="katselemma").first()
        if not lem:
            lem = Lemma(lemma="katselemma", df=None)
            session.add(lem)
            session.commit()
        lem_id = lem.id

        # Insert speech terms
        for sp_id in [70001, 70002, 70003, 70004]:
            st = session.query(SpeechTerm).filter_by(speech_id=sp_id, lemma_id=lem_id).first()
            if not st:
                session.add(SpeechTerm(speech_id=sp_id, lemma_id=lem_id, count=1))
        session.commit()

        # Run update_lemma_df
        elapsed = update_lemma_df()
        assert elapsed >= 0.0

        # Check df updated
        session.refresh(lem)
        assert lem.df >= 4
    finally:
        session.close()


def test_dashboard_overview_topics_tfidf():
    session = SessionLocal()
    try:
        # Ensure last_sync_at changes to bust overview cache
        _OVERVIEW_CACHE["data"] = None

        source_file = "test_tfidf_session.api"
        # Create 30 background speeches (total_speeches >= 30)
        for i in range(80000, 80030):
            session.merge(
                Speech(
                    id=i,
                    speech_key=f"bg-speech-{i}",
                    date="2026-03-01",
                    time="10:00",
                    speaker="Saadik",
                    source_file=f"other_{i}.api",
                    source_url=f"https://stenogrammid.riigikogu.ee/et/other_{i}",
                    text="taust",
                )
            )

        # Create session speeches
        session.merge(
            Speech(
                id=80031,
                speech_key="tfidf-sp-1",
                date="2026-03-02",
                time="11:00",
                speaker="Saadik",
                source_file=source_file,
                source_url="https://stenogrammid.riigikogu.ee/et/tfidf",
                text="istung",
            )
        )

        total_count = session.query(Speech).count()
        # Lemma A: common verb, appears in ~70% of speeches
        # Lemma B: specific noun, appears in 4 speeches (df=4), 20 times in session
        # Lemma C: low df word (< 3), appears 100 times in session but df=2 -> must be ignored!

        verb_df = max(10, int(total_count * 0.7))
        lem_verb = session.query(Lemma).filter_by(lemma="rääkima").first()
        if not lem_verb:
            lem_verb = Lemma(lemma="rääkima", df=verb_df)
            session.add(lem_verb)
        else:
            lem_verb.df = verb_df

        lem_noun = session.query(Lemma).filter_by(lemma="metsandustulu").first()
        if not lem_noun:
            lem_noun = Lemma(lemma="metsandustulu", df=4)
            session.add(lem_noun)
        else:
            lem_noun.df = 4

        lem_rare = session.query(Lemma).filter_by(lemma="haruldus").first()
        if not lem_rare:
            lem_rare = Lemma(lemma="haruldus", df=2)
            session.add(lem_rare)
        else:
            lem_rare.df = 2

        session.commit()

        # Link speech_terms to speech 80031
        session.merge(SpeechTerm(speech_id=80031, lemma_id=lem_verb.id, count=50))
        session.merge(SpeechTerm(speech_id=80031, lemma_id=lem_noun.id, count=20))
        session.merge(SpeechTerm(speech_id=80031, lemma_id=lem_rare.id, count=100))
        session.commit()

        overview = get_dashboard_overview()
        target_session = next(
            (s for s in overview["sessions"] if s.get("source_url") and "tfidf" in s["source_url"]),
            None,
        )
        assert target_session is not None
        topics = target_session["topics"]

        # 'haruldus' has df=2 < 3, so it should NOT be in topics
        assert "haruldus" not in topics

        # 'metsandustulu' has tfidf score = 20 * ln(total / 4)
        # 'rääkima' has tfidf score = 50 * ln(total / 28)
        # With total ~ 130 speeches:
        # ln(130/4) = 3.48 -> 20 * 3.48 = 69.6
        # ln(130/28) = 1.53 -> 50 * 1.53 = 76.5 or with smaller total e.g. 35:
        # ln(35/4) = 2.17 -> 20 * 2.17 = 43.4
        # ln(35/28) = 0.22 -> 50 * 0.22 = 11.0
        # The specific noun should rank before the common verb!
        assert "metsandustulu" in topics
        if "rääkima" in topics:
            noun_idx = topics.index("metsandustulu")
            verb_idx = topics.index("rääkima")
            assert noun_idx < verb_idx
    finally:
        session.close()
