import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import OUTPUT_DIR_PROCESSED, START_DATE
from src.fetch_models import (
    UpstreamSchemaError,
    VotingDetail,
    VotingsSitting,
    validate_response,
)
from src.load.loader import classify_sitting_type, upsert_attendance_checks_jsonl


def append_attendance_atomic(attendance_file: str, new_records: list[dict]) -> None:
    """Atomically append new attendance records to attendance.jsonl using a temporary file."""
    if not new_records:
        return
    tmp_file = f"{attendance_file}.tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as out_f:
            if os.path.exists(attendance_file):
                with open(attendance_file, encoding="utf-8") as in_f:
                    for line in in_f:
                        out_f.write(line)
            for rec in new_records:
                out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        os.replace(tmp_file, attendance_file)
    except Exception:
        if os.path.exists(tmp_file):
            try:
                os.unlink(tmp_file)
            except OSError:
                pass
        raise


def fetch_attendance(start_date: str = None, end_date: str = None) -> bool:
    """Fetch attendance voting checks from Riigikogu API and record to attendance.jsonl."""
    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)
    attendance_file = os.path.join(OUTPUT_DIR_PROCESSED, "attendance.jsonl")

    existing_uuids = set()
    latest_existing_date = None

    # Load existing voting UUIDs from attendance.jsonl
    if os.path.exists(attendance_file):
        with open(attendance_file, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        if "voting_uuid" in record:
                            existing_uuids.add(record["voting_uuid"])
                        rec_date = record.get("session_date") or record.get("date")
                        if rec_date:
                            clean_date = rec_date[:10]
                            if latest_existing_date is None or clean_date > latest_existing_date:
                                latest_existing_date = clean_date
                    except json.JSONDecodeError:
                        continue

    if not start_date:
        now_dt = datetime.now()
        start_bound = datetime.strptime(START_DATE, "%Y-%m-%d")
        if latest_existing_date:
            latest_dt = datetime.strptime(latest_existing_date, "%Y-%m-%d")
            window_dt = min(latest_dt - timedelta(days=7), now_dt - timedelta(days=30))
            start_dt = max(start_bound, window_dt)
            start_date = start_dt.strftime("%Y-%m-%d")
        elif existing_uuids:
            start_dt = max(start_bound, now_dt - timedelta(days=30))
            start_date = start_dt.strftime("%Y-%m-%d")
        else:
            start_date = START_DATE

    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    votings_url = f"https://api.riigikogu.ee/api/votings?startDate={start_date}&endDate={end_date}"
    print(f"Fetching votings from {start_date} to {end_date} ({votings_url})")

    votings = None
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(votings_url, timeout=(5, 30))
            if resp.status_code == 200:
                raw_data = resp.json()
                validate_response(
                    VotingsSitting,
                    raw_data,
                    endpoint="/api/votings",
                    ref=f"{start_date}..{end_date}",
                )
                votings = raw_data
                break
            print(
                f"Warning: HTTP {resp.status_code} fetching votings (attempt {attempt}/{max_retries})"
            )
        except UpstreamSchemaError:
            raise
        except requests.exceptions.Timeout:
            print(f"Warning: Connection timeout fetching votings (attempt {attempt}/{max_retries})")
        except requests.exceptions.RequestException as e:
            print(
                f"Warning: Network error fetching votings ({e}) (attempt {attempt}/{max_retries})"
            )
        time.sleep(3)

    if not isinstance(votings, list):
        print("Error: Could not retrieve votings list. Exiting.")
        return False

    attendance_votings = []
    attendance_checks = []
    for v_day in votings:
        s_uuid = v_day.get("uuid")
        s_title = v_day.get("title")
        s_dt = v_day.get("sittingDateTime")
        s_type = classify_sitting_type(s_title)
        for v in v_day.get("votings", []):
            if v.get("type", {}).get("code") == "KOHALOLEKU_KONTROLL":
                check_uuid = v["uuid"]
                attendance_votings.append({"uuid": check_uuid, "date": v.get("startDateTime")})
                attendance_checks.append(
                    {
                        "voting_uuid": check_uuid,
                        "sitting_uuid": s_uuid,
                        "sitting_title": s_title,
                        "sitting_datetime": s_dt,
                        "sitting_type": s_type,
                    }
                )

    if attendance_checks:
        upsert_attendance_checks_jsonl(attendance_checks)

    print(f"Found {len(attendance_votings)} attendance checks in period.")
    new_checks_count = 0
    new_records_count = 0
    failed_uuids = []

    for av in attendance_votings:
        uuid = av["uuid"]
        date = av["date"]

        if uuid in existing_uuids:
            continue

        voters = []
        for attempt in range(1, max_retries + 1):
            time.sleep(5.1)  # Rate limit: max 12 requests per minute
            print(f"Fetching voters for {uuid} ({date[:10]})...")
            try:
                v_resp = requests.get(
                    f"https://api.riigikogu.ee/api/votings/{uuid}", timeout=(5, 25)
                )
                if v_resp.status_code == 200:
                    raw_detail = v_resp.json()
                    validate_response(
                        VotingDetail,
                        raw_detail,
                        endpoint="/api/votings/{uuid}",
                        ref=uuid,
                    )
                    voters = raw_detail.get("voters", [])
                    break
                if v_resp.status_code == 429:
                    print(
                        f"Rate limited (429) for {uuid}. Sleeping 15s (Attempt {attempt}/{max_retries})..."
                    )
                    time.sleep(15)
                else:
                    print(
                        f"Warning: HTTP {v_resp.status_code} for {uuid} (Attempt {attempt}/{max_retries})"
                    )
            except UpstreamSchemaError:
                raise
            except requests.exceptions.Timeout:
                print(
                    f"Warning: Timeout fetching voters for {uuid} (Attempt {attempt}/{max_retries})"
                )
            except requests.exceptions.RequestException as e:
                print(
                    f"Warning: Network error fetching voters for {uuid}: {e} (Attempt {attempt}/{max_retries})"
                )

        if not voters:
            print(f"Error: Could not retrieve voters for attendance check {uuid}")
            failed_uuids.append(uuid)
            continue

        check_records = []
        for voter in voters:
            name = voter.get("fullName", "").strip()
            member_uuid = voter.get("uuid", "").strip() or None if voter.get("uuid") else None
            faction = (
                voter.get("faction", {}).get("name", "").strip() if voter.get("faction") else ""
            )
            status = voter.get("decision", {}).get("code", "").strip()

            record_dict = {
                "session_date": date,
                "voting_uuid": uuid,
                "member_uuid": member_uuid,
                "member_name": name,
                "faction": faction,
                "status": status,
            }
            check_records.append(record_dict)

        append_attendance_atomic(attendance_file, check_records)
        new_checks_count += 1
        new_records_count += len(check_records)
        existing_uuids.add(uuid)

    print(
        f"Done fetching attendance: added {new_checks_count} new checks ({new_records_count} records) to {attendance_file}."
    )

    if failed_uuids:
        print(
            f"Error: Failed to fetch voter details for {len(failed_uuids)} check(s): {failed_uuids}"
        )
        return False

    return True


if __name__ == "__main__":
    try:
        success = fetch_attendance()
    except UpstreamSchemaError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    sys.exit(0 if success else 1)
