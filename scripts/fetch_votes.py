#!/usr/bin/env python3
"""Fetch voting records and votes from the official Riigikogu API.

Stores processed records in data/processed/votes_{YYYY}.jsonl atomically.
"""

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import MEMBERSHIP_DATES, OUTPUT_DIR_PROCESSED, START_DATE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("fetch_votes")


def get_membership_for_date(date_str: str) -> int | None:
    """Resolve parliamentary membership number from ISO date string YYYY-MM-DD."""
    for mem_id, (start_d, end_d) in MEMBERSHIP_DATES.items():
        if start_d <= date_str <= end_d:
            try:
                return int(mem_id)
            except ValueError:
                pass
    return None


def get_existing_voting_records(year: int) -> dict[str, dict]:
    """Load existing voting records for a given year indexed by voting_uuid."""
    fpath = Path(OUTPUT_DIR_PROCESSED) / f"votes_{year}.jsonl"
    records = {}
    if fpath.exists():
        with open(fpath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    v_uuid = data.get("voting_uuid")
                    if v_uuid:
                        records[v_uuid] = data
                except json.JSONDecodeError:
                    continue
    return records


def find_latest_existing_vote_date() -> str | None:
    """Find the latest recorded voting date across all votes_*.jsonl files."""
    processed_dir = Path(OUTPUT_DIR_PROCESSED)
    if not processed_dir.exists():
        return None

    latest_date = None
    for f in processed_dir.glob("votes_*.jsonl"):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    d = data.get("date")
                    if d:
                        clean_d = d[:10]
                        if latest_date is None or clean_d > latest_date:
                            latest_date = clean_d
                except json.JSONDecodeError:
                    continue
    return latest_date


def write_votes_jsonl_atomic(year: int, records_by_uuid: dict[str, dict]) -> None:
    """Atomically write voting records for a given year sorted by date and voting_number."""
    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)
    target_file = Path(OUTPUT_DIR_PROCESSED) / f"votes_{year}.jsonl"
    tmp_file = Path(OUTPUT_DIR_PROCESSED) / f"votes_{year}.jsonl.tmp"

    # Sort records chronologically
    sorted_records = sorted(
        records_by_uuid.values(),
        key=lambda r: (
            r.get("date") or "",
            r.get("start_time") or "",
            r.get("voting_number") or 0,
        ),
    )

    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            for rec in sorted_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        os.replace(tmp_file, target_file)
    except Exception:
        if tmp_file.exists():
            tmp_file.unlink()
        raise


def fetch_votings_list(start_date: str, end_date: str, max_retries: int = 3) -> list[dict] | None:
    """Fetch sittings and their votings list from Riigikogu API."""
    url = f"https://api.riigikogu.ee/api/votings?startDate={start_date}&endDate={end_date}"
    headers = {"User-Agent": "RiigivaadeBot/1.0"}

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=(5, 30))
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                wait_time = 15 * attempt
                logger.warning(
                    "Rate limit (429) fetching votings list. Waiting %ds (attempt %d/%d)...",
                    wait_time,
                    attempt,
                    max_retries,
                )
                time.sleep(wait_time)
            else:
                logger.warning(
                    "HTTP %d fetching votings list (attempt %d/%d)",
                    resp.status_code,
                    attempt,
                    max_retries,
                )
        except requests.exceptions.RequestException as e:
            logger.warning(
                "Network error fetching votings list: %s (attempt %d/%d)", e, attempt, max_retries
            )
        time.sleep(3)
    return None


def fetch_voting_detail(uuid: str, max_retries: int = 3) -> dict | None:
    """Fetch full detail for a single voting, respecting rate limit and 429 backoff."""
    url = f"https://api.riigikogu.ee/api/votings/{uuid}"
    headers = {"User-Agent": "RiigivaadeBot/1.0"}

    for attempt in range(1, max_retries + 1):
        time.sleep(5.1)  # Rate limit: ~12 requests/minute
        try:
            resp = requests.get(url, headers=headers, timeout=(5, 25))
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                wait_time = 15 * attempt
                logger.warning(
                    "Rate limit (429) fetching voting %s. Waiting %ds (attempt %d/%d)...",
                    uuid,
                    wait_time,
                    attempt,
                    max_retries,
                )
                time.sleep(wait_time)
            elif resp.status_code == 404:
                logger.warning("Voting %s returned HTTP 404 Not Found.", uuid)
                return None
            else:
                logger.warning(
                    "HTTP %d fetching voting %s (attempt %d/%d)",
                    resp.status_code,
                    uuid,
                    attempt,
                    max_retries,
                )
        except requests.exceptions.RequestException as e:
            logger.warning(
                "Network error fetching voting %s: %s (attempt %d/%d)",
                uuid,
                e,
                attempt,
                max_retries,
            )
        time.sleep(2)
    return None


