from collections import Counter

from src.load.database import SessionLocal
from src.load.models import Speech, SpeechTerm, Lemma


def get_or_create_lemma(session, lemma_text):
    lemma_obj = (
        session.query(Lemma)
        .filter(Lemma.lemma == lemma_text)
        .first()
    )

    if lemma_obj:
        return lemma_obj

    lemma_obj = Lemma(lemma=lemma_text)
    session.add(lemma_obj)
    session.flush()

    return lemma_obj


def create_speech_terms(session, speech_id, text_lemmas):
    if not text_lemmas:
        return

    lemma_counts = Counter(text_lemmas.split())

    for lemma_text, lemma_count in lemma_counts.items():
        lemma_obj = get_or_create_lemma(
            session=session,
            lemma_text=lemma_text
        )

        term = SpeechTerm(
            speech_id=speech_id,
            lemma_id=lemma_obj.id,
            count=lemma_count,
        )

        session.add(term)


def build_missing_terms(batch_size=500):
    session = SessionLocal()

    speeches = (
        session.query(Speech)
        .outerjoin(
            SpeechTerm,
            Speech.id == SpeechTerm.speech_id
        )
        .filter(
            SpeechTerm.id.is_(None)
        )
        .yield_per(batch_size)
    )

    count = 0

    for speech in speeches:
        try:
            create_speech_terms(
                session=session,
                speech_id=speech.id,
                text_lemmas=speech.text_lemmas,
            )

            count += 1

            if count % batch_size == 0:
                session.commit()
                print(f"Committed {count} speeches")

        except Exception as e:
            session.rollback()
            print(f"ERROR: speech_id={speech.id} -> {e}")

    session.commit()
    print(f"Final commit: {count} speeches processed")
    session.close()