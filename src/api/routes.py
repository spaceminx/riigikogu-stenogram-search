from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.api.attendance import (
    get_attendance_stats,
    get_faction_attendance_stats,
    get_factions_list,
)
from src.api.search import keyword_activity, keyword_top_speakers, search_by_keyword

router = APIRouter()


@router.get("/")
def root():
    return {"status": "ok"}


@router.get("/attendance/stats")
def attendance_stats(
    membership: str = Query("15", description="Riigikogu koosseis (14, 15 või all)"),
    faction: str | None = Query(None, description="Filtreeri fraktsiooni nime järgi"),
    active_only: bool = Query(False, description="Ainult praegu aktiivsed saadikud"),
):
    try:
        return get_attendance_stats(membership=membership, faction=faction, active_only=active_only)
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või kohalolekutabel ei ole initsialiseeritud. Käivita scripts/fetch_attendance.py või scripts/build_full_database.py.",
        ) from e
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Andmebaasipäring ebaõnnestus: {e}",
        ) from e


@router.get("/attendance/factions")
def attendance_factions(
    membership: str = Query("15", description="Riigikogu koosseis (14, 15 või all)"),
    active_only: bool = Query(False, description="Ainult praegu aktiivsed saadikud"),
):
    try:
        return get_faction_attendance_stats(membership=membership, active_only=active_only)
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või kohalolekutabel ei ole initsialiseeritud. Käivita scripts/fetch_attendance.py või scripts/build_full_database.py.",
        ) from e
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Andmebaasipäring ebaõnnestus: {e}",
        ) from e


@router.get("/attendance/factions/list")
def factions_list(
    membership: str = Query("15", description="Riigikogu koosseis (14, 15 või all)"),
):
    try:
        return get_factions_list(membership=membership)
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või kohalolekutabel ei ole initsialiseeritud.",
        ) from e
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Andmebaasipäring ebaõnnestus: {e}",
        ) from e


@router.get("/search")
def search(
    q: str = Query(..., min_length=1, max_length=1000),
    limit: int = Query(50, ge=1, le=200),
):
    try:
        results = search_by_keyword(q, limit)
        return {
            "query": q,
            "count": len(results),
            "results": results,
        }
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või otsingutabelid ei ole initsialiseeritud. Käivita scripts/build_full_database.py.",
        ) from e
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Otsingupäring ebaõnnestus: {e}",
        ) from e


@router.get("/search/activity")
def search_activity(
    q: str = Query(..., min_length=1, max_length=1000), interval: str = Query("monthly")
):
    if interval not in ("daily", "weekly", "monthly"):
        raise HTTPException(
            status_code=400,
            detail="Intervall peab olema üks järgmistest: 'daily', 'weekly', 'monthly'.",
        )
    try:
        return {"query": q, "interval": interval, "activity": keyword_activity(q, interval)}
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või otsingutabelid ei ole initsialiseeritud. Käivita scripts/build_full_database.py.",
        ) from e
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Aktiivsuse päring ebaõnnestus: {e}",
        ) from e


@router.get("/search/speakers")
def search_speakers(
    q: str = Query(..., min_length=1, max_length=1000),
    limit: int = Query(20, ge=1, le=100),
):
    try:
        return {"query": q, "speakers": keyword_top_speakers(q, limit)}
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või otsingutabelid ei ole initsialiseeritud. Käivita scripts/build_full_database.py.",
        ) from e
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Kõnelejate päring ebaõnnestus: {e}",
        ) from e
