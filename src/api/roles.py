"""Government periods and coalition/opposition role resolution."""

import json
from pathlib import Path
from typing import Any

from sqlalchemy import and_, case, or_

_GOVERNMENTS_FILE = Path(__file__).resolve().parent.parent / "data" / "governments.json"
_GOVERNMENTS_CACHE: list[dict[str, Any]] | None = None


def load_governments() -> list[dict[str, Any]]:
    """Load government periods from governments.json with memory caching."""
    global _GOVERNMENTS_CACHE
    if _GOVERNMENTS_CACHE is None:
        with open(_GOVERNMENTS_FILE, encoding="utf-8") as f:
            _GOVERNMENTS_CACHE = json.load(f)
    return _GOVERNMENTS_CACHE


def role(faction: str | None, date: str | None) -> str:
    """Determine role ("coalition", "opposition", or "none") for a faction on a given date.

    - "none" for empty faction or "Fraktsiooni mittekuuluvad Riigikogu liikmed".
    - "coalition" if the faction was part of the government coalition on that date.
    - "opposition" otherwise.
    """
    if not faction or faction == "Fraktsiooni mittekuuluvad Riigikogu liikmed" or not date:
        return "none"

    d = date[:10]
    governments = load_governments()
    for period in governments:
        p_from = period["from"]
        p_to = period.get("to")
        if p_to:
            in_period = p_from <= d < p_to
        else:
            in_period = d >= p_from

        if in_period:
            if faction in period.get("coalition", []):
                return "coalition"
            return "opposition"

    return "opposition"


def role_expression(faction_col, date_col):
    """Return a SQLAlchemy CASE expression that evaluates to 'coalition', 'opposition', or 'none'.

    date_col can be a date string column (e.g. Voting.sitting_date) or func.substr(datetime_col, 1, 10).
    """
    governments = load_governments()
    coalition_whens = []
    for p in governments:
        p_from = p["from"]
        p_to = p.get("to")
        if p_to:
            date_cond = and_(date_col >= p_from, date_col < p_to)
        else:
            date_cond = date_col >= p_from

        coalition_whens.append((and_(date_cond, faction_col.in_(p["coalition"])), "coalition"))

    return case(
        (
            or_(
                faction_col.is_(None),
                faction_col == "",
                faction_col == "Fraktsiooni mittekuuluvad Riigikogu liikmed",
            ),
            "none",
        ),
        *coalition_whens,
        else_="opposition",
    )


def role_condition(faction_col, date_col, target_role: str):
    """Return a SQLAlchemy filter condition for matching target_role ('coalition' or 'opposition')."""
    return role_expression(faction_col, date_col) == target_role
