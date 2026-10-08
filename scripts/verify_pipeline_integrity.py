#!/usr/bin/env python3
"""Verify data pipeline integrity by cross-referencing processed JSONL sessions
and speech counts directly against official Riigikogu API verbatims (no database required).

Runs quickly in GitHub Actions or locally to guarantee no sessions are missing
or truncated in the processed archive.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import OUTPUT_DIR_PROCESSED


def load_local_sessions_from_jsonl(years: list[int]) -> dict[str, dict]:
    """Parse processed JSONL files and group speech counts and statuses by source file."""
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
                    src_url = data.get("source_url") or ""

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

                        # Extract meeting codes from source_url
                        clean_url = src_url.split("#")[0].split("?")[0].rstrip("/")
                        url_code = clean_url.split("/")[-1] if clean_url else ""
                        if url_code.isdigit():
                            sessions[src_file]["meeting_codes"].add(url_code)

                        # Extract candidate code from source_file (e.g. 2026-10-01_1000.api -> 202610011000)
                        file_code = src_file.replace("-", "").replace("_", "").replace(".api", "")
                        if file_code.isdigit() and len(file_code) >= 8:
                            sessions[src_file]["meeting_codes"].add(file_code)
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

    # Index local sessions by meeting_code and date
    code_to_session: dict[str, dict] = {}
    date_to_sessions: dict[str, list[dict]] = {}
    for s_info in local_sessions.values():
        for code in s_info["meeting_codes"]:
            code_to_session[code] = s_info
        d = s_info.get("date")
        if d:
            if d not in date_to_sessions:
                date_to_sessions[d] = []
            date_to_sessions[d].append(s_info)

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
    truncated_sessions = []

    for v in official_verbatims:
        link = v.get("link") or ""
        meeting_code = link.rstrip("/").split("/")[-1].split("?")[0] if link else ""
        raw_date = v.get("date", "")
        v_date = raw_date.split("T")[0] if raw_date else ""
        title = v.get("title", "")

        matched_session = None
        if meeting_code and meeting_code in code_to_session:
            matched_session = code_to_session[meeting_code]

        if matched_session:
            sp_count = matched_session["speech_count"]
            if sp_count == 0:
                truncated_sessions.append(
                    (meeting_code or title, v_date, "Empty session (0 speeches)")
                )
            else:
                matched_sessions.append((meeting_code or title, v_date, sp_count))
        else:
            missing_sessions.append((meeting_code or title, v_date, title))

    # Optional sample check of speech count against rich meeting API (check newest sessions first)
    if sample_meeting_checks > 0 and matched_sessions:
        sample_targets = [m for m in reversed(matched_sessions) if str(m[0]).isdigit()][
            :sample_meeting_checks
        ]
        for code, m_date, local_count in sample_targets:
            try:
                meeting_url = f"https://stenogrammid.riigikogu.ee/api/meeting/{code}"
                m_resp = requests.get(
                    meeting_url, timeout=(5, 15), headers={"User-Agent": "Mozilla/5.0"}
                )
                if m_resp.status_code == 200:
                    rich_meeting = m_resp.json()
                    agendas = rich_meeting.get("stenograph", {}).get("agendaItems", [])
                    official_speeches = 0
                    for a in agendas:
                        for sp in a.get("speeches", []):
                            content = sp.get("content") or ""
                            sp_name = sp.get("name") or ""
                            sp_type = sp.get("speechType")
                            if (
                                sp_name
                                and content
                                and sp_type not in ["SESSION_END", "SESSION_START"]
                            ):
                                official_speeches += 1

                    if official_speeches > 5 and local_count < official_speeches * 0.8:
                        truncated_sessions.append(
                            (
                                code,
                                m_date,
                                f"Truncated: local={local_count} vs official={official_speeches}",
                            )
                        )
                    else:
                        print(
                            f"  Verified session {code} ({m_date}): {local_count} speeches (official: {official_speeches})"
                        )
                time.sleep(0.5)
            except Exception as e:
                print(f"  Notice: Sample check skipped for {code}: {e}")

    print(f"\nVerification Results (last {days} days):")
    print(f"  Matched sessions in archive: {len(matched_sessions)}")
    print(f"  Missing sessions:            {len(missing_sessions)}")
    print(f"  Truncated/empty sessions:    {len(truncated_sessions)}")

    is_ok = True
    if missing_sessions:
        is_ok = False
        print("\nAlert: The following official sessions are missing from local JSONL:")
        for code, dt, t in missing_sessions:
            print(f"  - [{dt}] Code: {code} | Title: {t}")

    if truncated_sessions:
        is_ok = False
        print("\nAlert: The following sessions appear truncated or empty:")
        for code, dt, reason in truncated_sessions:
            print(f"  - [{dt}] Code: {code} | Reason: {reason}")

    if not is_ok and fail_on_missing:
        return False

    return True


if __name__ == "__main__":
    ok = verify_pipeline_integrity(days=14, fail_on_missing=True)
    sys.exit(0 if ok else 1)
