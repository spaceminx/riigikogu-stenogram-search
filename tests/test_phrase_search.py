import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.search import parse_query_groups
from src.load.database import SessionLocal
from src.load.loader import create_tables
from src.load.models import Lemma, Speech, SpeechTerm
from src.transform.lemmatizer import lemmatize_text

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_phrase_test_data():
    create_tables()
    session = SessionLocal()

    # Clear speeches and terms for clean isolation
    session.query(SpeechTerm).delete()
    session.query(Speech).delete()
    session.query(Lemma).delete()
    session.commit()

    test_speeches = [
        # id=101: adjacent phrase "riigi eelarvest", inflected
        {
            "id": 101,
            "speech_key": "2024-02-01_1000_01",
            "date": "2024-02-01",
            "time": "1000",
            "speaker": "Kaja Kallas",
            "speaker_uuid": "speaker-kaja",
            "speaker_faction": "Reformierakonna fraktsioon",
            "text": "Me arutame täna riigi eelarvest ja majandusest.",
            "source_file": "2024-02-01_1000.api",
            "source_url": "https://stenogrammid.riigikogu.ee/et/202402011000",
        },
        # id=102: words "riigi" and "eelarve" far apart
        {
            "id": 102,
            "speech_key": "2024-02-01_1000_02",
            "date": "2024-02-01",
            "time": "1005",
            "speaker": "Martin Helme",
            "speaker_uuid": "speaker-martin",
            "speaker_faction": "EKRE fraktsioon",
            "text": "Riigi eesmärk on hoida tasakaalu. Meie suur eelarve ei luba seda.",
            "source_file": "2024-02-01_1000.api",
            "source_url": "https://stenogrammid.riigikogu.ee/et/202402011000",
        },
        # id=103: reverse order "eelarve riigi"
        {
            "id": 103,
            "speech_key": "2024-02-02_1000_01",
            "date": "2024-02-02",
            "time": "1000",
            "speaker": "Urmas Reinsalu",
            "speaker_uuid": "speaker-urmas",
            "speaker_faction": "Isamaa fraktsioon",
            "text": "Eelarve riigi jaoks on liiga koormav ja keeruline.",
            "source_file": "2024-02-02_1000.api",
        },
        # id=104: phrase "Eesti 200" adjacent
        {
            "id": 104,
            "speech_key": "2024-02-03_1000_01",
            "date": "2024-02-03",
            "time": "1000",
            "speaker": "Marek Reinaas",
            "speaker_uuid": "speaker-marek",
            "speaker_faction": "Eesti 200 fraktsioon",
            "text": "Erakond Eesti 200 seisab vajalike reformide eest.",
            "source_file": "2024-02-03_1000.api",
        },
        # id=105: "Eesti ... 200 miljonit" far apart
        {
            "id": 105,
            "speech_key": "2024-02-04_1000_01",
            "date": "2024-02-04",
            "time": "1000",
            "speaker": "Jürgen Ligi",
            "speaker_uuid": "speaker-jurgen",
            "speaker_faction": "Reformierakonna fraktsioon",
            "text": "Eesti saab varsti umbes 200 miljonit eurot investeeringuteks.",
            "source_file": "2024-02-04_1000.api",
        },
        # id=106: phrase "Rail Baltic"
        {
            "id": 106,
            "speech_key": "2024-02-05_1000_01",
            "date": "2024-02-05",
            "time": "1000",
            "speaker": "Kristen Michal",
            "speaker_uuid": "speaker-kristen",
            "speaker_faction": "Reformierakonna fraktsioon",
            "text": "Me ehitame Rail Baltic trassi kiiresti valmis.",
            "source_file": "2024-02-05_1000.api",
        },
        # id=107: phrase "riigi eelarvest" PLUS separate word "kärped"
        {
            "id": 107,
            "speech_key": "2024-02-06_1000_01",
            "date": "2024-02-06",
            "time": "1000",
            "speaker": "Mart Helme",
            "speaker_uuid": "speaker-mart",
            "speaker_faction": "EKRE fraktsioon",
            "text": "Riigi eelarvest tuleb rääkida, sest vajalikud on suured kärped kuludes.",
            "source_file": "2024-02-06_1000.api",
        },
        # id=108: phrase with comma "Hea juhataja, austatud kolleegid!"
        {
            "id": 108,
            "speech_key": "2024-02-07_1000_01",
            "date": "2024-02-07",
            "time": "1000",
            "speaker": "Lauri Hussar",
            "speaker_uuid": "speaker-lauri",
            "speaker_faction": "Eesti 200 fraktsioon",
            "text": "Hea juhataja, austatud kolleegid! Alustame tänast istungit.",
            "source_file": "2024-02-07_1000.api",
        },
    ]

    lemma_cache: dict[str, int] = {}

    for sp in test_speeches:
        lemmatized = lemmatize_text(sp["text"])
        speech_obj = Speech(
            id=sp["id"],
            speech_key=sp["speech_key"],
            date=sp["date"],
            time=sp["time"],
            speaker=sp["speaker"],
            speaker_uuid=sp["speaker_uuid"],
            speaker_faction=sp["speaker_faction"],
            text=sp["text"],
            text_lemmas=lemmatized,
            source_file=sp["source_file"],
            source_url=sp.get("source_url", "https://stenogrammid.riigikogu.ee/et/202402011000"),
            speech_type="SPEECH",
        )
        session.add(speech_obj)
        session.flush()

        # Build Lemma and SpeechTerm rows
        words = lemmatized.split() if lemmatized else []
        from collections import Counter

        counts = Counter(words)
        for w, cnt in counts.items():
            if w not in lemma_cache:
                lem_row = session.query(Lemma).filter_by(lemma=w).first()
                if not lem_row:
                    lem_row = Lemma(lemma=w)
                    session.add(lem_row)
                    session.flush()
                lemma_cache[w] = lem_row.id
            term_row = SpeechTerm(
                speech_id=speech_obj.id,
                lemma_id=lemma_cache[w],
                count=cnt,
            )
            session.add(term_row)

    session.commit()
    session.close()


