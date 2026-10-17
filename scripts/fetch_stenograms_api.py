import difflib
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

from config import IGNORED_VERBATIMS, OUTPUT_DIR_PROCESSED, START_DATE, UNEDITED_REFETCH_DAYS
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


def slugify_estonian(text: str) -> str:
    """Generate a clean ASCII slug transliterating Estonian special characters."""
    tr_map = str.maketrans(
        {
            "ä": "a",
            "ö": "o",
            "õ": "o",
            "ü": "u",
            "Ä": "a",
            "Ö": "o",
            "Õ": "o",
            "Ü": "u",
            "š": "s",
            "ž": "z",
            "Š": "s",
            "Ž": "z",
        }
    )
    cleaned = text.translate(tr_map).lower()
    return re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")


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
                backoff = 10 * (2 ** (attempt - 1))
                print(
                    f"Notice: Rate limited (429) for meeting {meeting_code}. Waiting {backoff}s (attempt {attempt}/{max_retries})..."
                )
                time.sleep(backoff)
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
    "kandidaat",
}


def split_speaker_role(full_name: str) -> tuple[str, str | None]:
    """Separate official titles (e.g. 'Peaminister', 'Õiguskantsler', 'Riigikontrolör') from speaker's full name."""
    parts = full_name.strip().split(" ")
    if len(parts) <= 1:
        return full_name, None

    # Check for suffix role: trailing words that are lowercase and contain a role keyword
    suffix_parts = []
    j = len(parts) - 1
    while j >= 0 and parts[j] and parts[j][0].islower():
        suffix_parts.insert(0, parts[j])
        j -= 1

    suffix_role = None
    if suffix_parts and j >= 0:
        if any(any(kw in w.lower() for kw in KNOWN_ROLE_KEYWORDS) for w in suffix_parts):
            role_str = " ".join(suffix_parts)
            suffix_role = role_str[0].upper() + role_str[1:]
            parts = parts[: j + 1]

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
        if suffix_role:
            return " ".join(parts), suffix_role
        return full_name, None

    name = " ".join(name_parts)
    prefix_role = " ".join(parts[: i + 1]).strip()

    if prefix_role and suffix_role:
        role = f"{prefix_role} {suffix_role}"
    elif prefix_role:
        role = prefix_role
    elif suffix_role:
        role = suffix_role
    else:
        role = None

    return name, role


def get_faction_for_date(faction_map: dict, name: str, date_str: str) -> str | None:
    """Find member's political faction on a given session date from faction history."""
    history = faction_map.get(name, [])
    for h in history:
        if h["start"] <= date_str <= h["end"]:
            return h["faction"]
    return None


_logged_name_changes: set[tuple[str, str]] = set()
_person_factions_cache: dict[str, list[dict]] | None = None


def _get_person_factions(processed_dir: str = OUTPUT_DIR_PROCESSED) -> dict[str, list[dict]]:
    """Load and cache person_factions.json for MP membership period lookups."""
    global _person_factions_cache
    if _person_factions_cache is not None:
        return _person_factions_cache
    pf_file = os.path.join(processed_dir, "person_factions.json")
    if os.path.exists(pf_file):
        try:
            with open(pf_file, encoding="utf-8") as f:
                _person_factions_cache = json.load(f)
                return _person_factions_cache
        except Exception:
            pass
    return {}


def is_member_on_date(
    person_uuid: str, speech_date: str, factions_dict: dict[str, list[dict]]
) -> bool:
    """Check if person was a member of Riigikogu on given speech date based on faction intervals."""
    intervals = factions_dict.get(person_uuid, [])
    if not intervals:
        return False
    dt = speech_date[:10]
    for interval in intervals:
        start = interval.get("start", "")
        end = interval.get("end", "")
        if start and end and start <= dt <= end:
            return True
    return False


def is_ambiguous_person_name(
    speaker_name: str,
    uuid_to_name_map: dict[str, str] | None,
    person_name_map: dict[str, str] | None,
) -> bool:
    """Check if a name belongs to multiple individuals in persons.json."""
    if uuid_to_name_map:
        matches = [u for u, name in uuid_to_name_map.items() if name == speaker_name]
        if len(matches) > 1:
            return True
    if person_name_map is not None and uuid_to_name_map is not None:
        if speaker_name in uuid_to_name_map.values() and speaker_name not in person_name_map:
            return True
    return False


