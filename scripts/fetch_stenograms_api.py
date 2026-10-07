import glob
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


def clean_html(raw_html: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    if not raw_html:
        return ""
    clean = re.sub(r"<[^>]+>", " ", raw_html)
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


def split_speaker_role(full_name: str) -> tuple[str, str | None]:
    """Separate official titles (e.g. 'Peaminister') from speaker's full name."""
    parts = full_name.strip().split(" ")
    if len(parts) <= 1:
        return full_name, None

    name_parts = []
    i = len(parts) - 1
    while i >= 0:
        word = parts[i]
        if (
            word
            and word[0].isupper()
            and "minister" not in word.lower()
            and "esimees" not in word.lower()
        ):
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
) -> None:
    """Fetch recent stenograms from Riigikogu API, lemmatize, and append to yearly datasets."""
    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)

    # Load existing verbatim links/dates from processed jsonl files
    processed_uuids = set()
    for jsonl_path in glob.glob(os.path.join(OUTPUT_DIR_PROCESSED, "*.jsonl")):
        if os.path.basename(jsonl_path) == "attendance.jsonl":
            continue
        try:
            with open(jsonl_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        record = json.loads(line)
                        if record.get("source_url"):
                            processed_uuids.add(record["source_url"])
                        if record.get("date"):
                            processed_uuids.add(record["date"])
        except Exception as e:
            print(f"Notice: Could not read {jsonl_path}: {e}")

    if not start_date:
        if processed_uuids:
            # Incremental run: only fetch the last 14 days
            start_date = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
        else:
            start_date = START_DATE

    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    date_ranges = get_month_ranges(start_date, end_date)

    factions_file = os.path.join(OUTPUT_DIR_PROCESSED, "factions_map.json")

    if os.path.exists(factions_file):
        with open(factions_file) as f:
            faction_map = json.load(f)
    else:
        faction_map = {}

    print(f"Starting API fetch from {start_date} to {end_date}")

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
            print(f"Notice: Skipping {start}-{end} (no valid data received).")
            continue

        try:
            for verbatim in verbatims:
                verbatim_link = verbatim.get("link", "")
                # If we don't have a reliable UUID in verbatim root, use the link as the unique ID
                uid = verbatim_link if verbatim_link else str(verbatim.get("date"))

                if uid in processed_uuids:
                    continue

                print(f"Processing verbatim: {verbatim.get('title')} ({verbatim.get('date')})")

                # Extract date and time for our JSONL format
                v_date_str = verbatim.get("date")  # e.g. "2024-01-08T13:00:00.000+00:00"
                if not v_date_str:
                    continue

                v_dt = datetime.strptime(v_date_str.split("T")[0], "%Y-%m-%d")
                year_str = v_dt.strftime("%Y")
                date_formatted = v_dt.strftime("%Y-%m-%d")

                # Extract time from link if possible, or from date string
                # e.g. https://stenogrammid.riigikogu.ee/202401081500
                time_formatted = "0000"
                if verbatim_link and len(verbatim_link) >= 4:
                    time_formatted = verbatim_link[-4:]
                    if not time_formatted.isdigit():
                        time_formatted = "0000"

                meeting_code = verbatim_link.rstrip("/").split("/")[-1] if verbatim_link else ""
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

                            if (
                                not raw_text
                                or not speaker_raw
                                or sp.get("speechType") == "PRESENCE_CHECK"
                                or speaker_raw.lower() == "kohaloleku kontroll"
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

                            speeches_to_save.append(
                                {
                                    "date": date_formatted,
                                    "time": time_formatted,
                                    "source_file": f"{date_formatted}_{time_formatted}.api",
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
                                        "source_file": f"{date_formatted}_{time_formatted}.api",
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

                processed_uuids.add(uid)

        except Exception as e:
            print(f"Error on {start}-{end}: {e}")


if __name__ == "__main__":
    fetch_and_process_stenograms()
