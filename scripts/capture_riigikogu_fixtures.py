#!/usr/bin/env python3
"""Capture small real API response fixtures from api.riigikogu.ee and stenogrammid.riigikogu.ee.

Saves fixtures into tests/fixtures/riigikogu_api/ for both a recent date (2026-10)
and an old date (2019-04). Lists are trimmed to at most 5 items.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "riigikogu_api"

OPENER = urllib.request.build_opener()
OPENER.addheaders = [("User-Agent", "Mozilla/5.0 (riigivaade-fixture-capture)")]


def fetch_json(url: str, delay: float = 1.0) -> dict | list:
    """Fetch JSON with delay to respect rate limits."""
    time.sleep(delay)
    req = urllib.request.Request(url)
    with OPENER.open(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def trim_list(data: list, max_items: int = 5) -> list:
    return data[:max_items]


def trim_voting_detail(detail: dict, max_voters: int = 5) -> dict:
    d = dict(detail)
    if "voters" in d and isinstance(d["voters"], list):
        d["voters"] = d["voters"][:max_voters]
    return d


def trim_votings_list(data: list, max_items: int = 5) -> list:
    res = []
    for sitting in data[:max_items]:
        s = dict(sitting)
        if "votings" in s and isinstance(s["votings"], list):
            s["votings"] = s["votings"][:max_items]
        res.append(s)
    return res


def trim_rich_meeting(data: dict, max_items: int = 5) -> dict:
    d = dict(data)
    if "stenograph" in d and isinstance(d["stenograph"], dict):
        steno = dict(d["stenograph"])
        if "agendaItems" in steno and isinstance(steno["agendaItems"], list):
            items = []
            for item in steno["agendaItems"][:max_items]:
                it = dict(item)
                if "speeches" in it and isinstance(it["speeches"], list):
                    it["speeches"] = it["speeches"][:max_items]
                items.append(it)
            steno["agendaItems"] = items
        d["stenograph"] = steno
    return d


def trim_usergroup_detail(data: dict) -> dict:
    """Keep the XV leadership, a few ordinary members and staff, and one old chair; drop contacts."""
    members = data.get("members") or []

    def code(m):
        return ((m.get("membership") or {}).get("role") or {}).get("code")

    def number(m):
        return (m.get("membership") or {}).get("membershipNumber")

    picked = [m for m in members if number(m) == 15 and code(m) in ("ESIMEES", "ASEESIMEES")]
    picked += [m for m in members if number(m) == 15 and code(m) == "LIIGE"][:2]
    picked += [m for m in members if code(m) == "TOOTAJA"][:1]
    picked += [m for m in members if number(m) == 12 and code(m) == "ESIMEES"][:1]
    d = dict(data)
    d["members"] = []
    for m in picked:
        trimmed = {k: v for k, v in m.items() if k not in ("email", "phone", "photo", "upn")}
        # Staff are not MPs; keep the row shape without the person
        if code(m) == "TOOTAJA":
            trimmed.update(
                uuid="00000000-0000-0000-0000-000000000000",
                fullName="Fraktsiooni Töötaja",
                firstName="Fraktsiooni",
                lastName="Töötaja",
            )
        d["members"].append(trimmed)
    return d


def trim_agenda(data: dict, max_items: int = 5) -> dict:
    d = dict(data)
    if "sittings" in d and isinstance(d["sittings"], list):
        sittings = []
        for sitting in d["sittings"][:max_items]:
            s = dict(sitting)
            if "agendaItems" in s and isinstance(s["agendaItems"], list):
                s["agendaItems"] = s["agendaItems"][:max_items]
            sittings.append(s)
        d["sittings"] = sittings
    return d


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    endpoints = [
        # (filename, url, trimmer)
        (
            "memberships.json",
            "https://api.riigikogu.ee/api/memberships",
            trim_list,
        ),
        (
            "plenary_members_recent.json",
            "https://api.riigikogu.ee/api/plenary-members?status=ALL&membership=15",
            trim_list,
        ),
        (
            "plenary_members_2019.json",
            "https://api.riigikogu.ee/api/plenary-members?status=ALL&membership=14",
            trim_list,
        ),
        (
            "votings_recent.json",
            "https://api.riigikogu.ee/api/votings?startDate=2026-10-01&endDate=2026-10-22",
            trim_votings_list,
        ),
        (
            "votings_2019.json",
            "https://api.riigikogu.ee/api/votings?startDate=2019-04-04&endDate=2019-04-30",
            trim_votings_list,
        ),
        (
            "voting_detail_recent.json",
            "https://api.riigikogu.ee/api/votings/688c290c-cd08-48a1-8d47-e10f8db9d5a8",
            trim_voting_detail,
        ),
        (
            "voting_detail_2019.json",
            "https://api.riigikogu.ee/api/votings/6e0f93c6-1cfc-4fcd-b825-a27b542c0e4f",
            trim_voting_detail,
        ),
        (
            "verbatims_recent.json",
            "https://api.riigikogu.ee/api/steno/verbatims?startDate=2026-10-01&endDate=2026-10-22",
            trim_list,
        ),
        (
            "verbatims_2019.json",
            "https://api.riigikogu.ee/api/steno/verbatims?startDate=2019-04-04&endDate=2019-04-30",
            trim_list,
        ),
        (
            "meeting_recent.json",
            "https://stenogrammid.riigikogu.ee/api/meeting/202610191500",
            trim_rich_meeting,
        ),
        (
            "meeting_2019.json",
            "https://stenogrammid.riigikogu.ee/api/meeting/201904041100",
            trim_rich_meeting,
        ),
        (
            "agenda_recent.json",
            "https://api.riigikogu.ee/api/agenda/plenary?startDate=2026-10-01&endDate=2026-10-22&lang=et",
            trim_agenda,
        ),
        (
            "agenda_2019.json",
            "https://api.riigikogu.ee/api/agenda/plenary?startDate=2019-04-04&endDate=2019-04-30&lang=et",
            trim_agenda,
        ),
        (
            "usergroups_factions.json",
            "https://api.riigikogu.ee/api/usergroups?typeCode=FRAKTSIOON&hideInactive=true&lang=ET",
            None,
        ),
        (
            "usergroup_detail.json",
            "https://api.riigikogu.ee/api/usergroups/8772fd6f-3197-6a53-2ffc-8c4d63407d1e?lang=ET",
            trim_usergroup_detail,
        ),
    ]

    for fname, url, trimmer in endpoints:
        dest = FIXTURES_DIR / fname
        print(f"Fetching {url} -> {fname}...")
        try:
            raw = fetch_json(url, delay=1.2)
            trimmed = trimmer(raw) if trimmer else raw
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(trimmed, f, ensure_ascii=False, indent=2)
            print(f"Saved {fname}")
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            raise


if __name__ == "__main__":
    main()
