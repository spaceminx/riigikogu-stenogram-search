import os
from concurrent.futures import ProcessPoolExecutor, as_completed

from estnltk import Text
from sqlalchemy import text
from tqdm import tqdm

from src.load.database import SessionLocal, engine
from src.load.models import Speech


def get_default_workers() -> int:
    """
    Auto-detects host CPU threads, leaving at least 2 threads free
    for system and UI responsiveness.
    """
    cpu_count = os.cpu_count() or 4
    return max(1, cpu_count - 2)


def lemmatize_text(text):
    if not text:
        return ""

    try:
        est_text = Text(text)
        est_text.tag_layer()

        lemmas = []
        for word in est_text.words:
            lemma = word.lemma[0]
            if lemma and lemma.isalpha():
                lemmas.append(lemma.lower())

        return " ".join(lemmas)
    except Exception:
        return ""


def _lemmatize_chunk(chunk):
    """
    Worker function executed in parallel processes.
    chunk is a list of (speech_id, text) tuples.
    """
    results = []
    for speech_id, raw_text in chunk:
        lemmas = lemmatize_text(raw_text)
        results.append({"id": speech_id, "text_lemmas": lemmas})
    return results


def build_missing_lemmas(
    max_workers: int = None, chunk_size: int = 50, commit_interval: int = 2000
):
    if max_workers is None or max_workers <= 0:
        max_workers = get_default_workers()

    # Optimize SQLite for rapid batch writes
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL;"))
        conn.execute(text("PRAGMA synchronous=NORMAL;"))
        conn.commit()

    session = SessionLocal()

    try:
        print("Querying speeches that require lemmatization...")
        missing_speeches = (
            session.query(Speech.id, Speech.text)
            .filter((Speech.text_lemmas.is_(None)) | (Speech.text_lemmas == ""))
            .all()
        )

        total_count = len(missing_speeches)
        if total_count == 0:
            print("No speeches need lemmatization.")
            return

        print(f"Found {total_count} speeches to lemmatize.")
        print(
            f"Launching ProcessPoolExecutor with {max_workers} worker processes (chunk size: {chunk_size})..."
        )

        data = [(row[0], row[1]) for row in missing_speeches]
        chunks = [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]

        pending_updates = []
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_lemmatize_chunk, ch) for ch in chunks]

            with tqdm(total=total_count, desc="Lemmatizing speeches", unit="speech") as pbar:
                for future in as_completed(futures):
                    chunk_results = future.result()
                    pending_updates.extend(chunk_results)
                    pbar.update(len(chunk_results))

                    if len(pending_updates) >= commit_interval:
                        session.bulk_update_mappings(Speech, pending_updates)
                        session.commit()
                        pending_updates.clear()

        if pending_updates:
            session.bulk_update_mappings(Speech, pending_updates)
            session.commit()
            pending_updates.clear()

        print(f"Successfully lemmatized and committed {total_count} speeches.")

    except Exception as e:
        session.rollback()
        print(f"Error during parallel lemmatization: {e}")
        raise
    finally:
        session.close()
