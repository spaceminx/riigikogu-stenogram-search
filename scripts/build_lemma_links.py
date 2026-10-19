#!/usr/bin/env python3
"""CLI script to build or rebuild the lemma_links database table.

Always performs a full atomic rebuild in a single transaction (delete + insert).
"""

import argparse
import os
import sys
import time

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.load.database import engine
from src.transform.lemma_links import build_lemma_links


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild lemma links table in SQLite database.")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild all links from scratch (always performed by default).",
    )
    parser.parse_args()

    print("Building lemma links (full atomic rebuild)...")
    t0 = time.time()
    try:
        stats = build_lemma_links(engine=engine)
        elapsed = time.time() - t0
        print(
            f"Successfully built {stats['total']} lemma links in {elapsed:.2f}s "
            f"({stats['compound_head']} compound_head, {stats['name_form']} name_form, "
            f"{stats['alias']} alias)."
        )
    except Exception as e:
        print(f"Error rebuilding lemma links: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
