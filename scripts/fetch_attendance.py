import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import requests
import json
from datetime import datetime, timedelta
from src.load.database import SessionLocal, engine
from src.load.models import Base, Attendance

def fetch_attendance(start_date, end_date):
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    
    votings_url = f"https://api.riigikogu.ee/api/votings?startDate={start_date}&endDate={end_date}"
    print(f"Fetching votings from {votings_url}")
    resp = requests.get(votings_url)
    if resp.status_code != 200:
        print(f"Error fetching votings: {resp.status_code}")
        return
        
    votings = resp.json()
    attendance_votings = []
    
    for v_day in votings:
        for v in v_day.get('votings', []):
            if v.get('type', {}).get('code') == 'KOHALOLEKU_KONTROLL':
                attendance_votings.append({
                    'uuid': v['uuid'],
                    'date': v['startDateTime']
                })
                
    print(f"Found {len(attendance_votings)} attendance checks.")
    
    for av in attendance_votings:
        uuid = av['uuid']
        date = av['date']
        
        exists = session.query(Attendance).filter_by(voting_uuid=uuid).first()
        if exists:
            print(f"Skipping {uuid} - already in DB")
            continue
            
        import time
        max_retries = 3
        voters = []
        for attempt in range(max_retries):
            time.sleep(5.1) # 12 requests per minute max -> 5 seconds per request
            print(f"Fetching voters for {uuid}")
            v_resp = requests.get(f"https://api.riigikogu.ee/api/votings/{uuid}")
            if v_resp.status_code == 200:
                voters = v_resp.json().get('voters', [])
                break
            elif v_resp.status_code == 429:
                print(f"Rate limited (429) for {uuid}. Sleeping 10s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(10)
            else:
                print(f"Error {v_resp.status_code} for {uuid}")
                break
                
        if not voters:
            continue
            
        for voter in voters:
            name = voter.get('fullName', '')
            faction = voter.get('faction', {}).get('name', '') if voter.get('faction') else ''
            status = voter.get('decision', {}).get('code', '')
            
            record = Attendance(
                session_date=date,
                voting_uuid=uuid,
                member_name=name,
                faction=faction,
                status=status
            )
            session.add(record)
            
        session.commit()
        
    print("Done fetching attendance.")
    
from config import START_DATE, DOWNLOAD_SYNC_FILE
import json
import os

if __name__ == "__main__":
    end_date = None
    if os.path.exists(DOWNLOAD_SYNC_FILE):
        with open(DOWNLOAD_SYNC_FILE, "r") as f:
            state = json.load(f)
            end_date = state.get("last_processed_date")
            
    if not end_date:
        from datetime import datetime
        end_date = datetime.now().strftime("%Y-%m-%d")

    print(f"Fetching from {START_DATE} to {end_date}")
    fetch_attendance(START_DATE, end_date)
