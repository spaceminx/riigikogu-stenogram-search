import json
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from config import OUTPUT_DIR_PROCESSED
from src.load.database import SessionLocal, engine
from src.load.models import (
    Attendance,
    Base,
    Person,
    Speech,
    SpeechAlias,
    SpeechTerm,
    SystemMeta,
    Vote,
    Voting,
)


def compute_capped_duration_seconds(
    start_time_str: str | None,
    end_time_str: str | None,
    next_start_time_str: str | None = None,
) -> int | None:
    """Calculate duration in seconds capped by next speech start time.

    Rule:
    duration = min(end_time, next_speech.start_time) - start_time.
    If no next speech or next speech starts earlier than this speech: end_time - start_time.
    If start_time or end_time is missing: None.
    """
    if not start_time_str or not end_time_str:
        return None
    try:
        dt_start = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        dt_end = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
    except Exception:
        return None

    effective_end = dt_end
    if next_start_time_str:
        try:
            dt_next_start = datetime.fromisoformat(next_start_time_str.replace("Z", "+00:00"))
            if dt_next_start >= dt_start:
                effective_end = min(dt_end, dt_next_start)
        except Exception:
            pass

    return max(0, round((effective_end - dt_start).total_seconds()))


def apply_capped_durations_to_session_speeches(speeches: list) -> None:
    """Sort speeches in a session by start_time and calculate capped duration_seconds."""
    if not speeches:
        return

    def get_attr(obj, attr):
        if isinstance(obj, dict):
            return obj.get(attr)
        return getattr(obj, attr, None)

    def set_attr(obj, attr, val):
        if isinstance(obj, dict):
            obj[attr] = val
        else:
            setattr(obj, attr, val)

    indexed = list(enumerate(speeches))
    indexed.sort(
        key=lambda item: (
            get_attr(item[1], "start_time") is None,
            get_attr(item[1], "start_time") or "",
            item[0],
        )
    )

    for i, (_, cur_sp) in enumerate(indexed):
        cur_start = get_attr(cur_sp, "start_time")
        cur_end = get_attr(cur_sp, "end_time")
        if not cur_start or not cur_end:
            set_attr(cur_sp, "duration_seconds", None)
            continue

        next_start = None
        if i + 1 < len(indexed):
            next_sp = indexed[i + 1][1]
            next_start = get_attr(next_sp, "start_time")

        dur = compute_capped_duration_seconds(cur_start, cur_end, next_start)
        set_attr(cur_sp, "duration_seconds", dur)


def ensure_schema(target_engine=None) -> None:
    """Ensure database schema is up to date (idempotent migration helper)."""
    eng = target_engine or engine
    SystemMeta.__table__.create(eng, checkfirst=True)
    Voting.__table__.create(eng, checkfirst=True)
    Vote.__table__.create(eng, checkfirst=True)

    with eng.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
        if "votings" in tables:
            v_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(votings)"))}
            if "sitting_date" not in v_cols:
                conn.execute(text("ALTER TABLE votings ADD COLUMN sitting_date TEXT;"))
            if "sitting_datetime" not in v_cols:
                conn.execute(text("ALTER TABLE votings ADD COLUMN sitting_datetime TEXT;"))

        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_votings_date ON votings(date);"))
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_votings_sitting_date ON votings(sitting_date);")
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_votings_doc_uuid ON votings(related_document_uuid);"
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_votes_member_uuid ON votes(member_uuid);")
        )
        conn.execute(text("DROP INDEX IF EXISTS idx_votes_voting_uuid;"))
        conn.execute(text("DROP INDEX IF EXISTS ix_votes_voting_uuid;"))
        conn.execute(text("DROP INDEX IF EXISTS ix_votings_date;"))
        conn.execute(text("DROP INDEX IF EXISTS ix_votings_sitting_date;"))
        conn.execute(text("DROP INDEX IF EXISTS ix_votings_related_document_uuid;"))
        conn.execute(text("DROP INDEX IF EXISTS ix_votes_member_uuid;"))
        if "attendance" in tables:
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(attendance)"))}
            if "member_uuid" not in cols:
                conn.execute(text("ALTER TABLE attendance ADD COLUMN member_uuid TEXT;"))
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_attendance_member_uuid ON attendance(member_uuid);"
                )
            )
        conn.commit()


