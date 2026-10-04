import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from config import OUTPUT_DIR_PROCESSED
from src.load.database import SessionLocal, engine
from src.load.models import Attendance, Base, Speech


def create_tables() -> None:
    """Create all database tables defined in SQLAlchemy ORM models."""
    Base.metadata.create_all(bind=engine)


def load_attendance_to_database(batch_size: int = 2000) -> None:
    """Load attendance voting records from attendance.jsonl into the attendance table."""
    attendance_file = Path(OUTPUT_DIR_PROCESSED) / "attendance.jsonl"
    if not attendance_file.exists():
        return

    print(f"Loading attendance records from {attendance_file.name}...")
    session = SessionLocal()
    batch = []
    total_loaded = 0

    with open(attendance_file, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                print(
                    f"Warning: Corrupted JSON on line {line_num} in attendance.jsonl: {e}. Skipping."
                )
                continue

            try:
                record = Attendance(
                    session_date=data["session_date"],
                    voting_uuid=data["voting_uuid"],
                    member_name=data["member_name"],
                    faction=data.get("faction", ""),
                    status=data.get("status", ""),
                )
                batch.append(record)
            except KeyError as e:
                print(
                    f"Warning: Missing required field {e} on line {line_num} in attendance.jsonl. Skipping."
                )
                continue

            if len(batch) >= batch_size:
                try:
                    session.bulk_save_objects(batch)
                    session.commit()
                    total_loaded += len(batch)
                except IntegrityError:
                    session.rollback()
                    for item in batch:
                        try:
                            session.add(item)
                            session.commit()
                            total_loaded += 1
                        except IntegrityError:
                            session.rollback()
                batch.clear()

        if batch:
            try:
                session.bulk_save_objects(batch)
                session.commit()
                total_loaded += len(batch)
            except IntegrityError:
                session.rollback()
                for item in batch:
                    try:
                        session.add(item)
                        session.commit()
                        total_loaded += 1
                    except IntegrityError:
                        session.rollback()
            batch.clear()

    session.close()
    print(f"Done loading attendance ({total_loaded} records processed).")


def load_jsonl_to_database(batch_size: int = 2000) -> None:
    """Load processed speech JSONL files into the speeches table in SQLite database."""
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL;"))
        conn.execute(text("PRAGMA synchronous=NORMAL;"))
        conn.commit()

    processed_dir = Path(OUTPUT_DIR_PROCESSED)
    session = SessionLocal()

    jsonl_files = [f for f in processed_dir.glob("*.jsonl") if f.name != "attendance.jsonl"]
    if not jsonl_files:
        print(f"No speech .jsonl files found in {OUTPUT_DIR_PROCESSED}")
    else:
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

        print("Done loading speech JSONL files to database.")

    session.close()

    # Also load attendance records if attendance.jsonl is present
    load_attendance_to_database(batch_size=batch_size)