def resolve_speaker_uuid(
    speaker_name: str,
    ems_id: str | None,
    date: str,
    known_uuids: set[str] | None,
    uuid_to_name_map: dict[str, str] | None,
    person_name_map: dict[str, str] | None,
    person_factions: dict[str, list[dict]] | None = None,
    speech_key: str | None = None,
) -> tuple[str | None, str]:
    """Resolve canonical MP UUID for a speaker.

    Priority order:
    1. For ambiguous names (multiple individuals with identical full name):
       Resolved by the member's faction membership period in person_factions.json.
       If none or >1 match covers the date, leave speaker_uuid empty and log the speech key.
    2. ems_id in known_uuids and name matches canonical name -> (ems_id, "ems")
    3. ems_id in known_uuids, name does not match, but first name matches (case-insensitive)
       and speaker_name is not any other person's canonical name -> (ems_id, "ems_name_change")
    4. person_name_map match -> (uuid, "name")
    5. otherwise -> (None, "unresolved")
    """
    raw_ems = str(ems_id).strip() if ems_id else None
    dt = date[:10] if date else ""

    if uuid_to_name_map is None:
        p_known, p_name_map, p_uuid_map = load_persons_metadata()
        if p_known:
            if known_uuids is None:
                known_uuids = p_known
            if person_name_map is None:
                person_name_map = p_name_map
            uuid_to_name_map = p_uuid_map

    # 1. Ambiguous name handling (multiple persons with the same name in persons.json)
    if is_ambiguous_person_name(speaker_name, uuid_to_name_map, person_name_map):
        factions = person_factions if person_factions is not None else _get_person_factions()
        candidate_uuids = [
            u for u, name in (uuid_to_name_map or {}).items() if name == speaker_name
        ]
        covering = [u for u in candidate_uuids if is_member_on_date(u, dt, factions)]
        if len(covering) == 1:
            matched_uuid = covering[0]
            if raw_ems == matched_uuid:
                return (matched_uuid, "ems")
            return (matched_uuid, "member_period")

        key_info = f" (speech_key: {speech_key})" if speech_key else ""
        print(
            f"Notice: Ambiguous speaker '{speaker_name}' on {dt} has {len(covering)} matching faction periods{key_info}"
        )
        return (None, "unresolved")

    # 2. Standard unambiguous resolution via ems_id
    if raw_ems:
        if known_uuids is None:
            if not uuid_to_name_map or uuid_to_name_map.get(raw_ems) == speaker_name:
                return (raw_ems, "ems")
        elif raw_ems in known_uuids:
            canonical_name = uuid_to_name_map.get(raw_ems) if uuid_to_name_map else None
            if not uuid_to_name_map or canonical_name == speaker_name:
                return (raw_ems, "ems")

            # Name change check: first name matches, and speaker_name is not another person's canonical name
            all_canonical_names = (
                set(uuid_to_name_map.values())
                if uuid_to_name_map
                else (set(person_name_map.keys()) if person_name_map else set())
            )
            speaker_first = speaker_name.strip().split()[0] if speaker_name.strip() else ""
            canonical_first = (
                canonical_name.strip().split()[0]
                if canonical_name and canonical_name.strip()
                else ""
            )

            if (
                speaker_first
                and canonical_first
                and speaker_first.lower() == canonical_first.lower()
                and speaker_name not in all_canonical_names
            ):
                pair = (speaker_name, canonical_name)
                if pair not in _logged_name_changes:
                    _logged_name_changes.add(pair)
                    print(
                        f"Notice: Name change resolved for '{speaker_name}' -> '{canonical_name}' ({raw_ems})"
                    )
                return (raw_ems, "ems_name_change")

    # 3. person_name_map
    if person_name_map and speaker_name in person_name_map:
        return (person_name_map[speaker_name], "name")

    # 4. Unresolved
    return (None, "unresolved")


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