def create_tables() -> None:
    """Create all database tables and ensure optional columns exist."""
    Base.metadata.create_all(bind=engine)
    ensure_schema()
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
            if "speaker_uuid" not in existing_cols:
                conn.execute(text("ALTER TABLE speeches ADD COLUMN speaker_uuid TEXT;"))
            if "ems_id" not in existing_cols:
                conn.execute(text("ALTER TABLE speeches ADD COLUMN ems_id TEXT;"))
            if "speech_type" not in existing_cols:
                conn.execute(text("ALTER TABLE speeches ADD COLUMN speech_type TEXT;"))
            if "external_id" not in existing_cols:
                conn.execute(text("ALTER TABLE speeches ADD COLUMN external_id INTEGER;"))
            if "start_time" not in existing_cols:
                conn.execute(text("ALTER TABLE speeches ADD COLUMN start_time TEXT;"))
            if "end_time" not in existing_cols:
                conn.execute(text("ALTER TABLE speeches ADD COLUMN end_time TEXT;"))
            if "duration_seconds" not in existing_cols:
                conn.execute(text("ALTER TABLE speeches ADD COLUMN duration_seconds INTEGER;"))
            if "speech_key" not in existing_cols:
                conn.execute(text("ALTER TABLE speeches ADD COLUMN speech_key TEXT;"))
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
                    member_uuid=data.get("member_uuid"),
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


def load_persons_to_database() -> None:
    """Load person profiles from persons.json into the persons table."""
    persons_file = Path(OUTPUT_DIR_PROCESSED) / "persons.json"
    if not persons_file.exists():
        return

    print(f"Loading persons from {persons_file.name}...")
    session = SessionLocal()
    try:
        with open(persons_file, encoding="utf-8") as f:
            persons_data = json.load(f)

        existing_uuids = set(r[0] for r in session.query(Person.uuid).all())
        new_objects = []
        for p in persons_data:
            uuid_val = p.get("uuid")
            if not uuid_val:
                continue
            is_active = 1 if p.get("active") else 0
            if uuid_val in existing_uuids:
                session.query(Person).filter(Person.uuid == uuid_val).update(
                    {
                        "first_name": p.get("first_name", ""),
                        "last_name": p.get("last_name", ""),
                        "full_name": p.get("full_name", ""),
                        "gender": p.get("gender"),
                        "date_of_birth": p.get("date_of_birth"),
                        "email": p.get("email"),
                        "photo_url": p.get("photo_url"),
                        "electoral_district": p.get("electoral_district"),
                        "seniority_days": p.get("seniority_days"),
                        "active": is_active,
                    }
                )
            else:
                new_objects.append(
                    Person(
                        uuid=uuid_val,
                        first_name=p.get("first_name", ""),
                        last_name=p.get("last_name", ""),
                        full_name=p.get("full_name", ""),
                        gender=p.get("gender"),
                        date_of_birth=p.get("date_of_birth"),
                        email=p.get("email"),
                        photo_url=p.get("photo_url"),
                        electoral_district=p.get("electoral_district"),
                        seniority_days=p.get("seniority_days"),
                        active=is_active,
                    )
                )

        if new_objects:
            session.bulk_save_objects(new_objects)
        session.commit()
        print(f"Done loading persons ({len(new_objects)} added, {len(existing_uuids)} updated).")
    except Exception as e:
        session.rollback()
        print(f"Notice: Error loading persons: {e}")
        raise
    finally:
        session.close()

    # Check for missing speaker_uuid on speeches (read-only audit)
    matchable = backfill_speaker_uuids()
    if matchable > 0:
        print(f"Audit notice: {matchable} speeches have missing speaker_uuid in database.")


