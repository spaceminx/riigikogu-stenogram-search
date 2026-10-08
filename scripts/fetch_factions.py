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
    max_membership = 15 + max(0, (current_year - 2023) // 4)
    target_memberships = list(range(13, max_membership + 1))

    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)
    out_file = os.path.join(OUTPUT_DIR_PROCESSED, "factions_map.json")

    members = None
    max_retries = 3

    while target_memberships:
        membership_params = "&".join(f"membership={m}" for m in target_memberships)
        url = f"https://api.riigikogu.ee/api/plenary-members?status=ALL&{membership_params}"
        print(f"Fetching members from {url}...")

        success_for_url = False
        last_status = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(url, timeout=(5, 25))
                last_status = resp.status_code
                if resp.status_code == 200:
                    members = resp.json()
                    success_for_url = True
                    break
                elif (
                    resp.status_code == 404
                    and len(target_memberships) > 1
                    and target_memberships[-1] > 15
                ):
                    print(
                        f"Notice: Membership {target_memberships[-1]} not yet available (HTTP 404). Dropping it."
                    )
                    target_memberships.pop()
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

        if success_for_url:
            break
        if last_status != 404:
            break

    if members is None:
        if os.path.exists(out_file):
            print(
                f"Warning: Could not refresh factions from API. Continuing with existing cache from {out_file}."
            )
            return True
        else:
            print(f"Error: Failed to fetch factions from API and no cached {out_file} found.")
            return False

    faction_map: dict[str, list[dict]] = {}

    for m in members:
        first_name = m.get("firstName", "").strip()
        last_name = m.get("lastName", "").strip()
        full_name = f"{first_name} {last_name}".strip()
        if not full_name:
            continue

        factions = m.get("factions", [])
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

            entry = {"faction": fname, "start": start, "end": end}
            if full_name not in faction_map:
                faction_map[full_name] = []
            if entry not in faction_map[full_name]:
                faction_map[full_name].append(entry)

    # Sort history by start date for each member
    for name in faction_map:
        faction_map[name].sort(key=lambda x: x["start"])

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(faction_map, f, ensure_ascii=False, indent=2)

    print(f"Saved faction history for {len(faction_map)} members to {out_file}")
    return True


if __name__ == "__main__":
    success = fetch_factions()
    sys.exit(0 if success else 1)
