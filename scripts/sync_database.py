import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy.exc import IntegrityError

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import OUTPUT_DIR_PROCESSED
from scripts.download_from_b2 import download_from_b2
from src.load.database import SessionLocal
from src.load.indexes import create_indexes
from src.load.loader import create_tables, load_attendance_to_database
from src.load.models import Speech
from src.transform.lemmatizer import build_missing_lemmas
from src.transform.term_builder import build_missing_terms


def sync_current_year_speeches(year: str | None = None, batch_size: int = 2000) -> int:
    """Load new speeches from the current year's JSONL file into SQLite."""
    if not year:
        year = datetime.today().strftime("%Y")

    year_file = Path(OUTPUT_DIR_PROCESSED) / f"{year}.jsonl"
    if not year_file.exists():
        print(f"Notice: Year file {year_file.name} not found.")
        return 0

    session = SessionLocal()
    new_count = 0
    batch = []

    print(f"Checking {year_file.name} for new speeches...")
    existing_keys = set(
        session.query(Speech.source_file, Speech.speaker)
        .filter(Speech.date >= f"{year}-01-01")
        .all()
    )

    with open(year_file, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            src_file = data.get("source_file", f"{year_file.name}:{line_num}")
            spk = data.get("speaker", "Tundmatu")

            if (src_file, spk) in existing_keys:
                continue

            speech = Speech(
                date=data["date"],
                time=data["time"],
                source_file=src_file,
                source_url=data.get("source_url"),
                agenda_title=data.get("agenda_title"),
                video_url=data.get("video_url"),
                speaker=spk,
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
                    new_count += len(batch)
                except IntegrityError:
                    session.rollback()
                    for item in batch:
                        try:
                            session.add(item)
                            session.commit()
                            new_count += 1
                        except IntegrityError:
                            session.rollback()
                batch.clear()

        if batch:
            try:
                session.bulk_save_objects(batch)
                session.commit()
                new_count += len(batch)
            except IntegrityError:
                session.rollback()
                for item in batch:
                    try:
                        session.add(item)
                        session.commit()
                        new_count += 1
                    except IntegrityError:
                        session.rollback()
            batch.clear()

    session.close()
    return new_count


def sync_database() -> bool:
    """Run incremental database sync: download from B2, update SQLite, lemmatize, and index."""
    t0 = time.time()
    print("=" * 60)
    print("STARTING INCREMENTAL DATABASE SYNC")
    print("=" * 60)

    # 1. Download latest data and state from B2
    print("\n[1/5] Downloading latest files from Backblaze B2...")
    download_from_b2()

    # 2. Ensure tables and indexes exist
    print("\n[2/5] Ensuring database tables and indexes exist...")
    create_tables()
    create_indexes()

    # 3. Load current year speeches & attendance
    print("\n[3/5] Inserting new speeches and attendance records...")
    sync_current_year_speeches()
    load_attendance_to_database()

    # 4. Lemmatize any new speeches
    print("\n[4/5] Checking and lemmatizing new speeches...")
    build_missing_lemmas()

    # 5. Build term index for new speeches
    print("\n[5/5] Indexing new terms...")
    build_missing_terms()

    duration = time.time() - t0
    print("\n" + "=" * 60)
    print(f"DATABASE SYNC COMPLETE in {duration:.2f} seconds!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    sync_database()
