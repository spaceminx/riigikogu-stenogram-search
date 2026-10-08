import glob
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import OUTPUT_DIR_PROCESSED, START_DATE
from src.transform.lemmatizer import lemmatize_text

IGNORED_SPEECH_TYPES = {
    "PRESENCE_CHECK",
    "SESSION_START",
    "SESSION_END",
    "VOTING_EVENT",
}

IGNORED_SPEAKER_NAMES = {
    "kohaloleku kontroll",
    "istung lõppes",
    "istung algas",
    "hääletustulemused",
}


def clean_html(raw_html: str) -> str:
    """Remove HTML tags, decode HTML entities (&nbsp;, &quot;, etc.) and normalize whitespace."""
    if not raw_html:
        return ""
    clean = re.sub(r"<[^>]+>", " ", raw_html)
    clean = html.unescape(clean)
    return " ".join(clean.split()).strip()


def fetch_rich_meeting_data(meeting_code: str, max_retries: int = 3) -> dict | None:
    """Fetch rich meeting details (agenda item PKP IDs and video timestamps) from new stenogram API."""
    if not meeting_code or not meeting_code.isdigit():
        return None
    url = f"https://stenogrammid.riigikogu.ee/api/meeting/{meeting_code}"
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, timeout=(5, 20), headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                time.sleep(2 * attempt)
            elif resp.status_code >= 500:
                time.sleep(1 * attempt)
        except Exception as e:
            if attempt == max_retries:
                print(f"Notice: Could not fetch rich meeting details for {meeting_code}: {e}")
            time.sleep(1)
    return None


def format_stenogram_url(
    meeting_code: str, verbatim_link: str = "", agenda_id: int | str | None = None
) -> str:
    """Construct Riigikogu stenogram URL with the required /et/ language prefix and optional PKP anchor."""
    if meeting_code and meeting_code.isdigit():
        base = f"https://stenogrammid.riigikogu.ee/et/{meeting_code}"
    elif verbatim_link:
        base = re.sub(
            r"^https?://stenogrammid\.riigikogu\.ee/(?!et/|en/|ru/)(\d{12})(.*)$",
            r"https://stenogrammid.riigikogu.ee/et/\1\2",
            verbatim_link,
        )
    else:
        base = verbatim_link

    if base and agenda_id:
        return f"{base}#PKP-{agenda_id}"
    return base


KNOWN_ROLE_KEYWORDS = {
    "minister",
    "esimees",
    "aseesimees",
    "õiguskantsler",
    "riigikontrolör",
    "president",
    "riigisekretär",
    "kantsler",
    "asekantsler",
    "peadirektor",
    "juhataja",
    "ettekandja",
    "kaasettekandja",
    "nõunik",
    "ekspert",
}


def split_speaker_role(full_name: str) -> tuple[str, str | None]:
    """Separate official titles (e.g. 'Peaminister', 'Õiguskantsler', 'Riigikontrolör') from speaker's full name."""
    parts = full_name.strip().split(" ")
    if len(parts) <= 1:
        return full_name, None

    name_parts = []
    i = len(parts) - 1
    while i >= 0:
        word = parts[i]
        word_lower = word.lower()
        if word and word[0].isupper() and not any(kw in word_lower for kw in KNOWN_ROLE_KEYWORDS):
            name_parts.insert(0, word)
            i -= 1
        else:
            break

    if not name_parts:
        return full_name, None

    name = " ".join(name_parts)
    role = " ".join(parts[: i + 1]).strip()
    return name, role if role else None


def get_faction_for_date(faction_map: dict, name: str, date_str: str) -> str | None:
    """Find member's political faction on a given session date from faction history."""
    history = faction_map.get(name, [])
    for h in history:
        if h["start"] <= date_str <= h["end"]:
            return h["faction"]
    return None


