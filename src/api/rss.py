import re
from datetime import datetime
from email.utils import format_datetime
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

TALLINN_TZ = ZoneInfo("Europe/Tallinn")
BASE_URL = "https://www.riigivaade.me"


def format_pubdate(start_time: str | None, date_str: str | None, time_str: str | None) -> str:
    """Format speech date/time into RFC 822 format in Europe/Tallinn timezone."""
    dt = None
    if start_time:
        try:
            # e.g. "2020-09-14T15:02:23.82" or "2020-09-14T15:02:23"
            clean_iso = start_time.strip()
            if "T" in clean_iso:
                dt = datetime.fromisoformat(clean_iso)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=TALLINN_TZ)
                else:
                    dt = dt.astimezone(TALLINN_TZ)
        except Exception:
            dt = None

    if dt is None and date_str:
        try:
            # Fallback to date + time (e.g. date="2019-04-04", time="1100")
            if time_str and len(time_str.strip()) >= 4:
                t_clean = time_str.strip()[:4]
                dt = datetime.strptime(f"{date_str.strip()} {t_clean}", "%Y-%m-%d %H%M").replace(
                    tzinfo=TALLINN_TZ
                )
            else:
                dt = datetime.strptime(date_str.strip(), "%Y-%m-%d").replace(
                    hour=10, minute=0, second=0, tzinfo=TALLINN_TZ
                )
        except Exception:
            dt = None

    if dt is None:
        dt = datetime.now(TALLINN_TZ)

    return format_datetime(dt)


def extract_search_snippet(text: str | None, query: str = "", max_length: int = 300) -> str:
    """Extract a ~300 character snippet centered around the first matching term."""
    if not text:
        return ""
    text_clean = " ".join(text.split())
    if len(text_clean) <= max_length:
        return text_clean

    # Find first keyword match
    terms = [t.strip().lower() for t in re.split(r"[\s,\"\'+]+", query) if len(t.strip()) >= 2]
    first_idx = -1
    lower_text = text_clean.lower()
    for term in terms:
        idx = lower_text.find(term)
        if idx != -1 and (first_idx == -1 or idx < first_idx):
            first_idx = idx

    if first_idx == -1 or first_idx < 100:
        return text_clean[:max_length].rstrip() + "..."

    start = max(0, first_idx - 100)
    end = min(len(text_clean), start + max_length)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text_clean) else ""
    return prefix + text_clean[start:end].strip() + suffix


def extract_person_snippet(text: str | None, max_length: int = 300) -> str:
    """Extract the first ~300 characters of a speech."""
    if not text:
        return ""
    text_clean = " ".join(text.split())
    if len(text_clean) <= max_length:
        return text_clean
    return text_clean[:max_length].rstrip() + "..."


def escape_xml(s: str | None) -> str:
    """Escape XML special characters, preserving quotes."""
    if not s:
        return ""
    return escape(str(s), entities={'"': "&quot;", "'": "&apos;"})


def build_rss_xml(
    title: str,
    page_link: str,
    self_link: str,
    description: str,
    items: list[dict],
    build_date: datetime | None = None,
) -> str:
    """Build an RSS 2.0 XML string conforming to RSS 2.0 and Atom namespace specs."""
    if build_date is None:
        build_date = datetime.now(TALLINN_TZ)
    last_build_date_str = format_datetime(build_date)

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "  <channel>",
        f"    <title>{escape_xml(title)}</title>",
        f"    <link>{escape_xml(page_link)}</link>",
        f"    <description>{escape_xml(description)}</description>",
        "    <language>et</language>",
        f"    <lastBuildDate>{last_build_date_str}</lastBuildDate>",
        f'    <atom:link href="{escape_xml(self_link)}" rel="self" type="application/rss+xml" />',
    ]

    for item in items:
        # Item fields
        speaker = item.get("speaker") or "Saadik"
        agenda = item.get("agenda_title") or "Sõnavõtt"
        item_title = f"{speaker}: {agenda}"

        # PermaLink: external_id or id
        speech_ref = item.get("external_id") or item.get("id")
        item_link = f"{BASE_URL}/kone/{speech_ref}"

        pub_date = format_pubdate(item.get("start_time"), item.get("date"), item.get("time"))
        item_desc = item.get("snippet") or ""
        faction = item.get("speaker_faction")

        xml_lines.append("    <item>")
        xml_lines.append(f"      <title>{escape_xml(item_title)}</title>")
        xml_lines.append(f"      <link>{escape_xml(item_link)}</link>")
        xml_lines.append(f'      <guid isPermaLink="true">{escape_xml(item_link)}</guid>')
        xml_lines.append(f"      <pubDate>{pub_date}</pubDate>")
        xml_lines.append(f"      <description>{escape_xml(item_desc)}</description>")
        if faction:
            xml_lines.append(f"      <category>{escape_xml(faction)}</category>")
        xml_lines.append("    </item>")

    xml_lines.append("  </channel>")
    xml_lines.append("</rss>")
    return "\n".join(xml_lines)
