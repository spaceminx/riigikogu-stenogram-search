"""sort_by=match_count_desc: order, ties, filters and paging, and no grouping of full speech rows."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from sqlalchemy import event

from src.api.search import clear_expansion_cache, search_by_keyword
from src.load.database import SessionLocal, engine
from src.load.loader import create_tables
from src.load.models import Lemma, Speech, SpeechTerm
from src.transform.lemmatizer import lemmatize_text

WORD_A = "kaalikas"
WORD_B = "porgand"
FIRST_ID = 870_001

# (date, faction, count of WORD_A, count of WORD_B); 0 = the word is absent
ROWS = [
    ("2024-03-01", "Isamaa fraktsioon", 5, 0),
    ("2024-03-01", "Isamaa fraktsioon", 5, 0),  # same count and date as above: id decides
    ("2024-03-02", "Eesti 200 fraktsioon", 5, 0),  # same count, later date: comes first
    ("2024-02-10", "Isamaa fraktsioon", 2, 3),
    ("2024-01-05", "Eesti 200 fraktsioon", 1, 0),
    ("2024-01-06", "Eesti 200 fraktsioon", 0, 7),
    ("2023-12-24", "Isamaa fraktsioon", 9, 1),
    ("2023-11-11", "Eesti 200 fraktsioon", 1, 1),
    ("2023-10-10", "Isamaa fraktsioon", 0, 0),  # matches neither word
    ("2023-09-09", "Eesti 200 fraktsioon", 3, 0),
]


@pytest.fixture(scope="module")
def seeded():
    create_tables()
    clear_expansion_cache()
    lemma_a = lemmatize_text(WORD_A)
    lemma_b = lemmatize_text(WORD_B)
    session = SessionLocal()
    try:
        lemma_ids = {}
        for lemma in (lemma_a, lemma_b):
            row = session.query(Lemma).filter_by(lemma=lemma).first()
            if row is None:
                row = Lemma(lemma=lemma)
                session.add(row)
                session.flush()
            lemma_ids[lemma] = row.id
        for i, (date, faction, count_a, count_b) in enumerate(ROWS):
            sid = FIRST_ID + i
            words = " ".join([WORD_A] * count_a + [WORD_B] * count_b) or "muu jutt"
            session.add(
                Speech(
                    id=sid,
                    date=date,
                    time="10:00",
                    source_file=f"{date}_1000.api",
                    source_url="https://stenogrammid.riigikogu.ee/et/x",
                    speaker=f"Kõneleja {i}",
                    speaker_faction=faction,
                    text=words,
                    text_lemmas=words,
                )
            )
            for lemma, count in ((lemma_a, count_a), (lemma_b, count_b)):
                if count:
                    session.add(SpeechTerm(speech_id=sid, lemma_id=lemma_ids[lemma], count=count))
        session.commit()
        yield
    finally:
        ids = [FIRST_ID + i for i in range(len(ROWS))]
        session.query(SpeechTerm).filter(SpeechTerm.speech_id.in_(ids)).delete()
        session.query(Speech).filter(Speech.id.in_(ids)).delete()
        session.commit()
        session.close()
        clear_expansion_cache()


def expected(match, score=lambda a, b: a + b, faction=None):
    """Ids and summed counts in the order the frequency sort must return them:
    higher count first, then the later date, then the higher id."""
    out = []
    for i, (date, row_faction, count_a, count_b) in enumerate(ROWS):
        if faction and row_faction != faction:
            continue
        if match(count_a, count_b):
            out.append((FIRST_ID + i, date, score(count_a, count_b)))
    out.sort(key=lambda r: (r[2], r[1], r[0]), reverse=True)
    return [(sid, count) for sid, _, count in out]


def run(query, **kwargs):
    results, total = search_by_keyword(
        query, sort_by="match_count_desc", expand=False, include_matched_words=False, **kwargs
    )
    return [(r["id"], r["count"]) for r in results], total


def test_single_word_order_and_ties(seeded):
    got, total = run(WORD_A, limit=50)
    # Only WORD_A's count is summed when WORD_B is not searched for
    want = expected(lambda a, b: a > 0, score=lambda a, b: a)
    assert got == want
    assert total == len(want)


def test_either_word_sums_both_counts(seeded):
    got, total = run(f"{WORD_A}, {WORD_B}", limit=50)
    assert got == expected(lambda a, b: a > 0 or b > 0)
    assert total == len(got)


def test_both_words_required(seeded):
    got, _ = run(f"{WORD_A} {WORD_B}", limit=50)
    assert got == expected(lambda a, b: a > 0 and b > 0)


def test_filter_and_paging(seeded):
    want = expected(lambda a, b: a > 0 or b > 0, faction="Eesti 200 fraktsioon")
    page1, total = run(f"{WORD_A}, {WORD_B}", limit=2, offset=0, faction="Eesti 200 fraktsioon")
    page2, _ = run(f"{WORD_A}, {WORD_B}", limit=2, offset=2, faction="Eesti 200 fraktsioon")
    assert page1 + page2 == want[:4]
    assert total == len(want)


def test_does_not_group_full_speech_rows(seeded):
    statements = []

    def capture(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        run(f"{WORD_A}, {WORD_B}", limit=3)
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    grouped = [s for s in statements if "GROUP BY" in s.upper()]
    assert grouped, "the counts query was not captured"
    for statement in grouped:
        assert "speeches.text" not in statement
