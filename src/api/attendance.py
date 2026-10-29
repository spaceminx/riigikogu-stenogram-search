import json
import os
from datetime import datetime

from sqlalchemy import case, func

from config import MEMBERSHIP_DATES, OUTPUT_DIR_PROCESSED, latest_membership
from src.api.roles import NO_FACTION, role_condition
from src.api.votings import get_faction_vote_participation, get_member_vote_participation
from src.load.database import SessionLocal
from src.load.models import Attendance, AttendanceCheck


def get_active_members_data() -> tuple[set[str], dict[str, int], dict[str, str]]:
    """Return active member names, count per current faction, and member-to-faction mapping."""
    factions_file = os.path.join(OUTPUT_DIR_PROCESSED, "factions_map.json")
    if not os.path.exists(factions_file):
        return set(), {}, {}
    try:
        with open(factions_file, encoding="utf-8") as f:
            factions_map = json.load(f)
        today = datetime.now().strftime("%Y-%m-%d")
        active = set()
        faction_counts: dict[str, int] = {}
        member_factions: dict[str, str] = {}
        for member, periods in factions_map.items():
            for p in periods:
                if p.get("end", "") >= today or p.get("end") == "2099-12-31":
                    active.add(member)
                    fac = p.get("faction") or NO_FACTION
                    member_factions[member] = fac
                    faction_counts[fac] = faction_counts.get(fac, 0) + 1
                    break
        return active, faction_counts, member_factions
    except Exception:
        return set(), {}, {}


def get_attendance_stats(
    membership: str | None = None,
    faction: str | None = None,
    active_only: bool = False,
    exclude_infotund: bool = False,
    role: str | None = None,
) -> list[dict]:
    """Calculate attendance statistics for parliament members with optional filters."""
    if membership is None:
        membership = latest_membership()
    session = SessionLocal()
    try:
        from src.load.models import Person

        member_key = func.coalesce(Attendance.member_uuid, Attendance.member_name)

        active_uuids: set[str] | None = None
        if active_only:
            active_persons = session.query(Person.uuid).filter(Person.active == 1).all()
            active_uuids = {r[0] for r in active_persons if r[0]}

        infotund_uuids = (
            session.query(AttendanceCheck.voting_uuid).filter(
                AttendanceCheck.sitting_type == "infotund"
            )
            if exclude_infotund
            else None
        )

        f_query = session.query(
            member_key.label("member_key"),
            Attendance.faction,
            func.max(Attendance.session_date),
        ).filter(Attendance.faction != "", Attendance.faction.isnot(None))
        if membership in MEMBERSHIP_DATES:
            start_d, end_d = MEMBERSHIP_DATES[membership]
            f_query = f_query.filter(
                Attendance.session_date >= start_d,
                Attendance.session_date <= f"{end_d}T23:59:59",
            )
        if exclude_infotund:
            f_query = f_query.filter(Attendance.voting_uuid.not_in(infotund_uuids))
        if role in ("coalition", "opposition"):
            f_query = f_query.filter(
                role_condition(
                    Attendance.faction, func.substr(Attendance.session_date, 1, 10), role
                )
            )
        f_rows = f_query.group_by(member_key).all()
        faction_map = {r[0]: r[1] for r in f_rows}

        query = session.query(
            func.max(Attendance.member_name).label("member_name"),
            func.max(Attendance.member_uuid).label("member_uuid"),
            func.count(Attendance.id).label("total_sessions"),
            func.sum(case((Attendance.status == "KOHAL", 1), else_=0)).label("present_sessions"),
            member_key.label("member_key"),
        )

        if membership in MEMBERSHIP_DATES:
            start_d, end_d = MEMBERSHIP_DATES[membership]
            query = query.filter(
                Attendance.session_date >= start_d,
                Attendance.session_date <= f"{end_d}T23:59:59",
            )

        if exclude_infotund:
            query = query.filter(Attendance.voting_uuid.not_in(infotund_uuids))

        if role in ("coalition", "opposition"):
            query = query.filter(
                role_condition(
                    Attendance.faction, func.substr(Attendance.session_date, 1, 10), role
                )
            )

        if active_only:
            if active_uuids:
                if faction:
                    target_uuids = {u for u in active_uuids if faction_map.get(u) == faction}
                    if not target_uuids:
                        return []
                    query = query.filter(Attendance.member_uuid.in_(target_uuids))
                else:
                    query = query.filter(Attendance.member_uuid.in_(active_uuids))
            else:
                active_members, _, active_member_factions = get_active_members_data()
                if not active_members:
                    return []
                if faction:
                    target_members = [
                        m for m, fac in active_member_factions.items() if fac == faction
                    ]
                    if not target_members:
                        return []
                    query = query.filter(Attendance.member_name.in_(target_members))
                else:
                    query = query.filter(Attendance.member_name.in_(active_members))
        elif faction:
            query = query.filter(Attendance.faction == faction)

        results = query.group_by(member_key).all()

        # Without active_only the attendance rows are limited to the faction, so the votes are too.
        member_votes = get_member_vote_participation(
            session,
            membership=membership,
            role=role,
            faction=faction if not active_only else None,
        )

        stats = []
        for member_name, member_uuid, total, present, m_key in results:
            if not total:
                continue

            present_val = int(present) if present else 0
            total_val = int(total)

            percentage = round((present_val / total_val) * 100, 1)
            default_fac = NO_FACTION if active_only else "Fraktsioonita"
            member_faction = faction or faction_map.get(m_key, default_fac)

            mv = member_votes.get(
                member_uuid,
                {"voted": 0, "not_voted": 0, "absent": 0, "total": 0, "voted_pct": None},
            )

            stats.append(
                {
                    "member_name": member_name,
                    "member_uuid": member_uuid,
                    "faction": member_faction,
                    "total_sessions": total_val,
                    "present_sessions": present_val,
                    "attendance_percentage": percentage,
                    "registered_checks": present_val,
                    "total_checks": total_val,
                    "registered_pct": percentage,
                    "votes_voted": mv["voted"],
                    "votes_not_voted": mv["not_voted"],
                    "votes_absent": mv["absent"],
                    "votes_total": mv["total"],
                    "votes_voted_pct": mv["voted_pct"],
                }
            )

        stats.sort(key=lambda x: (x["present_sessions"], x["attendance_percentage"]), reverse=True)
        return stats
    finally:
        session.close()


