"""Fetch faction chairs and vice-chairs from the Riigikogu API into faction_roles.json."""

import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import OUTPUT_DIR_PROCESSED
from src.fetch_models import (
    UpstreamSchemaError,
    UserGroupDetail,
    UserGroupItem,
    validate_response,
)

API_BASE = "https://api.riigikogu.ee/api/usergroups"
ROLES = {"ESIMEES": "esimees", "ASEESIMEES": "aseesimees"}
# The site covers memberships from XIII on, like fetch_factions.py
FIRST_MEMBERSHIP = 13
# The API answers HTTP 429 to quick successive requests
SLEEP_BETWEEN_REQUESTS_SECONDS = 2
MAX_RETRIES = 3


def _get_json(url: str):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=(5, 30))
            if resp.status_code == 200:
                return resp.json()
            print(f"Warning: HTTP {resp.status_code} for {url} (attempt {attempt}/{MAX_RETRIES})")
        except requests.exceptions.RequestException as e:
            print(f"Warning: Network error for {url} ({e}) (attempt {attempt}/{MAX_RETRIES})")
        if attempt < MAX_RETRIES:
            time.sleep(5 * attempt)
    return None


def extract_leader_roles(group: dict) -> dict[str, list[dict]]:
    """Return {person_uuid: [{faction, role, start, end}]} for the chairs and vice-chairs of one faction.

    The group also lists ordinary members and staff, which are left out.
    """
    roles: dict[str, list[dict]] = {}
    for member in group.get("members") or []:
        membership = member.get("membership") or {}
        role = ROLES.get((membership.get("role") or {}).get("code"))
        try:
            number = int(membership.get("membershipNumber"))
        except (TypeError, ValueError):
            continue
        if not role or number < FIRST_MEMBERSHIP or not membership.get("startDate"):
            continue
        roles.setdefault(member["uuid"], []).append(
            {
                "faction": group["name"],
                "role": role,
                "start": membership["startDate"],
                "end": membership.get("endDate"),
            }
        )
    return roles


def fetch_faction_leaders() -> bool:
    """Fetch the leadership of the active factions; keep the previous file if any request fails.

    The active factions cover every membership the site shows (XIV and XV).
    """
    out_file = os.path.join(OUTPUT_DIR_PROCESSED, "faction_roles.json")

    groups = _get_json(f"{API_BASE}?typeCode=FRAKTSIOON&hideInactive=true&lang=ET")
    if groups is None:
        print("Warning: Could not fetch the faction list. Keeping the existing faction_roles.json.")
        return False
    validate_response(UserGroupItem, groups, endpoint="/api/usergroups", ref="FRAKTSIOON")

    roles: dict[str, list[dict]] = {}
    for group in groups:
        time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)
        detail = _get_json(f"{API_BASE}/{group['uuid']}?lang=ET")
        if detail is None:
            print(
                f"Warning: Could not fetch {group['name']}. Keeping the existing faction_roles.json."
            )
            return False
        validate_response(
            UserGroupDetail, detail, endpoint="/api/usergroups/{uuid}", ref=group["name"]
        )
        for uuid, entries in extract_leader_roles(detail).items():
            roles.setdefault(uuid, []).extend(entries)

    if not roles:
        print("Error: The API returned no faction chairs. Keeping the existing faction_roles.json.")
        return False

    for entries in roles.values():
        entries.sort(key=lambda e: e["start"])

    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)
    tmp = f"{out_file}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(roles, f, ensure_ascii=False, indent=2)
    os.replace(tmp, out_file)
    print(
        f"Saved faction leadership of {len(roles)} members from {len(groups)} factions to {out_file}"
    )
    return True


if __name__ == "__main__":
    try:
        success = fetch_faction_leaders()
    except UpstreamSchemaError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    sys.exit(0 if success else 1)
