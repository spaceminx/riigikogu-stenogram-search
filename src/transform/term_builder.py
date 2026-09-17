from collections import Counter

from sqlalchemy import text
from tqdm import tqdm

from src.load.database import SessionLocal, engine
from src.load.models import Lemma, Speech, SpeechTerm


def get_or_create_lemma(session, lemma_text):
    lemma_obj = session.query(Lemma).filter(Lemma.lemma == lemma_text).first()

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
        lemma_obj = get_or_create_lemma(session=session, lemma_text=lemma_text)

        term = SpeechTerm(
            speech_id=speech_id,
            lemma_id=lemma_obj.id,
            count=lemma_count,
        )

        session.add(term)


def build_missing_terms(chunk_size: int = 5000, terms_batch_size: int = 50000):
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL;"))
        conn.execute(text("PRAGMA synchronous=NORMAL;"))
        conn.commit()

    session = SessionLocal()

    try:
        print("Loading existing lemmas cache into memory...")
        lemma_rows = session.execute(text("SELECT lemma, id FROM lemmas")).all()
        lemma_map = {row[0]: row[1] for row in lemma_rows}
        print(f"Loaded {len(lemma_map)} existing lemmas.")

        print("Finding speeches without indexed terms...")
        # Speeches that have text_lemmas but no speech_terms yet
        speeches_query = (
            session.query(Speech.id, Speech.text_lemmas)
            .outerjoin(SpeechTerm, Speech.id == SpeechTerm.speech_id)
            .filter(
                SpeechTerm.id.is_(None), Speech.text_lemmas.isnot(None), Speech.text_lemmas != ""
            )
        )

        total_speeches = speeches_query.count()
        if total_speeches == 0:
            print("No speeches require term indexing.")
            return

        print(f"Indexing terms for {total_speeches} speeches...")

        all_speeches = speeches_query.all()

        # Step 1: Collect and insert all brand new lemmas in bulk
        new_lemmas = set()
        for _, text_lemmas in all_speeches:
            if not text_lemmas:
                continue
            words = text_lemmas.split()
            for w in words:
                if w not in lemma_map:
                    new_lemmas.add(w)

        if new_lemmas:
            print(f"Discovered {len(new_lemmas)} new lemmas. Inserting in bulk...")
            session.bulk_insert_mappings(Lemma, [{"lemma": lem} for lem in new_lemmas])
            session.commit()
            # Refresh lemma_map
            lemma_rows = session.execute(text("SELECT lemma, id FROM lemmas")).all()
            lemma_map = {row[0]: row[1] for row in lemma_rows}

        # Step 2: Build SpeechTerm rows in memory and bulk insert
        terms_buffer = []
        with tqdm(total=total_speeches, desc="Building speech terms", unit="speech") as pbar:
            for speech_id, text_lemmas in all_speeches:
                pbar.update(1)
                if not text_lemmas:
                    continue

                lemma_counts = Counter(text_lemmas.split())
                for lemma_word, count in lemma_counts.items():
                    lid = lemma_map.get(lemma_word)
                    if lid:
                        terms_buffer.append(
                            {"speech_id": speech_id, "lemma_id": lid, "count": count}
                        )

                if len(terms_buffer) >= terms_batch_size:
                    session.bulk_insert_mappings(SpeechTerm, terms_buffer)
                    session.commit()
                    terms_buffer.clear()

        if terms_buffer:
            session.bulk_insert_mappings(SpeechTerm, terms_buffer)
            session.commit()
            terms_buffer.clear()

        print("Term indexing complete.")

    except Exception as e:
        session.rollback()
        print(f"Error building terms: {e}")
        raise
    finally:
        session.close()
