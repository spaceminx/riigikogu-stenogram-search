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
from config import IGNORED_VERBATIMS, OUTPUT_DIR_PROCESSED, UNEDITED_REFETCH_DAYS

INTEGRITY_UNVERIFIED_EXIT_CODE = 3
# Speeches are fine, but votings or attendance checks are missing or could not be compared.
# The pipeline alerts on it without holding back the B2 upload.
RECORDS_GAP_EXIT_CODE = 4
# Upstream may publish a voting a little after the sitting; only older ones count as missing
RECORDS_GRACE_DAYS = 2
# api.riigikogu.ee was just asked for the verbatims list
RECORDS_CHECK_PAUSE_SECONDS = 2


class IntegrityUnverifiedError(Exception):
    """Raised when the official verbatims cannot be fetched, so nothing could be verified."""


RETRY_ATTEMPTS = 3
RETRY_BASE_WAIT_SECONDS = 15
RETRY_MAX_WAIT_SECONDS = 120


def get_with_retry(url: str, params: dict, attempts: int = RETRY_ATTEMPTS) -> requests.Response:
    """GET with retries on connection errors, HTTP 429 and 5xx.

    The check runs right after the fetchers, so the Riigikogu API often answers 429 at first.
    Waits Retry-After seconds when given, otherwise 15 s × attempt.
    """
    name = url.rstrip("/").split("/")[-1]
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, params=params, timeout=(5, 25))
        except Exception as e:
            if attempt == attempts:
                raise IntegrityUnverifiedError(f"could not connect to Riigikogu API: {e}") from e
            wait = RETRY_BASE_WAIT_SECONDS * attempt
            print(f"Warning: Riigikogu API connection failed ({e}). Retrying in {wait}s...")
            time.sleep(wait)
            continue

        if resp.status_code == 200:
            return resp
        if resp.status_code != 429 and resp.status_code < 500:
            raise IntegrityUnverifiedError(f"{name} API returned HTTP {resp.status_code}")
        if attempt == attempts:
            raise IntegrityUnverifiedError(
                f"{name} API returned HTTP {resp.status_code} after {attempts} attempts"
            )

        retry_after = resp.headers.get("Retry-After", "")
        wait = (
            min(int(retry_after), RETRY_MAX_WAIT_SECONDS)
            if retry_after.isdigit()
            else RETRY_BASE_WAIT_SECONDS * attempt
        )
        print(f"Warning: {name} API returned HTTP {resp.status_code}. Retrying in {wait}s...")
        time.sleep(wait)

    raise IntegrityUnverifiedError(f"{name} API request did not complete")


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
    days: int = UNEDITED_REFETCH_DAYS,
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

    resp = get_with_retry(url, params={"startDate": start_str, "endDate": end_str})
    try:
        official_verbatims = resp.json()
    except ValueError as e:
        raise IntegrityUnverifiedError(f"invalid JSON from verbatims API: {e}") from e

    if not isinstance(official_verbatims, list):
        raise IntegrityUnverifiedError("unexpected response from verbatims API (not a list)")

    print(f"Found {len(official_verbatims)} official session records from API.")

    missing_sessions = []
    matched_sessions = []
    truncated_sessions = []

    for v in official_verbatims:
        link = v.get("link") or ""
        meeting_code = link.rstrip("/").split("/")[-1].split("?")[0] if link else ""
        if meeting_code in IGNORED_VERBATIMS:
            print(f"Skipping ignored verbatim {meeting_code}: {IGNORED_VERBATIMS[meeting_code]}")
            continue

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

    blocked_files = set()
    for _code, dt, _reason in truncated_sessions:
        if dt and len(dt) >= 4:
            yr = dt[:4]
            blocked_files.add(f"{yr}.jsonl")

    report = {
        "generated_at": datetime.now().isoformat(),
        "missing_sessions": [
            {"code": code, "date": dt, "title": title} for code, dt, title in missing_sessions
        ],
        "truncated_sessions": [
            {"code": code, "date": dt, "reason": reason} for code, dt, reason in truncated_sessions
        ],
        "blocked_files": sorted(list(blocked_files)),
    }

    report_path = os.path.join(OUTPUT_DIR_PROCESSED, "integrity_report.json")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"Wrote integrity report to {report_path}")
    except Exception as e:
        print(f"Warning: Could not write integrity report: {e}")

    if not is_ok and fail_on_missing:
        return False

    return True


