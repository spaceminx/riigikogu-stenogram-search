import os
import sys
import argparse
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pathlib import Path
from config import OUTPUT_DIR_PROCESSED
from scripts.download_all_from_b2 import download_all_from_b2
from src.load.loader import create_tables, load_jsonl_to_database
from src.transform.lemmatizer import build_missing_lemmas
from src.transform.term_builder import build_missing_terms
from src.load.indexes import create_indexes

def build_full_database(workers: int = None, chunk_size: int = 50):
    start_total = time.time()
    print("=" * 60)
    print("STARTING RIIGIKOGU DATABASE BUILD PIPELINE")
    print(f"Parallel worker processes: {workers if workers else 'Auto-detect (CPU threads - 2)'}")
    print("=" * 60)

    # Step 0: Ensure data files exist
    processed_dir = Path(OUTPUT_DIR_PROCESSED)
    jsonl_files = list(processed_dir.glob("*.jsonl"))
    if not jsonl_files:
        print("\n[Step 0/5] No .jsonl files found in data/processed. Downloading from Backblaze B2...")
        download_all_from_b2()

    # Step 1: Create Database Tables
    print("\n[Step 1/5] Creating Database Tables...")
    create_tables()
    print("-> Tables created.")

    # Step 2: Load JSONL files into SQLite
    print("\n[Step 2/5] Loading JSONL files from data/processed into SQLite...")
    load_jsonl_to_database()
    print("-> JSONL files loaded.")

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
    parser = argparse.ArgumentParser(description="Build complete Riigikogu SQLite database with parallel multiprocessing")
    parser.add_argument("--workers", type=int, default=None, help="Number of parallel worker processes (default: auto-detect available CPU threads - 2)")
    parser.add_argument("--chunk-size", type=int, default=50, help="Chunk size for parallel workers (default: 50)")
    args = parser.parse_args()

    build_full_database(workers=args.workers, chunk_size=args.chunk_size)