def link_speech_aliases(old_speeches: list[dict], new_speeches: list[dict]) -> list[dict]:
    """Bind previous aliases to preserve permalinks across edits."""
    if not old_speeches or not new_speeches:
        return new_speeches

    new_speeches_by_ext_id = {sp["external_id"]: sp for sp in new_speeches if sp.get("external_id")}

    for old_sp in old_speeches:
        old_ext = old_sp.get("external_id")
        old_key = old_sp.get("speech_key")
        prev_exts = old_sp.get("previous_external_ids") or []
        prev_keys = old_sp.get("previous_speech_keys") or []
        if not old_ext and not old_key and not prev_exts and not prev_keys:
            continue

        best_match = None
        if old_ext and old_ext in new_speeches_by_ext_id:
            best_match = new_speeches_by_ext_id[old_ext]
        else:
            best_score = -1

            old_time_str = old_sp.get("start_time")
            old_time = None
            if old_time_str:
                try:
                    old_time = datetime.fromisoformat(old_time_str.replace("Z", "+00:00"))
                except Exception:
                    pass

            old_text = old_sp.get("text", "")
            old_speaker = old_sp.get("speaker")

            for new_sp in new_speeches:
                if new_sp.get("speaker") != old_speaker:
                    continue

                new_time_str = new_sp.get("start_time")
                new_time = None
                if new_time_str:
                    try:
                        new_time = datetime.fromisoformat(new_time_str.replace("Z", "+00:00"))
                    except Exception:
                        pass

                time_diff = None
                if old_time and new_time:
                    time_diff = abs((new_time - old_time).total_seconds())

                sim = 0.0
                new_text = new_sp.get("text", "")
                if old_text and new_text:
                    if old_text in new_text:
                        sim = 1.0
                    else:
                        q_ratio = difflib.SequenceMatcher(None, old_text, new_text).quick_ratio()
                        if (time_diff is not None and time_diff <= 120) or q_ratio >= 0.8:
                            sim = difflib.SequenceMatcher(
                                None, old_text, new_text, autojunk=False
                            ).ratio()

                # Matching rule: must have text overlap. Time alone is not enough.
                score = 0
                is_match = False

                if time_diff is not None and time_diff <= 60:
                    if sim >= 0.5:
                        is_match = True
                        score = sim * 100 + (60 - time_diff)
                else:
                    if sim >= 0.8:
                        is_match = True
                        score = sim * 100

                if is_match and score > best_score:
                    best_score = score
                    best_match = new_sp

        if best_match:
            if "previous_external_ids" not in best_match:
                best_match["previous_external_ids"] = []
            if (
                old_ext
                and old_ext != best_match.get("external_id")
                and old_ext not in best_match["previous_external_ids"]
            ):
                best_match["previous_external_ids"].append(old_ext)
            for prev_ext in old_sp.get("previous_external_ids", []):
                if (
                    prev_ext
                    and prev_ext != best_match.get("external_id")
                    and prev_ext not in best_match["previous_external_ids"]
                ):
                    best_match["previous_external_ids"].append(prev_ext)

            if "previous_speech_keys" not in best_match:
                best_match["previous_speech_keys"] = []
            if (
                old_key
                and old_key != best_match.get("speech_key")
                and old_key not in best_match["previous_speech_keys"]
            ):
                best_match["previous_speech_keys"].append(old_key)
            for prev_key in old_sp.get("previous_speech_keys", []):
                if (
                    prev_key
                    and prev_key != best_match.get("speech_key")
                    and prev_key not in best_match["previous_speech_keys"]
                ):
                    best_match["previous_speech_keys"].append(prev_key)

    return new_speeches


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

        old_speeches = []
        new_lines = []
        for line in existing_lines:
            if target_needle in line:
                try:
                    old_speeches.append(json.loads(line))
                except Exception:
                    pass
            else:
                new_lines.append(line)

        # Bind previous aliases to preserve permalinks across edits
        link_speech_aliases(old_speeches, speeches)

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


