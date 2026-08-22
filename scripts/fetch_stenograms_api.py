import os
import sys
import json
import time
from datetime import datetime, timedelta
import requests
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import OUTPUT_DIR_PROCESSED, START_DATE
from src.transform.lemmatizer import lemmatize_text

def split_speaker_role(full_name: str):
    parts = full_name.strip().split(" ")
    if len(parts) <= 1:
        return full_name, None
        
    name_parts = []
    i = len(parts) - 1
    while i >= 0:
        word = parts[i]
        if word and word[0].isupper() and "minister" not in word.lower() and "esimees" not in word.lower():
            name_parts.insert(0, word)
            i -= 1
        else:
            break
            
    if not name_parts:
        return full_name, None
        
    name = " ".join(name_parts)
    role = " ".join(parts[:i+1]).strip()
    return name, role if role else None

def get_faction_for_date(faction_map, name, date_str):
    history = faction_map.get(name, [])
    for h in history:
        if h['start'] <= date_str <= h['end']:
            return h['faction']
    return None

# Basic date generator to chunk requests by month
def get_month_ranges(start_date, end_date):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    
    ranges = []
    current = start
    while current <= end:
        next_month = current.replace(day=28) + timedelta(days=4)
        last_day = next_month - timedelta(days=next_month.day)
        
        chunk_end = min(last_day, end)
        ranges.append((current.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")))
        current = chunk_end + timedelta(days=1)
        
    return ranges

def fetch_and_process_stenograms():
    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)
    
    # Load state of already processed verbatims (we can use UUIDs or Links)
    sync_dir = os.path.join(os.path.dirname(OUTPUT_DIR_PROCESSED), "sync")
    Path(sync_dir).mkdir(parents=True, exist_ok=True)
    state_file = os.path.join(sync_dir, "api_parse_state.json")
    
    if os.path.exists(state_file):
        with open(state_file, "r") as f:
            processed_uuids = set(json.load(f))
            
        # Incremental run: only fetch the last 14 days
        run_start_date = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
    else:
        processed_uuids = set()
        run_start_date = START_DATE
        
    # We will fetch up to today
    end_date = datetime.now().strftime("%Y-%m-%d")
    date_ranges = get_month_ranges(run_start_date, end_date)
        
    sync_dir = os.path.join(os.path.dirname(OUTPUT_DIR_PROCESSED), "sync")
    factions_file = os.path.join(sync_dir, "factions_map.json")
    
    if os.path.exists(factions_file):
        with open(factions_file, "r") as f:
            faction_map = json.load(f)
    else:
        faction_map = {}

    print(f"Starting API fetch from {START_DATE} to {end_date}")
    
    for start, end in date_ranges:
        print(f"Fetching {start} to {end}...")
        url = "https://api.riigikogu.ee/api/steno/verbatims"
        
        # Respect rate limits (12 req/min)
        time.sleep(5.1) 
        
        try:
            resp = requests.get(url, params={"startDate": start, "endDate": end})
            if resp.status_code != 200:
                print(f"Failed to fetch {start}-{end}: HTTP {resp.status_code}")
                continue
                
            verbatims = resp.json()
            if not isinstance(verbatims, list):
                continue
                
            for verbatim in verbatims:
                verbatim_link = verbatim.get('link', '')
                # If we don't have a reliable UUID in verbatim root, use the link as the unique ID
                uid = verbatim_link if verbatim_link else str(verbatim.get('date'))
                
                if uid in processed_uuids:
                    continue
                    
                print(f"Processing verbatim: {verbatim.get('title')} ({verbatim.get('date')})")
                
                # Extract date and time for our JSONL format
                v_date_str = verbatim.get('date') # e.g. "2024-01-08T13:00:00.000+00:00"
                if not v_date_str:
                    continue
                    
                v_dt = datetime.strptime(v_date_str.split('T')[0], "%Y-%m-%d")
                year_str = v_dt.strftime("%Y")
                date_formatted = v_dt.strftime("%Y-%m-%d")
                
                # Extract time from link if possible, or from date string
                # e.g. https://stenogrammid.riigikogu.ee/202401081500
                time_formatted = "0000"
                if verbatim_link and len(verbatim_link) >= 4:
                    time_formatted = verbatim_link[-4:]
                    if not time_formatted.isdigit():
                        time_formatted = "0000"
                
                speeches_to_save = []
                
                for agenda_item in verbatim.get('agendaItems', []):
                    for event in agenda_item.get('events', []):
                        if event.get('type') == 'SPEECH':
                            raw_text = event.get('text', '')
                            speaker_raw = event.get('speaker', '')
                            
                            if not raw_text or not speaker_raw:
                                continue
                                
                            speaker_name, speaker_role = split_speaker_role(speaker_raw)
                            speaker_faction = get_faction_for_date(faction_map, speaker_name, date_formatted)
                            lemmas = lemmatize_text(raw_text)
                            
                            speeches_to_save.append({
                                "date": date_formatted,
                                "time": time_formatted,
                                "source_file": f"{date_formatted}_{time_formatted}.api",
                                "source_url": verbatim_link,
                                "speaker": speaker_name,
                                "speaker_role": speaker_role,
                                "speaker_faction": speaker_faction,
                                "text": raw_text,
                                "text_lemmas": lemmas
                            })
                            
                if speeches_to_save:
                    out_file = os.path.join(OUTPUT_DIR_PROCESSED, f"{year_str}.jsonl")
                    with open(out_file, "a", encoding="utf-8") as f:
                        for s in speeches_to_save:
                            f.write(json.dumps(s, ensure_ascii=False) + "\n")
                            
                    print(f"  -> Saved {len(speeches_to_save)} speeches to {year_str}.jsonl")
                
                processed_uuids.add(uid)
                with open(state_file, "w") as f:
                    json.dump(list(processed_uuids), f)
                    
        except Exception as e:
            print(f"Error on {start}-{end}: {e}")

if __name__ == "__main__":
    fetch_and_process_stenograms()
