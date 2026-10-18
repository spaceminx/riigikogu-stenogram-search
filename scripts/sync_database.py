import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import func

from config import DATABASE_DIR, OUTPUT_DIR_PROCESSED, active_years
from scripts.download_from_b2 import download_from_b2
from src.load.database import SessionLocal
from src.load.indexes import create_indexes
from src.load.loader import (
    apply_capped_durations_to_session_speeches,
    create_tables,
    load_attendance_to_database,
    load_persons_to_database,
    load_votes_to_database,
)
from src.load.lock import sync_lock
from src.load.models import Speech, SpeechAlias, SpeechTerm, SystemMeta
from src.transform.lemmatizer import build_missing_lemmas
from src.transform.term_builder import build_missing_terms


def sync_current_year_speeches(year: str | None = None, batch_size: int = 2000) -> list[str]:
    """Load new or updated speeches from JSONL files into SQLite session-by-session.

    Returns:
        list[str]: List of source_file paths/identifiers that failed to sync.
    """
    if year:
        years_to_check = [str(year)]
    else:
        years_to_check = active_years()

    session = SessionLocal()
    failed_sources: list[str] = []

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

                    apply_capped_durations_to_session_speeches(new_speech_objects)
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
                    db_sessions[src_file] = {"count": new_count_session, "status": new_status}
                except Exception as e:
                    session.rollback()
                    print(f"Notice: Error syncing session {src_file}: {e}")
                    failed_sources.append(src_file)
    finally:
        session.close()

    return failed_sources


def _sync_database_body(skip_download: bool = False) -> bool:
    t0 = time.time()
    print("=" * 60)
    print("STARTING INCREMENTAL DATABASE SYNC")
    print("=" * 60)

    errors: list[str] = []

    # 1. Download latest data and state from B2
    if not skip_download:
        print("\n[1/8] Downloading latest files from Backblaze B2...")
        try:
            b2_ok = download_from_b2()
            if not b2_ok:
                err_msg = "B2 download failed or returned False"
                print(f"Warning: {err_msg}. Continuing with available local files.")
                errors.append(err_msg)
        except Exception as e:
            err_msg = f"B2 download error: {e}"
            print(f"Warning: {err_msg}. Continuing with available local files.")
            errors.append(err_msg)
    else:
        print("\n[1/8] Skipping B2 download (--skip-download)...")

    # 2. Ensure tables and indexes exist
    print("\n[2/8] Ensuring database tables and indexes exist...")
    try:
        applied = create_tables()
        if applied:
            print(f"Applied migrations: {', '.join(applied)}")
        else:
            print("Schema up to date")
        create_indexes()
    except Exception as e:
        err_msg = f"Failed to ensure schema/indexes: {e}"
        print(f"Error: {err_msg}")
        errors.append(err_msg)

    # 3. Load current year speeches
    print("\n[3/8] Inserting new speeches...")
    try:
        failed_sources = sync_current_year_speeches()
        if failed_sources:
            err_msg = f"Failed to sync {len(failed_sources)} speech session(s): {failed_sources}"
            print(f"Error: {err_msg}")
            errors.append(err_msg)
    except Exception as e:
        err_msg = f"Speech sync failed: {e}"
        print(f"Error: {err_msg}")
        errors.append(err_msg)

    # 4. Lemmatize any new speeches
    print("\n[4/8] Checking and lemmatizing new speeches...")
    try:
        unlemmatized_count = build_missing_lemmas()
        if unlemmatized_count and unlemmatized_count > 0:
            session = SessionLocal()
            sample_ids = []
            try:
                sample_ids = [
                    r[0]
                    for r in session.query(Speech.id)
                    .filter(Speech.text_lemmas.is_(None))
                    .limit(20)
                    .all()
                ]
            finally:
                session.close()
            err_msg = (
                f"Lemmatization incomplete: {unlemmatized_count} speeches remain without lemmas "
                f"(sample IDs: {sample_ids})"
            )
            print(f"Error: {err_msg}")
            errors.append(err_msg)
    except Exception as e:
        err_msg = f"Lemmatization failed: {e}"
        print(f"Error: {err_msg}")
        errors.append(err_msg)

    # 5. Build term index for new speeches
    print("\n[5/8] Indexing new terms...")
    try:
        build_missing_terms()
    except Exception as e:
        err_msg = f"Term indexing failed: {e}"
        print(f"Error: {err_msg}")
        errors.append(err_msg)

    # 6. Attendance
    print("\n[6/8] Loading attendance records...")
    try:
        load_attendance_to_database()
    except Exception as e:
        err_msg = f"Attendance loading failed: {e}"
        print(f"Error: {err_msg}")
        errors.append(err_msg)

    # 7. Persons
    print("\n[7/8] Loading persons...")
    try:
        load_persons_to_database()
    except Exception as e:
        err_msg = f"Persons loading failed: {e}"
        print(f"Error: {err_msg}")
        errors.append(err_msg)

    # 8. Votes
    print("\n[8/8] Loading votes...")
    try:
        load_votes_to_database(years=active_years())
    except Exception as e:
        err_msg = f"Votes loading failed: {e}"
        print(f"Error: {err_msg}")
        errors.append(err_msg)

    # Record successful sync timestamp in system_meta only if NO errors occurred
    if len(errors) == 0:
        meta_session = SessionLocal()
        try:
            now_utc = datetime.now(timezone.utc).isoformat()
            row = meta_session.query(SystemMeta).filter_by(key="last_sync_at").first()
            if row:
                row.value = now_utc
            else:
                meta_session.add(SystemMeta(key="last_sync_at", value=now_utc))
            meta_session.commit()
        except Exception as meta_err:
            meta_session.rollback()
            err_msg = f"Failed to record last_sync_at in system_meta: {meta_err}"
            print(f"Notice: {err_msg}")
            errors.append(err_msg)
        finally:
            meta_session.close()
    else:
        print(f"\nNotice: last_sync_at not updated because {len(errors)} error(s) occurred.")

    duration = time.time() - t0
    print("\n" + "=" * 60)
    if len(errors) == 0:
        print(f"DATABASE SYNC COMPLETE in {duration:.2f} seconds!")
        print("=" * 60)
        return True
    else:
        print(f"DATABASE SYNC FINISHED WITH {len(errors)} ERROR(S) in {duration:.2f} seconds:")
        for err in errors:
            print(f"  - {err}")
        print("=" * 60)
        return False


def sync_database(skip_download: bool = False, skip_lock: bool = False) -> bool:
    """Run incremental database sync: download from B2, update SQLite, lemmatize, and index."""
    if skip_lock:
        return _sync_database_body(skip_download=skip_download)
    with sync_lock(database_dir=DATABASE_DIR):
        return _sync_database_body(skip_download=skip_download)


if __name__ == "__main__":
    skip_dl = "--skip-download" in sys.argv
    success = sync_database(skip_download=skip_dl)
    sys.exit(0 if success else 1)
