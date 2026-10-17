"""Shared voting query and formatting utilities."""

from sqlalchemy import and_, func

from src.load.models import Voting


def is_technical_voting(
    voting_type: str | None,
    in_favor: int | None,
    against: int | None,
    neutral: int | None,
) -> bool:
    """Determine if a voting is technical (AVALIK with 0 in_favor, against, and neutral votes)."""
    return voting_type == "AVALIK" and ((in_favor or 0) + (against or 0) + (neutral or 0)) == 0


def is_technical_voting_clause():
    """SQLAlchemy filter condition identifying technical votings."""
    return and_(
        Voting.type == "AVALIK",
        (
            func.coalesce(Voting.in_favor, 0)
            + func.coalesce(Voting.against, 0)
            + func.coalesce(Voting.neutral, 0)
        )
        == 0,
    )


def format_session_source_file(
    sitting_date: str | None, sitting_datetime: str | None
) -> str | None:
    """Format expected speeches.source_file name from sitting date and datetime."""
    if not sitting_date or not sitting_datetime:
        return None
    try:
        if "T" in sitting_datetime:
            time_part = sitting_datetime.split("T", 1)[1]
            hh = time_part[:2]
            mm = time_part[3:5]
            if len(hh) == 2 and len(mm) == 2 and hh.isdigit() and mm.isdigit():
                return f"{sitting_date}_{hh}{mm}.api"
    except Exception:
        pass
    return None
