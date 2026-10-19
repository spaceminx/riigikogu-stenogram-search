import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.search import _EXPANSION_CACHE, clear_expansion_cache
from src.load.database import SessionLocal, engine
from src.load.loader import create_tables
from src.load.models import Lemma, LemmaLink, Person, Speech, SpeechTerm, SystemMeta
from src.transform.lemma_links import build_lemma_links

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_c1_test_data():
    create_tables()
    session = SessionLocal()

    # Clear previous test data
    session.query(LemmaLink).delete()
    session.query(SpeechTerm).delete()
    session.query(Speech).delete()
    session.query(Lemma).delete()
    session.query(Person).delete()
    session.commit()

    # Seed persons
    persons = [
        Person(
            uuid="uuid-seeder",
            first_name="Helir-Valdor",
            last_name="Seeder",
            full_name="Helir-Valdor Seeder",
        ),
        Person(
            uuid="uuid-ratas",
            first_name="Jüri",
            last_name="Ratas",
            full_name="Jüri Ratas",
        ),
        Person(
            uuid="uuid-kallas",
            first_name="Kaja",
            last_name="Kallas",
            full_name="Kaja Kallas",
        ),
    ]
    for p in persons:
        session.add(p)
    session.commit()

    # Speeches designed for C1 test cases
    test_speeches = [
        # 201: contains compound words "riigieelarve" and "lisaeelarve"
        {
            "id": 201,
            "speech_key": "2024-03-01_1000_01",
            "date": "2024-03-01",
            "time": "1000",
            "speaker": "Kaja Kallas",
            "speaker_uuid": "uuid-kallas",
            "speaker_faction": "Reformierakonna fraktsioon",
            "text": "Riigikogus võeti vastu riigieelarve ja lisaeelarve.",
            "text_lemmas": "riigikogu võtma vastu riigieelarve ja lisaeelarve",
            "source_file": "2024-03-01_1000.api",
        },
        # 202: contains compound "eelarvestrateegia" and head "strateegia"
        {
            "id": 202,
            "speech_key": "2024-03-01_1000_02",
            "date": "2024-03-01",
            "time": "1005",
            "speaker": "Kaja Kallas",
            "speaker_uuid": "uuid-kallas",
            "speaker_faction": "Reformierakonna fraktsioon",
            "text": "Eelarvestrateegia määrab pikaajalise suuna ja strateegia.",
            "text_lemmas": "eelarvestrateegia määrama pikaajaline suund ja strateegia",
            "source_file": "2024-03-01_1000.api",
        },
        # 203: contains base word "arve"
        {
            "id": 203,
            "speech_key": "2024-03-01_1000_03",
            "date": "2024-03-01",
            "time": "1010",
            "speaker": "Jüri Ratas",
            "speaker_uuid": "uuid-ratas",
            "speaker_faction": "Isamaa fraktsioon",
            "text": "See arve tuleb tasuda õigeaegselt.",
            "text_lemmas": "see arve tulema tasuma õigeaegselt",
            "source_file": "2024-03-01_1000.api",
        },
        # 204: contains inflected surname form "seederi" only
        {
            "id": 204,
            "speech_key": "2024-03-02_1000_01",
            "date": "2024-03-02",
            "time": "1000",
            "speaker": "Helir-Valdor Seeder",
            "speaker_uuid": "uuid-seeder",
            "speaker_faction": "Isamaa fraktsioon",
            "text": "Helir-Valdor Seederi ettepanek leidis toetust.",
            "text_lemmas": "helir-valdor seederi ettepanek leidma toetus",
            "source_file": "2024-03-02_1000.api",
        },
        # 205: contains person name "Ratas"
        {
            "id": 205,
            "speech_key": "2024-03-02_1000_02",
            "date": "2024-03-02",
            "time": "1005",
            "speaker": "Jüri Ratas",
            "speaker_uuid": "uuid-ratas",
            "speaker_faction": "Isamaa fraktsioon",
            "text": "Jüri Ratas tegi valitsuses otsuse.",
            "text_lemmas": "jüri ratas tegema valitsus otsus",
            "source_file": "2024-03-02_1000.api",
        },
        # 206: contains compound common noun "jalgratas"
        {
            "id": 206,
            "speech_key": "2024-03-02_1000_03",
            "date": "2024-03-02",
            "time": "1010",
            "speaker": "Kaja Kallas",
            "speaker_uuid": "uuid-kallas",
            "speaker_faction": "Reformierakonna fraktsioon",
            "text": "Tänaval sõitis jalgratas kiiresti.",
            "text_lemmas": "tänav sõitma jalgratas kiiresti",
            "source_file": "2024-03-02_1000.api",
        },
        # 207: contains "Rail Baltica" (inflected / alias form)
        {
            "id": 207,
            "speech_key": "2024-03-03_1000_01",
            "date": "2024-03-03",
            "time": "1000",
            "speaker": "Kristen Michal",
            "speaker_uuid": "uuid-michal",
            "speaker_faction": "Reformierakonna fraktsioon",
            "text": "Rail Baltica projekt edeneb plaanipäraselt.",
            "text_lemmas": "rail baltica projekt edenema plaanipäraselt",
            "source_file": "2024-03-03_1000.api",
        },
        # 208: contains plain uncompounded "eelarve"
        {
            "id": 208,
            "speech_key": "2024-03-03_1000_02",
            "date": "2024-03-03",
            "time": "1005",
            "speaker": "Kaja Kallas",
            "speaker_uuid": "uuid-kallas",
            "speaker_faction": "Reformierakonna fraktsioon",
            "text": "Valitsus arutas tavalist eelarvet.",
            "text_lemmas": "valitsus arutama tavaline eelarve",
            "source_file": "2024-03-03_1000.api",
        },
    ]

    # Pre-populate lemmas so compute_compound_heads and compute_name_forms find them
    extra_lemmas = ["eelarve", "seeder", "ratas", "baltic", "strateegia"]
    for sp in test_speeches:
        for w in sp["text_lemmas"].split():
            extra_lemmas.append(w)

    lemma_map = {}
    for word in set(extra_lemmas):
        lem_row = Lemma(lemma=word)
        session.add(lem_row)
        session.flush()
        lemma_map[word] = lem_row.id

    for sp in test_speeches:
        speech_obj = Speech(
            id=sp["id"],
            speech_key=sp["speech_key"],
            date=sp["date"],
            time=sp["time"],
            speaker=sp["speaker"],
            speaker_uuid=sp["speaker_uuid"],
            speaker_faction=sp["speaker_faction"],
            text=sp["text"],
            text_lemmas=sp["text_lemmas"],
            source_file=sp["source_file"],
            source_url="https://stenogrammid.riigikogu.ee/et/test",
            speech_type="SPEECH",
        )
        session.add(speech_obj)
        session.flush()

        from collections import Counter

        counts = Counter(sp["text_lemmas"].split())
        for w, cnt in counts.items():
            term_row = SpeechTerm(
                speech_id=speech_obj.id,
                lemma_id=lemma_map[w],
                count=cnt,
            )
            session.add(term_row)

    session.commit()
    session.close()

    # Build lemma links table
    build_lemma_links(engine=engine)
    clear_expansion_cache()