def backfill_speaker_uuids() -> int:
    """Count speeches with missing speaker_uuid that match unique MP names in persons table.

    Read-only audit: does NOT modify the database to preserve JSONL as the source of truth.
    Logs a recommendation to run repair_speaker_uuids.py if matches are found.
    """
    with engine.connect() as conn:
        res = (
            conn.execute(
                text(
                    "SELECT count(*) FROM speeches "
                    "WHERE speaker_uuid IS NULL "
                    "  AND speaker IN ("
                    "    SELECT full_name FROM persons GROUP BY full_name HAVING count(*) = 1"
                    ");"
                )
            ).scalar()
            or 0
        )
        res_tt1 = (
            conn.execute(
                text(
                    "SELECT count(*) FROM speeches "
                    "WHERE speaker = 'Tarmo Tamm' "
                    "  AND speaker_uuid IS NULL "
                    "  AND date < '2023-04-10';"
                )
            ).scalar()
            or 0
        )
        res_tt2 = (
            conn.execute(
                text(
                    "SELECT count(*) FROM speeches "
                    "WHERE speaker = 'Tarmo Tamm' "
                    "  AND speaker_uuid IS NULL "
                    "  AND date >= '2023-04-10';"
                )
            ).scalar()
            or 0
        )
        total_matchable = res + res_tt1 + res_tt2
        if total_matchable > 0:
            print(
                f"Notice: Found {total_matchable} speeches in database with missing speaker_uuid matching MP names. "
                "Database was not modified. Run 'python scripts/repair_speaker_uuids.py' to resolve them in JSONL."
            )
        return total_matchable


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

    jsonl_files = [f for f in processed_dir.glob("*.jsonl") if re.match(r"^\d{4}\.jsonl$", f.name)]
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
                            status=rec_status,
                        )
                        speech._prev_ext_ids = data.get("previous_external_ids", [])
                        speech._prev_keys = data.get("previous_speech_keys", [])
                        speeches_by_session[src_file].append(speech)
                    except KeyError as e:
                        print(
                            f"Warning: Missing required field {e} on line {line_num} in {input_file.name}. Skipping."
                        )
                        continue

            for src_file, speeches_list in speeches_by_session.items():
                apply_capped_durations_to_session_speeches(speeches_list)
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
                            session.query(SpeechAlias).filter(
                                SpeechAlias.speech_id.in_(old_ids)
                            ).delete(synchronize_session=False)
                            session.query(Speech).filter(Speech.source_file == src_file).delete(
                                synchronize_session=False
                            )

                    session.add_all(speeches_list)
                    session.flush()

                    aliases = []
                    for sp in speeches_list:
                        prev_exts = getattr(sp, "_prev_ext_ids", [])
                        prev_keys = getattr(sp, "_prev_keys", [])
                        for p_ext in prev_exts:
                            aliases.append(SpeechAlias(alias_external_id=p_ext, speech_id=sp.id))
                        for p_key in prev_keys:
                            aliases.append(SpeechAlias(alias_speech_key=p_key, speech_id=sp.id))

                    if aliases:
                        session.add_all(aliases)

                    session.commit()
                    existing_source_files.add(src_file)
                    unedited_db_files.discard(src_file)
                except Exception as e:
                    session.rollback()
                    print(f"Notice: Error loading session {src_file}: {e}")

        print("Done loading speech JSONL files to database.")

    session.close()

    # Also load attendance, persons, and votes records if files are present
    load_attendance_to_database(batch_size=batch_size)
    load_persons_to_database()
    load_votes_to_database(batch_size=batch_size)


