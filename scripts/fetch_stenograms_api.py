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


def fetch_rich_meeting_data(meeting_code: str) -> dict | None:
    """Fetch rich meeting details (agenda item PKP IDs and video timestamps) from new stenogram API."""
    if not meeting_code or not meeting_code.isdigit():
        return None
    url = f"https://stenogrammid.riigikogu.ee/api/meeting/{meeting_code}"
    try:
        resp = requests.get(url, timeout=(5, 20), headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"Notice: Could not fetch rich meeting details for {meeting_code}: {e}")
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


def fetch_and_process_stenograms(
    start_date: str | None = None,
    end_date: str | None = None,
) -> bool:
    """Fetch recent stenograms from Riigikogu API, lemmatize, and append to yearly datasets."""
    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)

    # Load existing meeting codes and source files from processed jsonl files
    processed_meeting_codes = set()
    processed_source_files = set()
    total_existing_records = 0

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
                        if src_file:
                            processed_source_files.add(src_file)
                        src_url = record.get("source_url")
                        if src_url:
                            # Extract meeting code e.g. "https://stenogrammid.riigikogu.ee/et/202609141500#PKP-..." -> "202609141500"
                            code = src_url.split("#")[0].rstrip("/").split("/")[-1]
                            if code.isdigit():
                                processed_meeting_codes.add(code)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Notice: Could not read {jsonl_path}: {e}")

    if not start_date:
        if total_existing_records > 0:
            # Incremental run: only fetch the last 14 days
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

    print(f"Starting API fetch from {start_date} to {end_date}")
    has_errors = False

    for start, end in date_ranges:
        print(f"Fetching {start} to {end}...")
        url = "https://api.riigikogu.ee/api/steno/verbatims"

        # Respect rate limits (12 req/min)
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

        try:
            for verbatim in verbatims:
                verbatim_link = verbatim.get("link", "")
                meeting_code = verbatim_link.rstrip("/").split("/")[-1] if verbatim_link else ""

                # Extract date and time for our JSONL format
                v_date_str = verbatim.get("date")  # e.g. "2024-01-08T13:00:00.000+00:00"
                if not v_date_str:
                    continue

                v_dt = datetime.strptime(v_date_str.split("T")[0], "%Y-%m-%d")
                year_str = v_dt.strftime("%Y")
                date_formatted = v_dt.strftime("%Y-%m-%d")

                # Extract time from link if possible, or from date string
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
                            speaker_faction = get_faction_for_date(
                                faction_map, speaker_name, date_formatted
                            )
                            lemmas = lemmatize_text(raw_text)
                            video_url = sp.get("parsedVideoLink")

                            # Extract speech specific start time if available
                            sp_time_raw = sp.get("startTime")
                            sp_time = time_formatted
                            if sp_time_raw and "T" in sp_time_raw:
                                time_part = sp_time_raw.split("T")[1].replace(":", "")[:4]
                                if len(time_part) == 4 and time_part.isdigit():
                                    sp_time = time_part

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
                                    "text": raw_text,
                                    "text_lemmas": lemmas,
                                }
                            )
                else:
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
                                        "text": raw_text,
                                        "text_lemmas": lemmas,
                                    }
                                )

                if speeches_to_save:
                    out_file = os.path.join(OUTPUT_DIR_PROCESSED, f"{year_str}.jsonl")
                    with open(out_file, "a", encoding="utf-8") as f:
                        for s in speeches_to_save:
                            f.write(json.dumps(s, ensure_ascii=False) + "\n")

                    print(f"  -> Saved {len(speeches_to_save)} speeches to {year_str}.jsonl")

                if meeting_code:
                    processed_meeting_codes.add(meeting_code)
                processed_source_files.add(source_file_key)

        except Exception as e:
            print(f"Error on {start}-{end}: {e}")
            has_errors = True

    return not has_errors


if __name__ == "__main__":
    success = fetch_and_process_stenograms()
    sys.exit(0 if success else 1)
