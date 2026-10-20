"""Tests for lemma POS filtering in suggestions and overview topics."""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.search import _OVERVIEW_CACHE, get_dashboard_overview
from src.api.suggest import clear_suggest_cache
from src.load.database import SessionLocal
from src.load.migrations import apply_migrations
from src.load.models import Lemma, Person, Speech, SpeechTerm
from src.transform.lemma_links import pick_best_pos

client = TestClient(app)


@pytest.fixture(autouse=True)
def init_db():
    apply_migrations()


# ---------------------------------------------------------------------------
# 1. POS preference order
# ---------------------------------------------------------------------------


def test_pos_preference_order():
    # Given analyses with pos=['V', 'S'], prefer 'S'
    analyses = [
        {"analysis": [{"partofspeech": "V", "lemma": "foo"}, {"partofspeech": "S", "lemma": "foo"}]}
    ]
    assert pick_best_pos(analyses, "foo") == "S"

    # Given analyses with pos=['V', 'H'], prefer 'H'
    analyses2 = [
        {"analysis": [{"partofspeech": "V", "lemma": "bar"}, {"partofspeech": "H", "lemma": "bar"}]}
    ]
    assert pick_best_pos(analyses2, "bar") == "H"

    # Lemma-match filter gives only 'V' (no S/H/A/Y matching lemma), fallback still returns 'V'
    analyses3 = [
        {
            "analysis": [
                {"partofspeech": "V", "lemma": "baz"},
                {"partofspeech": "S", "lemma": "other"},
            ]
        }
    ]
    # "baz" matches only the V analysis; S matches "other", so matching_pos = ['V'], fallback not needed
    assert pick_best_pos(analyses3, "baz") == "V"

    # Lemma-match gives 'A' and 'S', prefer 'S'
    analyses4 = [
        {
            "analysis": [
                {"partofspeech": "A", "lemma": "qux"},
                {"partofspeech": "S", "lemma": "qux"},
            ]
        }
    ]
    assert pick_best_pos(analyses4, "qux") == "S"


# ---------------------------------------------------------------------------
# 2. Suggest drops verbs and adverbs
# ---------------------------------------------------------------------------


def test_suggest_drops_verbs_and_adverbs():
    session = SessionLocal()
    try:
        # Ensure enough speeches for df ratio (use prefix "zz" to avoid collision)
        total_speeches = session.query(Speech).count()
        if total_speeches < 100:
            for i in range(total_speeches, 100):
                session.add(
                    Speech(
                        id=90000 + i,
                        speech_key=f"test-pos-sp-{i}",
                        date="2026-01-01",
                        time="10:00",
                        speaker="Saadik",
                        text="Test kõne",
                        source_file="test_pos.api",
                        source_url="https://stenogrammid.riigikogu.ee/et/pos",
                    )
                )
            session.commit()

        # Add a person so person-lemma logic works
        p = session.query(Person).filter_by(uuid="test-uuid-zorro").first()
        if not p:
            session.add(
                Person(
                    uuid="test-uuid-zorro",
                    first_name="Zorro",
                    last_name="Ztest",
                    full_name="Zorro Ztest",
                    active=1,
                )
            )
            session.commit()

        # Lemmas with unique prefix "zzz" to avoid clashing with other tests
        lemmas_data = [
            ("zzzverb", "V", 20),  # verb - should be excluded
            ("zzzdverb", "D", 15),  # adverb - should be excluded
            ("zzznull_person", None, 10),  # NULL pos, is a person lemma -> included
            ("zzznull_noperson", None, 8),  # NULL pos, not a person -> excluded
            ("zzznoun", "S", 12),  # noun - included
        ]

        for lemma_text, pos_val, df_val in lemmas_data:
            lem = session.query(Lemma).filter_by(lemma=lemma_text).first()
            if not lem:
                lem = Lemma(lemma=lemma_text, df=df_val, pos=pos_val)
                session.add(lem)
            else:
                lem.df = df_val
                lem.pos = pos_val

        # "zzznull_person" must match a person name part -> add "zorro" as a lemma linked to person
        # The person_lemmas set comes from first/last name parts. "zorro" is a first name.
        # We use "zzznull_person" which does NOT match "zorro" -> use a different approach:
        # Add Person with first_name matching the lemma text directly.
        p2 = session.query(Person).filter_by(uuid="test-uuid-zzznull").first()
        if not p2:
            session.add(
                Person(
                    uuid="test-uuid-zzznull",
                    first_name="Zzznull_person",
                    last_name="Testperson",
                    full_name="Zzznull_person Testperson",
                    active=1,
                )
            )

        session.commit()
    finally:
        session.close()

    clear_suggest_cache()

    res = client.get("/suggest?prefix=zzz&limit=20")
    assert res.status_code == 200
    suggestions = res.json()
    lemmas_returned = [s["lemma"] for s in suggestions]

    # Verb excluded
    assert "zzzverb" not in lemmas_returned
    # Adverb excluded
    assert "zzzdverb" not in lemmas_returned
    # NULL-pos with no person match excluded
    assert "zzznull_noperson" not in lemmas_returned
    # Noun included
    assert "zzznoun" in lemmas_returned
    # NULL-pos person lemma: "zzznull_person" matches person first_name "Zzznull" -> included
    assert "zzznull_person" in lemmas_returned


