#!/usr/bin/env python3
"""Load voting records from processed votes_{YYYY}.jsonl files into the SQLite database.

Default behavior loads all votes_*.jsonl files present in data/processed/.
Optionally accepts specific years via --year YYYY [...].
"""

import argparse
import os
import re
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import OUTPUT_DIR_PROCESSED
from src.load.loader import ensure_schema, load_votes_to_database


def load_votes(years: list[int] | None = None) -> int:
    """Load voting records into SQLite and report counts per year."""
    ensure_schema()

    processed_dir = Path(OUTPUT_DIR_PROCESSED)
    if not processed_dir.exists():
        print(f"Processed directory '{OUTPUT_DIR_PROCESSED}' does not exist.")
        return 0

    available_years = []
    for f in sorted(processed_dir.glob("votes_*.jsonl")):
        m = re.match(r"^votes_(\d{4})\.jsonl$", f.name)
        if m:
            available_years.append(int(m.group(1)))

    if not available_years:
        print("No votes_*.jsonl files found in processed directory.")
        return 0

    if years:
        target_years = sorted(set(y for y in years if y in available_years))
        missing_years = sorted(set(years) - set(available_years))
        if missing_years:
            print(f"Notice: No votes_*.jsonl file found for year(s): {missing_years}")
    else:
        target_years = sorted(available_years)

    if not target_years:
        print("No matching vote files to process.")
        return 0

    print(f"Loading votes for {len(target_years)} year(s): {target_years}...")
    total_loaded = 0
    for yr in target_years:
        count = load_votes_to_database(years=[yr])
        total_loaded += count
        print(f"Year {yr}: {count} votings loaded")

    print(f"Completed loading votes into database: {total_loaded} total votings loaded.")
    return total_loaded


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Load votes_{YYYY}.jsonl files into SQLite database"
    )
    parser.add_argument(
        "--year",
        action="extend",
        nargs="+",
        type=int,
        default=None,
        help="Specific year(s) to load (e.g. --year 2024 2025 or --year 2024 --year 2025)",
    )
    args = parser.parse_args()

    try:
        load_votes(years=args.year)
        sys.exit(0)
    except Exception as e:
        print(f"Error loading votes into database: {e}", file=sys.stderr)
        sys.exit(1)
