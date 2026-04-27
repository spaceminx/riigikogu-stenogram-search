from sqlalchemy import func

from src.load.database import SessionLocal
from src.load.models import Speech, SpeechTerm, Lemma
from src.transform.lemmatizer import lemmatize_text


def normalized_query_to_lemma(query):
    lemmas = lemmatize_text(query).split()

    if not lemmas:
        return None

    return lemmas[0]

def search_by_keyword(query, limit = 50):
    normalized_query = normalized_query_to_lemma(query)

    if not normalized_query:
        return []

    session = SessionLocal()

    results = (
        session.query(Speech, SpeechTerm.count)
        .join(SpeechTerm, Speech.id == SpeechTerm.speech_id)
        .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
        .filter(Lemma.lemma == normalized_query)
        .order_by(Speech.date.desc())
        .limit(limit)
        .all()
    )

    output = []

    for speech, count in results:
        output.append({
            "speaker": speech.speaker,
            "text": speech.text,
            "count": count,
            "date": speech.date,
            "time": speech.time,
            "source_url": speech.source_url,
        })
    session.close()

    return output

def keyword_activity_by_date(query):
    normalized_query = normalized_query_to_lemma(query)

    if not normalized_query:
        return []

    session = SessionLocal()

    results = (
        session.query(
            Speech.date,
            func.sum(SpeechTerm.count).label("total_count")
        )
        .join(SpeechTerm, Speech.id == SpeechTerm.speech_id)
        .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
        .filter(Lemma.lemma == normalized_query)
        .group_by(Speech.date)
        .order_by(Speech.date)
        .all()
    )

    output = [
        {
            "date": date,
            "count": int(total_count)
        }
        for date, total_count in results
    ]

    session.close()
    return output

def keyword_top_speakers(query, limit = 20):
    normalized_query = normalized_query_to_lemma(query)

    if not normalized_query:
        return []

    session = SessionLocal()

    results = (
        session.query(
            Speech.speaker,
            func.sum(SpeechTerm.count).label("total_count")
        )
        .join(SpeechTerm, Speech.id == SpeechTerm.speech_id)
        .join(Lemma, SpeechTerm.lemma_id == Lemma.id)
        .filter(Lemma.lemma == normalized_query)
        .group_by(Speech.speaker)
        .order_by(func.sum(SpeechTerm.count).desc())
        .limit(limit)
        .all()
    )

    output = [
        {
            "speaker": speaker,
            "count": int(total_count)
        }
        for speaker, total_count in results
    ]

    session.close()
    return output
