"""Calculation and caching of member faction alignment statistics.

Descriptive statistics indicating how often an MP voted the same way as the
strict majority of their own faction on non-technical public votings.
"""

import logging
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import and_, func
from sqlalchemy.orm import aliased

from src.api.lru import MISSING, LRUDict
from src.api.roles import NO_FACTION
from src.api.votings import format_session_source_file, is_technical_voting_clause
from src.load.models import Person, Speech, SystemMeta, Vote, Voting

logger = logging.getLogger(__name__)

POSITIONS = {"POOLT", "VASTU", "ERAPOOLETU", "EI_HAALETANUD"}
EXCLUDED_FACTIONS = {None, "", NO_FACTION}

ALIGNMENT_CACHE_MAX_SIZE = 64

# Each entry holds every ballot of one person; a crawler following the sitemap would
# otherwise keep all ~280 profiles in memory.
_ALIGNMENT_CACHE: dict = {
    "last_sync_at": None,
    "persons": LRUDict(ALIGNMENT_CACHE_MAX_SIZE),  # person_uuid -> dict of computed data
}


def _get_last_sync_at(session) -> str | None:
    try:
        row = session.query(SystemMeta).filter_by(key="last_sync_at").first()
        return row.value if row else None
    except Exception:
        return None


def _summarize_items(items: list[dict]) -> dict:
    same = sum(1 for it in items if it["result_type"] == "same")
    diff = sum(1 for it in items if it["result_type"] == "different")
    tot = same + diff
    share_same = round((same / tot) * 100.0, 1) if tot > 0 else None
    excluded = {
        "absent": sum(1 for it in items if it["result_type"] == "absent"),
        "split": sum(1 for it in items if it["result_type"] == "split"),
        "too_few": sum(1 for it in items if it["result_type"] == "too_few"),
        "no_faction": sum(1 for it in items if it["result_type"] == "no_faction"),
    }
    return {
        "same": same,
        "different": diff,
        "share_same": share_same,
        "excluded": excluded,
    }


def compute_person_alignment(session, person_uuid: str) -> dict:
    """Compute faction alignment data for a person across all non-technical public votings."""
    person = session.query(Person).filter(Person.uuid == person_uuid).first()
    if not person:
        raise HTTPException(status_code=404, detail="Saadikut ei leitud.")

    is_tech_sql = is_technical_voting_clause()
    mv_query = (
        session.query(
            Voting.uuid.label("voting_uuid"),
            Voting.voting_number,
            Voting.date,
            Voting.start_time,
            Voting.sitting_date,
            Voting.sitting_datetime,
            Voting.description,
            Voting.related_document_title,
            Voting.membership,
            Vote.decision.label("member_decision"),
            Vote.faction.label("member_faction"),
        )
        .join(Voting, Vote.voting_uuid == Voting.uuid)
        .filter(Vote.member_uuid == person_uuid)
        .filter(Voting.type == "AVALIK")
        .filter(~is_tech_sql)
        .order_by(Voting.date.desc(), Voting.start_time.desc(), Voting.voting_number.desc())
    )
    member_votes = mv_query.all()

    if not member_votes:
        return {
            "all_items": [],
            "overall": {
                "same": 0,
                "different": 0,
                "share_same": None,
                "excluded": {"absent": 0, "split": 0, "too_few": 0, "no_faction": 0},
            },
            "by_membership": [],
            "differences": [],
        }

    # Query counts of decisions among other members of the same faction on each voting
    MemberVote = aliased(Vote)
    other_counts = (
        session.query(
            Vote.voting_uuid,
            Vote.decision,
            func.count(Vote.decision),
        )
        .join(
            MemberVote,
            and_(
                Vote.voting_uuid == MemberVote.voting_uuid,
                Vote.faction == MemberVote.faction,
            ),
        )
        .join(Voting, Vote.voting_uuid == Voting.uuid)
        .filter(MemberVote.member_uuid == person_uuid)
        .filter(Vote.member_uuid != person_uuid)
        .filter(Voting.type == "AVALIK")
        .filter(~is_tech_sql)
        .filter(Vote.decision.in_(list(POSITIONS)))
        .group_by(Vote.voting_uuid, Vote.decision)
        .all()
    )

    other_positions_map: dict[str, dict[str, int]] = defaultdict(dict)
    for v_uuid, dec, cnt in other_counts:
        other_positions_map[v_uuid][dec] = cnt

    # Pre-check existing session source files for speech linking
    candidate_files = {
        format_session_source_file(r.sitting_date, r.sitting_datetime) for r in member_votes
    }
    candidate_files.discard(None)
    existing_source_files: set[str] = set()
    if candidate_files:
        try:
            existing_rows = (
                session.query(Speech.source_file)
                .filter(Speech.source_file.in_(candidate_files))
                .distinct()
                .all()
            )
            existing_source_files = {r[0] for r in existing_rows}
        except Exception as e:
            logger.warning("Could not query Speech.source_file for session matching: %s", e)

    all_items = []
    differences = []

    for row in member_votes:
        v_uuid = row.voting_uuid
        v_num = row.voting_number
        s_date = row.sitting_date
        desc = row.description
        doc_title = row.related_document_title
        m_dec = row.member_decision
        m_fac = row.member_faction
        mem_num = row.membership

        cf = format_session_source_file(row.sitting_date, row.sitting_datetime)
        session_src_file = cf if cf in existing_source_files else None

        if m_fac in EXCLUDED_FACTIONS:
            res_type = "no_faction"
            fac_pos = None
        elif m_dec == "PUUDUB":
            res_type = "absent"
            fac_pos = None
        else:
            counts = other_positions_map.get(v_uuid, {})
            total_other = sum(counts.values())
            if total_other < 3:
                res_type = "too_few"
                fac_pos = None
            else:
                strict_maj = None
                for dec, cnt in counts.items():
                    if cnt > total_other / 2:
                        strict_maj = dec
                        break
                if not strict_maj:
                    res_type = "split"
                    fac_pos = None
                else:
                    fac_pos = strict_maj
                    if m_dec == fac_pos:
                        res_type = "same"
                    else:
                        res_type = "different"

        item = {
            "voting_uuid": v_uuid,
            "voting_number": v_num,
            "sitting_date": s_date,
            "description": desc,
            "related_document_title": doc_title,
            "related_document": {"title": doc_title} if doc_title else None,
            "member_decision": m_dec,
            "decision": m_dec,
            "faction_position": fac_pos,
            "faction": m_fac,
            "faction_name": m_fac,
            "session_source_file": session_src_file,
            "membership": mem_num,
            "result_type": res_type,
        }
        all_items.append(item)

        if res_type == "different":
            differences.append(item)

    # Compute breakdown by membership
    items_by_mem: dict[int, list[dict]] = defaultdict(list)
    for it in all_items:
        if it["membership"] is not None:
            items_by_mem[it["membership"]].append(it)

    by_membership = []
    for m in sorted(items_by_mem.keys(), reverse=True):
        m_summary = _summarize_items(items_by_mem[m])
        by_membership.append(
            {
                "membership": int(m),
                "same": m_summary["same"],
                "different": m_summary["different"],
                "share_same": m_summary["share_same"],
            }
        )

    overall = _summarize_items(all_items)

    return {
        "all_items": all_items,
        "overall": overall,
        "by_membership": by_membership,
        "differences": differences,
        "items_by_mem": items_by_mem,
    }