def load_persons_metadata(
    processed_dir: str = OUTPUT_DIR_PROCESSED,
) -> tuple[set[str], dict[str, str], dict[str, str]]:
    """Load known MP UUIDs, unambiguous full_name -> uuid mapping, and uuid -> full_name mapping from persons.json."""
    p_path = os.path.join(processed_dir, "persons.json")
    if not os.path.exists(p_path):
        return set(), {}, {}
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
        uuid_to_name = {}
        for p in persons:
            name = p.get("full_name")
            uuid_val = p.get("uuid")
            if name and uuid_val:
                uuid_to_name[uuid_val] = name
                if name_counts.get(name) == 1:
                    name_map[name] = uuid_val
        return known_uuids, name_map, uuid_to_name
    except Exception:
        return set(), {}, {}


def load_persons_name_map(processed_dir: str = OUTPUT_DIR_PROCESSED) -> dict[str, str]:
    """Compatibility wrapper returning name -> uuid map."""
    _, name_map, _ = load_persons_metadata(processed_dir=processed_dir)
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
    uuid_to_name_map: dict[str, str] | None = None,
    lemma_cache: dict[str, str] | None = None,
) -> tuple[list[dict], str]:
    if rich_meeting is None:
        meeting_status = "UNEDITED"
    else:
        is_edited = (rich_meeting.get("meetingStatus") == "EDITED") or bool(
            verbatim and verbatim.get("edited")
        )
        meeting_status = "EDITED" if is_edited else "UNEDITED"

    speeches_to_save = []

    if rich_meeting and rich_meeting.get("stenograph", {}).get("agendaItems"):
        agendas = rich_meeting["stenograph"]["agendaItems"]
        speech_idx = 0
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
                speech_idx += 1
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
                sp_time_raw = sp.get("startTime")
                end_time_raw = sp.get("endTime")
                duration_seconds = compute_duration_seconds(sp_time_raw, end_time_raw)

                sp_time = time_formatted
                if sp_time_raw and "T" in sp_time_raw:
                    time_part = sp_time_raw.split("T")[1].replace(":", "")[:4]
                    if len(time_part) == 4 and time_part.isdigit():
                        sp_time = time_part

                clean_time = (
                    (sp_time_raw or sp_time or "0000")
                    .replace(":", "")
                    .replace("-", "")
                    .replace(".", "")
                )
                speaker_slug = slugify_estonian(speaker_name)

                if sp_time_raw:
                    key_suffix = f"{clean_time}_{speaker_slug}"
                else:
                    key_suffix = f"{clean_time}_{speech_idx}_{speaker_slug}"

                speech_key = (
                    f"{meeting_code}_{key_suffix}" if meeting_code and speaker_slug else None
                )

                raw_ems_id = sp.get("emsId")
                raw_ems_str = str(raw_ems_id).strip() if raw_ems_id else None
                speaker_uuid, _ = resolve_speaker_uuid(
                    speaker_name=speaker_name,
                    ems_id=raw_ems_str,
                    date=date_formatted,
                    known_uuids=known_person_uuids,
                    uuid_to_name_map=uuid_to_name_map,
                    person_name_map=person_name_map,
                    speech_key=speech_key,
                )
                canonical_name = (
                    uuid_to_name_map.get(speaker_uuid)
                    if (speaker_uuid and uuid_to_name_map)
                    else speaker_name
                )
                speaker_faction = get_faction_for_date(faction_map, canonical_name, date_formatted)

                if lemma_cache is not None and raw_text in lemma_cache:
                    lemmas = lemma_cache[raw_text]
                else:
                    lemmas = lemmatize_text(raw_text)
                video_url = sp.get("parsedVideoLink")

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
                        "ems_id": raw_ems_str,
                        "speech_type": sp_type,
                        "external_id": ext_id_int,
                        "start_time": sp_time_raw,
                        "end_time": end_time_raw,
                        "duration_seconds": duration_seconds,
                        "speech_key": speech_key,
                        "text": raw_text,
                        "text_lemmas": lemmas,
                        "status": meeting_status,
                    }
                )
    elif verbatim:
        verbatim_idx = 0
        for agenda_item in verbatim.get("agendaItems", []):
            raw_agenda_name = agenda_item.get("title", "")
            agenda_title = clean_html(raw_agenda_name)
            for event in agenda_item.get("events", []):
                if event.get("type") == "SPEECH":
                    verbatim_idx += 1
                    raw_text = event.get("text", "")
                    speaker_raw = event.get("speaker", "")

                    if not raw_text or not speaker_raw:
                        continue

                    speaker_name, speaker_role = split_speaker_role(speaker_raw)
                    speaker_slug = slugify_estonian(speaker_name)
                    speech_key = (
                        f"{meeting_code}_{time_formatted}_{verbatim_idx}_{speaker_slug}"
                        if meeting_code and speaker_slug
                        else None
                    )

                    raw_ems_id = event.get("emsId")
                    raw_ems_str = str(raw_ems_id).strip() if raw_ems_id else None
                    speaker_uuid, _ = resolve_speaker_uuid(
                        speaker_name=speaker_name,
                        ems_id=raw_ems_str,
                        date=date_formatted,
                        known_uuids=known_person_uuids,
                        uuid_to_name_map=uuid_to_name_map,
                        person_name_map=person_name_map,
                        speech_key=speech_key,
                    )
                    canonical_name = (
                        uuid_to_name_map.get(speaker_uuid)
                        if (speaker_uuid and uuid_to_name_map)
                        else speaker_name
                    )
                    speaker_faction = get_faction_for_date(
                        faction_map, canonical_name, date_formatted
                    )

                    if lemma_cache is not None and raw_text in lemma_cache:
                        lemmas = lemma_cache[raw_text]
                    else:
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
                            "ems_id": raw_ems_str,
                            "speech_type": "SPEECH",
                            "external_id": None,
                            "start_time": None,
                            "end_time": None,
                            "duration_seconds": None,
                            "speech_key": speech_key,
                            "text": raw_text,
                            "text_lemmas": lemmas,
                            "status": meeting_status,
                        }
                    )

    return speeches_to_save, meeting_status


