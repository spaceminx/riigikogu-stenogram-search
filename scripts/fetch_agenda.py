#!/usr/bin/env python3
"""Fetch agenda items and verbatim titles from the Riigikogu API and link them to drafts and speeches.

Stores records in data/processed/agenda_items.jsonl.
"""

import argparse
import json
import logging
import os
import re
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

STRUCTURAL_TITLES = (
    "Istungi rakendamine",
    "Infotund",
    "Vaba mikrofon",
    "Muud küsimused",
)

DRAFT_MARK_RE = re.compile(r"\((\d+)\s+[A-ZÕÄÖÜ]+(?:\s+[IV]+)?\)", re.IGNORECASE)
INTERPELLATION_VERBATIM_RE = re.compile(r"\(nr\.?\s*(\d+)\)", re.IGNORECASE)
INTERPELLATION_AGENDA_RE = re.compile(r"^(\d+)\s")


def extract_draft_mark(title: str | None) -> str | None:
    """Extract numeric draft mark from verbatim steno title (e.g. '(366 SE II)' -> '366')."""
    if not title:
        return None
    m = DRAFT_MARK_RE.search(title)
    return m.group(1) if m else None


def extract_reading_stage(title: str | None) -> str | None:
    """Extract reading stage from verbatim steno title."""
    if not title:
        return None
    t_lower = title.lower()
    if "kolmas lugemine" in t_lower:
        return "KOLMAS_LUGEMINE"
    if "teine lugemine" in t_lower:
        return "TEINE_LUGEMINE"
    if "esimene lugemine" in t_lower:
        return "ESIMENE_LUGEMINE"
    return None


def extract_interpellation_nr(title: str | None) -> str | None:
    """Extract interpellation number from verbatim steno title (e.g. '(nr 36)' -> '36')."""
    if not title:
        return None
    m = INTERPELLATION_VERBATIM_RE.search(title)
    return m.group(1) if m else None


def extract_agenda_interpellation_nr(item: dict) -> str | None:
    """Extract interpellation number from agenda item if documentType is interpellationsAgendaItemDocument."""
    doc_type = item.get("documentType") or item.get("document_type")
    if doc_type != "interpellationsAgendaItemDocument":
        return None
    title = clean_html(item.get("title") or "")
    m = INTERPELLATION_AGENDA_RE.match(title)
    return m.group(1) if m else None


def draft_marks_match(mark_digits: str, item_mark: str | int | None) -> bool:
    """Check if verbatim draft mark digits match agenda draft mark (e.g. '366' matches '366 SE' or 366)."""
    if item_mark is None or not mark_digits:
        return False
    item_mark_str = str(item_mark).strip()
    if item_mark_str == mark_digits:
        return True
    parts = item_mark_str.split()
    if parts and parts[0] == mark_digits:
        return True
    return False


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


