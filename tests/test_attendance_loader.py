import json

from src.load import loader
from src.load.database import SessionLocal
from src.load.loader import create_tables, load_attendance_to_database
from src.load.models import Attendance

CHECK_UUID = "att-loader-check-1"
OTHER_UUID = "att-loader-check-2"


def _rows(uuid, n):
    return [
        {
            "session_date": "2026-11-20",
            "voting_uuid": uuid,
            "member_uuid": f"{uuid}-m{i}",
            "member_name": f"Liige {i}",
            "faction": "Fraktsioon",
            "status": "KOHAL",
        }
        for i in range(n)
    ]


def _cleanup(session):
    session.query(Attendance).filter(Attendance.voting_uuid.in_([CHECK_UUID, OTHER_UUID])).delete(
        synchronize_session=False
    )
    session.commit()


def test_part_loaded_check_is_completed(tmp_path, monkeypatch):
    """A check cut off between two commits gets its missing rows on the next load."""
    create_tables()
    rows = _rows(CHECK_UUID, 7) + _rows(OTHER_UUID, 5)
    (tmp_path / "attendance.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    monkeypatch.setattr(loader, "OUTPUT_DIR_PROCESSED", str(tmp_path))

    session = SessionLocal()
    try:
        _cleanup(session)
        # Simulate an interrupted load: three of the seven rows of the first check committed
        for r in rows[:3]:
            session.add(Attendance(**r))
        session.commit()

        load_attendance_to_database(batch_size=2)

        counts = {
            uuid: session.query(Attendance).filter(Attendance.voting_uuid == uuid).count()
            for uuid in (CHECK_UUID, OTHER_UUID)
        }
        assert counts == {CHECK_UUID: 7, OTHER_UUID: 5}

        # A second load adds nothing
        load_attendance_to_database(batch_size=2)
        assert session.query(Attendance).filter(Attendance.voting_uuid == CHECK_UUID).count() == 7
    finally:
        _cleanup(session)
        session.close()
