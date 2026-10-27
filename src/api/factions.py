"""Faction rosters for one Riigikogu membership, built from the members' faction periods."""

import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any

from config import MEMBERSHIP_DATES, OUTPUT_DIR_PROCESSED
from src.api.roles import government_at, role
from src.load.database import SessionLocal
from src.load.models import Person

logger = logging.getLogger(__name__)

NO_FACTION = "Fraktsiooni mittekuuluvad Riigikogu liikmed"
# Riigikogu API marks a faction membership that has not ended with this date
OPEN_END = "2099-12-31"
# Riigikogu lists a new or returning member as non-affiliated until their faction admits
# them, usually for a few days. Longer non-affiliated periods are kept.
JOINING_DAYS = 31


def _load_json(file_name: str) -> dict:
    path = os.path.join(OUTPUT_DIR_PROCESSED, file_name)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as e:
        logger.warning("Failed to load %s: %s", file_name, e)
        return {}


def _shift(day: str, days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


def normalize_periods(periods: list[dict]) -> list[dict]:
    """Drop the non-affiliated waiting time before joining a faction and join split periods.

    Periods end on the day the next one starts, so `end` is treated as exclusive.
    """
    items = sorted(
        (
            {
                "faction": p.get("faction") or NO_FACTION,
                "start": p["start"],
                "end": p.get("end") or OPEN_END,
            }
            for p in periods
            if p.get("start")
        ),
        key=lambda p: (p["start"], p["end"]),
    )

    def is_joining(p: dict) -> bool:
        if p["faction"] != NO_FACTION or p["end"] >= OPEN_END:
            return False
        if p["end"] > _shift(p["start"], JOINING_DAYS):
            return False
        joined_by = _shift(p["end"], 1)
        return any(
            q["faction"] != NO_FACTION and p["start"] <= q["start"] <= joined_by for q in items
        )

    merged: list[dict] = []
    for p in items:
        if is_joining(p):
            continue
        prev = next((m for m in reversed(merged) if m["faction"] == p["faction"]), None)
        if prev and prev["end"] < OPEN_END and p["start"] <= _shift(prev["end"], 1):
            prev["end"] = max(prev["end"], p["end"])
            continue
        merged.append(dict(p))
    return merged


def build_factions_overview(
    persons: list[dict[str, Any]],
    periods_by_uuid: dict[str, list[dict]],
    periods_by_name: dict[str, list[dict]],
    membership_start: str,
    membership_end: str,
    today: str,
    active_only: bool = False,
    leader_roles: dict[str, list[dict]] | None = None,
) -> dict[str, Any]:
    """Group members into the factions they belonged to during the membership.

    A member is current when the membership is ongoing, the member is active and one of
    their faction periods covers today. Members who moved between factions appear in each.
    `leader_roles` (faction_roles.json) adds the chair and vice-chair periods per faction.
    """
    leader_roles = leader_roles or {}
    is_current_membership = membership_start <= today <= membership_end
    ref_date = min(today, membership_end)

    factions: dict[str, list[dict[str, Any]]] = {}
    for person in persons:
        periods = periods_by_uuid.get(person["uuid"]) or periods_by_name.get(
            person["full_name"], []
        )
        by_faction: dict[str, list[dict]] = {}
        for p in normalize_periods(periods):
            start, end = p["start"], p["end"]
            # A period that ends on the first day of the membership belongs to the previous one
            if start > membership_end or end <= membership_start:
                continue
            by_faction.setdefault(p["faction"], []).append(
                {"start": start, "end": None if end >= OPEN_END else end}
            )

        for faction, fac_periods in by_faction.items():
            fac_periods.sort(key=lambda x: x["start"])
            current = (
                is_current_membership
                and person["active"]
                and any(
                    x["start"] <= today and (x["end"] is None or today < x["end"])
                    for x in fac_periods
                )
            )
            if active_only and not current:
                continue
            roles = [
                {"role": r["role"], "start": r["start"], "end": r.get("end")}
                for r in leader_roles.get(person["uuid"], [])
                if r.get("faction") == faction
                and r["start"] <= membership_end
                and (not r.get("end") or r["end"] > membership_start)
            ]
            current_role = next(
                (
                    r["role"]
                    for r in roles
                    if current and r["start"] <= today and (not r["end"] or today < r["end"])
                ),
                None,
            )
            factions.setdefault(faction, []).append(
                {
                    "uuid": person["uuid"],
                    "full_name": person["full_name"],
                    "first_name": person["first_name"],
                    "last_name": person["last_name"],
                    "electoral_district": person["electoral_district"],
                    "photo_url": person["photo_url"],
                    "current": current,
                    "periods": fac_periods,
                    "leader_role": current_role,
                    "leader_roles": roles,
                }
            )

    result = []
    for faction, members in factions.items():
        members.sort(key=lambda m: (m["last_name"], m["first_name"]))
        result.append(
            {
                "faction": faction,
                "role": role(faction, ref_date),
                "current_count": sum(1 for m in members if m["current"]),
                "members": members,
            }
        )
    result.sort(
        key=lambda f: (
            f["faction"] == NO_FACTION,
            -f["current_count"],
            -len(f["members"]),
            f["faction"],
        )
    )

    government = government_at(ref_date)
    return {
        "date": ref_date,
        "is_current_membership": is_current_membership,
        "government": {
            "name": government["government"],
            "from": government["from"],
            "to": government.get("to"),
            "coalition": government["coalition"],
            "source": government["source"],
        }
        if government
        else None,
        "factions": result,
    }


def get_factions_overview(membership: str, active_only: bool = False) -> dict[str, Any]:
    """Return the faction rosters of a membership with each faction's government role."""
    start, end = MEMBERSHIP_DATES[membership]
    session = SessionLocal()
    try:
        persons = [
            {
                "uuid": p.uuid,
                "full_name": p.full_name,
                "first_name": p.first_name,
                "last_name": p.last_name,
                "electoral_district": p.electoral_district,
                "photo_url": p.photo_url,
                "active": bool(p.active),
            }
            for p in session.query(Person).all()
        ]
    finally:
        session.close()

    overview = build_factions_overview(
        persons,
        _load_json("person_factions.json"),
        _load_json("factions_map.json"),
        start,
        end,
        datetime.now().strftime("%Y-%m-%d"),
        active_only=active_only,
        leader_roles=_load_json("faction_roles.json"),
    )
    return {"membership": membership, **overview}