def match_sitting_fallback(
    sitting_key: str,
    unmatched_agenda_items: list[dict],
    unmatched_verbatim_items: list[dict],
) -> dict[str, dict]:
    """Perform fallback matching within a sitting:
    a) exact title
    b) draft mark (mark + stage, or mark-only if no candidate has same mark and stage)
    c) interpellation number

    Returns dict mapping item_uuid -> {steno_title, source_file, match_method}.
    """
    results: dict[str, dict] = {}
    matched_v_indices: set[int] = set()
    matched_a_uuids: set[str] = set()

    # Step 1: Match by exact title
    # clean_html(api_title) == verbatim_steno_title
    v_by_title: dict[str, list[int]] = {}
    for idx, v in enumerate(unmatched_verbatim_items):
        v_by_title.setdefault(v["steno_title"], []).append(idx)

    a_by_title: dict[str, list[dict]] = {}
    for a in unmatched_agenda_items:
        a_title = clean_html(a.get("title") or "")
        if a_title:
            a_by_title.setdefault(a_title, []).append(a)

    for title, v_indices in v_by_title.items():
        if title in a_by_title:
            a_items = a_by_title[title]
            if len(v_indices) == 1 and len(a_items) == 1:
                v_idx = v_indices[0]
                a_item = a_items[0]
                a_uuid = a_item.get("uuid")
                results[a_uuid] = {
                    "steno_title": unmatched_verbatim_items[v_idx]["steno_title"],
                    "source_file": unmatched_verbatim_items[v_idx]["source_file"],
                    "match_method": "title",
                }
                matched_v_indices.add(v_idx)
                matched_a_uuids.add(a_uuid)
            else:
                logger.warning(
                    "Ambiguous title match in sitting %s for title '%s': %d verbatim items, %d agenda items. Skipping.",
                    sitting_key,
                    title,
                    len(v_indices),
                    len(a_items),
                )

    # Step 2: Match by draft mark + reading
    # 2a: Match by same mark AND stage (or mark alone if verbatim title has no reading words)
    remaining_v = [
        (idx, v) for idx, v in enumerate(unmatched_verbatim_items) if idx not in matched_v_indices
    ]
    remaining_a = [a for a in unmatched_agenda_items if a.get("uuid") not in matched_a_uuids]

    candidates_for_v: dict[int, list[dict]] = {}
    candidates_for_a: dict[str, list[tuple[int, dict]]] = {a.get("uuid"): [] for a in remaining_a}

    for idx, v in remaining_v:
        v_mark = extract_draft_mark(v["steno_title"])
        if not v_mark:
            continue
        v_stage = extract_reading_stage(v["steno_title"])
        candidates_for_v[idx] = []

        for a in remaining_a:
            a_uuid = a.get("uuid")
            rel_draft = a.get("relatedDraft") if isinstance(a.get("relatedDraft"), dict) else None
            a_mark = rel_draft.get("mark") if rel_draft else None
            if not draft_marks_match(v_mark, a_mark):
                continue
            if v_stage is not None and a.get("stage") != v_stage:
                continue
            candidates_for_v[idx].append(a)
            candidates_for_a[a_uuid].append((idx, v))

    ambiguous_v_indices: set[int] = set()
    ambiguous_a_uuids: set[str] = set()

    for idx, a_list in candidates_for_v.items():
        if len(a_list) > 1:
            ambiguous_v_indices.add(idx)
            v_title = unmatched_verbatim_items[idx]["steno_title"]
            logger.warning(
                "Ambiguous draft mark match in sitting %s for verbatim title '%s': %d agenda candidates. Skipping.",
                sitting_key,
                v_title,
                len(a_list),
            )

    for a_uuid, v_list in candidates_for_a.items():
        if len(v_list) > 1:
            ambiguous_a_uuids.add(a_uuid)
            a_item = next(a for a in remaining_a if a.get("uuid") == a_uuid)
            logger.warning(
                "Ambiguous draft mark match in sitting %s for agenda item %s ('%s'): %d verbatim candidates. Skipping.",
                sitting_key,
                a_uuid,
                a_item.get("title"),
                len(v_list),
            )

    for idx, a_list in candidates_for_v.items():
        if idx in ambiguous_v_indices:
            continue
        if len(a_list) == 1:
            a = a_list[0]
            a_uuid = a.get("uuid")
            if a_uuid in ambiguous_a_uuids:
                continue
            if len(candidates_for_a.get(a_uuid, [])) == 1:
                v = unmatched_verbatim_items[idx]
                results[a_uuid] = {
                    "steno_title": v["steno_title"],
                    "source_file": v["source_file"],
                    "match_method": "draft_mark",
                }
                matched_v_indices.add(idx)
                matched_a_uuids.add(a_uuid)

    # 2b: Mark-only fallback if no candidate has the same mark AND stage
    # (e.g. 494 SE has stage VASTU_VOETUD in agenda while steno says "kolmas lugemine")
    remaining_v = [
        (idx, v) for idx, v in enumerate(unmatched_verbatim_items) if idx not in matched_v_indices
    ]
    remaining_a = [a for a in unmatched_agenda_items if a.get("uuid") not in matched_a_uuids]

    mark_only_candidates_v: dict[int, list[dict]] = {}
    mark_only_candidates_a: dict[str, list[tuple[int, dict]]] = {
        a.get("uuid"): [] for a in remaining_a
    }

    for idx, v in remaining_v:
        v_mark = extract_draft_mark(v["steno_title"])
        if not v_mark:
            continue
        v_stage = extract_reading_stage(v["steno_title"])
        if v_stage is None:
            continue
        mark_only_candidates_v[idx] = []

        for a in remaining_a:
            a_uuid = a.get("uuid")
            rel_draft = a.get("relatedDraft") if isinstance(a.get("relatedDraft"), dict) else None
            a_mark = rel_draft.get("mark") if rel_draft else None
            if not draft_marks_match(v_mark, a_mark):
                continue
            mark_only_candidates_v[idx].append(a)
            mark_only_candidates_a[a_uuid].append((idx, v))

    ambiguous_mark_v: set[int] = set()
    ambiguous_mark_a: set[str] = set()

    for idx, a_list in mark_only_candidates_v.items():
        if len(a_list) > 1:
            ambiguous_mark_v.add(idx)
            v_title = unmatched_verbatim_items[idx]["steno_title"]
            logger.warning(
                "Ambiguous mark-only match in sitting %s for verbatim title '%s': %d agenda candidates share mark. Skipping.",
                sitting_key,
                v_title,
                len(a_list),
            )

    for a_uuid, v_list in mark_only_candidates_a.items():
        if len(v_list) > 1:
            ambiguous_mark_a.add(a_uuid)
            a_item = next(a for a in remaining_a if a.get("uuid") == a_uuid)
            logger.warning(
                "Ambiguous mark-only match in sitting %s for agenda item %s ('%s'): %d verbatim candidates share mark. Skipping.",
                sitting_key,
                a_uuid,
                a_item.get("title"),
                len(v_list),
            )

    for idx, a_list in mark_only_candidates_v.items():
        if idx in ambiguous_mark_v:
            continue
        if len(a_list) == 1:
            a = a_list[0]
            a_uuid = a.get("uuid")
            if a_uuid in ambiguous_mark_a:
                continue
            if len(mark_only_candidates_a.get(a_uuid, [])) == 1:
                v = unmatched_verbatim_items[idx]
                results[a_uuid] = {
                    "steno_title": v["steno_title"],
                    "source_file": v["source_file"],
                    "match_method": "draft_mark",
                }
                matched_v_indices.add(idx)
                matched_a_uuids.add(a_uuid)

    # Step 3: Rule c) Interpellation number
    remaining_v = [
        (idx, v) for idx, v in enumerate(unmatched_verbatim_items) if idx not in matched_v_indices
    ]
    remaining_a = [a for a in unmatched_agenda_items if a.get("uuid") not in matched_a_uuids]

    interp_candidates_v: dict[int, list[dict]] = {}
    interp_candidates_a: dict[str, list[tuple[int, dict]]] = {
        a.get("uuid"): [] for a in remaining_a
    }

    for idx, v in remaining_v:
        v_nr = extract_interpellation_nr(v["steno_title"])
        if not v_nr:
            continue
        interp_candidates_v[idx] = []

        for a in remaining_a:
            a_uuid = a.get("uuid")
            a_nr = extract_agenda_interpellation_nr(a)
            if a_nr and a_nr == v_nr:
                interp_candidates_v[idx].append(a)
                interp_candidates_a[a_uuid].append((idx, v))

    ambiguous_interp_v: set[int] = set()
    ambiguous_interp_a: set[str] = set()

    for idx, a_list in interp_candidates_v.items():
        if len(a_list) > 1:
            ambiguous_interp_v.add(idx)
            v_title = unmatched_verbatim_items[idx]["steno_title"]
            logger.warning(
                "Ambiguous interpellation match in sitting %s for verbatim title '%s': %d agenda candidates. Skipping.",
                sitting_key,
                v_title,
                len(a_list),
            )

    for a_uuid, v_list in interp_candidates_a.items():
        if len(v_list) > 1:
            ambiguous_interp_a.add(a_uuid)
            a_item = next(a for a in remaining_a if a.get("uuid") == a_uuid)
            logger.warning(
                "Ambiguous interpellation match in sitting %s for agenda item %s ('%s'): %d verbatim candidates. Skipping.",
                sitting_key,
                a_uuid,
                a_item.get("title"),
                len(v_list),
            )

    for idx, a_list in interp_candidates_v.items():
        if idx in ambiguous_interp_v:
            continue
        if len(a_list) == 1:
            a = a_list[0]
            a_uuid = a.get("uuid")
            if a_uuid in ambiguous_interp_a:
                continue
            if len(interp_candidates_a.get(a_uuid, [])) == 1:
                v = unmatched_verbatim_items[idx]
                results[a_uuid] = {
                    "steno_title": v["steno_title"],
                    "source_file": v["source_file"],
                    "match_method": "interpellation_nr",
                }
                matched_v_indices.add(idx)
                matched_a_uuids.add(a_uuid)

    return results


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

    verbatim_by_uuid: dict[str, dict] = {}
    all_verbatim_entries: list[dict] = []

    if verbatims_data and isinstance(verbatims_data, list):
        for v_sitting in verbatims_data:
            if not isinstance(v_sitting, dict):
                continue
            v_source_file = map_verbatim_to_source_file(v_sitting)
            for v_item in v_sitting.get("agendaItems", []):
                if not isinstance(v_item, dict):
                    continue
                v_uuid = v_item.get("agendaItemUuid")
                raw_title = v_item.get("title", "")
                steno_title = clean_html(raw_title)

                entry = {
                    "v_uuid": v_uuid if is_valid_uuid(v_uuid) else None,
                    "steno_title": steno_title or None,
                    "source_file": v_source_file,
                    "raw": v_item,
                }
                all_verbatim_entries.append(entry)

                if is_valid_uuid(v_uuid):
                    verbatim_by_uuid[v_uuid] = entry

    # Pass 1: Match agenda items by UUID
    match_results: dict[str, dict] = {}
    unmatched_agenda_by_sitting: dict[str, list[dict]] = {}
    matched_verbatim_uuids: set[str] = set()

    for sitting in agenda_data.get("sittings", []):
        if not isinstance(sitting, dict):
            continue
        sitting_datetime = sitting.get("sittingDateTime")
        sitting_date = sitting_datetime.split("T")[0] if sitting_datetime else ""
        sitting_source_file = (
            format_session_source_file(sitting_date, sitting_datetime) or f"{sitting_date}_0000.api"
        )

        for item in sitting.get("agendaItems", []):
            if not isinstance(item, dict):
                continue
            item_uuid = item.get("uuid")
            if not is_valid_uuid(item_uuid):
                continue

            if item_uuid in verbatim_by_uuid:
                matched_verbatim_uuids.add(item_uuid)
                match_results[item_uuid] = {
                    "steno_title": verbatim_by_uuid[item_uuid]["steno_title"],
                    "source_file": verbatim_by_uuid[item_uuid]["source_file"],
                    "match_method": "uuid",
                }
            else:
                unmatched_agenda_by_sitting.setdefault(sitting_source_file, []).append(item)

    # Collect unmatched verbatims per sitting:
    # includes items without valid UUID AND items whose valid UUID was not matched in current batch
    unmatched_verbatims_by_sitting: dict[str, list[dict]] = {}
    for entry in all_verbatim_entries:
        v_uuid = entry["v_uuid"]
        if v_uuid and v_uuid in matched_verbatim_uuids:
            continue
        steno_title = entry["steno_title"]
        if not steno_title or steno_title in STRUCTURAL_TITLES:
            continue
        unmatched_verbatims_by_sitting.setdefault(entry["source_file"], []).append(entry)

    # Pass 2: Fallback matching per sitting
    for sitting_key, unmatched_agenda in unmatched_agenda_by_sitting.items():
        unmatched_verbatims = unmatched_verbatims_by_sitting.get(sitting_key, [])
        if not unmatched_verbatims:
            continue

        fallback_matches = match_sitting_fallback(
            sitting_key, unmatched_agenda, unmatched_verbatims
        )
        match_results.update(fallback_matches)

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

            v_info = match_results.get(item_uuid)
            existing = existing_records.get(item_uuid)
            if v_info:
                steno_title = v_info["steno_title"]
                source_file = v_info["source_file"]
                match_method = v_info["match_method"]
            elif existing:
                steno_title = existing.get("steno_title")
                source_file = existing.get("source_file") or fallback_source_file
                match_method = existing.get("match_method")
            else:
                steno_title = None
                source_file = fallback_source_file
                match_method = None

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
                "match_method": match_method,
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