def test_build_lemma_links_populates_atomically():
    session = SessionLocal()
    try:
        links = session.query(LemmaLink).all()
        assert len(links) > 0

        # Check eelarve links
        eelarve_row = session.query(Lemma).filter_by(lemma="eelarve").first()
        riigieelarve_row = session.query(Lemma).filter_by(lemma="riigieelarve").first()
        lisaeelarve_row = session.query(Lemma).filter_by(lemma="lisaeelarve").first()

        assert eelarve_row is not None
        assert riigieelarve_row is not None
        assert lisaeelarve_row is not None

        # riigieelarve -> eelarve compound_head
        link1 = (
            session.query(LemmaLink)
            .filter_by(
                lemma_id=riigieelarve_row.id,
                target_lemma_id=eelarve_row.id,
                kind="compound_head",
            )
            .first()
        )
        assert link1 is not None

        # lisaeelarve -> eelarve compound_head
        link2 = (
            session.query(LemmaLink)
            .filter_by(
                lemma_id=lisaeelarve_row.id,
                target_lemma_id=eelarve_row.id,
                kind="compound_head",
            )
            .first()
        )
        assert link2 is not None

        # Manual alias baltic <-> baltica
        baltic_row = session.query(Lemma).filter_by(lemma="baltic").first()
        baltica_row = session.query(Lemma).filter_by(lemma="baltica").first()
        assert baltic_row is not None
        assert baltica_row is not None

        alias_link = (
            session.query(LemmaLink)
            .filter_by(
                lemma_id=baltica_row.id,
                target_lemma_id=baltic_row.id,
                kind="alias",
            )
            .first()
        )
        assert alias_link is not None
    finally:
        session.close()


def test_rollback_on_failure_preserves_old_links():
    session = SessionLocal()
    try:
        initial_count = session.query(LemmaLink).count()
        assert initial_count > 0

        # Force an error during build by monkeypatching load_manual_aliases to raise
        with (
            patch(
                "src.transform.lemma_links.load_manual_aliases",
                side_effect=RuntimeError("Simulated failure"),
            ),
            pytest.raises(RuntimeError, match="Simulated failure"),
        ):
            build_lemma_links(engine=engine)

        # Confirm old links were preserved
        after_count = session.query(LemmaLink).count()
        assert after_count == initial_count
    finally:
        session.close()