def test_phrase_riigi_eelarve_adjacency():
    # "riigi eelarve" matches 101 and 107, but NOT 102 (far apart) or 103 (reversed)
    resp = client.get('/search?q="riigi eelarve"')
    assert resp.status_code == 200
    data = resp.json()
    ids = {r["id"] for r in data["results"]}
    assert ids == {101, 107}
    assert data["total_count"] == 2


def test_phrase_eesti_200_does_not_match_separated():
    # "Eesti 200" matches 104, does NOT match 105 ("Eesti ... 200")
    resp = client.get('/search?q="Eesti 200"')
    assert resp.status_code == 200
    data = resp.json()
    ids = {r["id"] for r in data["results"]}
    assert ids == {104}
    assert 105 not in ids


def test_word_order_matters():
    # "eelarve riigi" (reversed) matches 103, does NOT match 101 or 107
    resp = client.get('/search?q="eelarve riigi"')
    assert resp.status_code == 200
    data = resp.json()
    ids = {r["id"] for r in data["results"]}
    assert ids == {103}


def test_phrase_plus_separate_and_word():
    # "riigi eelarve" kärped -> only 107 has both phrase and kärped
    resp = client.get('/search?q="riigi eelarve" kärped')
    assert resp.status_code == 200
    data = resp.json()
    ids = {r["id"] for r in data["results"]}
    assert ids == {107}


def test_two_quoted_phrases_as_or_groups():
    # "Eesti 200", "Rail Baltic" -> 104 and 106
    resp = client.get('/search?q="Eesti 200", "Rail Baltic"')
    assert resp.status_code == 200
    data = resp.json()
    ids = {r["id"] for r in data["results"]}
    assert ids == {104, 106}


def test_unquoted_returns_same_ids_as_before():
    # unquoted 'riigi eelarve' matches speeches containing both lemmas regardless of adjacency/order:
    # 101 (adjacent), 102 (far apart), 103 (reversed), 107 (adjacent + kärped)
    resp = client.get("/search?q=riigi eelarve")
    assert resp.status_code == 200
    data = resp.json()
    ids = {r["id"] for r in data["results"]}
    assert ids == {101, 102, 103, 107}
    assert data["total_count"] == 4


def test_stopword_only_phrase_raises_400():
    resp = client.get('/search?q="ja ning"')
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Fraas koosneb ainult stoppsõnadest."

    resp2 = client.get('/search?q="see on"')
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "Fraas koosneb ainult stoppsõnadest."


def test_activity_honours_phrase():
    resp = client.get('/search/activity?q="riigi eelarve"&interval=daily')
    assert resp.status_code == 200
    data = resp.json()
    activity = {item["date"]: item["count"] for item in data["activity"] if item["count"] > 0}
    # 101 is on 2024-02-01, 107 is on 2024-02-06
    # 102 (2024-02-01) is far apart so 2024-02-01 count must be 1, not 2!
    # 103 (2024-02-02) is reversed so 2024-02-02 must be 0 or omitted
    assert activity.get("2024-02-01") == 1
    assert activity.get("2024-02-06") == 1
    assert "2024-02-02" not in activity or activity.get("2024-02-02") == 0


