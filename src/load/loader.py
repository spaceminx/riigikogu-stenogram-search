import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from config import OUTPUT_DIR_PROCESSED
from src.load.database import SessionLocal, engine
from src.load.models import Attendance, Base, Speech, SpeechTerm


def create_tables() -> None:
    """Create all database tables and ensure optional columns exist."""
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        # Migrate optional columns if speeches table already exists
        existing_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(speeches)"))}
        if existing_cols:
            if "agenda_title" not in existing_cols:
                conn.execute(text("ALTER TABLE speeches ADD COLUMN agenda_title TEXT;"))
            if "video_url" not in existing_cols:
                conn.execute(text("ALTER TABLE speeches ADD COLUMN video_url TEXT;"))
            if "status" not in existing_cols:
                conn.execute(text("ALTER TABLE speeches ADD COLUMN status TEXT;"))
        conn.commit()


def load_attendance_to_database(batch_size: int = 2000) -> None:
    """Load attendance voting records from attendance.jsonl into the attendance table."""
    attendance_file = Path(OUTPUT_DIR_PROCESSED) / "attendance.jsonl"
    if not attendance_file.exists():
        return

    print(f"Loading attendance records from {attendance_file.name}...")
    session = SessionLocal()

    # Query existing voting_uuid set to quickly skip records already in database
    existing_uuids = set(r[0] for r in session.query(Attendance.voting_uuid).distinct().all())

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

            v_uuid = data.get("voting_uuid")
            if v_uuid in existing_uuids:
                continue

            try:
                record = Attendance(
                    session_date=data["session_date"],
                    voting_uuid=v_uuid,
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
    print(f"Done loading attendance ({total_loaded} records added).")


def load_jsonl_to_database(batch_size: int = 2000) -> None:
    """Load processed speech JSONL files into the speeches table in SQLite database."""
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL;"))
        conn.execute(text("PRAGMA synchronous=NORMAL;"))
        conn.commit()

    processed_dir = Path(OUTPUT_DIR_PROCESSED)
    session = SessionLocal()

    existing_source_files = set(r[0] for r in session.query(Speech.source_file).distinct().all())
    unedited_db_files = set(
        r[0]
        for r in session.query(Speech.source_file)
        .filter(Speech.status == "UNEDITED")
        .distinct()
        .all()
    )

    jsonl_files = [f for f in processed_dir.glob("*.jsonl") if f.name != "attendance.jsonl"]
    if not jsonl_files:
        print(f"No speech .jsonl files found in {OUTPUT_DIR_PROCESSED}")
    else:
        for input_file in sorted(jsonl_files):
            print(f"Processing {input_file.name}...")
            speeches_by_session: dict[str, list[Speech]] = {}
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

                    src_file = data.get("source_file", f"{input_file.name}:{line_num}")
                    rec_status = data.get("status", "EDITED")
                    if src_file in existing_source_files and not (
                        src_file in unedited_db_files and rec_status == "EDITED"
                    ):
                        continue

                    if src_file not in speeches_by_session:
                        speeches_by_session[src_file] = []

                    try:
                        speech = Speech(
                            date=data["date"],
                            time=data["time"],
                            source_file=src_file,
                            source_url=data.get("source_url"),
                            agenda_title=data.get("agenda_title"),
                            video_url=data.get("video_url"),
                            speaker=data.get("speaker", "Tundmatu"),
                            speaker_role=data.get("speaker_role"),
                            speaker_faction=data.get("speaker_faction"),
                            text=data["text"],
                            text_lemmas=data.get("text_lemmas"),
                            status=rec_status,
                        )
                        speeches_by_session[src_file].append(speech)
                    except KeyError as e:
                        print(
                            f"Warning: Missing required field {e} on line {line_num} in {input_file.name}. Skipping."
                        )
                        continue

            for src_file, speeches_list in speeches_by_session.items():
                try:
                    if src_file in unedited_db_files:
                        old_ids = [
                            r[0]
                            for r in session.query(Speech.id)
                            .filter(Speech.source_file == src_file)
                            .all()
                        ]
                        if old_ids:
                            session.query(SpeechTerm).filter(
                                SpeechTerm.speech_id.in_(old_ids)
                            ).delete(synchronize_session=False)
                            session.query(Speech).filter(Speech.source_file == src_file).delete(
                                synchronize_session=False
                            )
                    session.bulk_save_objects(speeches_list)
                    session.commit()
                    existing_source_files.add(src_file)
                    unedited_db_files.discard(src_file)
                except Exception as e:
                    session.rollback()
                    print(f"Notice: Error loading session {src_file}: {e}")

        print("Done loading speech JSONL files to database.")

    session.close()

    # Also load attendance records if attendance.jsonl is present
    load_attendance_to_database(batch_size=batch_size)
