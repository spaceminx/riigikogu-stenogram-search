"""Shared voting query and formatting utilities."""

from sqlalchemy import and_, case, func

from src.load.models import SystemMeta, Vote, Voting


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


def format_voting_summary(
    v: Voting,
    existing_source_files: set[str] | None = None,
) -> dict:
    """Format a Voting row into the standard API summary dictionary."""
    rel_doc = None
    if v.related_document_uuid or v.related_document_reference or v.related_document_title:
        rel_doc = {
            "uuid": v.related_document_uuid,
            "reference": v.related_document_reference,
            "title": v.related_document_title,
            "type": v.related_document_type,
        }
    cf = format_session_source_file(v.sitting_date, v.sitting_datetime)
    session_source_file = None
    if cf:
        if existing_source_files is not None:
            session_source_file = cf if cf in existing_source_files else None
        else:
            session_source_file = cf

    is_tech = is_technical_voting(v.type, v.in_favor, v.against, v.neutral)
    return {
        "uuid": v.uuid,
        "voting_number": v.voting_number,
        "type": v.type,
        "is_technical": is_tech,
        "description": v.description,
        "date": v.date,
        "start_time": v.start_time,
        "end_time": v.end_time,
        "sitting_date": v.sitting_date,
        "sitting_datetime": v.sitting_datetime,
        "session_source_file": session_source_file,
        "membership": v.membership,
        "sitting_uuid": v.sitting_uuid,
        "sitting_title": v.sitting_title,
        "related_document": rel_doc,
        "chairman_uuid": v.chairman_uuid,
        "totals": {
            "present": v.present,
            "absent": v.absent,
            "in_favor": v.in_favor,
            "against": v.against,
            "neutral": v.neutral,
            "abstained": v.abstained,
        },
    }


_VOTE_PARTICIPATION_CACHE: dict = {
    "last_sync_at": None,
    "members": {},
    "factions": {},
}


def _get_last_sync_at(session) -> str | None:
    try:
        row = session.query(SystemMeta).filter_by(key="last_sync_at").first()
        return row.value if row else None
    except Exception:
        return None


def clear_vote_participation_cache() -> None:
    """Clear in-memory cached vote participation data."""
    _VOTE_PARTICIPATION_CACHE["last_sync_at"] = None
    _VOTE_PARTICIPATION_CACHE["members"].clear()
    _VOTE_PARTICIPATION_CACHE["factions"].clear()


def _normalize_membership_key(membership: str | int | None) -> str:
    if membership is None or str(membership).lower() == "all":
        return "all"
    return str(membership)


def get_member_vote_participation(session, membership: str | int | None = None) -> dict[str, dict]:
    """Calculate vote participation per member on public, non-technical votings.

    Returns mapping from member_uuid to:
        {"voted": int, "not_voted": int, "absent": int, "total": int, "voted_pct": float | None}
    """
    last_sync = _get_last_sync_at(session)
    if _VOTE_PARTICIPATION_CACHE["last_sync_at"] != last_sync:
        _VOTE_PARTICIPATION_CACHE["last_sync_at"] = last_sync
        _VOTE_PARTICIPATION_CACHE["members"].clear()
        _VOTE_PARTICIPATION_CACHE["factions"].clear()

    cache_key = _normalize_membership_key(membership)
    if cache_key in _VOTE_PARTICIPATION_CACHE["members"]:
        return _VOTE_PARTICIPATION_CACHE["members"][cache_key]

    is_tech_sql = is_technical_voting_clause()
    query = (
        session.query(
            Vote.member_uuid,
            func.count(Vote.voting_uuid).label("total"),
            func.sum(case((Vote.decision.in_(["POOLT", "VASTU", "ERAPOOLETU"]), 1), else_=0)).label(
                "voted"
            ),
            func.sum(case((Vote.decision == "EI_HAALETANUD", 1), else_=0)).label("not_voted"),
            func.sum(case((Vote.decision == "PUUDUB", 1), else_=0)).label("absent"),
        )
        .join(Voting, Vote.voting_uuid == Voting.uuid)
        .filter(
            Voting.type == "AVALIK",
            ~is_tech_sql,
        )
    )

    if cache_key != "all":
        try:
            mem_int = int(cache_key)
            query = query.filter(Voting.membership == mem_int)
        except (ValueError, TypeError):
            pass

    results = query.group_by(Vote.member_uuid).all()

    stats: dict[str, dict] = {}
    for member_uuid, total, voted, not_voted, absent in results:
        tot = int(total) if total else 0
        v = int(voted) if voted else 0
        nv = int(not_voted) if not_voted else 0
        ab = int(absent) if absent else 0
        pct = round((v / tot) * 100.0, 1) if tot > 0 else None
        stats[member_uuid] = {
            "voted": v,
            "not_voted": nv,
            "absent": ab,
            "total": tot,
            "voted_pct": pct,
        }

    _VOTE_PARTICIPATION_CACHE["members"][cache_key] = stats
    return stats


def get_faction_vote_participation(session, membership: str | int | None = None) -> dict[str, dict]:
    """Calculate vote participation per faction on public, non-technical votings.

    Faction is determined by per-ballot Vote.faction.
    Returns mapping from faction name to:
        {"voted": int, "not_voted": int, "absent": int, "total": int, "voted_pct": float | None}
    """
    last_sync = _get_last_sync_at(session)
    if _VOTE_PARTICIPATION_CACHE["last_sync_at"] != last_sync:
        _VOTE_PARTICIPATION_CACHE["last_sync_at"] = last_sync
        _VOTE_PARTICIPATION_CACHE["members"].clear()
        _VOTE_PARTICIPATION_CACHE["factions"].clear()

    cache_key = _normalize_membership_key(membership)
    if cache_key in _VOTE_PARTICIPATION_CACHE["factions"]:
        return _VOTE_PARTICIPATION_CACHE["factions"][cache_key]

    is_tech_sql = is_technical_voting_clause()
    query = (
        session.query(
            Vote.faction,
            func.count(Vote.voting_uuid).label("total"),
            func.sum(case((Vote.decision.in_(["POOLT", "VASTU", "ERAPOOLETU"]), 1), else_=0)).label(
                "voted"
            ),
            func.sum(case((Vote.decision == "EI_HAALETANUD", 1), else_=0)).label("not_voted"),
            func.sum(case((Vote.decision == "PUUDUB", 1), else_=0)).label("absent"),
        )
        .join(Voting, Vote.voting_uuid == Voting.uuid)
        .filter(
            Voting.type == "AVALIK",
            ~is_tech_sql,
            Vote.faction != "",
            Vote.faction.isnot(None),
        )
    )

    if cache_key != "all":
        try:
            mem_int = int(cache_key)
            query = query.filter(Voting.membership == mem_int)
        except (ValueError, TypeError):
            pass

    results = query.group_by(Vote.faction).all()

    stats: dict[str, dict] = {}
    for faction, total, voted, not_voted, absent in results:
        if not faction:
            continue
        tot = int(total) if total else 0
        v = int(voted) if voted else 0
        nv = int(not_voted) if not_voted else 0
        ab = int(absent) if absent else 0
        pct = round((v / tot) * 100.0, 1) if tot > 0 else None
        stats[faction] = {
            "voted": v,
            "not_voted": nv,
            "absent": ab,
            "total": tot,
            "voted_pct": pct,
        }

    _VOTE_PARTICIPATION_CACHE["factions"][cache_key] = stats
    return stats