def test_speakers_honour_phrase():
    resp = client.get('/search/speakers?q="riigi eelarve"')
    assert resp.status_code == 200
    data = resp.json()
    speakers = {item["speaker"] for item in data["speakers"]}
    # Only Kaja Kallas (101) and Mart Helme (107)
    assert speakers == {"Kaja Kallas", "Mart Helme"}
    assert "Martin Helme" not in speakers
    assert "Urmas Reinsalu" not in speakers


def test_export_honours_phrase():
    resp = client.get('/search/export?q="riigi eelarve"&format=json')
    assert resp.status_code == 200
    results = resp.json()
    ids = {r["id"] for r in results}
    assert ids == {101, 107}
    assert resp.headers["X-Total-Count"] == "2"


def test_context_honours_phrase_and_matched_words():
    # Context for 101 in session 2024-02-01_1000.api: contains 101 and 102
    resp = client.get('/speeches/101/context?q="riigi eelarve"')
    assert resp.status_code == 200
    data = resp.json()
    speeches = {s["id"]: s for s in data["speeches"]}

    # 101 matches the phrase -> matched_words contains "riigi eelarvest"
    assert 101 in speeches
    assert "riigi eelarvest" in speeches[101]["matched_words"]
    # Standalone "riigi" should not be in matched_words
    assert "riigi" not in speeches[101]["matched_words"]

    # 102 does NOT match the phrase -> matched_words is empty
    assert 102 in speeches
    assert speeches[102]["matched_words"] == []


def test_matched_words_contains_phrase_substring_not_standalone():
    resp = client.get('/search?q="riigi eelarve"')
    assert resp.status_code == 200
    data = resp.json()
    res101 = next(r for r in data["results"] if r["id"] == 101)
    # matched_words must have "riigi eelarvest"
    assert "riigi eelarvest" in res101["matched_words"]
    # must NOT have standalone "riigi" or "eelarvest"
    assert "riigi" not in res101["matched_words"]
    assert "eelarvest" not in res101["matched_words"]


def test_phrase_search_fast_path_instr_matches_regex_fallback():
    from sqlalchemy import func

    from src.api.search import QueryPhrase, build_phrase_filter_clause, parse_query_groups

    session = SessionLocal()
    try:
        phrases_to_test = [
            '"riigi eelarve"',
            '"Eesti 200"',
            '"Rail Baltic"',
            '"suured kärped"',
            '"tundmatu fraas"',
        ]
        for query_str in phrases_to_test:
            groups = parse_query_groups(query_str)
            phrase = groups[0].phrases[0]

            fast_cond = build_phrase_filter_clause(phrase, Speech.text_lemmas)
            fallback_cond = func.phrase_match(Speech.text_lemmas, phrase.pattern)

            ids_fast = {r[0] for r in session.query(Speech.id).filter(fast_cond).all()}
            ids_fallback = {r[0] for r in session.query(Speech.id).filter(fallback_cond).all()}

            assert ids_fast == ids_fallback
            if query_str != '"tundmatu fraas"':
                assert len(ids_fast) > 0

        # Also test phrase with product > 16 falls back to phrase_match
        big_phrase = QueryPhrase(
            positions=[{"a", "b"}, {"c", "d"}, {"e", "f"}, {"g", "h"}, {"i", "j"}],
            pattern="(?:^| )(a|b) (c|d) (e|f) (g|h) (i|j)(?: |$)",
        )
        clause = build_phrase_filter_clause(big_phrase, Speech.text_lemmas)
        assert "phrase_match" in str(clause)
    finally:
        session.close()


def test_phrase_with_comma_matches_across_comma():
    # "\"hea juhataja, austatud kolleegid\"" is ONE group with one phrase and matches "Hea juhataja, austatud kolleegid!"
    groups = parse_query_groups('"hea juhataja, austatud kolleegid"')
    assert len(groups) == 1
    assert len(groups[0].phrases) == 1

    resp = client.get('/search?q="hea juhataja, austatud kolleegid"')
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 1
    assert data["results"][0]["id"] == 108
    assert "Hea juhataja, austatud kolleegid" in data["results"][0]["matched_words"]
