"""Script for removing ignored sessions/verbatims from JSONL datasets and the SQLite database.

Usage:
    python scripts/remove_ignored_sessions.py --year YYYY [--apply] [--data-dir PATH] [--db-path PATH]
"""

import argparse
import json
import os
import shutil
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import DATABASE_PATH, IGNORED_VERBATIMS, OUTPUT_DIR_PROCESSED
from scripts.backfill_history import write_year_file_atomic
from scripts.upload_to_b2 import upload_to_b2
from src.load.database import SessionLocal
from src.load.models import Speech, SpeechAlias, SpeechTerm


def remove_ignored_sessions(
    year: str | int,
    apply: bool = False,
    data_dir: str = OUTPUT_DIR_PROCESSED,
    db_path: str = DATABASE_PATH,
) -> int:
    year_str = str(year)
    jsonl_path = os.path.join(data_dir, f"{year_str}.jsonl")

    if not os.path.exists(jsonl_path):
        print(
            f"Error: {year_str}.jsonl not found in {data_dir}. "
            f"Please download it first: python scripts/download_from_b2.py --year {year_str}"
        )
        return 1

    # Read JSONL file
    speeches_to_keep: list[dict] = []
    ignored_speeches_jsonl: list[dict] = []
    ignored_source_files: set[str] = set()

    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            sp = json.loads(line_str)
            s_key = sp.get("speech_key", "")
            is_ignored = False
            for code in IGNORED_VERBATIMS:
                if s_key.startswith(f"{code}_"):
                    is_ignored = True
                    sf = sp.get("source_file", "")
                    if sf:
                        ignored_source_files.add(sf)
                    break
            if is_ignored:
                ignored_speeches_jsonl.append(sp)
            else:
                speeches_to_keep.append(sp)

    # Check if any ignored source_file contains speeches from other meeting codes in JSONL
    for sp in speeches_to_keep:
        sf = sp.get("source_file", "")
        if sf in ignored_source_files:
            print(
                f"Error: source_file '{sf}' contains speeches from both ignored and non-ignored meeting codes in JSONL. "
                "Refusing to remove."
            )
            return 1

    # Check database
    session = SessionLocal()
    try:
        # Find DB speeches matching ignored codes
        db_speeches_to_remove = []
        for code in IGNORED_VERBATIMS:
            prefix = f"{code}_"
            rows = session.query(Speech).filter(Speech.speech_key.like(f"{prefix}%")).all()
            db_speeches_to_remove.extend(rows)

        # Check for mixed source_files in DB
        db_ignored_source_files = {s.source_file for s in db_speeches_to_remove if s.source_file}
        if db_ignored_source_files:
            for sf in db_ignored_source_files:
                other_query = session.query(Speech).filter(Speech.source_file == sf)
                for code in IGNORED_VERBATIMS:
                    other_query = other_query.filter(~Speech.speech_key.like(f"{code}_%"))
                if other_query.count() > 0:
                    print(
                        f"Error: source_file '{sf}' in database contains speeches from other meeting codes. "
                        "Refusing to remove."
                    )
                    return 1

        db_speech_ids = [s.id for s in db_speeches_to_remove]
        terms_count = 0
        aliases_count = 0
        if db_speech_ids:
            terms_count = (
                session.query(SpeechTerm).filter(SpeechTerm.speech_id.in_(db_speech_ids)).count()
            )
            aliases_count = (
                session.query(SpeechAlias).filter(SpeechAlias.speech_id.in_(db_speech_ids)).count()
            )

        jsonl_count = len(ignored_speeches_jsonl)
        db_count = len(db_speeches_to_remove)

        if jsonl_count == 0 and db_count == 0:
            print("No ignored rows found.")
            return 0

        if not apply:
            print(
                f"Dry run for year {year_str}:\n"
                f"  JSONL: {jsonl_count} speeches would be removed from {year_str}.jsonl\n"
                f"  Database:\n"
                f"    - {db_count} speeches\n"
                f"    - {terms_count} speech_terms\n"
                f"    - {aliases_count} speech_aliases\n"
                "Run with --apply to apply changes."
            )
            return 0

        # --apply mode
        print(f"Applying removal of ignored sessions for year {year_str}...")

        # 1. Overwrite {year}.jsonl atomically (keeping a backup in case upload fails)
        backup_path = f"{jsonl_path}.bak"
        shutil.copy2(jsonl_path, backup_path)
        write_year_file_atomic(year_str, speeches_to_keep, processed_dir=data_dir)
        print(f"  -> Rewrote {year_str}.jsonl (removed {jsonl_count} speeches)")

        # 2. Upload to B2 with ETag check
        print(f"  -> Uploading {year_str}.jsonl to B2...")
        upload_ok = upload_to_b2(only_files=[f"{year_str}.jsonl"])
        if not upload_ok:
            print(
                f"Error: Upload of {year_str}.jsonl to B2 failed. Restoring original file and aborting database deletion."
            )
            shutil.copy2(backup_path, jsonl_path)
            if os.path.exists(backup_path):
                os.remove(backup_path)
            return 1

        if os.path.exists(backup_path):
            os.remove(backup_path)

        # 3. Delete database rows in one transaction
        if db_speech_ids:
            print(
                f"  -> Deleting {db_count} speeches, {terms_count} terms, {aliases_count} aliases from database..."
            )
            session.query(SpeechTerm).filter(SpeechTerm.speech_id.in_(db_speech_ids)).delete(
                synchronize_session=False
            )
            session.query(SpeechAlias).filter(SpeechAlias.speech_id.in_(db_speech_ids)).delete(
                synchronize_session=False
            )
            session.query(Speech).filter(Speech.id.in_(db_speech_ids)).delete(
                synchronize_session=False
            )
            session.commit()
            print("  -> Database transaction committed successfully.")

        print(
            f"Successfully removed {jsonl_count} speeches from {year_str}.jsonl and "
            f"{db_count} speeches ({terms_count} terms, {aliases_count} aliases) from database."
        )
        return 0

    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Remove ignored sessions (e.g. 202103250048) from JSONL and database."
    )
    parser.add_argument("--year", required=True, help="Year to process, e.g. 2021")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (rewrite JSONL, upload B2, delete DB)",
    )
    parser.add_argument(
        "--data-dir", default=OUTPUT_DIR_PROCESSED, help="Processed data directory path"
    )
    parser.add_argument("--db-path", default=DATABASE_PATH, help="Database path")
    args = parser.parse_args()

    exit_code = remove_ignored_sessions(
        year=args.year,
        apply=args.apply,
        data_dir=args.data_dir,
        db_path=args.db_path,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
