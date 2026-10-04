import json
import os
from datetime import datetime

from sqlalchemy import case, func

from config import OUTPUT_DIR_PROCESSED
from src.load.database import SessionLocal
from src.load.models import Attendance

MEMBERSHIP_DATES = {
    "14": ("2019-04-04", "2023-03-31T23:59:59"),
    "15": ("2023-04-01", "2099-12-31"),
}


def get_active_members() -> set[str]:
    """Return the set of member names who are currently active MPs."""
    factions_file = os.path.join(OUTPUT_DIR_PROCESSED, "factions_map.json")
    if not os.path.exists(factions_file):
        return set()
    try:
        with open(factions_file, encoding="utf-8") as f:
            factions_map = json.load(f)
        today = datetime.now().strftime("%Y-%m-%d")
        active = set()
        for member, periods in factions_map.items():
            for p in periods:
                if p.get("end", "") >= today or p.get("end") == "2099-12-31":
                    active.add(member)
                    break
        return active
    except Exception:
        return set()


def get_attendance_stats(
    membership: str | None = "15",
    faction: str | None = None,
    active_only: bool = False,
) -> list[dict]:
    """Calculate attendance statistics for parliament members with optional filters."""
    session = SessionLocal()
    try:
        query = session.query(
            Attendance.member_name,
            func.count(Attendance.id).label("total_sessions"),
            func.sum(case((Attendance.status == "KOHAL", 1), else_=0)).label("present_sessions"),
        )

        if membership in MEMBERSHIP_DATES:
            start_d, end_d = MEMBERSHIP_DATES[membership]
            query = query.filter(
                Attendance.session_date >= start_d, Attendance.session_date <= end_d
            )

        if faction:
            query = query.filter(Attendance.faction == faction)

        if active_only:
            active_members = get_active_members()
            if not active_members:
                return []
            query = query.filter(Attendance.member_name.in_(active_members))

        results = query.group_by(Attendance.member_name).all()

        faction_map = {}
        if not faction:
            f_query = session.query(
                Attendance.member_name,
                Attendance.faction,
                func.max(Attendance.session_date),
            ).filter(Attendance.faction != "", Attendance.faction.isnot(None))
            if membership in MEMBERSHIP_DATES:
                start_d, end_d = MEMBERSHIP_DATES[membership]
                f_query = f_query.filter(
                    Attendance.session_date >= start_d, Attendance.session_date <= end_d
                )
            f_rows = f_query.group_by(Attendance.member_name).all()
            faction_map = {r[0]: r[1] for r in f_rows}

        stats = []
        for member_name, total, present in results:
            if not total:
                continue

            present_val = int(present) if present else 0
            total_val = int(total)

            percentage = round((present_val / total_val) * 100, 1)
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

        stats.sort(key=lambda x: (x["attendance_percentage"], x["total_sessions"]), reverse=True)
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

        if active_only:
            active_members = get_active_members()
            if not active_members:
                return []
            query = query.filter(Attendance.member_name.in_(active_members))

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