def load_votes_to_database(years: list[int | str] | None = None, batch_size: int = 2000) -> int:
    """Load voting records and individual votes from votes_{YYYY}.jsonl files into the database."""
    ensure_schema()
    processed_dir = Path(OUTPUT_DIR_PROCESSED)
    if not processed_dir.exists():
        return 0

    target_years = {str(y) for y in years} if years else None
    vote_files = []
    for f in sorted(processed_dir.glob("votes_*.jsonl")):
        m = re.match(r"^votes_(\d{4})\.jsonl$", f.name)
        if m:
            yr = m.group(1)
            if target_years is None or yr in target_years:
                vote_files.append(f)

    if not vote_files:
        return 0

    session = SessionLocal()
    total_votings_loaded = 0
    total_votings_updated = 0
    try:
        existing_votings = {
            r[0]: (r[1], r[2], r[3], r[4])
            for r in session.query(
                Voting.uuid,
                Voting.sitting_date,
                Voting.sitting_datetime,
                Voting.sitting_uuid,
                Voting.sitting_title,
            ).all()
        }
        voting_batch = []
        vote_batch = []

        for vfile in vote_files:
            print(f"Loading votes from {vfile.name}...")
            with open(vfile, encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as err:
                        raise ValueError(
                            f"Corrupted JSON on line {line_num} in {vfile.name}: {err}"
                        ) from err

                    v_uuid = record.get("voting_uuid")
                    if not v_uuid:
                        continue

                    if v_uuid in existing_votings:
                        db_s_date, db_s_dt, db_s_uuid, db_s_title = existing_votings[v_uuid]
                        rec_s_date = record.get("sitting_date")
                        rec_s_dt = record.get("sitting_datetime")
                        rec_s_uuid = record.get("sitting_uuid")
                        rec_s_title = record.get("sitting_title")

                        update_data = {}
                        if rec_s_date and rec_s_date != db_s_date:
                            update_data["sitting_date"] = rec_s_date
                        if rec_s_dt and rec_s_dt != db_s_dt:
                            update_data["sitting_datetime"] = rec_s_dt
                        if rec_s_uuid and rec_s_uuid != db_s_uuid:
                            update_data["sitting_uuid"] = rec_s_uuid
                        if rec_s_title and rec_s_title != db_s_title:
                            update_data["sitting_title"] = rec_s_title

                        if update_data:
                            session.query(Voting).filter(Voting.uuid == v_uuid).update(update_data)
                            total_votings_updated += 1
                            existing_votings[v_uuid] = (
                                update_data.get("sitting_date", db_s_date),
                                update_data.get("sitting_datetime", db_s_dt),
                                update_data.get("sitting_uuid", db_s_uuid),
                                update_data.get("sitting_title", db_s_title),
                            )
                            if total_votings_updated % 100 == 0:
                                session.commit()
                        continue

                    rel_doc = record.get("related_document") or {}
                    totals = record.get("totals") or {}

                    voting_obj = Voting(
                        uuid=v_uuid,
                        voting_number=record.get("voting_number"),
                        type=record.get("type"),
                        description=record.get("description"),
                        date=record.get("date"),
                        start_time=record.get("start_time"),
                        end_time=record.get("end_time"),
                        sitting_date=record.get("sitting_date"),
                        sitting_datetime=record.get("sitting_datetime"),
                        membership=record.get("membership"),
                        sitting_uuid=record.get("sitting_uuid"),
                        sitting_title=record.get("sitting_title"),
                        related_document_uuid=rel_doc.get("uuid"),
                        related_document_reference=rel_doc.get("reference"),
                        related_document_title=rel_doc.get("title"),
                        related_document_type=rel_doc.get("type"),
                        chairman_uuid=record.get("chairman_uuid"),
                        present=totals.get("present"),
                        absent=totals.get("absent"),
                        in_favor=totals.get("in_favor"),
                        against=totals.get("against"),
                        neutral=totals.get("neutral"),
                        abstained=totals.get("abstained"),
                    )
                    voting_batch.append(voting_obj)

                    seen_members = set()
                    for v in record.get("votes", []):
                        if not isinstance(v, (list, tuple)) or len(v) < 2:
                            continue
                        m_uuid, decision = v[0], v[1]
                        faction = v[2] if len(v) > 2 else None
                        if not m_uuid or m_uuid in seen_members:
                            continue
                        seen_members.add(m_uuid)
                        vote_batch.append(
                            Vote(
                                voting_uuid=v_uuid,
                                member_uuid=m_uuid,
                                faction=faction,
                                decision=decision,
                            )
                        )

                    existing_votings[v_uuid] = (
                        record.get("sitting_date"),
                        record.get("sitting_datetime"),
                        record.get("sitting_uuid"),
                        record.get("sitting_title"),
                    )
                    total_votings_loaded += 1

                    if len(voting_batch) >= 100 or len(vote_batch) >= batch_size:
                        session.bulk_save_objects(voting_batch)
                        session.bulk_save_objects(vote_batch)
                        session.commit()
                        voting_batch.clear()
                        vote_batch.clear()

        if voting_batch or vote_batch or total_votings_updated:
            if voting_batch:
                session.bulk_save_objects(voting_batch)
            if vote_batch:
                session.bulk_save_objects(vote_batch)
            session.commit()
            voting_batch.clear()
            vote_batch.clear()

        print(
            f"Done loading votes ({total_votings_loaded} votings added, {total_votings_updated} votings updated)."
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return total_votings_loaded
