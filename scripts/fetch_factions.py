import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import OUTPUT_DIR_PROCESSED


def extract_electoral_district(member: dict) -> str | None:
    """Extract member's electoral district from current or historical records."""
    ed = member.get("electoralDistrict")
    if isinstance(ed, dict):
        return ed.get("value")
    elif isinstance(ed, str):
        return ed
    ed_hist = member.get("electoralDistrictHistory")
    if ed_hist and isinstance(ed_hist, list):
        sorted_hist = sorted(
            [h for h in ed_hist if isinstance(h, dict)],
            key=lambda x: x.get("membership", 0),
            reverse=True,
        )
        if sorted_hist:
            dist = sorted_hist[0].get("electoralDistrict")
            if isinstance(dist, dict):
                return dist.get("value")
            elif isinstance(dist, str):
                return dist
    return None


def extract_photo_url(member: dict) -> str | None:
    """Extract MP portrait photo download URL."""
    photo = member.get("photo")
    if isinstance(photo, dict):
        download_href = photo.get("_links", {}).get("download", {}).get("href")
        if download_href:
            return download_href
        photo_uuid = photo.get("uuid")
        if photo_uuid:
            return f"https://api.riigikogu.ee/api/files/{photo_uuid}/download"
    return None


def fetch_factions() -> bool:
    """Fetch MP parliamentary faction membership history and person profiles from Riigikogu API."""
    current_year = datetime.now().year
    # 13th Riigikogu was 2015-2019, 14th 2019-2023, 15th 2023-2027, 16th 2027+
    max_membership = 15 + max(0, (current_year - 2023) // 4)
    target_memberships = list(range(13, max_membership + 1))

    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)
    out_file = os.path.join(OUTPUT_DIR_PROCESSED, "factions_map.json")
    persons_file = os.path.join(OUTPUT_DIR_PROCESSED, "persons.json")

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
    persons_by_uuid: dict[str, dict] = {}

    for m in members:
        uuid_str = m.get("uuid")
        first_name = m.get("firstName", "").strip()
        last_name = m.get("lastName", "").strip()
        full_name = m.get("fullName", f"{first_name} {last_name}").strip()
        if not full_name:
            continue

        # Process faction history
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

        # Process person profile
        plenary_membership = m.get("plenaryMembership") or {}
        membership_num = (
            plenary_membership.get("membershipNumber", 0)
            if isinstance(plenary_membership, dict)
            else 0
        )

        person_entry = {
            "uuid": uuid_str,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "gender": m.get("gender"),
            "date_of_birth": m.get("dateOfBirth"),
            "email": m.get("email"),
            "photo_url": extract_photo_url(m),
            "electoral_district": extract_electoral_district(m),
            "seniority_days": m.get("parliamentSeniority"),
            "active": bool(m.get("active")),
            "_membership_num": membership_num,
        }

        if uuid_str:
            if uuid_str not in persons_by_uuid:
                persons_by_uuid[uuid_str] = person_entry
            else:
                prev = persons_by_uuid[uuid_str]
                if membership_num >= prev["_membership_num"]:
                    if not person_entry["photo_url"] and prev.get("photo_url"):
                        person_entry["photo_url"] = prev["photo_url"]
                    if not person_entry["electoral_district"] and prev.get("electoral_district"):
                        person_entry["electoral_district"] = prev["electoral_district"]
                    persons_by_uuid[uuid_str] = person_entry

    # Sort history by start date for each member
    for name in faction_map:
        faction_map[name].sort(key=lambda x: x["start"])

    # Atomic write for factions_map.json
    out_tmp = f"{out_file}.tmp"
    with open(out_tmp, "w", encoding="utf-8") as f:
        json.dump(faction_map, f, ensure_ascii=False, indent=2)
    os.replace(out_tmp, out_file)
    print(f"Saved faction history for {len(faction_map)} members to {out_file}")

    # Prepare persons list
    persons_list = []
    for p in persons_by_uuid.values():
        p_clean = {k: v for k, v in p.items() if k != "_membership_num"}
        persons_list.append(p_clean)
    persons_list.sort(key=lambda x: (x["last_name"], x["first_name"]))

    # Atomic write for persons.json
    persons_tmp = f"{persons_file}.tmp"
    with open(persons_tmp, "w", encoding="utf-8") as f:
        json.dump(persons_list, f, ensure_ascii=False, indent=2)
    os.replace(persons_tmp, persons_file)
    print(f"Saved {len(persons_list)} person profiles to {persons_file}")

    return True


if __name__ == "__main__":
    success = fetch_factions()
    sys.exit(0 if success else 1)
