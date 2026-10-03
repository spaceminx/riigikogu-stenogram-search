import json
import os
import time
from datetime import datetime

import requests

from config import DOWNLOAD_SYNC_FILE, START_DATE
from src.load.database import SessionLocal, engine
from src.load.models import Attendance, Base


def fetch_attendance(start_date, end_date):
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()

    votings_url = f"https://api.riigikogu.ee/api/votings?startDate={start_date}&endDate={end_date}"
    print(f"Fetching votings from {votings_url}")

    votings = []
    for attempt in range(1, 4):
        try:
            resp = requests.get(votings_url, timeout=(5, 30))
            if resp.status_code == 200:
                votings = resp.json()
                break
            print(f"Warning: HTTP {resp.status_code} fetching votings (attempt {attempt}/3)")
        except requests.exceptions.Timeout:
            print(f"Warning: Connection timeout fetching votings (attempt {attempt}/3)")
        except requests.exceptions.RequestException as e:
            print(f"Warning: Network error fetching votings ({e}) (attempt {attempt}/3)")
        time.sleep(3)

    if not isinstance(votings, list):
        print("Error: Could not retrieve votings list. Exiting.")
        return

    attendance_votings = []

    for v_day in votings:
        for v in v_day.get("votings", []):
            if v.get("type", {}).get("code") == "KOHALOLEKU_KONTROLL":
                attendance_votings.append({"uuid": v["uuid"], "date": v["startDateTime"]})

    print(f"Found {len(attendance_votings)} attendance checks.")

    for av in attendance_votings:
        uuid = av["uuid"]
        date = av["date"]

        exists = session.query(Attendance).filter_by(voting_uuid=uuid).first()
        if exists:
            print(f"Skipping {uuid} - already in DB")
            continue

        max_retries = 3
        voters = []
        for attempt in range(1, max_retries + 1):
            time.sleep(5.1)  # 12 requests per minute max -> 5 seconds per request
            print(f"Fetching voters for {uuid}")
            try:
                v_resp = requests.get(
                    f"https://api.riigikogu.ee/api/votings/{uuid}", timeout=(5, 25)
                )
                if v_resp.status_code == 200:
                    voters = v_resp.json().get("voters", [])
                    break
                if v_resp.status_code == 429:
                    print(
                        f"Rate limited (429) for {uuid}. Sleeping 10s... (Attempt {attempt}/{max_retries})"
                    )
                    time.sleep(10)
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

        for voter in voters:
            name = voter.get("fullName", "")
            faction = voter.get("faction", {}).get("name", "") if voter.get("faction") else ""
            status = voter.get("decision", {}).get("code", "")

            record = Attendance(
                session_date=date,
                voting_uuid=uuid,
                member_name=name,
                faction=faction,
                status=status,
            )
            session.add(record)

        session.commit()

    print("Done fetching attendance.")


if __name__ == "__main__":
    end_date = None
    if os.path.exists(DOWNLOAD_SYNC_FILE):
        with open(DOWNLOAD_SYNC_FILE) as f:
            state = json.load(f)
            end_date = state.get("last_processed_date")

    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    print(f"Fetching from {START_DATE} to {end_date}")
    fetch_attendance(START_DATE, end_date)