def _compute_person_attendance_data(
    session,
    person_uuid: str,
    infotund_uuids,
    target_role: str | None = None,
) -> dict:
    base_filter = Attendance.member_uuid == person_uuid

    overall_query = session.query(
        func.count(Attendance.id).label("total"),
        func.sum(case((Attendance.status == "KOHAL", 1), else_=0)).label("present"),
    ).filter(base_filter)
    if infotund_uuids is not None:
        overall_query = overall_query.filter(Attendance.voting_uuid.not_in(infotund_uuids))
    if target_role in ("coalition", "opposition"):
        overall_query = overall_query.filter(
            role_condition(
                Attendance.faction, func.substr(Attendance.session_date, 1, 10), target_role
            )
        )
    overall_row = overall_query.first()

    total_sessions = int(overall_row[0]) if overall_row and overall_row[0] else 0
    present_sessions = int(overall_row[1]) if overall_row and overall_row[1] else 0
    absent_sessions = total_sessions - present_sessions
    percentage = round((present_sessions / total_sessions) * 100, 1) if total_sessions > 0 else 0.0

    overall_votes = get_member_vote_participation(session, membership="all", role=target_role).get(
        person_uuid,
        {"voted": 0, "not_voted": 0, "absent": 0, "total": 0, "voted_pct": None},
    )

    by_membership = []
    for mem_id, (start_d, end_d) in sorted(
        MEMBERSHIP_DATES.items(), key=lambda x: int(x[0]), reverse=True
    ):
        mem_query = session.query(
            func.count(Attendance.id).label("total"),
            func.sum(case((Attendance.status == "KOHAL", 1), else_=0)).label("present"),
        ).filter(
            base_filter,
            Attendance.session_date >= start_d,
            Attendance.session_date <= f"{end_d}T23:59:59",
        )
        if infotund_uuids is not None:
            mem_query = mem_query.filter(Attendance.voting_uuid.not_in(infotund_uuids))
        if target_role in ("coalition", "opposition"):
            mem_query = mem_query.filter(
                role_condition(
                    Attendance.faction, func.substr(Attendance.session_date, 1, 10), target_role
                )
            )
        mem_row = mem_query.first()
        m_total = int(mem_row[0]) if mem_row and mem_row[0] else 0
        m_votes = get_member_vote_participation(
            session, membership=str(mem_id), role=target_role
        ).get(
            person_uuid,
            {"voted": 0, "not_voted": 0, "absent": 0, "total": 0, "voted_pct": None},
        )
        if m_total > 0 or m_votes["total"] > 0:
            m_present = int(mem_row[1]) if mem_row and mem_row[1] else 0
            m_absent = m_total - m_present
            m_pct = round((m_present / m_total) * 100, 1) if m_total > 0 else 0.0
            by_membership.append(
                {
                    "membership": str(mem_id),
                    "total_sessions": m_total,
                    "present_sessions": m_present,
                    "absent_sessions": m_absent,
                    "attendance_percentage": m_pct,
                    "votes": m_votes,
                }
            )

    return {
        "total_sessions": total_sessions,
        "present_sessions": present_sessions,
        "absent_sessions": absent_sessions,
        "attendance_percentage": percentage,
        "votes": overall_votes,
        "by_membership": by_membership,
    }


