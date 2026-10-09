import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import OUTPUT_DIR_PROCESSED

FALLBACK_MEMBERSHIPS = {
    "13": {
        "number": 13,
        "name": "XIII Riigikogu",
        "startDate": "2015-03-30",
        "endDate": "2019-04-03",
    },
    "14": {
        "number": 14,
        "name": "XIV Riigikogu",
        "startDate": "2019-04-04",
        "endDate": "2023-04-09",
    },
    "15": {
        "number": 15,
        "name": "XV Riigikogu",
        "startDate": "2023-04-10",
        "endDate": "2027-02-25",
    },
}


def roman_numeral(n: int) -> str:
    """Convert integer to Roman numeral."""
    val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syb = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
    roman_num = ""
    i = 0
    while n > 0:
        for _ in range(n // val[i]):
            roman_num += syb[i]
            n -= val[i]
        i += 1
    return roman_num


def fetch_memberships() -> bool:
    """Fetch official Riigikogu parliamentary membership start and end dates from API."""
    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)
    out_file = os.path.join(OUTPUT_DIR_PROCESSED, "memberships.json")
    tmp_file = os.path.join(OUTPUT_DIR_PROCESSED, "memberships.json.tmp")

    url = "https://api.riigikogu.ee/api/memberships"
    print(f"Fetching parliamentary memberships from {url}...")

    data = None
    max_retries = 3

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, timeout=(5, 25))
            if resp.status_code == 200:
                data = resp.json()
                break
            print(
                f"Warning: HTTP {resp.status_code} fetching memberships (attempt {attempt}/{max_retries})"
            )
        except requests.exceptions.Timeout:
            print(
                f"Warning: Connection timed out to api.riigikogu.ee (attempt {attempt}/{max_retries})"
            )
        except requests.exceptions.RequestException as e:
            print(
                f"Warning: Network error fetching memberships (attempt {attempt}/{max_retries}): {e}"
            )

        if attempt < max_retries:
            time.sleep(2 * attempt)

    if not data:
        if os.path.exists(out_file):
            print(
                f"Warning: Failed to fetch memberships from API, continuing with existing cache in {out_file}."
            )
            return False

        print("Notice: API unavailable and no cache found. Initializing with fallback memberships.")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(FALLBACK_MEMBERSHIPS, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, out_file)
        return False

    sorted_items = sorted(
        [it for it in data if it.get("number") and it.get("startDate")],
        key=lambda x: int(x["number"]),
    )
    memberships_map: dict[str, dict] = {}
    for i, item in enumerate(sorted_items):
        num = int(item["number"])
        start = item["startDate"]
        session_end = item.get("endDate")
        if i + 1 < len(sorted_items):
            next_start = sorted_items[i + 1]["startDate"]
            mandate_end = (datetime.strptime(next_start, "%Y-%m-%d") - timedelta(days=1)).strftime(
                "%Y-%m-%d"
            )
        else:
            mandate_end = session_end or "2099-12-31"

        roman = roman_numeral(num)
        memberships_map[str(num)] = {
            "number": num,
            "name": f"{roman} Riigikogu",
            "startDate": start,
            "endDate": mandate_end,
            "sessionEndDate": session_end,
        }

    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(memberships_map, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, out_file)

    print(f"Successfully saved {len(memberships_map)} memberships to {out_file}.")
    return True


if __name__ == "__main__":
    success = fetch_memberships()
    sys.exit(0 if success else 1)
