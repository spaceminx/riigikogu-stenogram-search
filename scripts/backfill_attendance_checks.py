"""Backfill attendance check metadata (sitting_uuid, sitting_title, sitting_datetime, sitting_type).

Queries the Riigikogu votings list API month by month starting from 2019-04-01,
classifies sitting titles into standard sitting types (infotund, korraline,
lisaistung, erakorraline, muu), and upserts records into
data/processed/attendance_checks.jsonl.
"""

import argparse
import calendar
import os
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import OUTPUT_DIR_PROCESSED
from src.load.loader import classify_sitting_type, upsert_attendance_checks_jsonl


def generate_month_ranges(start_date_str: str, end_date_str: str) -> list[tuple[str, str]]:
    """Generate (first_day, last_day) string tuples for each calendar month."""
    start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date()

    ranges = []
    curr = date(start_dt.year, start_dt.month, 1)

    while curr <= end_dt:
        _, last_day = calendar.monthrange(curr.year, curr.month)
        m_start = max(curr, start_dt)
        m_end = min(date(curr.year, curr.month, last_day), end_dt)
        ranges.append((m_start.strftime("%Y-%m-%d"), m_end.strftime("%Y-%m-%d")))

        if curr.month == 12:
            curr = date(curr.year + 1, 1, 1)
        else:
            curr = date(curr.year, curr.month + 1, 1)

    return ranges


def fetch_attendance_checks_for_period(
    start_date_str: str, end_date_str: str, max_retries: int = 3
) -> list[dict]:
    """Fetch sittings from Riigikogu votings list endpoint and extract attendance checks."""
    url = f"https://api.riigikogu.ee/api/votings?startDate={start_date_str}&endDate={end_date_str}"
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, timeout=(5, 30))
            if resp.status_code == 200:
                sittings = resp.json()
                if not isinstance(sittings, list):
                    return []
                checks = []
                for s in sittings:
                    s_uuid = s.get("uuid")
                    s_title = s.get("title")
                    s_dt = s.get("sittingDateTime")
                    s_type = classify_sitting_type(s_title)
                    for v in s.get("votings", []):
                        if v.get("type", {}).get("code") == "KOHALOLEKU_KONTROLL":
                            checks.append(
                                {
                                    "voting_uuid": v["uuid"],
                                    "sitting_uuid": s_uuid,
                                    "sitting_title": s_title,
                                    "sitting_datetime": s_dt,
                                    "sitting_type": s_type,
                                }
                            )
                return checks
            print(
                f"Warning: HTTP {resp.status_code} for {start_date_str}..{end_date_str} (attempt {attempt}/{max_retries})"
            )
        except requests.exceptions.RequestException as e:
            print(
                f"Warning: Request failed for {start_date_str}..{end_date_str}: {e} (attempt {attempt}/{max_retries})"
            )
        time.sleep(2)
    return []


def backfill_attendance_checks(
    start_date: str = "2019-04-01",
    end_date: str | None = None,
    upload: bool = False,
) -> bool:
    """Run monthly backfill for attendance checks."""
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    month_ranges = generate_month_ranges(start_date, end_date)
    print(
        f"Backfilling attendance checks from {start_date} to {end_date} across {len(month_ranges)} months..."
    )

    all_checks: list[dict] = []
    for idx, (m_start, m_end) in enumerate(month_ranges, 1):
        print(f"[{idx}/{len(month_ranges)}] Fetching {m_start}..{m_end}...")
        checks = fetch_attendance_checks_for_period(m_start, m_end)
        all_checks.extend(checks)
        # Rate limit constraint: >= 1 s between calls
        time.sleep(1.0)

    print(f"Retrieved {len(all_checks)} total attendance check records.")
    out_file = Path(OUTPUT_DIR_PROCESSED) / "attendance_checks.jsonl"
    total_written = upsert_attendance_checks_jsonl(all_checks, filepath=out_file)
    print(f"Saved {total_written} unique attendance checks to {out_file}.")

    # Print counts per sitting_type
    counts = Counter(r["sitting_type"] for r in all_checks)
    print("\nAttendance checks by sitting_type:")
    for st, count in counts.most_common():
        print(f"  {st}: {count}")
    print(f"Total: {sum(counts.values())}")

    if upload:
        print("\nUploading attendance_checks.jsonl to Backblaze B2...")
        try:
            from scripts.upload_to_b2 import upload_to_b2

            ok = upload_to_b2(only_files=["attendance_checks.jsonl"])
            if not ok:
                print("Error: Upload to B2 failed.")
                return False
            print("Successfully uploaded attendance_checks.jsonl to B2.")
        except Exception as e:
            print(f"Error uploading to B2: {e}")
            return False

    return True


def main():
    parser = argparse.ArgumentParser(description="Backfill attendance checks metadata.")
    parser.add_argument("--start-date", default="2019-04-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--upload", action="store_true", help="Upload attendance_checks.jsonl to Backblaze B2"
    )
    args = parser.parse_args()

    success = backfill_attendance_checks(
        start_date=args.start_date,
        end_date=args.end_date,
        upload=args.upload,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
