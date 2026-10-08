import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import OUTPUT_DIR_PROCESSED
from scripts.download_from_b2 import download_from_b2
from src.load.database import SessionLocal
from src.load.indexes import create_indexes
from src.load.loader import create_tables, load_attendance_to_database
from src.load.models import Speech, SpeechTerm
from src.transform.lemmatizer import build_missing_lemmas
from src.transform.term_builder import build_missing_terms


def sync_current_year_speeches(year: str | None = None, batch_size: int = 2000) -> int:
    """Load new or updated speeches from JSONL files into SQLite session-by-session."""
    current_year_int = datetime.today().year
    if year:
        years_to_check = [year]
    else:
        # Check all available year JSONL files (or at least recent years)
        available_years = sorted(
            [
                p.stem
                for p in Path(OUTPUT_DIR_PROCESSED).glob("*.jsonl")
                if p.stem.isdigit() and len(p.stem) == 4
            ]
        )
        years_to_check = available_years or [str(current_year_int - 1), str(current_year_int)]

    session = SessionLocal()
    new_count = 0

    try:
        unedited_db_files = set(
            r[0]
            for r in session.query(Speech.source_file)
            .filter(Speech.status == "UNEDITED")
            .distinct()
            .all()
        )

        for yr in years_to_check:
            year_file = Path(OUTPUT_DIR_PROCESSED) / f"{yr}.jsonl"
            if not year_file.exists():
                continue

            print(f"Checking {year_file.name} for new or updated speeches...")
            existing_source_files = set(
                r[0]
                for r in session.query(Speech.source_file)
                .filter(Speech.date >= f"{yr}-01-01")
                .distinct()
                .all()
            )

            speeches_by_session: dict[str, list[Speech]] = {}

            with open(year_file, encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    src_file = data.get("source_file", f"{year_file.name}:{line_num}")
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
                            f"Warning: Missing required field {e} on line {line_num} in {year_file.name}. Skipping."
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
                    new_count += len(speeches_list)
                    existing_source_files.add(src_file)
                    unedited_db_files.discard(src_file)
                except Exception as e:
                    session.rollback()
                    print(f"Notice: Error syncing session {src_file}: {e}")
    finally:
        session.close()

    return new_count


def sync_database() -> bool:
    """Run incremental database sync: download from B2, update SQLite, lemmatize, and index."""
    t0 = time.time()
    print("=" * 60)
    print("STARTING INCREMENTAL DATABASE SYNC")
    print("=" * 60)

    try:
        # 1. Download latest data and state from B2
        print("\n[1/5] Downloading latest files from Backblaze B2...")
        b2_ok = download_from_b2()
        if not b2_ok:
            print("Warning: B2 download was not successful. Continuing with available local files.")

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
    except Exception as e:
        print(f"\nDATABASE SYNC FAILED: {e}")
        return False


if __name__ == "__main__":
    success = sync_database()
    sys.exit(0 if success else 1)
