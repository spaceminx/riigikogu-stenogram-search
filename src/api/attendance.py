import json
import os
from datetime import datetime

from sqlalchemy import case, func

from config import MEMBERSHIP_DATES, OUTPUT_DIR_PROCESSED
from src.load.database import SessionLocal
from src.load.models import Attendance


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
                    fac = p.get("faction") or "Fraktsiooni mittekuuluvad Riigikogu liikmed"
                    member_factions[member] = fac
                    faction_counts[fac] = faction_counts.get(fac, 0) + 1
                    break
        return active, faction_counts, member_factions
    except Exception:
        return set(), {}, {}


def get_attendance_stats(
    membership: str | None = "15",
    faction: str | None = None,
    active_only: bool = False,
) -> list[dict]:
    """Calculate attendance statistics for parliament members with optional filters."""
    session = SessionLocal()
    try:
        active_members, _, active_member_factions = (
            get_active_members_data() if active_only else (set(), {}, {})
        )

        if active_only and not active_members:
            return []

        if active_only and faction:
            target_members = [m for m, fac in active_member_factions.items() if fac == faction]
            if not target_members:
                return []
        elif active_only:
            target_members = list(active_members)
        else:
            target_members = None

        query = session.query(
            Attendance.member_name,
            func.count(Attendance.id).label("total_sessions"),
            func.sum(case((Attendance.status == "KOHAL", 1), else_=0)).label("present_sessions"),
        )

        if membership in MEMBERSHIP_DATES:
            start_d, end_d = MEMBERSHIP_DATES[membership]
            query = query.filter(
                Attendance.session_date >= start_d,
                Attendance.session_date <= f"{end_d}T23:59:59",
            )

        if target_members is not None:
            query = query.filter(Attendance.member_name.in_(target_members))
        elif faction:
            query = query.filter(Attendance.faction == faction)

        results = query.group_by(Attendance.member_name).all()

        faction_map = {}
        if not active_only:
            f_query = session.query(
                Attendance.member_name,
                Attendance.faction,
                func.max(Attendance.session_date),
            ).filter(Attendance.faction != "", Attendance.faction.isnot(None))
            if membership in MEMBERSHIP_DATES:
                start_d, end_d = MEMBERSHIP_DATES[membership]
                f_query = f_query.filter(
                    Attendance.session_date >= start_d,
                    Attendance.session_date <= f"{end_d}T23:59:59",
                )
            if faction:
                f_query = f_query.filter(Attendance.faction == faction)
            f_rows = f_query.group_by(Attendance.member_name).all()
            faction_map = {r[0]: r[1] for r in f_rows}

        stats = []
        for member_name, total, present in results:
            if not total:
                continue

            present_val = int(present) if present else 0
            total_val = int(total)

            percentage = round((present_val / total_val) * 100, 1)
            if active_only:
                member_faction = active_member_factions.get(
                    member_name, "Fraktsiooni mittekuuluvad Riigikogu liikmed"
                )
            else:
                member_faction = faction or faction_map.get(member_name, "Fraktsioonita")

            stats.append(
                {
                    "member_name": member_name,
                    "faction": member_faction,
                    "total_sessions": total_val,
                    "present_sessions": present_val,
                    "attendance_percentage": percentage,
                }
            )

        stats.sort(key=lambda x: (x["present_sessions"], x["attendance_percentage"]), reverse=True)
        return stats
    finally:
        session.close()


def get_faction_attendance_stats(
    membership: str | None = "15",
    active_only: bool = False,
) -> list[dict]:
    """Calculate aggregated attendance statistics for parliamentary factions."""
    session = SessionLocal()
    try:
        if active_only:
            active_members, active_faction_counts, active_member_factions = (
                get_active_members_data()
            )
            if not active_members:
                return []

            query = session.query(
                Attendance.member_name,
                func.count(Attendance.id).label("total_sessions"),
                func.sum(case((Attendance.status == "KOHAL", 1), else_=0)).label(
                    "present_sessions"
                ),
            )

            if membership in MEMBERSHIP_DATES:
                start_d, end_d = MEMBERSHIP_DATES[membership]
                query = query.filter(
                    Attendance.session_date >= start_d, Attendance.session_date <= end_d
                )

            query = query.filter(Attendance.member_name.in_(active_members))
            member_results = query.group_by(Attendance.member_name).all()

            faction_totals: dict[str, dict[str, int]] = {}
            for member_name, total, present in member_results:
                fac_name = active_member_factions.get(
                    member_name, "Fraktsiooni mittekuuluvad Riigikogu liikmed"
                )
                if fac_name not in faction_totals:
                    faction_totals[fac_name] = {"total": 0, "present": 0}
                faction_totals[fac_name]["total"] += int(total) if total else 0
                faction_totals[fac_name]["present"] += int(present) if present else 0

            stats = []
            for fac_name, m_count in active_faction_counts.items():
                totals = faction_totals.get(fac_name, {"total": 0, "present": 0})
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
                    }
                )

            stats.sort(key=lambda x: x["attendance_percentage"], reverse=True)
            return stats

        query = session.query(
            Attendance.faction,
            func.count(func.distinct(Attendance.member_name)).label("member_count"),
            func.count(Attendance.id).label("total_sessions"),
            func.sum(case((Attendance.status == "KOHAL", 1), else_=0)).label("present_sessions"),
        ).filter(Attendance.faction != "", Attendance.faction.isnot(None))

        if membership in MEMBERSHIP_DATES:
            start_d, end_d = MEMBERSHIP_DATES[membership]
            query = query.filter(
                Attendance.session_date >= start_d, Attendance.session_date <= end_d
            )

        results = query.group_by(Attendance.faction).all()

        stats = []
        for fac_name, member_count, total, present in results:
            if not total:
                continue

            present_val = int(present) if present else 0
            total_val = int(total)

            percentage = round((present_val / total_val) * 100, 1)
            stats.append(
                {
                    "faction": fac_name,
                    "member_count": int(member_count),
                    "total_sessions": total_val,
                    "present_sessions": present_val,
                    "attendance_percentage": percentage,
                }
            )

        stats.sort(key=lambda x: x["attendance_percentage"], reverse=True)
        return stats
    finally:
        session.close()


def get_factions_list(membership: str | None = "15") -> list[str]:
    """Return distinct faction names available for a parliamentary membership."""
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
                Attendance.session_date >= start_d, Attendance.session_date <= end_d
            )

        return [r[0] for r in query.order_by(Attendance.faction).all()]
    finally:
        session.close()