def get_cached_person_alignment(session, person_uuid: str) -> dict:
    """Get person alignment from in-memory cache, invalidated on sync."""
    last_sync = _get_last_sync_at(session)
    if _ALIGNMENT_CACHE["last_sync_at"] != last_sync:
        _ALIGNMENT_CACHE["last_sync_at"] = last_sync
        _ALIGNMENT_CACHE["persons"].clear()

    cached = _ALIGNMENT_CACHE["persons"].get(person_uuid, MISSING)
    if cached is not MISSING:
        return cached

    data = compute_person_alignment(session, person_uuid)
    _ALIGNMENT_CACHE["persons"][person_uuid] = data
    return data


def get_faction_alignment(session, person_uuid: str, membership: str = "all") -> dict:
    """Return faction alignment statistics for person, optionally filtered by membership."""
    data = get_cached_person_alignment(session, person_uuid)

    if not membership or membership == "all":
        summary = data["overall"]
    else:
        mem_int = int(membership)
        m_items = data.get("items_by_mem", {}).get(mem_int, [])
        summary = _summarize_items(m_items)

    return {
        "same": summary["same"],
        "different": summary["different"],
        "share_same": summary["share_same"],
        "excluded": summary["excluded"],
        "by_membership": data["by_membership"],
    }


def get_faction_alignment_differences(
    session,
    person_uuid: str,
    membership: str = "all",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Return paged list of votings where the MP voted differently from their faction majority."""
    data = get_cached_person_alignment(session, person_uuid)
    diffs = data["differences"]

    if membership and membership != "all":
        mem_int = int(membership)
        diffs = [d for d in diffs if d.get("membership") == mem_int]

    paged = diffs[offset : offset + limit]
    results = [
        {
            "voting_uuid": it["voting_uuid"],
            "voting_number": it["voting_number"],
            "sitting_date": it["sitting_date"],
            "description": it["description"],
            "related_document_title": it["related_document_title"],
            "related_document": it["related_document"],
            "member_decision": it["member_decision"],
            "decision": it["decision"],
            "faction_position": it["faction_position"],
            "faction": it["faction"],
            "faction_name": it["faction_name"],
            "session_source_file": it["session_source_file"],
        }
        for it in paged
    ]
    return {
        "total": len(diffs),
        "limit": limit,
        "offset": offset,
        "results": results,
    }
