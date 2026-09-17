import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from config import OUTPUT_DIR_PROCESSED
from src.load.database import SessionLocal, engine
from src.load.models import Base, Speech


def create_tables():
    Base.metadata.create_all(bind=engine)


def load_jsonl_to_database(batch_size: int = 2000):
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL;"))
        conn.execute(text("PRAGMA synchronous=NORMAL;"))
        conn.commit()

    processed_dir = Path(OUTPUT_DIR_PROCESSED)
    session = SessionLocal()

    jsonl_files = list(processed_dir.glob("*.jsonl"))
    if not jsonl_files:
        print(f"No .jsonl files found in {OUTPUT_DIR_PROCESSED}")
        session.close()
        return

    for input_file in jsonl_files:
        print(f"Processing {input_file.name}...")
        batch = []
        with open(input_file, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)

                speech = Speech(
                    date=data["date"],
                    time=data["time"],
                    source_file=data["source_file"],
                    source_url=data["source_url"],
                    speaker=data["speaker"],
                    speaker_role=data.get("speaker_role"),
                    speaker_faction=data.get("speaker_faction"),
                    text=data["text"],
                    text_lemmas=data.get("text_lemmas"),
                )
                batch.append(speech)

                if len(batch) >= batch_size:
                    try:
                        session.bulk_save_objects(batch)
                        session.commit()
                    except IntegrityError:
                        session.rollback()
                        for item in batch:
                            try:
                                session.add(item)
                                session.commit()
                            except IntegrityError:
                                session.rollback()
                    batch.clear()

        if batch:
            try:
                session.bulk_save_objects(batch)
                session.commit()
            except IntegrityError:
                session.rollback()
                for item in batch:
                    try:
                        session.add(item)
                        session.commit()
                    except IntegrityError:
                        session.rollback()
            batch.clear()

    session.close()
    print("Done loading JSONL files to database.")