def get_person_attendance(
    person_uuid: str,
    exclude_infotund: bool = False,
    role: str | None = None,
) -> dict:
    """Calculate attendance statistics for a specific MP by UUID.

    Uses the same attendance definition as get_attendance_stats:
    - total_sessions: count of attendance checks (Attendance.id)
    - present_sessions: count of Attendance.status == 'KOHAL'
    - absent_sessions: total_sessions - present_sessions
    - attendance_percentage: round((present_sessions / total_sessions) * 100, 1)
    """
    session = SessionLocal()
    try:
        from src.load.models import Person

        person = session.query(Person).filter(Person.uuid == person_uuid).first()
        if not person:
            raise ValueError("Isikut ei leitud.")

        infotund_uuids = (
            session.query(AttendanceCheck.voting_uuid).filter(
                AttendanceCheck.sitting_type == "infotund"
            )
            if exclude_infotund
            else None
        )

        main_data = _compute_person_attendance_data(
            session, person_uuid, infotund_uuids, target_role=role
        )
        coalition_data = _compute_person_attendance_data(
            session, person_uuid, infotund_uuids, target_role="coalition"
        )
        opposition_data = _compute_person_attendance_data(
            session, person_uuid, infotund_uuids, target_role="opposition"
        )

        return {
            "uuid": person_uuid,
            "member_name": person.full_name,
            "total_sessions": main_data["total_sessions"],
            "present_sessions": main_data["present_sessions"],
            "absent_sessions": main_data["absent_sessions"],
            "attendance_percentage": main_data["attendance_percentage"],
            "votes": main_data["votes"],
            "by_membership": main_data["by_membership"],
            "role_breakdown": {
                "coalition": coalition_data,
                "opposition": opposition_data,
            },
        }
    finally:
        session.close()