def parse_and_validate_voting(detail: dict, sitting_membership: int | None = None) -> dict:
    """Parse raw API voting detail into canonical schema and validate voter counts."""
    v_uuid = detail.get("uuid")
    v_number = detail.get("votingNumber")

    type_obj = detail.get("type")
    type_code = type_obj.get("code") if isinstance(type_obj, dict) else (type_obj or "")

    description = detail.get("description") or ""
    start_time = detail.get("startDateTime")
    end_time = detail.get("endDateTime")

    # Date
    v_date = start_time[:10] if start_time else ""

    # Sitting info
    sitting_data = detail.get("sitting") or {}
    sitting_uuid = sitting_data.get("uuid")
    sitting_title = sitting_data.get("title")

    # Membership
    membership = sitting_membership or get_membership_for_date(v_date)

    # Chairman
    chairman_data = detail.get("chairman") or {}
    chairman_uuid = chairman_data.get("uuid")

    # Related document / draft
    rel_doc = None
    if detail.get("relatedDocument"):
        rd = detail["relatedDocument"]
        rel_doc = {
            "uuid": rd.get("uuid"),
            "reference": str(rd.get("reference") or rd.get("mark") or ""),
            "title": rd.get("title") or "",
            "type": rd.get("documentType") or rd.get("type") or "",
        }
    elif detail.get("relatedDraft"):
        rd = detail["relatedDraft"]
        rel_doc = {
            "uuid": rd.get("uuid"),
            "reference": str(rd.get("mark") or rd.get("reference") or ""),
            "title": rd.get("title") or "",
            "type": rd.get("documentType") or "DRAFT",
        }

    # Voters and totals
    voters = detail.get("voters") or []
    votes_list = []

    c_in_favor = 0
    c_against = 0
    c_neutral = 0
    c_not_voted = 0
    c_absent = 0

    for voter in voters:
        m_uuid = voter.get("uuid")
        dec = voter.get("decision")
        dec_code = dec.get("code", "") if isinstance(dec, dict) else (dec or "")
        faction = voter.get("faction")
        faction_name = faction.get("name") if isinstance(faction, dict) else None

        votes_list.append([m_uuid, dec_code, faction_name])

        if dec_code == "POOLT":
            c_in_favor += 1
        elif dec_code == "VASTU":
            c_against += 1
        elif dec_code == "ERAPOOLETU":
            c_neutral += 1
        elif dec_code == "EI_HAALETANUD":
            c_not_voted += 1
        elif dec_code == "PUUDUB":
            c_absent += 1

    c_abstained = c_not_voted + c_absent
    c_present = len(voters) - c_absent

    # Check against API reported totals
    api_in_favor = detail.get("inFavor")
    api_against = detail.get("against")
    api_neutral = detail.get("neutral")
    api_abstained = detail.get("abstained")
    api_present = detail.get("present")
    api_absent = detail.get("absent")

    if voters:
        mismatches = []
        if api_in_favor is not None and api_in_favor != c_in_favor:
            mismatches.append(f"inFavor ({api_in_favor} != counted {c_in_favor})")
        if api_against is not None and api_against != c_against:
            mismatches.append(f"against ({api_against} != counted {c_against})")
        if api_neutral is not None and api_neutral != c_neutral:
            mismatches.append(f"neutral ({api_neutral} != counted {c_neutral})")
        if api_abstained is not None and api_abstained != c_abstained:
            mismatches.append(f"abstained ({api_abstained} != counted {c_abstained})")
        if api_present is not None and api_present != c_present:
            mismatches.append(f"present ({api_present} != counted {c_present})")
        if api_absent is not None and api_absent != c_absent:
            mismatches.append(f"absent ({api_absent} != counted {c_absent})")

        if mismatches:
            logger.warning(
                "Totals mismatch for voting %s ('%s'): %s",
                v_uuid,
                description,
                ", ".join(mismatches),
            )

    totals = {
        "present": api_present if api_present is not None else c_present,
        "absent": api_absent if api_absent is not None else c_absent,
        "in_favor": api_in_favor if api_in_favor is not None else c_in_favor,
        "against": api_against if api_against is not None else c_against,
        "neutral": api_neutral if api_neutral is not None else c_neutral,
        "abstained": api_abstained if api_abstained is not None else c_abstained,
    }

    return {
        "voting_uuid": v_uuid,
        "voting_number": v_number,
        "type": type_code,
        "description": description,
        "start_time": start_time,
        "end_time": end_time,
        "date": v_date,
        "membership": membership,
        "sitting_uuid": sitting_uuid,
        "sitting_title": sitting_title,
        "related_document": rel_doc,
        "chairman_uuid": chairman_uuid,
        "totals": totals,
        "votes": votes_list,
    }


