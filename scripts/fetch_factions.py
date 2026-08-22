import os
import sys
import json
import requests
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import OUTPUT_DIR_PROCESSED

def fetch_factions():
    url = "https://api.riigikogu.ee/api/plenary-members?status=ALL&membership=13&membership=14&membership=15"
    print(f"Fetching members from {url}...")
    
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"Error fetching members: {resp.status_code}")
        return
        
    members = resp.json()
    faction_map = {}
    
    for m in members:
        # Some names might have multiple spaces, let's just use what API gives
        first_name = m.get('firstName', '').strip()
        last_name = m.get('lastName', '').strip()
        full_name = f"{first_name} {last_name}".strip()
        
        factions = m.get('factions', [])
        history = []
        
        for f in factions:
            fname = f.get('name')
            membership = f.get('membership', {})
            start = membership.get('startDate')
            end = membership.get('endDate')
            
            if not start:
                continue
                
            # If no end date, make it far in the future for easy comparison
            if not end:
                end = "2099-12-31"
                
            history.append({
                "faction": fname,
                "start": start,
                "end": end
            })
            
        # Sort history by start date just in case
        history.sort(key=lambda x: x['start'])
        faction_map[full_name] = history
        
    sync_dir = os.path.join(os.path.dirname(OUTPUT_DIR_PROCESSED), "sync")
    Path(sync_dir).mkdir(parents=True, exist_ok=True)
    out_file = os.path.join(sync_dir, "factions_map.json")
    
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(faction_map, f, ensure_ascii=False, indent=2)
        
    print(f"Saved faction history for {len(faction_map)} members to {out_file}")

if __name__ == "__main__":
    fetch_factions()
