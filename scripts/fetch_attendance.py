import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import OUTPUT_DIR_PROCESSED, START_DATE

# Optional database support (for local runs)
try:
    from src.load.database import SessionLocal, engine
    from src.load.models import Attendance, Base

    HAS_DB = True
except Exception:
    HAS_DB = False


def fetch_attendance(start_date: str = None, end_date: str = None):
    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)
    attendance_file = os.path.join(OUTPUT_DIR_PROCESSED, "attendance.jsonl")

    existing_uuids = set()

    # Load existing voting UUIDs from attendance.jsonl
    if os.path.exists(attendance_file):
        with open(attendance_file, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        if "voting_uuid" in record:
                            existing_uuids.add(record["voting_uuid"])
                    except json.JSONDecodeError:
                        continue

    session = None
    if HAS_DB:
        try:
            Base.metadata.create_all(bind=engine)
            session = SessionLocal()
        except Exception as e:
            print(f"Notice: Database session not initialized: {e}")
            session = None

    if not start_date:
        if existing_uuids:
            # Incremental run: only check last 14 days
            start_date = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
        else:
            start_date = START_DATE

    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    votings_url = f"https://api.riigikogu.ee/api/votings?startDate={start_date}&endDate={end_date}"
    print(f"Fetching votings from {start_date} to {end_date} ({votings_url})")

    votings = []
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(votings_url, timeout=(5, 30))
            if resp.status_code == 200:
                votings = resp.json()
                break
            print(
                f"Warning: HTTP {resp.status_code} fetching votings (attempt {attempt}/{max_retries})"
            )
        except requests.exceptions.Timeout:
            print(f"Warning: Connection timeout fetching votings (attempt {attempt}/{max_retries})")
        except requests.exceptions.RequestException as e:
            print(
                f"Warning: Network error fetching votings ({e}) (attempt {attempt}/{max_retries})"
            )
        time.sleep(3)

    if not isinstance(votings, list):
        print("Error: Could not retrieve votings list. Exiting.")
        if session:
            session.close()
        return

    attendance_votings = []
    for v_day in votings:
        for v in v_day.get("votings", []):
            if v.get("type", {}).get("code") == "KOHALOLEKU_KONTROLL":
                attendance_votings.append({"uuid": v["uuid"], "date": v["startDateTime"]})

    print(f"Found {len(attendance_votings)} attendance checks in period.")
    new_checks_count = 0
    new_records_count = 0

    with open(attendance_file, "a", encoding="utf-8") as out_f:
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
                        voters = v_resp.json().get("voters", [])
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
                except requests.exceptions.Timeout:
                    print(
                        f"Warning: Timeout fetching voters for {uuid} (Attempt {attempt}/{max_retries})"
                    )
                except requests.exceptions.RequestException as e:
                    print(
                        f"Warning: Network error fetching voters for {uuid}: {e} (Attempt {attempt}/{max_retries})"
                    )

            if not voters:
                continue

            new_checks_count += 1
            existing_uuids.add(uuid)

            for voter in voters:
                name = voter.get("fullName", "").strip()
                faction = (
                    voter.get("faction", {}).get("name", "").strip()
                    if voter.get("faction")
                    else ""
                )
                status = voter.get("decision", {}).get("code", "").strip()

                record_dict = {
                    "session_date": date,
                    "voting_uuid": uuid,
                    "member_name": name,
                    "faction": faction,
                    "status": status,
                }
                out_f.write(json.dumps(record_dict, ensure_ascii=False) + "\n")
                new_records_count += 1

                if session:
                    record = Attendance(
                        session_date=date,
                        voting_uuid=uuid,
                        member_name=name,
                        faction=faction,
                        status=status,
                    )
                    session.add(record)

            if session:
                try:
                    session.commit()
                except Exception:
                    session.rollback()

    if session:
        session.close()

    print(
        f"Done fetching attendance: added {new_checks_count} new checks ({new_records_count} records) to {attendance_file}."
    )


if __name__ == "__main__":
    fetch_attendance()
