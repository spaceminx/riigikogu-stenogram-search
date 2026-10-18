#!/usr/bin/env python3
"""Fetch agenda items and verbatim titles from the Riigikogu API and link them to drafts and speeches.

Stores records in data/processed/agenda_items.jsonl.
"""

import argparse
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import requests

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import OUTPUT_DIR_PROCESSED, UNEDITED_REFETCH_DAYS
from scripts.fetch_stenograms_api import clean_html, get_month_ranges
from src.api.votings import format_session_source_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("fetch_agenda")

AGENDA_API_URL = "https://api.riigikogu.ee/api/agenda/plenary"
VERBATIMS_API_URL = "https://api.riigikogu.ee/api/steno/verbatims"


def is_valid_uuid(val: str | None) -> bool:
    """Check if value is a valid 36-character hyphenated UUID string."""
    if not val or not isinstance(val, str):
        return False
    try:
        u = uuid.UUID(val)
        return str(u) == val.lower()
    except (ValueError, AttributeError):
        return False


def map_verbatim_to_source_file(verbatim: dict) -> str:
    """Map a verbatim sitting to our source_file name (YYYY-MM-DD_HHMM.api)."""
    v_date = verbatim.get("date") or ""
    sitting_date = v_date.split("T")[0] if v_date else ""
    candidate_time = None

    v_link = verbatim.get("link") or ""
    if v_link:
        suffix = v_link.rstrip("/").split("/")[-1].split("?")[0]
        if len(suffix) >= 4 and suffix[-4:].isdigit():
            candidate_time = suffix[-4:]

    if not candidate_time:
        start_time = verbatim.get("startTime") or verbatim.get("sittingDateTime")
        if start_time and "T" in str(start_time):
            time_str = str(start_time).split("T")[1].replace(":", "")[:4]
            if len(time_str) == 4 and time_str.isdigit():
                candidate_time = time_str
        elif start_time and ":" in str(start_time):
            time_str = str(start_time).replace(":", "")[:4]
            if len(time_str) == 4 and time_str.isdigit():
                candidate_time = time_str

    if candidate_time and sitting_date:
        return f"{sitting_date}_{candidate_time}.api"

    if sitting_date:
        logger.warning(
            "Could not determine start time for verbatim sitting '%s' on %s; falling back to sitting date only.",
            verbatim.get("title"),
            sitting_date,
        )
        return f"{sitting_date}_0000.api"

    return "unknown_session.api"


def fetch_api_with_retry(
    url: str,
    params: dict,
    max_retries: int = 3,
    sleep_between: float = 1.05,
) -> dict | list | None:
    """Fetch JSON from Riigikogu API with rate limiting and retry/backoff."""
    time.sleep(sleep_between)
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=(5, 30))
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                logger.warning(
                    "Rate limited (429) on %s %s. Waiting 15s (attempt %d/%d)...",
                    url,
                    params,
                    attempt,
                    max_retries,
                )
                time.sleep(15)
            elif resp.status_code in (500, 502, 503, 504):
                logger.warning(
                    "Server error (%d) on %s %s (attempt %d/%d)...",
                    resp.status_code,
                    url,
                    params,
                    attempt,
                    max_retries,
                )
                time.sleep(3 * attempt)
            else:
                logger.warning(
                    "Unexpected status (%d) on %s %s",
                    resp.status_code,
                    url,
                    params,
                )
                return None
        except Exception as e:
            logger.warning(
                "Request failed on %s %s (attempt %d/%d): %s",
                url,
                params,
                attempt,
                max_retries,
                e,
            )
            time.sleep(2 * attempt)
    return None


def load_existing_agenda_items(filepath: Path) -> dict[str, dict]:
    """Load existing agenda items from JSONL file into a dict keyed by agenda_item_uuid."""
    records = {}
    if not filepath.exists():
        return records
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                u = data.get("agenda_item_uuid")
                if u:
                    records[u] = data
            except json.JSONDecodeError:
                continue
    return records