def get_month_ranges(start_date: str, end_date: str) -> list[tuple[str, str]]:
    """Generate (start, end) date ranges chunked by calendar months."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    ranges = []
    current = start
    while current <= end:
        next_month = current.replace(day=28) + timedelta(days=4)
        last_day = next_month - timedelta(days=next_month.day)

        chunk_end = min(last_day, end)
        ranges.append((current.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")))
        current = chunk_end + timedelta(days=1)

    return ranges


def save_session_to_jsonl(year_str: str, source_file_key: str, speeches: list[dict]) -> None:
    """Save or update session speeches in yearly JSONL dataset using atomic file writes."""
    out_file = os.path.join(OUTPUT_DIR_PROCESSED, f"{year_str}.jsonl")
    tmp_file = os.path.join(OUTPUT_DIR_PROCESSED, f"{year_str}.jsonl.tmp")

    if not os.path.exists(out_file):
        with open(tmp_file, "w", encoding="utf-8") as f:
            for s in speeches:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        os.replace(tmp_file, out_file)
        return

    # Check if session already exists (e.g. updating an unedited session)
    with open(out_file, encoding="utf-8") as f:
        existing_lines = f.readlines()

    target_needle = f'"source_file": "{source_file_key}"'
    has_existing = any(target_needle in line for line in existing_lines)

    if has_existing:
        if len(speeches) == 0:
            print(f"Warning: Refusing to replace session {source_file_key} with 0 speeches.")
            return

        new_lines = [line for line in existing_lines if target_needle not in line]
        for s in speeches:
            new_lines.append(json.dumps(s, ensure_ascii=False) + "\n")
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        os.replace(tmp_file, out_file)
    else:
        with open(out_file, "a", encoding="utf-8") as f:
            for s in speeches:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")


def compute_duration_seconds(start_time_str: str | None, end_time_str: str | None) -> int | None:
    """Calculate speech duration in seconds from ISO start and end timestamps."""
    if not start_time_str or not end_time_str:
        return None
    try:
        dt_start = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        dt_end = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
        return max(0, round((dt_end - dt_start).total_seconds()))
    except Exception:
        return None


def load_persons_metadata() -> tuple[set[str], dict[str, str]]:
    """Load known MP UUIDs and unambiguous full_name -> uuid mapping from persons.json."""
    p_path = os.path.join(OUTPUT_DIR_PROCESSED, "persons.json")
    if not os.path.exists(p_path):
        return set(), {}
    try:
        with open(p_path, encoding="utf-8") as f:
            persons = json.load(f)
        known_uuids = {p.get("uuid") for p in persons if p.get("uuid")}
        name_counts: dict[str, int] = {}
        for p in persons:
            name = p.get("full_name")
            if name:
                name_counts[name] = name_counts.get(name, 0) + 1
        name_map = {}
        for p in persons:
            name = p.get("full_name")
            uuid_val = p.get("uuid")
            if name and uuid_val and name_counts.get(name) == 1:
                name_map[name] = uuid_val
        return known_uuids, name_map
    except Exception:
        return set(), {}


def load_persons_name_map() -> dict[str, str]:
    """Compatibility wrapper returning name -> uuid map."""
    _, name_map = load_persons_metadata()
    return name_map


def parse_meeting_speeches(
    rich_meeting: dict | None,
    verbatim: dict | None,
    meeting_code: str,
    verbatim_link: str,
    date_formatted: str,
    time_formatted: str,
    source_file_key: str,
    faction_map: dict,
    person_name_map: dict | None = None,
    known_person_uuids: set[str] | None = None,
) -> tuple[list[dict], str]:
    """Extract and lemmatize speech records from a meeting dataset."""
    is_edited = (rich_meeting and rich_meeting.get("meetingStatus") == "EDITED") or bool(
        verbatim and verbatim.get("edited")
    )
    meeting_status = "EDITED" if is_edited else "UNEDITED"

    speeches_to_save = []

    if rich_meeting and rich_meeting.get("stenograph", {}).get("agendaItems"):
        agendas = rich_meeting["stenograph"]["agendaItems"]
        for agenda_item in agendas:
            agenda_id = agenda_item.get("id")
            raw_agenda_name = agenda_item.get("name", "")
            agenda_title = clean_html(raw_agenda_name)
            item_source_url = format_stenogram_url(
                meeting_code=meeting_code,
                verbatim_link=verbatim_link,
                agenda_id=agenda_id,
            )

            for sp in agenda_item.get("speeches", []):
                speaker_raw = sp.get("name", "")
                raw_content = sp.get("content", "")
                raw_text = clean_html(raw_content)
                sp_type = sp.get("speechType")

                if (
                    not raw_text
                    or not speaker_raw
                    or sp_type in IGNORED_SPEECH_TYPES
                    or speaker_raw.lower() in IGNORED_SPEAKER_NAMES
                    or raw_text.startswith("http://")
                    or raw_text.startswith("https://")
                ):
                    continue

                speaker_name, speaker_role = split_speaker_role(speaker_raw)
                speaker_faction = get_faction_for_date(faction_map, speaker_name, date_formatted)
                raw_ems_id = sp.get("emsId")
                speaker_uuid = None

                # 1. Direct match with canonical MP UUID
                if raw_ems_id and known_person_uuids and str(raw_ems_id) in known_person_uuids:
                    speaker_uuid = str(raw_ems_id)
                # 2. Specific disambiguation for Tarmo Tamm by date
                elif speaker_name == "Tarmo Tamm":
                    if date_formatted < "2023-04-10":
                        speaker_uuid = "76afbcdc-b41d-4fc6-b5eb-d0cce01e94d5"
                    else:
                        speaker_uuid = "236e49d6-eecb-4562-8ad4-bedd586bb149"
                # 3. Canonical mapping for unique names (including ministers, e.g. Hanno Pevkur)
                elif person_name_map and speaker_name in person_name_map:
                    speaker_uuid = person_name_map[speaker_name]
                elif raw_ems_id:
                    speaker_uuid = str(raw_ems_id)

                lemmas = lemmatize_text(raw_text)
                video_url = sp.get("parsedVideoLink")

                sp_time_raw = sp.get("startTime")
                end_time_raw = sp.get("endTime")
                duration_seconds = compute_duration_seconds(sp_time_raw, end_time_raw)

                sp_time = time_formatted
                if sp_time_raw and "T" in sp_time_raw:
                    time_part = sp_time_raw.split("T")[1].replace(":", "")[:4]
                    if len(time_part) == 4 and time_part.isdigit():
                        sp_time = time_part

                ext_id = sp.get("id")
                try:
                    ext_id_int = int(ext_id) if ext_id is not None else None
                except (ValueError, TypeError):
                    ext_id_int = None

                speeches_to_save.append(
                    {
                        "date": date_formatted,
                        "time": sp_time,
                        "source_file": source_file_key,
                        "source_url": item_source_url,
                        "agenda_title": agenda_title or None,
                        "video_url": video_url,
                        "speaker": speaker_name,
                        "speaker_role": speaker_role,
                        "speaker_faction": speaker_faction,
                        "speaker_uuid": str(speaker_uuid) if speaker_uuid else None,
                        "ems_id": str(raw_ems_id) if raw_ems_id else None,
                        "speech_type": sp_type,
                        "external_id": ext_id_int,
                        "start_time": sp_time_raw,
                        "end_time": end_time_raw,
                        "duration_seconds": duration_seconds,
                        "text": raw_text,
                        "text_lemmas": lemmas,
                        "status": meeting_status,
                    }
                )
    elif verbatim:
        for agenda_item in verbatim.get("agendaItems", []):
            raw_agenda_name = agenda_item.get("title", "")
            agenda_title = clean_html(raw_agenda_name)
            for event in agenda_item.get("events", []):
                if event.get("type") == "SPEECH":
                    raw_text = event.get("text", "")
                    speaker_raw = event.get("speaker", "")

                    if not raw_text or not speaker_raw:
                        continue

                    speaker_name, speaker_role = split_speaker_role(speaker_raw)
                    speaker_faction = get_faction_for_date(
                        faction_map, speaker_name, date_formatted
                    )
                    speaker_uuid = None
                    if speaker_name == "Tarmo Tamm":
                        if date_formatted < "2023-04-10":
                            speaker_uuid = "76afbcdc-b41d-4fc6-b5eb-d0cce01e94d5"
                        else:
                            speaker_uuid = "236e49d6-eecb-4562-8ad4-bedd586bb149"
                    elif person_name_map and speaker_name in person_name_map:
                        speaker_uuid = person_name_map[speaker_name]

                    lemmas = lemmatize_text(raw_text)

                    speeches_to_save.append(
                        {
                            "date": date_formatted,
                            "time": time_formatted,
                            "source_file": source_file_key,
                            "source_url": format_stenogram_url(
                                meeting_code=meeting_code,
                                verbatim_link=verbatim_link,
                            ),
                            "agenda_title": agenda_title or None,
                            "video_url": None,
                            "speaker": speaker_name,
                            "speaker_role": speaker_role,
                            "speaker_faction": speaker_faction,
                            "speaker_uuid": str(speaker_uuid) if speaker_uuid else None,
                            "ems_id": None,
                            "speech_type": "SPEECH",
                            "external_id": None,
                            "start_time": None,
                            "end_time": None,
                            "duration_seconds": None,
                            "text": raw_text,
                            "text_lemmas": lemmas,
                            "status": meeting_status,
                        }
                    )

    return speeches_to_save, meeting_status


def fetch_and_process_stenograms(
    start_date: str | None = None,
    end_date: str | None = None,
) -> bool:
    """Fetch recent stenograms from Riigikogu API, lemmatize, and append to yearly datasets."""
    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)

    # Load existing meeting codes and source files from processed jsonl files
    processed_meeting_codes = set()
    processed_source_files = set()
    unedited_meeting_codes = set()
    unedited_source_files = set()
    unedited_sessions: dict[str, dict] = {}
    total_existing_records = 0
    latest_existing_date = None
    cutoff_60d = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

    for jsonl_path in glob.glob(os.path.join(OUTPUT_DIR_PROCESSED, "*.jsonl")):
        if os.path.basename(jsonl_path) == "attendance.jsonl":
            continue
        try:
            with open(jsonl_path, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    total_existing_records += 1
                    try:
                        record = json.loads(line)
                        src_file = record.get("source_file")
                        src_url = record.get("source_url")
                        rec_date = record.get("date")
                        if rec_date and (
                            latest_existing_date is None or rec_date > latest_existing_date
                        ):
                            latest_existing_date = rec_date

                        code = None
                        if src_url:
                            candidate_code = src_url.split("#")[0].rstrip("/").split("/")[-1]
                            if candidate_code.isdigit() and len(candidate_code) == 12:
                                code = candidate_code
                        if not code and src_file:
                            clean_c = src_file.split(".")[0].replace("-", "").replace("_", "")
                            if clean_c.isdigit() and len(clean_c) == 12:
                                code = clean_c

                        status = record.get("status")
                        if status == "UNEDITED" or (
                            status is None and rec_date and rec_date >= cutoff_60d
                        ):
                            if src_file:
                                unedited_source_files.add(src_file)
                            if code:
                                unedited_meeting_codes.add(code)
                                y_str = rec_date.split("-")[0] if rec_date else "2026"
                                unedited_sessions[code] = {
                                    "source_file": src_file,
                                    "date": rec_date,
                                    "year": y_str,
                                    "status": status,
                                }
                        else:
                            if src_file:
                                processed_source_files.add(src_file)
                            if code:
                                processed_meeting_codes.add(code)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Notice: Could not read {jsonl_path}: {e}")

    # Remove unedited codes from finalized sets so they can be re-fetched
    processed_meeting_codes.difference_update(unedited_meeting_codes)
    processed_source_files.difference_update(unedited_source_files)

    if not start_date:
        if latest_existing_date:
            latest_dt = datetime.strptime(latest_existing_date, "%Y-%m-%d")
            start_dt = max(datetime.strptime(START_DATE, "%Y-%m-%d"), latest_dt - timedelta(days=7))
            start_date = start_dt.strftime("%Y-%m-%d")
        elif total_existing_records > 0:
            start_date = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
        else:
            start_date = START_DATE

    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    date_ranges = get_month_ranges(start_date, end_date)

    factions_file = os.path.join(OUTPUT_DIR_PROCESSED, "factions_map.json")
    if os.path.exists(factions_file):
        with open(factions_file, encoding="utf-8") as f:
            faction_map = json.load(f)
    else:
        faction_map = {}

    known_person_uuids, person_name_map = load_persons_metadata()

    print(f"Starting API fetch from {start_date} to {end_date}")
    has_errors = False

    for start, end in date_ranges:
        print(f"Fetching {start} to {end}...")
        url = "https://api.riigikogu.ee/api/steno/verbatims"

        time.sleep(6.1)

        verbatims = None
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(
                    url, params={"startDate": start, "endDate": end}, timeout=(5, 30)
                )
                if resp.status_code == 200:
                    verbatims = resp.json()
                    break
                if resp.status_code == 429:
                    print(
                        f"Warning: Rate limited (429) on {start}-{end}. Waiting 15s (attempt {attempt}/{max_retries})..."
                    )
                    time.sleep(15)
                else:
                    print(
                        f"Warning: HTTP {resp.status_code} fetching {start}-{end} (attempt {attempt}/{max_retries})"
                    )
            except requests.exceptions.Timeout:
                print(f"Warning: Timeout fetching {start}-{end} (attempt {attempt}/{max_retries})")
            except requests.exceptions.RequestException as e:
                print(
                    f"Warning: Network error fetching {start}-{end}: {e} (attempt {attempt}/{max_retries})"
                )

            if attempt < max_retries:
                time.sleep(5)

        if not isinstance(verbatims, list):
            print(f"Warning: Skipping {start}-{end} (no valid data received).")
            has_errors = True
            continue

        for verbatim in verbatims:
            try:
                verbatim_link = verbatim.get("link", "")
                meeting_code = verbatim_link.rstrip("/").split("/")[-1] if verbatim_link else ""

                v_date_str = verbatim.get("date")
                if not v_date_str:
                    continue

                v_dt = datetime.strptime(v_date_str.split("T")[0], "%Y-%m-%d")
                year_str = v_dt.strftime("%Y")
                date_formatted = v_dt.strftime("%Y-%m-%d")

                time_formatted = "0000"
                if verbatim_link and len(verbatim_link) >= 4:
                    candidate_time = verbatim_link[-4:]
                    if candidate_time.isdigit():
                        time_formatted = candidate_time

                source_file_key = f"{date_formatted}_{time_formatted}.api"

                if (meeting_code and meeting_code in processed_meeting_codes) or (
                    source_file_key in processed_source_files
                ):
                    continue

                print(f"Processing verbatim: {verbatim.get('title')} ({verbatim.get('date')})")

                rich_meeting = fetch_rich_meeting_data(meeting_code)

                speeches_to_save, meeting_status = parse_meeting_speeches(
                    rich_meeting=rich_meeting,
                    verbatim=verbatim,
                    meeting_code=meeting_code,
                    verbatim_link=verbatim_link,
                    date_formatted=date_formatted,
                    time_formatted=time_formatted,
                    source_file_key=source_file_key,
                    faction_map=faction_map,
                    person_name_map=person_name_map,
                    known_person_uuids=known_person_uuids,
                )

                if speeches_to_save:
                    save_session_to_jsonl(year_str, source_file_key, speeches_to_save)
                    print(
                        f"  -> Saved {len(speeches_to_save)} speeches ({meeting_status}) to {year_str}.jsonl"
                    )

                if meeting_status == "EDITED":
                    if meeting_code:
                        processed_meeting_codes.add(meeting_code)
                    processed_source_files.add(source_file_key)
                    unedited_meeting_codes.discard(meeting_code)
                    unedited_source_files.discard(source_file_key)
                else:
                    if meeting_code:
                        unedited_meeting_codes.add(meeting_code)
                        unedited_sessions[meeting_code] = {
                            "source_file": source_file_key,
                            "date": date_formatted,
                            "year": year_str,
                            "status": "UNEDITED",
                        }
                    unedited_source_files.add(source_file_key)

            except Exception as e:
                print(f"Warning: Error processing verbatim {verbatim.get('title')}: {e}")
                has_errors = True

    # Re-fetch and update unedited meetings directly by code, regardless of date range
    if unedited_sessions:
        print(f"\nChecking {len(unedited_sessions)} unedited sessions for published edits...")
        for meeting_code, info in sorted(
            unedited_sessions.items(), key=lambda x: x[1].get("date") or ""
        ):
            src_file_key = info.get("source_file")
            date_str = info.get("date")
            year_str = info.get("year") or (date_str.split("-")[0] if date_str else "2026")

            if meeting_code in processed_meeting_codes:
                continue

            if date_str:
                try:
                    session_dt = datetime.strptime(date_str, "%Y-%m-%d")
                    if datetime.now() - session_dt > timedelta(days=60):
                        print(
                            f"Notice: Session {meeting_code} ({date_str}) is over 60 days old and still UNEDITED in API. Skipping."
                        )
                        continue
                except ValueError:
                    pass

            time.sleep(2)
            rich_meeting = fetch_rich_meeting_data(meeting_code)
            if not rich_meeting:
                has_errors = True
                continue

            is_edited = rich_meeting.get("meetingStatus") == "EDITED"

            if is_edited or info.get("status") is None:
                time_str = "0000"
                if src_file_key and "_" in src_file_key:
                    t_cand = src_file_key.split("_")[1].split(".")[0]
                    if t_cand.isdigit() and len(t_cand) == 4:
                        time_str = t_cand

                speeches_to_save, determined_status = parse_meeting_speeches(
                    rich_meeting=rich_meeting,
                    verbatim=None,
                    meeting_code=meeting_code,
                    verbatim_link=f"https://stenogrammid.riigikogu.ee/et/{meeting_code}",
                    date_formatted=date_str or "",
                    time_formatted=time_str,
                    source_file_key=src_file_key or f"{date_str}_{time_str}.api",
                    faction_map=faction_map,
                    person_name_map=person_name_map,
                    known_person_uuids=known_person_uuids,
                )

                if speeches_to_save:
                    save_session_to_jsonl(
                        year_str, src_file_key or f"{date_str}_{time_str}.api", speeches_to_save
                    )
                    if determined_status == "EDITED":
                        print(
                            f"  -> Successfully updated unedited session {meeting_code} ({date_str}) to EDITED ({len(speeches_to_save)} speeches)"
                        )
                        processed_meeting_codes.add(meeting_code)
                        if src_file_key:
                            processed_source_files.add(src_file_key)
                        unedited_meeting_codes.discard(meeting_code)
                    else:
                        print(
                            f"  -> Session {meeting_code} ({date_str}) remains UNEDITED ({len(speeches_to_save)} speeches saved)"
                        )

    return not has_errors


if __name__ == "__main__":
    success = fetch_and_process_stenograms()
    sys.exit(0 if success else 1)
