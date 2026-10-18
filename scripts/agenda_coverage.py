#!/usr/bin/env python3
"""Coverage check for agenda items and drafts linked to speeches."""

import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.load.database import SessionLocal


def compute_agenda_coverage(session) -> dict:
    """Query database for yearly speech coverage and top unlinked agenda titles."""
    yearly_sql = text(
        """
        SELECT
            substr(s.date, 1, 4) AS yr,
            COUNT(s.id) AS total_speeches,
            COUNT(a.agenda_item_uuid) AS linked_agenda,
            COUNT(CASE WHEN a.draft_uuid IS NOT NULL AND a.draft_uuid != '' THEN 1 END) AS linked_draft
        FROM speeches s
        LEFT JOIN (
            SELECT
                source_file,
                steno_title,
                MAX(agenda_item_uuid) AS agenda_item_uuid,
                MAX(draft_uuid) AS draft_uuid
            FROM agenda_items
            WHERE source_file IS NOT NULL AND steno_title IS NOT NULL
            GROUP BY source_file, steno_title
        ) a ON s.source_file = a.source_file AND s.agenda_title = a.steno_title
        WHERE s.date IS NOT NULL AND length(s.date) >= 4
        GROUP BY substr(s.date, 1, 4)
        ORDER BY yr ASC;
        """
    )
    yearly_rows = session.execute(yearly_sql).fetchall()

    unlinked_sql = text(
        """
        SELECT
            s.agenda_title,
            COUNT(s.id) AS cnt
        FROM speeches s
        LEFT JOIN (
            SELECT DISTINCT source_file, steno_title
            FROM agenda_items
            WHERE source_file IS NOT NULL AND steno_title IS NOT NULL
        ) a ON s.source_file = a.source_file AND s.agenda_title = a.steno_title
        WHERE a.steno_title IS NULL
          AND s.agenda_title IS NOT NULL
          AND trim(s.agenda_title) != ''
        GROUP BY s.agenda_title
        ORDER BY cnt DESC
        LIMIT 20;
        """
    )
    unlinked_rows = session.execute(unlinked_sql).fetchall()

    return {
        "yearly": yearly_rows,
        "unlinked_titles": unlinked_rows,
    }


def print_coverage_report(data: dict) -> None:
    """Print formatted coverage summary to stdout."""
    print("=" * 80)
    print("AGENDA ITEMS & DRAFTS SPEECH COVERAGE REPORT")
    print("=" * 80)
    print(
        f"{'Year':<6} | {'Total Speeches':<15} | {'Linked to Agenda':<20} | {'Linked to Draft':<20}"
    )
    print("-" * 80)

    total_all = 0
    total_agenda = 0
    total_draft = 0

    for yr, total, linked_ag, linked_dr in data["yearly"]:
        total_all += total
        total_agenda += linked_ag
        total_draft += linked_dr
        ag_pct = (linked_ag / total * 100.0) if total > 0 else 0.0
        dr_pct = (linked_dr / total * 100.0) if total > 0 else 0.0
        ag_str = f"{linked_ag} ({ag_pct:.1f}%)"
        dr_str = f"{linked_dr} ({dr_pct:.1f}%)"
        print(f"{yr:<6} | {total:<15} | {ag_str:<20} | {dr_str:<20}")

    print("-" * 80)
    overall_ag_pct = (total_agenda / total_all * 100.0) if total_all > 0 else 0.0
    overall_dr_pct = (total_draft / total_all * 100.0) if total_all > 0 else 0.0
    total_ag_str = f"{total_agenda} ({overall_ag_pct:.1f}%)"
    total_dr_str = f"{total_draft} ({overall_dr_pct:.1f}%)"
    print(f"{'TOTAL':<6} | {total_all:<15} | {total_ag_str:<20} | {total_dr_str:<20}")
    print("=" * 80)
    print("\nTOP 20 MOST FREQUENT UNLINKED AGENDA TITLES:")
    print("-" * 80)
    print(f"{'Count':<8} | {'Agenda Title'}")
    print("-" * 80)
    for title, count in data["unlinked_titles"]:
        print(f"{count:<8} | {title}")
    print("=" * 80)


def main() -> int:
    session = SessionLocal()
    try:
        data = compute_agenda_coverage(session)
        print_coverage_report(data)
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