def write_agenda_items_atomic(filepath: Path, records: dict[str, dict]) -> None:
    """Atomically write agenda items dictionary to JSONL file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = filepath.with_suffix(".jsonl.tmp")

    sorted_records = sorted(
        records.values(),
        key=lambda r: (
            r.get("sitting_date") or "",
            r.get("sitting_datetime") or "",
            r.get("order") if r.get("order") is not None else 999999,
            r.get("agenda_item_uuid") or "",
        ),
    )

    with open(tmp_path, "w", encoding="utf-8") as f:
        for r in sorted_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    os.replace(tmp_path, filepath)


def process_agenda_and_verbatims(
    agenda_data: dict | None,
    verbatims_data: list | None,
    existing_records: dict[str, dict],
) -> tuple[int, int]:
    """Extract and upsert agenda items from agenda and verbatims API responses.

    Returns (added_count, updated_count).
    """
    if not agenda_data or not isinstance(agenda_data, dict):
        return 0, 0

    verbatim_items_map: dict[str, dict] = {}
    if verbatims_data and isinstance(verbatims_data, list):
        for v_sitting in verbatims_data:
            if not isinstance(v_sitting, dict):
                continue
            v_source_file = map_verbatim_to_source_file(v_sitting)
            for v_item in v_sitting.get("agendaItems", []):
                if not isinstance(v_item, dict):
                    continue
                v_uuid = v_item.get("agendaItemUuid")
                if not is_valid_uuid(v_uuid):
                    continue
                raw_title = v_item.get("title", "")
                steno_title = clean_html(raw_title)
                verbatim_items_map[v_uuid] = {
                    "steno_title": steno_title or None,
                    "source_file": v_source_file,
                }

    added = 0
    updated = 0

    for sitting in agenda_data.get("sittings", []):
        if not isinstance(sitting, dict):
            continue
        sitting_uuid = sitting.get("uuid")
        sitting_datetime = sitting.get("sittingDateTime")
        sitting_date = sitting_datetime.split("T")[0] if sitting_datetime else ""
        fallback_source_file = (
            format_session_source_file(sitting_date, sitting_datetime) or f"{sitting_date}_0000.api"
        )

        for item in sitting.get("agendaItems", []):
            if not isinstance(item, dict):
                continue
            item_uuid = item.get("uuid")
            if not is_valid_uuid(item_uuid):
                continue

            v_info = verbatim_items_map.get(item_uuid)
            existing = existing_records.get(item_uuid)
            if v_info:
                steno_title = v_info["steno_title"]
                source_file = v_info["source_file"]
            elif existing:
                steno_title = existing.get("steno_title")
                source_file = existing.get("source_file") or fallback_source_file
            else:
                steno_title = None
                source_file = fallback_source_file

            rel_draft = (
                item.get("relatedDraft") if isinstance(item.get("relatedDraft"), dict) else None
            )
            draft_uuid = rel_draft.get("uuid") if rel_draft else None
            draft_mark = rel_draft.get("mark") if rel_draft else None
            draft_title = rel_draft.get("title") if rel_draft else None

            type_obj = item.get("type")
            type_code = (
                type_obj.get("code")
                if isinstance(type_obj, dict)
                else (type_obj if isinstance(type_obj, str) else None)
            )

            decision_obj = item.get("decision")
            decision_code = decision_obj.get("code") if isinstance(decision_obj, dict) else None
            decision_value = decision_obj.get("value") if isinstance(decision_obj, dict) else None

            votings = item.get("votings") or []
            voting_uuids = [
                v.get("uuid")
                for v in votings
                if isinstance(v, dict) and is_valid_uuid(v.get("uuid"))
            ]

            record = {
                "agenda_item_uuid": item_uuid,
                "sitting_uuid": sitting_uuid,
                "sitting_date": sitting_date,
                "sitting_datetime": sitting_datetime,
                "source_file": source_file,
                "order": item.get("order"),
                "steno_title": steno_title,
                "api_title": item.get("title"),
                "document_type": item.get("documentType"),
                "type_code": type_code,
                "stage": item.get("stage"),
                "decision_code": decision_code,
                "decision_value": decision_value,
                "draft_uuid": draft_uuid,
                "draft_mark": draft_mark,
                "draft_title": draft_title,
                "voting_uuids": voting_uuids,
            }

            if item_uuid in existing_records:
                existing_records[item_uuid] = record
                updated += 1
            else:
                existing_records[item_uuid] = record
                added += 1

    return added, updated


def fetch_agenda_items(
    start_date: str | None = None,
    end_date: str | None = None,
    upload: bool = False,
) -> bool:
    """Fetch agenda items and verbatim associations for date range and write to JSONL."""
    if not start_date:
        start_date = (datetime.now() - timedelta(days=UNEDITED_REFETCH_DAYS)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    logger.info("Starting agenda fetch from %s to %s", start_date, end_date)

    target_file = Path(OUTPUT_DIR_PROCESSED) / "agenda_items.jsonl"
    existing_records = load_existing_agenda_items(target_file)
    initial_count = len(existing_records)
    logger.info("Loaded %d existing agenda item records", initial_count)

    month_ranges = get_month_ranges(start_date, end_date)
    has_errors = False
    total_added = 0
    total_updated = 0

    for m_start, m_end in month_ranges:
        logger.info("Fetching agenda items and verbatims for %s to %s...", m_start, m_end)
        agenda_data = fetch_api_with_retry(
            AGENDA_API_URL,
            params={"startDate": m_start, "endDate": m_end, "lang": "et"},
        )
        if agenda_data is None:
            logger.warning("Could not fetch agenda for %s to %s", m_start, m_end)
            has_errors = True
            continue

        verbatims_data = fetch_api_with_retry(
            VERBATIMS_API_URL,
            params={"startDate": m_start, "endDate": m_end, "lang": "et"},
        )
        if verbatims_data is None:
            logger.warning("Could not fetch verbatims for %s to %s", m_start, m_end)
            has_errors = True

        added, updated = process_agenda_and_verbatims(
            agenda_data=agenda_data,
            verbatims_data=verbatims_data,
            existing_records=existing_records,
        )
        total_added += added
        total_updated += updated

    write_agenda_items_atomic(target_file, existing_records)
    logger.info(
        "Saved agenda items: %d added, %d updated (total %d records in file)",
        total_added,
        total_updated,
        len(existing_records),
    )

    if upload:
        logger.info("Uploading agenda_items.jsonl to Backblaze B2...")
        try:
            from scripts.upload_to_b2 import upload_to_b2

            up_ok = upload_to_b2(only_files=["agenda_items.jsonl"])
            if not up_ok:
                logger.error("B2 upload failed for agenda_items.jsonl")
                return False
        except Exception as e:
            logger.error("B2 upload exception for agenda_items.jsonl: %s", e)
            return False

    return not has_errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Riigikogu agenda items and link to verbatims and drafts."
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date in YYYY-MM-DD format (defaults to 60 days ago)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date in YYYY-MM-DD format (defaults to today)",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload agenda_items.jsonl to Backblaze B2 after fetch",
    )
    args = parser.parse_args()

    ok = fetch_agenda_items(
        start_date=args.start_date,
        end_date=args.end_date,
        upload=args.upload,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
