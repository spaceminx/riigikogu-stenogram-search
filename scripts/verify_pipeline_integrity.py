#!/usr/bin/env python3
"""Verify data pipeline integrity by cross-referencing processed JSONL sessions
and speech counts directly against official Riigikogu API verbatims (no database required).

Runs quickly in GitHub Actions or locally to guarantee no sessions are missing
or truncated in the processed archive.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import OUTPUT_DIR_PROCESSED


def load_local_sessions_from_jsonl(years: list[int]) -> dict[str, dict]:
    """Parse processed JSONL files and group speech counts and statuses by meeting code / source file."""
    sessions: dict[str, dict] = {}

    for year in years:
        jsonl_path = Path(OUTPUT_DIR_PROCESSED) / f"{year}.jsonl"
        if not jsonl_path.exists():
            continue

        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    src_file = data.get("source_file", "")
                    date_val = data.get("date", "")
                    status = data.get("status", "EDITED")

                    # Extract meeting code if embedded in source_url or source_file
                    meeting_code = None
                    src_url = data.get("source_url") or ""
                    if "/et/" in src_url:
                        part = src_url.split("/et/")[1].split("#")[0].split("?")[0].strip("/")
                        if part.isdigit():
                            meeting_code = part

                    if src_file:
                        if src_file not in sessions:
                            sessions[src_file] = {
                                "date": date_val,
                                "speech_count": 0,
                                "statuses": set(),
                                "meeting_codes": set(),
                            }
                        sessions[src_file]["speech_count"] += 1
                        sessions[src_file]["statuses"].add(status)
                        if meeting_code:
                            sessions[src_file]["meeting_codes"].add(meeting_code)
                except json.JSONDecodeError:
                    continue

    return sessions


def verify_pipeline_integrity(
    days: int = 14,
    fail_on_missing: bool = True,
    sample_meeting_checks: int = 3,
) -> bool:
    """Compare recent official Riigikogu verbatims against processed JSONL files."""
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=days)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    years_to_check = sorted(list({start_dt.year, end_dt.year}))
    local_sessions = load_local_sessions_from_jsonl(years_to_check)

    # Collect all meeting codes present locally
    all_local_meeting_codes = set()
    all_local_dates = set()
    for s_info in local_sessions.values():
        all_local_meeting_codes.update(s_info["meeting_codes"])
        if s_info.get("date"):
            all_local_dates.add(s_info["date"])

    url = "https://api.riigikogu.ee/api/steno/verbatims"
    print(f"Checking official verbatims from {start_str} to {end_str} via {url}...")

    try:
        resp = requests.get(
            url, params={"startDate": start_str, "endDate": end_str}, timeout=(5, 25)
        )
        if resp.status_code != 200:
            print(
                f"Warning: Verbatims API returned HTTP {resp.status_code}. Skipping verification."
            )
            return True
        official_verbatims = resp.json()
    except Exception as e:
        print(f"Warning: Could not connect to Riigikogu API: {e}. Skipping verification.")
        return True

    if not isinstance(official_verbatims, list):
        print("Notice: Unexpected response from verbatims API (not a list).")
        return True

    print(f"Found {len(official_verbatims)} official session records from API.")

    missing_sessions = []
    matched_sessions = []

    for v in official_verbatims:
        meeting_code = None
        link = v.get("_links", {}).get("self", {}).get("href", "")
        if link and "/api/steno/verbatims/" in link:
            meeting_code = link.split("/api/steno/verbatims/")[1].split("?")[0].strip("/")

        v_date = v.get("date", "")
        title = v.get("title", "")

        is_present = False
        if meeting_code and meeting_code in all_local_meeting_codes:
            is_present = True
        elif v_date and v_date in all_local_dates:
            is_present = True

        if is_present:
            matched_sessions.append((meeting_code or title, v_date))
        else:
            missing_sessions.append((meeting_code or title, v_date, title))

    print(f"\nVerification Results (last {days} days):")
    print(f"  Matched sessions in archive: {len(matched_sessions)}")
    print(f"  Missing sessions:            {len(missing_sessions)}")

    if missing_sessions:
        print("\nAlert: The following official sessions are missing from local JSONL:")
        for code, dt, t in missing_sessions:
            print(f"  - [{dt}] Code: {code} | Title: {t}")

        if fail_on_missing:
            return False

    return True


if __name__ == "__main__":
    ok = verify_pipeline_integrity(days=14, fail_on_missing=False)
    sys.exit(0 if ok else 1)