def get_faction_attendance_stats(
    membership: str | None = None,
    active_only: bool = False,
    exclude_infotund: bool = False,
    role: str | None = None,
) -> list[dict]:
    """Calculate aggregated attendance statistics for parliamentary factions."""
    if membership is None:
        membership = latest_membership()
    session = SessionLocal()
    try:
        from src.load.models import Person

        member_key = func.coalesce(Attendance.member_uuid, Attendance.member_name)

        infotund_uuids = (
            session.query(AttendanceCheck.voting_uuid).filter(
                AttendanceCheck.sitting_type == "infotund"
            )
            if exclude_infotund
            else None
        )

        if active_only:
            active_persons = session.query(Person.uuid).filter(Person.active == 1).all()
            active_uuids = {r[0] for r in active_persons if r[0]}

            if active_uuids:
                f_query = session.query(
                    member_key,
                    Attendance.faction,
                    func.max(Attendance.session_date),
                ).filter(
                    Attendance.faction != "",
                    Attendance.faction.isnot(None),
                )
                if membership in MEMBERSHIP_DATES:
                    start_d, end_d = MEMBERSHIP_DATES[membership]
                    f_query = f_query.filter(
                        Attendance.session_date >= start_d,
                        Attendance.session_date <= f"{end_d}T23:59:59",
                    )
                if exclude_infotund:
                    f_query = f_query.filter(Attendance.voting_uuid.not_in(infotund_uuids))
                if role in ("coalition", "opposition"):
                    f_query = f_query.filter(
                        role_condition(
                            Attendance.faction, func.substr(Attendance.session_date, 1, 10), role
                        )
                    )
                latest_factions = {r[0]: r[1] for r in f_query.group_by(member_key).all()}

                query = session.query(
                    member_key,
                    func.count(Attendance.id).label("total_sessions"),
                    func.sum(case((Attendance.status == "KOHAL", 1), else_=0)).label(
                        "present_sessions"
                    ),
                )
                if membership in MEMBERSHIP_DATES:
                    start_d, end_d = MEMBERSHIP_DATES[membership]
                    query = query.filter(
                        Attendance.session_date >= start_d,
                        Attendance.session_date <= f"{end_d}T23:59:59",
                    )
                if exclude_infotund:
                    query = query.filter(Attendance.voting_uuid.not_in(infotund_uuids))
                if role in ("coalition", "opposition"):
                    query = query.filter(
                        role_condition(
                            Attendance.faction, func.substr(Attendance.session_date, 1, 10), role
                        )
                    )
                query = query.filter(Attendance.member_uuid.in_(active_uuids))
                member_results = query.group_by(member_key).all()

                # Members with no attendance rows in the selected period/role are left out,
                # instead of being counted as non-affiliated with zero sessions.
                members_with_rows = {r[0] for r in member_results}
                active_faction_counts: dict[str, int] = {}
                active_uuid_factions: dict[str, str] = {}
                for uid in active_uuids:
                    if uid not in latest_factions and uid not in members_with_rows:
                        continue
                    fac = latest_factions.get(uid, NO_FACTION)
                    active_uuid_factions[uid] = fac
                    active_faction_counts[fac] = active_faction_counts.get(fac, 0) + 1

                faction_totals: dict[str, dict[str, int]] = {}
                for m_key, total, present in member_results:
                    fac_name = active_uuid_factions.get(m_key, NO_FACTION)
                    if fac_name not in faction_totals:
                        faction_totals[fac_name] = {"total": 0, "present": 0}
                    faction_totals[fac_name]["total"] += int(total) if total else 0
                    faction_totals[fac_name]["present"] += int(present) if present else 0

                active_faction_votes: dict[str, dict[str, int]] = {}
                member_votes = get_member_vote_participation(
                    session, membership=membership, role=role
                )
                for uid, fac in active_uuid_factions.items():
                    if fac not in active_faction_votes:
                        active_faction_votes[fac] = {
                            "voted": 0,
                            "not_voted": 0,
                            "absent": 0,
                            "total": 0,
                        }
                    mv = member_votes.get(uid)
                    if mv:
                        active_faction_votes[fac]["voted"] += mv["voted"]
                        active_faction_votes[fac]["not_voted"] += mv["not_voted"]
                        active_faction_votes[fac]["absent"] += mv["absent"]
                        active_faction_votes[fac]["total"] += mv["total"]

                stats = []
                for fac_name, m_count in active_faction_counts.items():
                    totals = faction_totals.get(fac_name, {"total": 0, "present": 0})
                    total_val = totals["total"]
                    present_val = totals["present"]
                    percentage = round((present_val / total_val) * 100, 1) if total_val > 0 else 0.0

                    f_votes = active_faction_votes.get(
                        fac_name, {"voted": 0, "not_voted": 0, "absent": 0, "total": 0}
                    )
                    v_tot = f_votes["total"]
                    v_voted = f_votes["voted"]
                    v_nv = f_votes["not_voted"]
                    v_ab = f_votes["absent"]
                    v_pct = round((v_voted / v_tot) * 100.0, 1) if v_tot > 0 else None

                    stats.append(
                        {
                            "faction": fac_name,
                            "member_count": m_count,
                            "total_sessions": total_val,
                            "present_sessions": present_val,
                            "attendance_percentage": percentage,
                            "registered_checks": present_val,
                            "total_checks": total_val,
                            "registered_pct": percentage,
                            "votes_voted": v_voted,
                            "votes_not_voted": v_nv,
                            "votes_absent": v_ab,
                            "votes_total": v_tot,
                            "votes_voted_pct": v_pct,
                        }
                    )

                stats.sort(key=lambda x: x["attendance_percentage"], reverse=True)
                return stats
            else:
                active_members, active_faction_counts, active_member_factions = (
                    get_active_members_data()
                )
                if not active_members:
                    return []

                query = session.query(
                    member_key,
                    func.count(Attendance.id).label("total_sessions"),
                    func.sum(case((Attendance.status == "KOHAL", 1), else_=0)).label(
                        "present_sessions"
                    ),
                )

                if membership in MEMBERSHIP_DATES:
                    start_d, end_d = MEMBERSHIP_DATES[membership]
                    query = query.filter(
                        Attendance.session_date >= start_d,
                        Attendance.session_date <= f"{end_d}T23:59:59",
                    )

                if exclude_infotund:
                    query = query.filter(Attendance.voting_uuid.not_in(infotund_uuids))

                if role in ("coalition", "opposition"):
                    query = query.filter(
                        role_condition(
                            Attendance.faction, func.substr(Attendance.session_date, 1, 10), role
                        )
                    )

                query = query.filter(Attendance.member_name.in_(active_members))
                member_results = query.group_by(member_key).all()

                faction_totals_fallback: dict[str, dict[str, int]] = {}
                for m_key, total, present in member_results:
                    fac_name = active_member_factions.get(m_key, NO_FACTION)
                    if fac_name not in faction_totals_fallback:
                        faction_totals_fallback[fac_name] = {"total": 0, "present": 0}
                    faction_totals_fallback[fac_name]["total"] += int(total) if total else 0
                    faction_totals_fallback[fac_name]["present"] += int(present) if present else 0

                stats = []
                for fac_name, m_count in active_faction_counts.items():
                    totals = faction_totals_fallback.get(fac_name, {"total": 0, "present": 0})
                    total_val = totals["total"]
                    present_val = totals["present"]
                    percentage = round((present_val / total_val) * 100, 1) if total_val > 0 else 0.0
                    stats.append(
                        {
                            "faction": fac_name,
                            "member_count": m_count,
                            "total_sessions": total_val,
                            "present_sessions": present_val,
                            "attendance_percentage": percentage,
                            "registered_checks": present_val,
                            "total_checks": total_val,
                            "registered_pct": percentage,
                            "votes_voted": 0,
                            "votes_not_voted": 0,
                            "votes_absent": 0,
                            "votes_total": 0,
                            "votes_voted_pct": None,
                        }
                    )

                stats.sort(key=lambda x: x["attendance_percentage"], reverse=True)
                return stats

        query = session.query(
            Attendance.faction,
            func.count(func.distinct(member_key)).label("member_count"),
            func.count(Attendance.id).label("total_sessions"),
            func.sum(case((Attendance.status == "KOHAL", 1), else_=0)).label("present_sessions"),
        ).filter(Attendance.faction != "", Attendance.faction.isnot(None))

        if membership in MEMBERSHIP_DATES:
            start_d, end_d = MEMBERSHIP_DATES[membership]
            query = query.filter(
                Attendance.session_date >= start_d,
                Attendance.session_date <= f"{end_d}T23:59:59",
            )

        if exclude_infotund:
            query = query.filter(Attendance.voting_uuid.not_in(infotund_uuids))

        if role in ("coalition", "opposition"):
            query = query.filter(
                role_condition(
                    Attendance.faction, func.substr(Attendance.session_date, 1, 10), role
                )
            )

        results = query.group_by(Attendance.faction).all()

        faction_votes = get_faction_vote_participation(session, membership=membership, role=role)

        stats = []
        for fac_name, member_count, total, present in results:
            if not total:
                continue

            present_val = int(present) if present else 0
            total_val = int(total)

            percentage = round((present_val / total_val) * 100, 1)
            fv = faction_votes.get(
                fac_name,
                {"voted": 0, "not_voted": 0, "absent": 0, "total": 0, "voted_pct": None},
            )

            stats.append(
                {
                    "faction": fac_name,
                    "member_count": int(member_count),
                    "total_sessions": total_val,
                    "present_sessions": present_val,
                    "attendance_percentage": percentage,
                    "registered_checks": present_val,
                    "total_checks": total_val,
                    "registered_pct": percentage,
                    "votes_voted": fv["voted"],
                    "votes_not_voted": fv["not_voted"],
                    "votes_absent": fv["absent"],
                    "votes_total": fv["total"],
                    "votes_voted_pct": fv["voted_pct"],
                }
            )

        stats.sort(key=lambda x: x["attendance_percentage"], reverse=True)
        return stats
    finally:
        session.close()


def get_factions_list(membership: str | None = None) -> list[str]:
    """Return distinct faction names available for a parliamentary membership."""
    if membership is None:
        membership = latest_membership()
    session = SessionLocal()
    try:
        query = (
            session.query(Attendance.faction)
            .filter(Attendance.faction != "", Attendance.faction.isnot(None))
            .distinct()
        )

        if membership in MEMBERSHIP_DATES:
            start_d, end_d = MEMBERSHIP_DATES[membership]
            query = query.filter(
                Attendance.session_date >= start_d,
                Attendance.session_date <= f"{end_d}T23:59:59",
            )

        return [r[0] for r in query.order_by(Attendance.faction).all()]
    finally:
        session.close()
