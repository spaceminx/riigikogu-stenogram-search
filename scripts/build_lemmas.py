import os
import sys
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.transform.lemmatizer import build_missing_lemmas

def main():
    parser = argparse.ArgumentParser(description="Multiprocessing lemmatizer for Riigikogu speeches")
    parser.add_argument("--workers", type=int, default=None, help="Number of parallel processes (default: auto-detect available CPU threads - 2)")
    parser.add_argument("--chunk-size", type=int, default=50, help="Chunk size sent to each process (default: 50)")
    parser.add_argument("--commit-interval", type=int, default=2000, help="Batch commit size to SQLite (default: 2000)")
    args = parser.parse_args()

    build_missing_lemmas(
        max_workers=args.workers,
        chunk_size=args.chunk_size,
        commit_interval=args.commit_interval
    )

if __name__ == "__main__":
    main()