# ---------------------------------------------------------------------------
# 3. Dashboard topics ignore verbs
# ---------------------------------------------------------------------------


def test_dashboard_topics_ignore_verbs():
    session = SessionLocal()
    try:
        _OVERVIEW_CACHE["data"] = None

        source_file = "test_pos_topics.api"

        # Background speeches so total_speeches is large enough
        for i in range(91000, 91030):
            session.merge(
                Speech(
                    id=i,
                    speech_key=f"pos-bg-{i}",
                    date="2026-03-01",
                    time="10:00",
                    speaker="Saadik",
                    source_file=f"other_pos_{i}.api",
                    source_url=f"https://stenogrammid.riigikogu.ee/et/other_{i}",
                    text="taust",
                )
            )

        session.merge(
            Speech(
                id=91031,
                speech_key="pos-topic-sp-1",
                date="2026-03-02",
                time="11:00",
                speaker="Saadik",
                source_file=source_file,
                source_url="https://stenogrammid.riigikogu.ee/et/postopic",
                text="istung",
            )
        )

        # Verb lemma: pos='V', high count in session
        lem_verb = session.query(Lemma).filter_by(lemma="poskasvama").first()
        if not lem_verb:
            lem_verb = Lemma(lemma="poskasvama", df=5, pos="V")
            session.add(lem_verb)
        else:
            lem_verb.df = 5
            lem_verb.pos = "V"

        # Noun lemma: pos='S', should appear in topics
        lem_noun = session.query(Lemma).filter_by(lemma="posettevõte").first()
        if not lem_noun:
            lem_noun = Lemma(lemma="posettevõte", df=4, pos="S")
            session.add(lem_noun)
        else:
            lem_noun.df = 4
            lem_noun.pos = "S"

        session.commit()

        session.merge(SpeechTerm(speech_id=91031, lemma_id=lem_verb.id, count=50))
        session.merge(SpeechTerm(speech_id=91031, lemma_id=lem_noun.id, count=20))
        session.commit()

        _OVERVIEW_CACHE["data"] = None
        overview = get_dashboard_overview()

        target_session = next(
            (
                s
                for s in overview["sessions"]
                if s.get("source_url") and "postopic" in s["source_url"]
            ),
            None,
        )
        assert target_session is not None, "Test session not found in overview"
        topics = target_session["topics"]

        # Verb lemma must NOT be in topics
        assert "poskasvama" not in topics
        # Noun lemma must be in topics
        assert "posettevõte" in topics
    finally:
        session.close()