def fetch_votes(
    start_date: str | None = None,
    end_date: str | None = None,
    dry_run: bool = False,
    upload: bool = False,
    load_db: bool = False,
) -> bool:
    """Fetch voting records from Riigikogu API and update votes_{YYYY}.jsonl files."""
    if not start_date:
        latest = find_latest_existing_vote_date()
        if latest:
            latest_dt = datetime.strptime(latest, "%Y-%m-%d")
            start_dt = max(
                datetime.strptime(START_DATE, "%Y-%m-%d"),
                latest_dt - timedelta(days=7),
            )
            start_date = start_dt.strftime("%Y-%m-%d")
        else:
            start_date = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")

    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    logger.info("Fetching votings from %s to %s", start_date, end_date)
    sittings = fetch_votings_list(start_date, end_date)
    if sittings is None:
        logger.error("Failed to retrieve votings list. Aborting.")
        return False

    # Extract all public votings
    all_votings_to_check = []
    type_counts = {}

    for sitting in sittings:
        sitting_membership = sitting.get("membership")
        for v in sitting.get("votings", []):
            t_obj = v.get("type")
            t_code = t_obj.get("code") if isinstance(t_obj, dict) else (t_obj or "")
            type_counts[t_code] = type_counts.get(t_code, 0) + 1

            if t_code == "KOHALOLEKU_KONTROLL":
                continue

            all_votings_to_check.append(
                {
                    "uuid": v.get("uuid"),
                    "votingNumber": v.get("votingNumber"),
                    "type": t_code,
                    "description": v.get("description"),
                    "startDateTime": v.get("startDateTime"),
                    "membership": sitting_membership,
                }
            )

    logger.info(
        "Found %d sittings, %d total votings in period.", len(sittings), sum(type_counts.values())
    )
    logger.info("Voting types encountered: %s", type_counts)
    logger.info("Target public votings: %d", len(all_votings_to_check))

    # Identify which votings need fetching by checking existing local files
    existing_by_year: dict[int, dict[str, dict]] = {}
    votings_to_fetch = []

    for v in all_votings_to_check:
        v_uuid = v["uuid"]
        start_time = v.get("startDateTime") or ""
        year = int(start_time[:4]) if len(start_time) >= 4 else datetime.now().year
        if year not in existing_by_year:
            existing_by_year[year] = get_existing_voting_records(year)

        if v_uuid not in existing_by_year[year]:
            votings_to_fetch.append((v, year))

    logger.info(
        "Votings already in local files: %d", len(all_votings_to_check) - len(votings_to_fetch)
    )
    logger.info("New votings to fetch details for: %d", len(votings_to_fetch))

    estimated_seconds = len(votings_to_fetch) * 5.1
    logger.info(
        "Estimated time for details: %.1fs (%.1f minutes)",
        estimated_seconds,
        estimated_seconds / 60,
    )

    if dry_run:
        logger.info("[Dry-run] No detail calls made and no files modified.")
        return True

    if not votings_to_fetch:
        logger.info("No new votings to fetch.")
        return True

    # Fetch details and accumulate updates
    modified_years = set()
    fetched_count = 0
    failed_uuids = []

    def _sigterm_handler(signum, frame):
        raise KeyboardInterrupt

    old_sigterm = None
    try:
        old_sigterm = signal.signal(signal.SIGTERM, _sigterm_handler)
    except (ValueError, AttributeError):
        pass

    try:
        for idx, (v_summary, year) in enumerate(votings_to_fetch, 1):
            v_uuid = v_summary["uuid"]
            desc = v_summary.get("description") or ""
            logger.info(
                "[%d/%d] Fetching detail for %s (%s)...",
                idx,
                len(votings_to_fetch),
                v_uuid,
                desc[:40],
            )

            detail = fetch_voting_detail(v_uuid)
            if not detail:
                logger.warning("Could not fetch detail for %s, skipping.", v_uuid)
                failed_uuids.append(v_uuid)
                continue

            parsed = parse_and_validate_voting(
                detail, sitting_membership=v_summary.get("membership")
            )
            existing_by_year[year][v_uuid] = parsed
            modified_years.add(year)
            fetched_count += 1

            # Intermediate atomic save every 25 successfully fetched votings
            if fetched_count % 25 == 0:
                for yr in modified_years:
                    write_votes_jsonl_atomic(yr, existing_by_year[yr])
                logger.info("Intermediate save: %d votings written to disk.", fetched_count)

    except KeyboardInterrupt:
        for yr in modified_years:
            write_votes_jsonl_atomic(yr, existing_by_year[yr])
        total_to_fetch = len(votings_to_fetch)
        logger.warning(
            "Interrupted after %d/%d votings, progress saved",
            fetched_count,
            total_to_fetch,
        )
        return False
    finally:
        if old_sigterm is not None:
            try:
                signal.signal(signal.SIGTERM, old_sigterm)
            except (ValueError, AttributeError):
                pass

    # Atomically write modified year files at end of loop
    for yr in modified_years:
        logger.info(
            "Writing updated votes_%d.jsonl (%d total records)...",
            yr,
            len(existing_by_year[yr]),
        )
        write_votes_jsonl_atomic(yr, existing_by_year[yr])

    logger.info("Successfully fetched and saved %d new votings.", fetched_count)

    # Optional local database sync if --load-db is requested
    if load_db:
        if modified_years:
            logger.info("Loading modified years %s into database...", sorted(modified_years))
            try:
                from src.load.loader import ensure_schema, load_votes_to_database

                ensure_schema()
                loaded = load_votes_to_database(years=list(modified_years))
                logger.info("Loaded %d new votings into database.", loaded)
            except Exception as e:
                logger.error("Failed to load votes into database: %s", e)
                return False
        else:
            logger.info("No modified years to load into database.")

    # Upload to B2 if requested
    if upload:
        if modified_years:
            changed_files = [f"votes_{yr}.jsonl" for yr in sorted(modified_years)]
            logger.info(
                "Uploading %d modified file(s) to Backblaze B2: %s",
                len(changed_files),
                changed_files,
            )
            try:
                from scripts.upload_to_b2 import upload_to_b2

                upload_ok = upload_to_b2(only_files=changed_files)
                if not upload_ok:
                    logger.error("B2 upload failed for modified vote files.")
                    return False
            except Exception as e:
                logger.error("Failed to upload to B2: %s", e)
                return False
        else:
            logger.info("No modified vote files to upload; skipping B2 upload.")

    # If any detail fetches failed, report skipped UUIDs and return False
    if failed_uuids:
        logger.error(
            "Completed with errors: failed to fetch details for %d voting(s):\n%s",
            len(failed_uuids),
            "\n".join(f"  - {u}" for u in failed_uuids),
        )
        return False

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch voting records from Riigikogu API")
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date YYYY-MM-DD (default: latest recorded date - 7 days)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="List query count and time estimate only, without fetching details",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        default=False,
        help="Upload updated votes_*.jsonl files to Backblaze B2",
    )
    parser.add_argument(
        "--load-db",
        action="store_true",
        default=False,
        help="Load modified years into SQLite database",
    )
    args = parser.parse_args()

    success = fetch_votes(
        start_date=args.start_date,
        end_date=args.end_date,
        dry_run=args.dry_run,
        upload=args.upload,
        load_db=args.load_db,
    )
    sys.exit(0 if success else 1)
