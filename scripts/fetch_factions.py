import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import OUTPUT_DIR_PROCESSED


def fetch_factions() -> bool:
    """Fetch MP parliamentary faction membership history from Riigikogu API."""
    current_year = datetime.now().year
    # 13th Riigikogu was 2015-2019, 14th 2019-2023, 15th 2023-2027, 16th 2027+
    max_membership = 15 + max(0, (current_year - 2023) // 4 + 1)
    membership_params = "&".join(f"membership={m}" for m in range(13, max_membership + 1))
    url = f"https://api.riigikogu.ee/api/plenary-members?status=ALL&{membership_params}"
    print(f"Fetching members from {url}...")

    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)
    out_file = os.path.join(OUTPUT_DIR_PROCESSED, "factions_map.json")

    max_retries = 3
    members = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, timeout=(5, 25))
            if resp.status_code == 200:
                members = resp.json()
                break
            print(
                f"Warning: HTTP {resp.status_code} fetching members (attempt {attempt}/{max_retries})"
            )
        except requests.exceptions.Timeout:
            print(
                f"Warning: Connection timed out to api.riigikogu.ee (attempt {attempt}/{max_retries})"
            )
        except requests.exceptions.RequestException as e:
            print(
                f"Warning: Network error fetching members ({e}) (attempt {attempt}/{max_retries})"
            )

        if attempt < max_retries:
            time.sleep(3 * attempt)

    if members is None:
        if os.path.exists(out_file):
            print(
                f"Notice: Could not refresh factions from API. Using existing cache from {out_file}."
            )
            return True
        print(f"Error: Failed to fetch factions from {url} and no cached {out_file} found.")
        return False

    faction_map = {}

    for m in members:
        # Some names might have multiple spaces, let's just use what API gives
        first_name = m.get("firstName", "").strip()
        last_name = m.get("lastName", "").strip()
        full_name = f"{first_name} {last_name}".strip()

        factions = m.get("factions", [])
        history = []

        for f in factions:
            fname = f.get("name")
            membership = f.get("membership", {})
            start = membership.get("startDate")
            end = membership.get("endDate")

            if not start:
                continue

            # If no end date, make it far in the future for easy comparison
            if not end:
                end = "2099-12-31"

            history.append({"faction": fname, "start": start, "end": end})

        # Sort history by start date just in case
        history.sort(key=lambda x: x["start"])
        faction_map[full_name] = history

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(faction_map, f, ensure_ascii=False, indent=2)

    print(f"Saved faction history for {len(faction_map)} members to {out_file}")
    return True


if __name__ == "__main__":
    success = fetch_factions()
    sys.exit(0 if success else 1)
