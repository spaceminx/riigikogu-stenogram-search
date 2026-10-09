"""History backfill script for enriching historical Riigikogu transcripts (2019-2026).

Fetches rich meeting details (external_id, ems_id, speech_type, start_time, duration, etc.)
from https://stenogrammid.riigikogu.ee/api/meeting/{code} and updates local yearly JSONL datasets.
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import requests

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import OUTPUT_DIR_PROCESSED, START_DATE, UNEDITED_REFETCH_DAYS
from scripts.fetch_stenograms_api import (
    fetch_rich_meeting_data,
    get_month_ranges,
    link_speech_aliases,
    load_persons_metadata,
    parse_meeting_speeches,
)
from scripts.upload_to_b2 import upload_to_b2


def get_default_end_date(now: datetime | None = None) -> str:
    """Default end-date is today minus UNEDITED_REFETCH_DAYS."""
    now = now or datetime.now()
    return (now - timedelta(days=UNEDITED_REFETCH_DAYS)).strftime("%Y-%m-%d")


def load_backfill_state(state_file: str) -> set[str]:
    """Load previously processed meeting codes from state file."""
    if os.path.exists(state_file):
        try:
            with open(state_file, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
                if isinstance(data, dict):
                    return set(data.get("processed_meeting_codes", []))
        except Exception as e:
            print(f"Warning: Could not read backfill state: {e}")
    return set()


def save_backfill_state(state_file: str, processed_codes: set[str]) -> None:
    """Save processed meeting codes atomically."""
    tmp_file = f"{state_file}.tmp"
    data = {
        "processed_meeting_codes": sorted(processed_codes),
        "last_updated": datetime.now().isoformat(),
    }
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_file, state_file)


def load_year_speeches(
    year_str: str, processed_dir: str = OUTPUT_DIR_PROCESSED
) -> tuple[list[dict], dict[str, list[dict]], dict[str, str]]:
    """Load existing speeches, index by source_file and build lemma cache for a given year."""
    all_speeches: list[dict] = []
    speeches_by_source: dict[str, list[dict]] = defaultdict(list)
    lemma_cache: dict[str, str] = {}

    jsonl_path = os.path.join(processed_dir, f"{year_str}.jsonl")
    if os.path.exists(jsonl_path):
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    record = json.loads(line_str)
                    all_speeches.append(record)
                    src = record.get("source_file")
                    if src:
                        speeches_by_source[src].append(record)
                    text = record.get("text")
                    lemmas = record.get("text_lemmas")
                    if text and lemmas:
                        lemma_cache[text] = lemmas
                except json.JSONDecodeError:
                    continue

    return all_speeches, speeches_by_source, lemma_cache


def replace_or_append_session(
    all_speeches: list[dict], source_file: str, new_speeches: list[dict]
) -> list[dict]:
    """Replace an existing session in place or append new session speeches."""
    first_idx = None
    remaining: list[dict] = []
    for sp in all_speeches:
        if sp.get("source_file") == source_file:
            if first_idx is None:
                first_idx = len(remaining)
        else:
            remaining.append(sp)

    if first_idx is not None:
        return remaining[:first_idx] + new_speeches + remaining[first_idx:]
    else:
        return remaining + new_speeches


def write_year_file_atomic(
    year_str: str, speeches: list[dict], processed_dir: str = OUTPUT_DIR_PROCESSED
) -> None:
    """Atomically overwrite yearly dataset file using a temporary file."""
    jsonl_path = os.path.join(processed_dir, f"{year_str}.jsonl")
    tmp_path = f"{jsonl_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        for sp in speeches:
            f.write(json.dumps(sp, ensure_ascii=False) + "\n")
    os.replace(tmp_path, jsonl_path)


def fetch_month_verbatims(
    start_date: str,
    end_date: str,
    max_retries: int = 3,
    sleep_delay: float = 6.1,
) -> list[dict] | None:
    """Fetch monthly verbatim overview list with rate-limiting and 429 retry."""
    time.sleep(sleep_delay)
    url = "https://api.riigikogu.ee/api/steno/verbatims"
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(
                url, params={"startDate": start_date, "endDate": end_date}, timeout=(5, 30)
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                print(
                    f"Warning: Rate limited (429) on {start_date}-{end_date}. Waiting 15s (attempt {attempt}/{max_retries})..."
                )
                time.sleep(15)
            else:
                print(
                    f"Warning: HTTP {resp.status_code} fetching {start_date}-{end_date} (attempt {attempt}/{max_retries})"
                )
        except requests.exceptions.Timeout:
            print(
                f"Warning: Timeout fetching {start_date}-{end_date} (attempt {attempt}/{max_retries})"
            )
        except requests.exceptions.RequestException as e:
            print(
                f"Warning: Network error fetching {start_date}-{end_date}: {e} (attempt {attempt}/{max_retries})"
            )
        if attempt < max_retries:
            time.sleep(5)
    return None


def run_upload_only(
    year: str | int | None = None,
    processed_dir: str = OUTPUT_DIR_PROCESSED,
) -> bool:
    """Upload specified year or backfilled years to B2 without fetching or modifying data."""
    files_to_upload: list[str] = []

    if year:
        files_to_upload.append(f"{year}.jsonl")
    else:
        report_file = os.path.join(processed_dir, "backfill_report.json")
        if os.path.exists(report_file):
            try:
                with open(report_file, encoding="utf-8") as f:
                    rep_data = json.load(f)
                for y_key, y_val in rep_data.items():
                    if isinstance(y_val, dict) and (
                        y_val.get("replaced", 0) > 0 or y_val.get("added", 0) > 0
                    ):
                        files_to_upload.append(f"{y_key}.jsonl")
            except Exception as e:
                print(f"Error reading backfill report {report_file}: {e}")

    if not files_to_upload:
        print(
            "ERROR: No files to upload found. Specify --year or ensure backfill_report.json has modified years."
        )
        return False

    print(f"Uploading files to B2 (upload-only): {files_to_upload}")
    success = upload_to_b2(only_files=files_to_upload)
    if not success:
        print("ERROR: B2 upload failed or was rejected.")
        return False
    return True


def run_backfill(
    start_date: str | None = None,
    end_date: str | None = None,
    year: str | int | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    sleep_delay: float = 2.0,
    upload: bool = False,
    upload_only: bool = False,
    report_file: str | None = None,
    processed_dir: str = OUTPUT_DIR_PROCESSED,
    year_speeches_dict: dict[str, list[dict]] | None = None,
) -> dict[str, Any]:
    """Execute the history backfill pipeline."""
    if upload_only:
        ok = run_upload_only(year=year, processed_dir=processed_dir)
        if not ok:
            raise RuntimeError("No files found to upload in upload-only mode or upload failed.")
        return {}

    # Mandatory metadata check before any network or processing activity
    factions_file = os.path.join(processed_dir, "factions_map.json")
    persons_file = os.path.join(processed_dir, "persons.json")

    if not os.path.isfile(factions_file):
        raise RuntimeError(f"Missing required metadata file: {factions_file}")
    if not os.path.isfile(persons_file):
        raise RuntimeError(f"Missing required metadata file: {persons_file}")

    try:
        with open(factions_file, encoding="utf-8") as f:
            faction_map = json.load(f)
    except Exception as e:
        raise RuntimeError(f"Could not read metadata file {factions_file}: {e}") from e

    if not isinstance(faction_map, dict) or not faction_map:
        raise RuntimeError(f"Metadata file {factions_file} is empty or invalid.")

    try:
        with open(persons_file, encoding="utf-8") as f:
            persons_list = json.load(f)
    except Exception as e:
        raise RuntimeError(f"Could not read metadata file {persons_file}: {e}") from e

    if not isinstance(persons_list, list) or not persons_list:
        raise RuntimeError(f"Metadata file {persons_file} is empty or invalid.")

    known_person_uuids, person_name_map, uuid_to_name_map = load_persons_metadata(
        processed_dir=processed_dir
    )

    # Resolve dates
    effective_start = start_date
    if not effective_start:
        effective_start = f"{year}-01-01" if year else START_DATE

    effective_end = end_date
    if not effective_end:
        default_cutoff = get_default_end_date()
        effective_end = min(default_cutoff, f"{year}-12-31") if year else default_cutoff

    if effective_start > effective_end:
        print(
            f"Notice: start_date ({effective_start}) > end_date ({effective_end}). Nothing to do."
        )
        return {}

    state_file = os.path.join(processed_dir, "backfill_state.json")
    processed_meeting_codes = load_backfill_state(state_file)

    date_ranges = get_month_ranges(effective_start, effective_end)
    if year:
        date_ranges = [
            (s, e) for s, e in date_ranges if s.startswith(str(year)) or e.startswith(str(year))
        ]

    year_speeches: dict[str, list[dict]] = (
        year_speeches_dict if year_speeches_dict is not None else {}
    )
    year_speeches_by_source: dict[str, dict[str, list[dict]]] = {}
    year_lemma_caches: dict[str, dict[str, str]] = {}
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "processed": 0,
            "replaced": 0,
            "added": 0,
            "skipped_no_rich": 0,
            "suspicious": 0,
            "suspicious_sessions": [],
            "speeches_before": 0,
            "speeches_after": 0,
            "external_id_count": 0,
            "speaker_uuid_count": 0,
        }
    )
    modified_years: set[str] = set()
    total_processed_meetings = 0
    pending_month_updates: dict[str, dict[str, list[dict]]] = defaultdict(dict)
    current_year: str | None = None

    def finalize_year(y: str) -> None:
        """Apply pending changes, record final stats, write to disk, and evict data from memory."""
        if y not in year_speeches:
            return

        if y in pending_month_updates and pending_month_updates[y]:
            for src_key, new_sp_list in pending_month_updates[y].items():
                year_speeches[y] = replace_or_append_session(year_speeches[y], src_key, new_sp_list)
                for sp in new_sp_list:
                    t = sp.get("text")
                    tl = sp.get("text_lemmas")
                    if t and tl:
                        year_lemma_caches[y][t] = tl
            if not dry_run:
                write_year_file_atomic(y, year_speeches[y], processed_dir)
                modified_years.add(y)
            pending_month_updates.pop(y, None)

        sp_list = year_speeches[y]
        stats[y]["speeches_after"] = len(sp_list)
        stats[y]["external_id_count"] = sum(1 for s in sp_list if s.get("external_id") is not None)
        stats[y]["speaker_uuid_count"] = sum(
            1 for s in sp_list if s.get("speaker_uuid") is not None
        )

        year_speeches.pop(y, None)
        year_speeches_by_source.pop(y, None)
        year_lemma_caches.pop(y, None)

    print(
        f"Starting history backfill from {effective_start} to {effective_end} "
        f"(dry_run={dry_run}, limit={limit})"
    )

    for m_start, m_end in date_ranges:
        if limit is not None and total_processed_meetings >= limit:
            break

        m_year = m_start.split("-")[0]
        if current_year is not None and m_year != current_year:
            finalize_year(current_year)
        current_year = m_year

        print(f"Checking verbatims for {m_start} .. {m_end}")
        verbatims = fetch_month_verbatims(m_start, m_end)
        if not verbatims:
            continue

        for verbatim in verbatims:
            if limit is not None and total_processed_meetings >= limit:
                break

            verbatim_link = verbatim.get("link", "")
            meeting_code = verbatim_link.rstrip("/").split("/")[-1] if verbatim_link else ""
            if not meeting_code:
                continue

            v_date = verbatim.get("date", "").split("T")[0]
            if not v_date:
                continue

            if v_date < effective_start or v_date > effective_end:
                continue
            if year and not v_date.startswith(str(year)):
                continue

            # Resumption check
            if meeting_code in processed_meeting_codes:
                continue

            v_year = v_date.split("-")[0]

            if v_year not in year_speeches:
                all_sp, by_src, l_cache = load_year_speeches(v_year, processed_dir)
                year_speeches[v_year] = all_sp
                year_speeches_by_source[v_year] = by_src
                year_lemma_caches[v_year] = l_cache
                stats[v_year]["speeches_before"] = len(all_sp)
                stats[v_year]["speeches_after"] = len(all_sp)
                stats[v_year]["external_id_count"] = sum(
                    1 for s in all_sp if s.get("external_id") is not None
                )
                stats[v_year]["speaker_uuid_count"] = sum(
                    1 for s in all_sp if s.get("speaker_uuid") is not None
                )

            time_formatted = "0000"
            if verbatim_link and len(verbatim_link) >= 4:
                candidate_time = verbatim_link[-4:]
                if candidate_time.isdigit():
                    time_formatted = candidate_time

            source_file_key = f"{v_date}_{time_formatted}.api"

            rich_data = fetch_rich_meeting_data(meeting_code)
            if sleep_delay > 0:
                time.sleep(sleep_delay)

            if not rich_data or not rich_data.get("stenograph", {}).get("agendaItems"):
                print(
                    f"Notice: No rich meeting data for {meeting_code} ({source_file_key}). Skipping."
                )
                stats[v_year]["skipped_no_rich"] += 1
                stats[v_year]["processed"] += 1
                # Transient error: do not add to processed_meeting_codes so it will be retried
                total_processed_meetings += 1
                continue

            new_speeches, _ = parse_meeting_speeches(
                rich_meeting=rich_data,
                verbatim=None,
                meeting_code=meeting_code,
                verbatim_link=verbatim_link,
                date_formatted=v_date,
                time_formatted=time_formatted,
                source_file_key=source_file_key,
                faction_map=faction_map,
                person_name_map=person_name_map,
                known_person_uuids=known_person_uuids,
                uuid_to_name_map=uuid_to_name_map,
                lemma_cache=year_lemma_caches[v_year],
            )

            old_speeches = year_speeches_by_source[v_year].get(source_file_key, [])
            old_count = len(old_speeches)
            new_count = len(new_speeches)

            if old_count > 0:
                if new_count < (old_count * 0.9):
                    print(
                        f"Warning: Suspicious session {meeting_code} ({source_file_key}): "
                        f"{new_count} speeches < 90% of existing {old_count}. Not replacing."
                    )
                    stats[v_year]["suspicious"] += 1
                    stats[v_year]["suspicious_sessions"].append(meeting_code)
                    stats[v_year]["processed"] += 1
                    processed_meeting_codes.add(meeting_code)
                    total_processed_meetings += 1
                    continue

                link_speech_aliases(old_speeches, new_speeches)
                stats[v_year]["replaced"] += 1
                stats[v_year]["processed"] += 1
                pending_month_updates[v_year][source_file_key] = new_speeches
                processed_meeting_codes.add(meeting_code)
                total_processed_meetings += 1
            else:
                stats[v_year]["added"] += 1
                stats[v_year]["processed"] += 1
                pending_month_updates[v_year][source_file_key] = new_speeches
                processed_meeting_codes.add(meeting_code)
                total_processed_meetings += 1

        # Apply monthly batch updates
        for upd_year, upd_sessions in list(pending_month_updates.items()):
            if upd_year in year_speeches:
                for src_key, new_sp_list in upd_sessions.items():
                    year_speeches[upd_year] = replace_or_append_session(
                        year_speeches[upd_year], src_key, new_sp_list
                    )
                    year_speeches_by_source[upd_year][src_key] = new_sp_list
                    for sp in new_sp_list:
                        t = sp.get("text")
                        tl = sp.get("text_lemmas")
                        if t and tl:
                            year_lemma_caches[upd_year][t] = tl

                if not dry_run:
                    write_year_file_atomic(upd_year, year_speeches[upd_year], processed_dir)
                    modified_years.add(upd_year)

        if not dry_run and processed_meeting_codes:
            save_backfill_state(state_file, processed_meeting_codes)

        pending_month_updates.clear()

    # Finalize any remaining open year in memory
    if current_year is not None:
        finalize_year(current_year)
    for remaining_y in list(year_speeches.keys()):
        finalize_year(remaining_y)

    # Compile final report
    report: dict[str, Any] = {}
    for y in sorted(stats.keys()):
        y_stats = stats[y]
        report[y] = {
            "processed": y_stats["processed"],
            "replaced": y_stats["replaced"],
            "added": y_stats["added"],
            "skipped_no_rich": y_stats["skipped_no_rich"],
            "suspicious": y_stats["suspicious"],
            "suspicious_sessions": y_stats["suspicious_sessions"],
            "speeches_before": y_stats["speeches_before"],
            "speeches_after": y_stats.get("speeches_after", y_stats["speeches_before"]),
            "external_id_count": y_stats.get("external_id_count", 0),
            "speaker_uuid_count": y_stats.get("speaker_uuid_count", 0),
        }

    # Print summary report
    print("\n" + "=" * 80)
    print("HISTORY BACKFILL REPORT")
    print("=" * 80)
    for y, rep in report.items():
        print(
            f"Year {y}: processed={rep['processed']}, replaced={rep['replaced']}, "
            f"added={rep['added']}, skipped_no_rich={rep['skipped_no_rich']}, "
            f"suspicious={rep['suspicious']}, speeches={rep['speeches_before']} -> {rep['speeches_after']}, "
            f"with external_id={rep['external_id_count']}, with speaker_uuid={rep['speaker_uuid_count']}"
        )
    print("=" * 80 + "\n")

    if not dry_run:
        target_report_file = report_file or os.path.join(processed_dir, "backfill_report.json")
        try:
            with open(target_report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"Report saved to {target_report_file}")
        except Exception as e:
            print(f"Warning: Could not save report JSON: {e}")
    elif report_file is not None:
        try:
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Could not save report JSON: {e}")

    # Optional B2 upload
    if upload:
        if dry_run:
            print("Notice: Dry-run active. Skipping upload to B2.")
        else:
            files_to_upload = [f"{y}.jsonl" for y in sorted(modified_years)]
            if not files_to_upload:
                # If run solely with --upload, check report or args
                for y, rep in report.items():
                    if rep.get("replaced", 0) > 0 or rep.get("added", 0) > 0:
                        files_to_upload.append(f"{y}.jsonl")
            if not files_to_upload and year:
                files_to_upload.append(f"{year}.jsonl")

            if not files_to_upload:
                print("Notice: No modified files found to upload.")
            else:
                print(f"Uploading modified files to B2: {files_to_upload}")
                success = upload_to_b2(only_files=files_to_upload)
                if not success:
                    raise RuntimeError("Upload to B2 failed or was rejected.")

    return report


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """CLI arguments parser."""
    parser = argparse.ArgumentParser(
        description="Backfill rich metadata for historical Riigikogu stenograms (2019-2026)."
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help=f"Start date (YYYY-MM-DD, default: {START_DATE} or start of --year).",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date (YYYY-MM-DD, default: today minus UNEDITED_REFETCH_DAYS).",
    )
    parser.add_argument(
        "--year",
        type=str,
        default=None,
        help="Process a single year only (e.g. 2019).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not modify dataset files on disk, only report changes.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of meetings to process (for testing).",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=2.0,
        help="Delay in seconds between rich API calls (default: 2.0).",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload modified year files to Backblaze B2.",
    )
    parser.add_argument(
        "--upload-only",
        action="store_true",
        help="Only upload modified files to Backblaze B2 without fetching or modifying transcripts.",
    )
    return parser.parse_args(args)


if __name__ == "__main__":
    cli_args = parse_args()
    if cli_args.upload_only:
        ok = run_upload_only(year=cli_args.year)
        sys.exit(0 if ok else 1)
    try:
        run_backfill(
            start_date=cli_args.start_date,
            end_date=cli_args.end_date,
            year=cli_args.year,
            dry_run=cli_args.dry_run,
            limit=cli_args.limit,
            sleep_delay=cli_args.sleep,
            upload=cli_args.upload,
            upload_only=cli_args.upload_only,
        )
    except Exception as exc:
        print(f"Error during backfill: {exc}")
        sys.exit(1)
