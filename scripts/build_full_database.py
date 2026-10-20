import argparse
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime
from pathlib import Path

from config import OUTPUT_DIR_PROCESSED
from scripts.download_all_from_b2 import download_all_from_b2
from src.load.indexes import create_indexes
from src.load.loader import (
    create_tables,
    load_agenda_items_to_database,
    load_jsonl_to_database,
    load_votes_to_database,
)
from src.transform.lemmatizer import build_missing_lemmas
from src.transform.term_builder import build_missing_terms, update_lemma_df


def get_expected_dataset_files(
    now: datetime | None = None,
    current_year: int | None = None,
) -> list[str]:
    """Calculate expected dataset files (2019 to current year, persons, person_factions, attendance, votes).

    - attendance.jsonl is always an expected file.
    - votes_{YYYY}.jsonl files are expected for all years.
    - Current year file is required from January 15 onwards. Prior to Jan 15, current year
      plenary sessions may not have started yet.
    """
    if now is None:
        if current_year is not None:
            now = datetime(current_year, 6, 1)
        else:
            now = datetime.now()

    year = now.year
    end_year = year if (now.month > 1 or now.day >= 15) else (year - 1)
    files = [f"{y}.jsonl" for y in range(2019, end_year + 1)]
    files.extend([f"votes_{y}.jsonl" for y in range(2019, end_year + 1)])
    files.extend(["persons.json", "person_factions.json", "attendance.jsonl"])
    return files


def build_full_database(
    workers: int | None = None,
    chunk_size: int = 50,
    allow_partial: bool = False,
    allow_missing_votes: bool = False,
) -> None:
    """Run full end-to-end database initialization, loading, lemmatization, and indexing."""
    start_total = time.time()
    print("=" * 60)
    print("STARTING RIIGIKOGU DATABASE BUILD PIPELINE")
    print(f"Parallel worker processes: {workers if workers else 'Auto-detect (CPU threads - 2)'}")
    if allow_partial:
        print("Mode: PARTIAL BUILD ALLOWED (--allow-partial)")
    print("=" * 60)

    # Step 0: Ensure all expected dataset files exist
    processed_dir = Path(OUTPUT_DIR_PROCESSED)
    expected_files = get_expected_dataset_files()
    missing_files = [f for f in expected_files if not (processed_dir / f).exists()]

    if allow_missing_votes:
        missing_votes = [f for f in missing_files if f.startswith("votes_")]
        if missing_votes:
            print(
                f"\n[Warning] Building database with missing votes files ignored (--allow-missing-votes enabled).\n"
                f"Missing votes files: {', '.join(missing_votes)}"
            )
            missing_files = [f for f in missing_files if not f.startswith("votes_")]

    if missing_files:
        if allow_partial:
            print(
                f"\n[Warning] Building database with partial dataset (--allow-partial enabled).\n"
                f"Missing expected files: {', '.join(missing_files)}"
            )
        else:
            print(
                f"\n[Step 0/5] Missing expected dataset files: {', '.join(missing_files)}.\n"
                "Attempting to download all files from Backblaze B2..."
            )
            download_all_from_b2()
            still_missing = [f for f in expected_files if not (processed_dir / f).exists()]
            if allow_missing_votes:
                still_missing = [f for f in still_missing if not f.startswith("votes_")]
            if still_missing:
                if all(f.startswith("votes_") for f in still_missing):
                    hint = "use '--allow-missing-votes' to proceed without historical vote files."
                else:
                    hint = "use '--allow-partial' to force building with a partial dataset."
                print(
                    f"\n[Error] Database build aborted. The following expected files are missing: {', '.join(still_missing)}.\n"
                    f"Please download datasets from B2 or {hint}",
                    file=sys.stderr,
                )
                sys.exit(1)

    # Step 1: Create Database Tables
    print("\n[Step 1/5] Creating Database Tables...")
    create_tables()
    print("-> Tables created.")

    # Step 2: Load JSONL files into SQLite
    print("\n[Step 2/5] Loading JSONL, vote, and agenda files from data/processed into SQLite...")
    load_jsonl_to_database()
    load_votes_to_database()
    load_agenda_items_to_database()
    print("-> JSONL, vote, and agenda files loaded.")

    # Step 3: Multiprocessing Lemmatization
    print(f"\n[Step 3/5] Lemmatizing speeches across {workers} parallel processes...")
    t0 = time.time()
    build_missing_lemmas(max_workers=workers, chunk_size=chunk_size)
    print(f"-> Lemmatization completed in {time.time() - t0:.1f}s.")

    # Step 4: Build Terms & Lemmas
    print("\n[Step 4/5] Building terms and lemmas index...")
    t0 = time.time()
    build_missing_terms()
    print(f"-> Term indexing completed in {time.time() - t0:.1f}s.")
    print("Updating lemma document frequencies...")
    df_time = update_lemma_df()
    print(f"-> Lemma document frequencies updated in {df_time:.2f}s.")

    # Step 5: Create SQL Indexes
    print("\n[Step 5/5] Creating SQL indexes for fast querying...")
    t0 = time.time()
    create_indexes()
    print(f"-> Indexes created in {time.time() - t0:.1f}s.")

    total_time = time.time() - start_total
    print("\n" + "=" * 60)
    print(f"DATABASE BUILD COMPLETE in {total_time:.1f} seconds ({total_time / 60:.2f} minutes)!")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build complete Riigikogu SQLite database with parallel multiprocessing"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of parallel worker processes (default: auto-detect available CPU threads - 2)",
    )
    parser.add_argument(
        "--chunk-size", type=int, default=50, help="Chunk size for parallel workers (default: 50)"
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        default=False,
        help="Allow building database from partial dataset without aborting if files are missing",
    )
    parser.add_argument(
        "--allow-missing-votes",
        action="store_true",
        default=False,
        help="Allow building database even if votes_*.jsonl files are missing (warning only)",
    )
    args = parser.parse_args()

    build_full_database(
        workers=args.workers,
        chunk_size=args.chunk_size,
        allow_partial=args.allow_partial,
        allow_missing_votes=args.allow_missing_votes,
    )
