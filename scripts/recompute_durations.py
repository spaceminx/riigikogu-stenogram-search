#!/usr/bin/env python3
"""Recompute speech durations in the SQLite database by capping them at the next speech start time.

Default mode is a dry-run that prints statistics without modifying the database.
Use --apply to commit changes session-by-session.
"""

import argparse
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.load.database import SessionLocal
from src.load.loader import apply_capped_durations_to_session_speeches
from src.load.models import Speech


def recompute_durations(apply: bool = False) -> dict:
    session = SessionLocal()
    try:
        # Get all distinct session source files ordered chronologically
        distinct_sessions = [
            r[0]
            for r in session.query(Speech.source_file)
            .distinct()
            .order_by(Speech.date.asc(), Speech.source_file.asc())
            .all()
        ]

        total_sessions = len(distinct_sessions)
        print(f"Analyzing speech durations across {total_sessions} plenary sessions...")

        modified_rows = 0
        total_before_seconds = 0
        total_after_seconds = 0
        all_changes = []

        for _idx, src_file in enumerate(distinct_sessions, 1):
            speeches = (
                session.query(Speech)
                .filter(Speech.source_file == src_file)
                .order_by(Speech.start_time.asc(), Speech.id.asc())
                .all()
            )
            if not speeches:
                continue

            old_durations = [sp.duration_seconds for sp in speeches]
            apply_capped_durations_to_session_speeches(speeches)

            session_modified = False
            for sp, old_dur in zip(speeches, old_durations, strict=False):
                new_dur = sp.duration_seconds
                if old_dur is not None:
                    total_before_seconds += old_dur
                if new_dur is not None:
                    total_after_seconds += new_dur

                if old_dur != new_dur:
                    session_modified = True
                    modified_rows += 1
                    diff = (old_dur or 0) - (new_dur or 0)
                    all_changes.append(
                        {
                            "speaker": sp.speaker,
                            "date": sp.date,
                            "source_file": src_file,
                            "old": old_dur,
                            "new": new_dur,
                            "diff": diff,
                        }
                    )

            if apply and session_modified:
                session.commit()
            else:
                session.rollback()

        # Sort changes by largest duration reduction (diff descending)
        all_changes.sort(key=lambda c: c["diff"], reverse=True)

        print("\n" + "=" * 60)
        mode_str = "APPLY (DATABASE UPDATED)" if apply else "DRY-RUN (DATABASE NOT MODIFIED)"
        print(f"DURATION RECOMPUTATION: {mode_str}")
        print("=" * 60)
        print(f"Analyzed sessions:        {total_sessions}")
        print(f"Modified speeches:        {modified_rows}")
        print(
            f"Total duration before:    {total_before_seconds:,} s ({total_before_seconds / 3600:.1f} h)"
        )
        print(
            f"Total duration after:     {total_after_seconds:,} s ({total_after_seconds / 3600:.1f} h)"
        )
        reduction = total_before_seconds - total_after_seconds
        reduction_pct = (reduction / total_before_seconds * 100) if total_before_seconds else 0.0
        print(f"Duration reduction:       {reduction:,} s (-{reduction_pct:.2f}%)")

        print("\nTop 10 largest duration changes:")
        for rank, c in enumerate(all_changes[:10], 1):
            print(
                f"  {rank:2d}. {c['speaker']} ({c['date']}): {c['old']} s -> {c['new']} s (-{c['diff']} s)"
            )

        if not apply:
            print("\nDry-run complete. Database was not modified.")
            print("To apply changes run: python scripts/recompute_durations.py --apply")
        else:
            print("\nDurations successfully updated in database.")

        return {
            "modified_rows": modified_rows,
            "total_before": total_before_seconds,
            "total_after": total_after_seconds,
            "top_10": all_changes[:10],
        }
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recompute speech durations in the database.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes to the database (default is dry-run).",
    )
    args = parser.parse_args()
    recompute_durations(apply=args.apply)