def process_single_verbatim(
    verbatim: dict,
    faction_map: dict,
    person_name_map: dict,
    known_person_uuids: set,
    uuid_to_name_map: dict,
    processed_meeting_codes: set,
    processed_source_files: set,
    unedited_meeting_codes: set,
    unedited_source_files: set,
    unedited_sessions: dict,
) -> bool:
    """Process a single verbatim record. Returns False if error occurred, else True."""
    has_errors = False
    try:
        verbatim_link = verbatim.get("link", "")
        meeting_code = (
            verbatim_link.rstrip("/").split("/")[-1].split("?")[0] if verbatim_link else ""
        )

        if meeting_code in IGNORED_VERBATIMS:
            print(f"Skipping ignored verbatim {meeting_code}: {IGNORED_VERBATIMS[meeting_code]}")
            return True

        v_date_str = verbatim.get("date")
        if not v_date_str:
            return True

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
            return True

        print(f"Processing verbatim: {verbatim.get('title')} ({verbatim.get('date')})")

        rich_meeting = fetch_rich_meeting_data(meeting_code)
        if rich_meeting is None:
            print(
                f"Warning: Could not fetch rich meeting details for {meeting_code}. "
                "Saving in UNEDITED status to retry on subsequent run."
            )
            has_errors = True

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
            uuid_to_name_map=uuid_to_name_map,
        )

        if rich_meeting is None:
            meeting_status = "UNEDITED"
            for s in speeches_to_save:
                s["status"] = "UNEDITED"

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

        time.sleep(1.5)

    except Exception as e:
        print(f"Warning: Error processing verbatim {verbatim.get('title')}: {e}")
        has_errors = True

    return not has_errors