def test_stoplist_guard_and_longest_suffix():
    session = SessionLocal()
    try:
        arve_row = session.query(Lemma).filter_by(lemma="arve").first()
        eelarve_row = session.query(Lemma).filter_by(lemma="eelarve").first()
        strateegia_row = session.query(Lemma).filter_by(lemma="strateegia").first()
        eelarvestrateegia_row = session.query(Lemma).filter_by(lemma="eelarvestrateegia").first()

        # "arve" is in HEAD_STOPLIST; eelarve must NOT have target_lemma_id == arve
        bad_link = (
            session.query(LemmaLink)
            .filter_by(
                lemma_id=eelarve_row.id,
                target_lemma_id=arve_row.id,
            )
            .first()
        )
        assert bad_link is None

        # "eelarvestrateegia" links to "strateegia"
        strat_link = (
            session.query(LemmaLink)
            .filter_by(
                lemma_id=eelarvestrateegia_row.id,
                target_lemma_id=strateegia_row.id,
                kind="compound_head",
            )
            .first()
        )
        assert strat_link is not None
    finally:
        session.close()


def test_search_eelarve_expands_to_compounds():
    clear_expansion_cache()
    # Unquoted "eelarve" finds speech 201 (riigieelarve, lisaeelarve) and speech 208 (eelarve)
    resp = client.get("/search?q=eelarve")
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()["results"]}
    assert 201 in ids
    assert 208 in ids


def test_search_eelarve_exact_disabled_does_not_expand():
    clear_expansion_cache()
    # expand=false disables compound expansion
    resp = client.get("/search?q=eelarve&expand=false")
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()["results"]}
    assert 208 in ids
    assert 201 not in ids


def test_search_quoted_word_does_not_expand():
    clear_expansion_cache()
    # Quoted single word disables compound expansion
    resp = client.get('/search?q="eelarve"')
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()["results"]}
    assert 208 in ids
    assert 201 not in ids


def test_search_arve_does_not_return_eelarve():
    clear_expansion_cache()
    resp = client.get("/search?q=arve")
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()["results"]}
    assert 203 in ids
    assert 201 not in ids
    assert 208 not in ids


def test_rule_b_capitalised_name_skips_compound_head():
    clear_expansion_cache()
    # "Ratas" (capitalised and is a person name lemma):
    # Should include inflected name form "ratase" (speech 205),
    # but skip compound "jalgratas" (speech 206).
    resp = client.get("/search?q=Ratas")
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()["results"]}
    assert 205 in ids
    assert 206 not in ids


def test_rule_b_lowercase_word_keeps_compound_head():
    clear_expansion_cache()
    # "ratas" (lowercase):
    # Should include both "ratase" (name form) and "jalgratas" (compound head).
    resp = client.get("/search?q=ratas")
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()["results"]}
    assert 205 in ids
    assert 206 in ids


def test_name_form_expansion_seeder():
    clear_expansion_cache()
    # "Seeder" should find speech 204 which only contains "seederi"
    resp = client.get("/search?q=Seeder")
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()["results"]}
    assert 204 in ids


def test_phrase_alias_expansion_rail_baltic():
    clear_expansion_cache()
    # Phrase "Rail Baltic" should find speech 207 ("Rail Baltica") via alias expansion
    resp = client.get('/search?q="Rail Baltic"')
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()["results"]}
    assert 207 in ids


def test_highlighter_marks_compounds_and_context():
    clear_expansion_cache()
    resp = client.get("/search?q=eelarve")
    assert resp.status_code == 200
    results = {r["id"]: r for r in resp.json()["results"]}

    # Speech 201 matched words should contain compound words
    assert 201 in results
    matched = {w.lower() for w in results[201].get("matched_words", [])}
    assert "riigieelarve" in matched or "lisaeelarve" in matched

    # Speech context endpoint also includes matched_words
    ctx_resp = client.get("/speeches/201/context?q=eelarve")
    assert ctx_resp.status_code == 200
    ctx_data = ctx_resp.json()
    speech_201_ctx = next(s for s in ctx_data["speeches"] if s["id"] == 201)
    ctx_matched = {w.lower() for w in speech_201_ctx.get("matched_words", [])}
    assert "riigieelarve" in ctx_matched or "lisaeelarve" in ctx_matched


def test_expansion_cache_invalidation():
    clear_expansion_cache()
    assert len(_EXPANSION_CACHE["expansions"]) == 0
    assert len(_EXPANSION_CACHE["lemma_ids"]) == 0

    # Query warms up the cache
    resp = client.get("/search?q=eelarve")
    assert resp.status_code == 200
    assert len(_EXPANSION_CACHE["expansions"]) > 0
    assert "eelarve" in _EXPANSION_CACHE["lemma_ids"]

    # Update system_meta last_sync_at to simulate sync finishing
    session = SessionLocal()
    try:
        now_str = datetime.now(timezone.utc).isoformat()
        row = session.query(SystemMeta).filter_by(key="last_sync_at").first()
        if not row:
            row = SystemMeta(key="last_sync_at", value=now_str)
            session.add(row)
        else:
            row.value = now_str
        session.commit()
    finally:
        session.close()

    # Next search detects updated last_sync_at and clears cache
    resp2 = client.get("/search?q=arve")
    assert resp2.status_code == 200
    # The cache was cleared and only repopulated with new entries
    assert "eelarve" not in _EXPANSION_CACHE["lemma_ids"]
    assert "arve" in _EXPANSION_CACHE["lemma_ids"]