def _local_uuids(file_names: list[str]) -> set[str]:
    uuids: set[str] = set()
    for name in file_names:
        fpath = Path(OUTPUT_DIR_PROCESSED) / name
        if not fpath.exists():
            continue
        with open(fpath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    v_uuid = json.loads(line).get("voting_uuid")
                except json.JSONDecodeError:
                    continue
                if v_uuid:
                    uuids.add(v_uuid)
    return uuids


def verify_votes_integrity(
    days: int = UNEDITED_REFETCH_DAYS,
    grace_days: int = RECORDS_GRACE_DAYS,
) -> bool:
    """Compare recent official votings and attendance checks against the processed files.

    Returns False when a voting (votes_{YYYY}.jsonl) or an attendance check (attendance.jsonl)
    older than grace_days is missing. Raises IntegrityUnverifiedError when the list cannot be read.
    """
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=days)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")
    cutoff = (end_dt - timedelta(days=grace_days)).strftime("%Y-%m-%dT%H:%M:%S")

    years_to_check = sorted(list({start_dt.year, end_dt.year}))
    local_votings = _local_uuids([f"votes_{yr}.jsonl" for yr in years_to_check])
    local_checks = _local_uuids(["attendance.jsonl"])

    url = "https://api.riigikogu.ee/api/votings"
    print(f"\nChecking official votings from {start_str} to {end_str} via {url}...")
    resp = get_with_retry(url, params={"startDate": start_str, "endDate": end_str})
    try:
        sittings = resp.json()
    except ValueError as e:
        raise IntegrityUnverifiedError(f"invalid JSON from votings API: {e}") from e
    if not isinstance(sittings, list):
        raise IntegrityUnverifiedError("unexpected response from votings API (not a list)")

    matched = 0
    missing = []
    pending = []
    for s in sittings:
        for v in s.get("votings", []) or []:
            is_check = (v.get("type") or {}).get("code") == "KOHALOLEKU_KONTROLL"
            if v.get("uuid") in (local_checks if is_check else local_votings):
                matched += 1
            elif (v.get("startDateTime") or "") < cutoff:
                missing.append((is_check, v))
            else:
                pending.append((is_check, v))

    print(f"Votings and attendance checks (last {days} days):")
    print(f"  Matched in archive:                {matched}")
    print(f"  Missing, older than {grace_days} days:      {len(missing)}")
    print(f"  Not yet in archive, newer:         {len(pending)}")

    for label, rows in (("missing", missing), ("not yet in archive", pending)):
        for is_check, v in rows:
            kind = "attendance check" if is_check else "voting"
            print(
                f"  - {label}: {kind} [{v.get('startDateTime')}] UUID: {v.get('uuid')}"
                f" | {v.get('description')}"
            )

    return not missing


def main() -> int:
    try:
        ok = verify_pipeline_integrity(days=UNEDITED_REFETCH_DAYS, fail_on_missing=True)
    except IntegrityUnverifiedError as e:
        print(f"Error: Integrity could not be verified: {e}", file=sys.stderr)
        return INTEGRITY_UNVERIFIED_EXIT_CODE
    if not ok:
        return 1

    time.sleep(RECORDS_CHECK_PAUSE_SECONDS)
    try:
        records_ok = verify_votes_integrity(days=UNEDITED_REFETCH_DAYS)
    except IntegrityUnverifiedError as e:
        print(f"Error: Votings could not be compared: {e}", file=sys.stderr)
        return RECORDS_GAP_EXIT_CODE
    if not records_ok:
        print("Error: Votings or attendance checks are missing.", file=sys.stderr)
        return RECORDS_GAP_EXIT_CODE
    return 0


if __name__ == "__main__":
    sys.exit(main())