def fetch_and_process_stenograms(
    start_date: str | None = None,
    end_date: str | None = None,
    processed_meeting_codes: set[str] | None = None,
    check_missing_days: int = UNEDITED_REFETCH_DAYS,
) -> bool:
    """Fetch recent stenograms from Riigikogu API, lemmatize, and append to yearly datasets."""
    explicit_window = start_date is not None
    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)

    # Load existing meeting codes and source files from processed jsonl files
    if processed_meeting_codes is None:
        processed_meeting_codes = set()
    processed_source_files = set()
    unedited_meeting_codes = set()
    unedited_source_files = set()
    unedited_sessions: dict[str, dict] = {}
    total_existing_records = 0
    latest_existing_date = None
    unedited_refetch_cutoff = (datetime.now() - timedelta(days=UNEDITED_REFETCH_DAYS)).strftime(
        "%Y-%m-%d"
    )

    for jsonl_path in glob.glob(os.path.join(OUTPUT_DIR_PROCESSED, "*.jsonl")):
        if not re.match(r"^\d{4}\.jsonl$", os.path.basename(jsonl_path)):
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
                            status is None and rec_date and rec_date >= unedited_refetch_cutoff
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

    known_person_uuids, person_name_map, uuid_to_name_map = load_persons_metadata()

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
            ok = process_single_verbatim(
                verbatim=verbatim,
                faction_map=faction_map,
                person_name_map=person_name_map,
                known_person_uuids=known_person_uuids,
                uuid_to_name_map=uuid_to_name_map,
                processed_meeting_codes=processed_meeting_codes,
                processed_source_files=processed_source_files,
                unedited_meeting_codes=unedited_meeting_codes,
                unedited_source_files=unedited_source_files,
                unedited_sessions=unedited_sessions,
            )
            if not ok:
                has_errors = True

    # In addition to the primary window, check for missing sessions across the last UNEDITED_REFETCH_DAYS days
    if check_missing_days and check_missing_days > 0 and not explicit_window:
        print(f"\nChecking last {check_missing_days} days for missing sessions...")
        missing_start = (datetime.now() - timedelta(days=check_missing_days)).strftime("%Y-%m-%d")
        missing_end = datetime.now().strftime("%Y-%m-%d")
        missing_ranges = get_month_ranges(missing_start, missing_end)

        for m_start, m_end in missing_ranges:
            url = "https://api.riigikogu.ee/api/steno/verbatims"
            time.sleep(1.0)
            verbatims = None
            for _attempt in range(1, 4):
                try:
                    resp = requests.get(
                        url, params={"startDate": m_start, "endDate": m_end}, timeout=(5, 30)
                    )
                    if resp.status_code == 200:
                        verbatims = resp.json()
                        break
                    if resp.status_code == 429:
                        time.sleep(15)
                except Exception:
                    time.sleep(2)

            if not isinstance(verbatims, list):
                continue

            for verbatim in verbatims:
                v_link = verbatim.get("link", "")
                m_code = v_link.rstrip("/").split("/")[-1].split("?")[0] if v_link else ""
                if m_code in IGNORED_VERBATIMS:
                    continue
                if m_code and (
                    m_code in processed_meeting_codes or m_code in unedited_meeting_codes
                ):
                    continue

                v_date_str = verbatim.get("date")
                if v_date_str:
                    try:
                        v_dt = datetime.strptime(v_date_str.split("T")[0], "%Y-%m-%d")
                        d_fmt = v_dt.strftime("%Y-%m-%d")
                        t_fmt = "0000"
                        if v_link and len(v_link) >= 4 and v_link[-4:].isdigit():
                            t_fmt = v_link[-4:]
                        if f"{d_fmt}_{t_fmt}.api" in processed_source_files:
                            continue
                    except ValueError:
                        pass

                ok = process_single_verbatim(
                    verbatim=verbatim,
                    faction_map=faction_map,
                    person_name_map=person_name_map,
                    known_person_uuids=known_person_uuids,
                    uuid_to_name_map=uuid_to_name_map,
                    processed_meeting_codes=processed_meeting_codes,
                    processed_source_files=processed_source_files,
                    unedited_meeting_codes=unedited_meeting_codes,
                    unedited_source_files=unedited_source_files,
                    unedited_sessions=unedited_sessions,
                )
                if not ok:
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

            if meeting_code in IGNORED_VERBATIMS:
                print(
                    f"Skipping ignored verbatim {meeting_code}: {IGNORED_VERBATIMS[meeting_code]}"
                )
                continue

            if meeting_code in processed_meeting_codes:
                continue

            if date_str:
                try:
                    session_dt = datetime.strptime(date_str, "%Y-%m-%d")
                    if datetime.now() - session_dt > timedelta(days=UNEDITED_REFETCH_DAYS):
                        print(
                            f"Notice: Session {meeting_code} ({date_str}) is over {UNEDITED_REFETCH_DAYS} days old and still UNEDITED in API. Skipping."
                        )
                        continue
                except ValueError:
                    pass

            time.sleep(1.5)
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
                    uuid_to_name_map=uuid_to_name_map,
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
