from sqlalchemy import func, case
from src.load.database import SessionLocal
from src.load.models import Attendance

def get_attendance_stats():
    session = SessionLocal()
    try:
        results = (
            session.query(
                Attendance.member_name,
                func.count(Attendance.id).label("total_sessions"),
                func.sum(
                    case(
                        (Attendance.status == "KOHAL", 1),
                        else_=0
                    )
                ).label("present_sessions")
            )
            .group_by(Attendance.member_name)
            .order_by(func.count(Attendance.id).desc())
            .all()
        )
        
        stats = []
        for member_name, total, present in results:
            if total == 0:
                continue
            
            present_val = int(present) if present else 0
            total_val = int(total)
            
            percentage = round((present_val / total_val) * 100, 1)
            stats.append({
                "member_name": member_name,
                "total_sessions": total_val,
                "present_sessions": present_val,
                "attendance_percentage": percentage
            })
            
        stats.sort(key=lambda x: x["attendance_percentage"], reverse=True)
        return stats
    finally:
        session.close()
