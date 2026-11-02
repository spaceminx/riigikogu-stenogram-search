"""Fetch the drafts (eelnõud) of every membership the site covers into drafts.json.

The list endpoint gives each draft's type, current stage and status, initiation date and
leading committee, including drafts that never reached the plenary. The file is a full
snapshot: it is rewritten only when every page of every membership was fetched.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import OUTPUT_DIR_PROCESSED, START_DATE, load_membership_dates
from src.fetch_models import DraftsPage, UpstreamSchemaError, validate_response

API_URL = "https://api.riigikogu.ee/api/volumes/drafts"
PAGE_SIZE = 200
# The API answers HTTP 429 to quick successive requests
SLEEP_BETWEEN_REQUESTS_SECONDS = 2
MAX_RETRIES = 3


def _get_json(url: str):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=(5, 60))
            if resp.status_code == 200:
                return resp.json()
            print(f"Warning: HTTP {resp.status_code} for {url} (attempt {attempt}/{MAX_RETRIES})")
        except requests.exceptions.RequestException as e:
            print(f"Warning: Network error for {url} ({e}) (attempt {attempt}/{MAX_RETRIES})")
        if attempt < MAX_RETRIES:
            time.sleep(5 * attempt)
    return None


def site_memberships() -> list[int]:
    """Memberships that end on or after the archive start, oldest first."""
    return sorted(
        int(number)
        for number, (_start, end) in load_membership_dates().items()
        if str(number).isdigit() and end >= START_DATE
    )


def normalize_draft(item: dict) -> dict:
    committee = item.get("leadingCommittee") or {}
    return {
        "uuid": item["uuid"],
        "membership": int(item["membership"]),
        "mark": int(item["mark"]),
        "type_code": item.get("draftTypeCode"),
        "title": item["title"].strip(),
        "stage": item.get("activeDraftStage"),
        "status": item.get("activeDraftStatus"),
        "status_date": item.get("activeDraftStatusDate"),
        "proceeding_status": item.get("proceedingStatus"),
        "initiated": item.get("initiated"),
        "leading_committee_uuid": committee.get("uuid"),
        "leading_committee": committee.get("name"),
    }


def fetch_membership_drafts(membership: int) -> list[dict] | None:
    """All drafts of one membership, or None if a page failed or the count does not add up.

    Sorting by mark keeps the pages stable: a draft initiated during the run lands on the last page.
    """
    drafts: dict[str, dict] = {}
    total = None
    page = 0
    while True:
        if page:
            time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)
        url = (
            f"{API_URL}?membership={membership}&size={PAGE_SIZE}&page={page}&sort=mark,asc&lang=ET"
        )
        data = _get_json(url)
        if data is None:
            return None
        validate_response(
            DraftsPage, data, endpoint="/api/volumes/drafts", ref=f"{membership}/{page}"
        )
        if total is None:
            total = data["page"]["totalElements"]
        for item in data["_embedded"]["content"]:
            drafts[item["uuid"]] = normalize_draft(item)
        page += 1
        if page >= data["page"]["totalPages"]:
            break

    if len(drafts) < total:
        print(f"Warning: Membership {membership} listed {total} drafts, got {len(drafts)}.")
        return None
    return list(drafts.values())


def fetch_drafts() -> bool:
    """Fetch all drafts; keep the previous drafts.json if any membership fails."""
    out_file = os.path.join(OUTPUT_DIR_PROCESSED, "drafts.json")
    records: list[dict] = []
    for idx, membership in enumerate(site_memberships()):
        if idx:
            time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)
        drafts = fetch_membership_drafts(membership)
        if drafts is None:
            print(
                f"Warning: Could not fetch the drafts of membership {membership}. Keeping the existing drafts.json."
            )
            return False
        records.extend(drafts)

    if not records:
        print("Error: The API returned no drafts. Keeping the existing drafts.json.")
        return False

    records.sort(key=lambda d: (d["membership"], d["mark"], d["uuid"]))
    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)
    tmp = f"{out_file}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    os.replace(tmp, out_file)
    print(f"Saved {len(records)} drafts to {out_file}")
    return True


if __name__ == "__main__":
    try:
        success = fetch_drafts()
    except UpstreamSchemaError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    sys.exit(0 if success else 1)
