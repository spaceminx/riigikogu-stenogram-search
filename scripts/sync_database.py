import json
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import func

from config import OUTPUT_DIR_PROCESSED, active_years
from scripts.download_from_b2 import download_from_b2
from src.load.database import SessionLocal
from src.load.indexes import create_indexes
from src.load.loader import (
    create_tables,
    load_attendance_to_database,
    load_persons_to_database,
)
from src.load.models import Speech, SpeechAlias, SpeechTerm
from src.transform.lemmatizer import build_missing_lemmas
from src.transform.term_builder import build_missing_terms


def sync_current_year_speeches(year: str | None = None, batch_size: int = 2000) -> int:
    """Load new or updated speeches from JSONL files into SQLite session-by-session."""
    if year:
        years_to_check = [str(year)]
    else:
        years_to_check = active_years()

    session = SessionLocal()
    new_count = 0

    try:
        for yr in years_to_check:
            year_file = Path(OUTPUT_DIR_PROCESSED) / f"{yr}.jsonl"
            if not year_file.exists():
                continue

            print(f"Checking {year_file.name} for new or updated speeches...")

            # Map source_file -> {"count": count, "status": status}
            db_sessions: dict[str, dict] = {}
            for r in (
                session.query(
                    Speech.source_file,
                    func.count(Speech.id),
                    func.max(Speech.status),
                )
                .filter(Speech.date >= f"{yr}-01-01", Speech.date <= f"{yr}-12-31")
                .group_by(Speech.source_file)
                .all()
            ):
                db_sessions[r[0]] = {"count": r[1], "status": r[2]}

            raw_speeches_by_session: dict[str, list[dict]] = {}

            with open(year_file, encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    src_file = data.get("source_file", f"{year_file.name}:{line_num}")
                    if src_file not in raw_speeches_by_session:
                        raw_speeches_by_session[src_file] = []
                    raw_speeches_by_session[src_file].append(data)

            for src_file, raw_speeches in raw_speeches_by_session.items():
                existing_info = db_sessions.get(src_file)
                new_status = raw_speeches[0].get("status", "EDITED") if raw_speeches else "EDITED"
                new_count_session = len(raw_speeches)

                needs_update = False
                is_replacement = False

                if existing_info is None:
                    needs_update = True
                elif existing_info["status"] == "UNEDITED":
                    if new_status == "EDITED":
                        needs_update = True
                        is_replacement = True
                    elif new_count_session > existing_info["count"]:
                        # Incomplete unedited session received more speeches (e.g. overnight meeting completed next day)
                        needs_update = True
                        is_replacement = True

                if not needs_update:
                    continue

                try:
                    # If replacing an existing session in DB, preserve old external_ids for permalink aliases
                    if is_replacement:
                        old_rows = (
                            session.query(Speech.id).filter(Speech.source_file == src_file).all()
                        )
                        old_ids = [r.id for r in old_rows]

                        if old_ids:
                            session.query(SpeechTerm).filter(
                                SpeechTerm.speech_id.in_(old_ids)
                            ).delete(synchronize_session=False)
                            session.query(SpeechAlias).filter(
                                SpeechAlias.speech_id.in_(old_ids)
                            ).delete(synchronize_session=False)
                            session.query(Speech).filter(Speech.source_file == src_file).delete(
                                synchronize_session=False
                            )

                    # Build new Speech models
                    new_speech_objects = []
                    for data in raw_speeches:
                        sp_obj = Speech(
                            date=data["date"],
                            time=data["time"],
                            source_file=src_file,
                            source_url=data.get("source_url"),
                            agenda_title=data.get("agenda_title"),
                            video_url=data.get("video_url"),
                            speaker=data.get("speaker", "Tundmatu"),
                            speaker_role=data.get("speaker_role"),
                            speaker_faction=data.get("speaker_faction"),
                            speaker_uuid=data.get("speaker_uuid"),
                            ems_id=data.get("ems_id"),
                            speech_type=data.get("speech_type"),
                            external_id=data.get("external_id"),
                            start_time=data.get("start_time"),
                            end_time=data.get("end_time"),
                            duration_seconds=data.get("duration_seconds"),
                            speech_key=data.get("speech_key"),
                            text=data["text"],
                            text_lemmas=data.get("text_lemmas"),
                            status=data.get("status", "EDITED"),
                        )
                        sp_obj._prev_ext_ids = data.get("previous_external_ids", [])
                        sp_obj._prev_keys = data.get("previous_speech_keys", [])
                        new_speech_objects.append(sp_obj)

                    session.add_all(new_speech_objects)
                    session.flush()

                    aliases_to_add = []
                    for sp in new_speech_objects:
                        for p_ext in getattr(sp, "_prev_ext_ids", []):
                            aliases_to_add.append(
                                SpeechAlias(alias_external_id=p_ext, speech_id=sp.id)
                            )
                        for p_key in getattr(sp, "_prev_keys", []):
                            aliases_to_add.append(
                                SpeechAlias(alias_speech_key=p_key, speech_id=sp.id)
                            )

                    if aliases_to_add:
                        session.add_all(aliases_to_add)

                    session.commit()
                    new_count += len(new_speech_objects)
                    db_sessions[src_file] = {"count": new_count_session, "status": new_status}
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

        # 3. Load current year speeches, attendance & persons
        print("\n[3/5] Inserting new speeches, attendance records, and persons...")
        sync_current_year_speeches()
        load_attendance_to_database()
        load_persons_to_database()

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
