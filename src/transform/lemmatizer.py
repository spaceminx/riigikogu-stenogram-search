from estnltk import Text

from src.load.database import SessionLocal
from src.load.models import Speech

def lemmatize_text(text):
    if not text:
        return ""

    est_text = Text(text)
    est_text.tag_layer()

    lemmas = []

    for word in est_text.words:
        lemma = word.lemma[0]
        if lemma and lemma.isalpha():
            lemmas.append(lemma.lower())

    return " ".join(lemmas)


def build_missing_lemmas(batch_size=500):
    session = SessionLocal()

    speeches = (
        session.query(Speech)
        .filter(
            (Speech.text_lemmas.is_(None)) |
            (Speech.text_lemmas == "")
        )
        .yield_per(batch_size)
    )

    count = 0

    for speech in speeches:
        try:
            speech.text_lemmas = lemmatize_text(speech.text)

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