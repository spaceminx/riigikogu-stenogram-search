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
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError as e:
                    print(
                        f"Warning: Corrupted JSON on line {line_num} in {input_file.name}: {e}. Skipping."
                    )
                    continue

                try:
                    speech = Speech(
                        date=data["date"],
                        time=data["time"],
                        source_file=data.get("source_file", f"{input_file.name}:{line_num}"),
                        source_url=data.get("source_url"),
                        speaker=data.get("speaker", "Tundmatu"),
                        speaker_role=data.get("speaker_role"),
                        speaker_faction=data.get("speaker_faction"),
                        text=data["text"],
                        text_lemmas=data.get("text_lemmas"),
                    )
                    batch.append(speech)
                except KeyError as e:
                    print(
                        f"Warning: Missing required field {e} on line {line_num} in {input_file.name}. Skipping."
                    )
                    continue

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
