import csv
import io
import json
import logging
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.api.attendance import (
    get_attendance_stats,
    get_faction_attendance_stats,
    get_factions_list,
)
from src.api.search import (
    get_dashboard_overview,
    get_plenary_session_dates,
    get_session_speeches,
    get_speech_context,
    keyword_activity,
    keyword_top_speakers,
    search_by_keyword,
)
from src.load.database import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
def root():
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        logger.error("Healthcheck database query failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Andmebaasi ühendus puudub.",
        ) from e
    finally:
        session.close()


@router.get("/overview")
def dashboard_overview():
    try:
        return get_dashboard_overview()
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Arhiivi koondandmed pole praegu kättesaadavad.",
        ) from e
    except SQLAlchemyError as e:
        logger.error("Overview query failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Arhiivi koondandmete päring ebaõnnestus.",
        ) from e


@router.get("/sessions/dates")
def plenary_session_dates():
    try:
        return {"dates": get_plenary_session_dates()}
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Istungite kuupäevad pole praegu kättesaadavad.",
        ) from e
    except SQLAlchemyError as e:
        logger.error("Session dates query failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Istungite kuupäevade päring ebaõnnestus.",
        ) from e


@router.get("/sessions/{session_date}")
def plenary_session(session_date: date):
    try:
        session_date_value = session_date.isoformat()
        speeches = get_session_speeches(session_date_value)
        return {"date": session_date_value, "count": len(speeches), "results": speeches}
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Istungi stenogramm pole praegu kättesaadav.",
        ) from e
    except SQLAlchemyError as e:
        logger.error(
            "Session transcript query failed for date %s: %s", session_date, e, exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Istungi stenogrammi päring ebaõnnestus.",
        ) from e


@router.get("/attendance/stats")
def attendance_stats(
    membership: str = Query(
        "15", description="Riigikogu koosseis (14, 15 või all)", pattern=r"^(\d+|all)$"
    ),
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
        logger.error("Attendance stats query failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Kohalolekuandmete päring ebaõnnestus.",
        ) from e


@router.get("/attendance/factions")
def attendance_factions(
    membership: str = Query(
        "15", description="Riigikogu koosseis (14, 15 või all)", pattern=r"^(\d+|all)$"
    ),
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
        logger.error("Faction attendance stats query failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Fraktsioonide kohaloleku päring ebaõnnestus.",
        ) from e


@router.get("/attendance/factions/list")
def factions_list(
    membership: str = Query(
        "15", description="Riigikogu koosseis (14, 15 või all)", pattern=r"^(\d+|all)$"
    ),
):
    try:
        return get_factions_list(membership=membership)
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või kohalolekutabel ei ole initsialiseeritud.",
        ) from e
    except SQLAlchemyError as e:
        logger.error("Factions list query failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Fraktsioonide nimekirja päring ebaõnnestus.",
        ) from e


@router.get("/search")
def search(
    q: str = Query(..., min_length=1, max_length=1000),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    membership: str = Query(
        "all", description="Riigikogu koosseis (14, 15 või all)", pattern=r"^(\d+|all)$"
    ),
    faction: str | None = Query(None, description="Filtreeri fraktsiooni nime järgi"),
    speaker: str | None = Query(None, description="Filtreeri esineja nime järgi"),
    start_date: str | None = Query(
        None, description="Alguskuupäev (YYYY-MM-DD)", pattern=r"^\d{4}-\d{2}-\d{2}$"
    ),
    end_date: str | None = Query(
        None, description="Lõppkuupäev (YYYY-MM-DD)", pattern=r"^\d{4}-\d{2}-\d{2}$"
    ),
    sort_by: str = Query(
        "date_desc",
        description="Sorteerimine: date_desc (uuemad enne), date_asc (vanemad enne), match_count_desc (sagedus)",
        pattern="^(date_desc|date_asc|match_count_desc)$",
    ),
):
    try:
        results, total_count = search_by_keyword(
            query=q,
            limit=limit,
            offset=offset,
            membership=membership,
            faction=faction,
            speaker=speaker,
            start_date=start_date,
            end_date=end_date,
            sort_by=sort_by,
        )
        return {
            "query": q,
            "total_count": total_count,
            "count": len(results),
            "offset": offset,
            "limit": limit,
            "results": results,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        ) from e
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või otsingutabelid ei ole initsialiseeritud. Käivita scripts/build_full_database.py.",
        ) from e
    except SQLAlchemyError as e:
        logger.error("Search query failed for %r: %s", q, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Otsingupäring ebaõnnestus.",
        ) from e


@router.get("/search/activity")
def search_activity(
    q: str = Query(..., min_length=1, max_length=1000),
    interval: str = Query("monthly"),
    membership: str = Query("all", pattern=r"^(\d+|all)$"),
    faction: str | None = Query(None),
    speaker: str | None = Query(None),
    start_date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
):
    if interval not in ("daily", "weekly", "monthly"):
        raise HTTPException(
            status_code=400,
            detail="Intervall peab olema üks järgmistest: 'daily', 'weekly', 'monthly'.",
        )
    try:
        return {
            "query": q,
            "interval": interval,
            "activity": keyword_activity(
                query=q,
                interval=interval,
                membership=membership,
                faction=faction,
                speaker=speaker,
                start_date=start_date,
                end_date=end_date,
            ),
        }
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        ) from e
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või otsingutabelid ei ole initsialiseeritud. Käivita scripts/build_full_database.py.",
        ) from e
    except SQLAlchemyError as e:
        logger.error("Search activity query failed for %r: %s", q, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Aktiivsuse päring ebaõnnestus.",
        ) from e


@router.get("/search/speakers")
def search_speakers(
    q: str = Query(..., min_length=1, max_length=1000),
    limit: int = Query(20, ge=1, le=100),
    membership: str = Query("all", pattern=r"^(\d+|all)$"),
    faction: str | None = Query(None),
    speaker: str | None = Query(None),
    start_date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
):
    try:
        return {
            "query": q,
            "speakers": keyword_top_speakers(
                query=q,
                limit=limit,
                membership=membership,
                faction=faction,
                speaker=speaker,
                start_date=start_date,
                end_date=end_date,
            ),
        }
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        ) from e
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või otsingutabelid ei ole initsialiseeritud. Käivita scripts/build_full_database.py.",
        ) from e
    except SQLAlchemyError as e:
        logger.error("Search speakers query failed for %r: %s", q, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Kõnelejate päring ebaõnnestus.",
        ) from e


@router.get("/speeches/{speech_id}/context")
def speech_context(
    speech_id: int,
    q: str | None = Query(None, description="Otsingupäring lemmade esiletõstmiseks"),
):
    try:
        context = get_speech_context(speech_id=speech_id, query=q)
        if not context:
            raise HTTPException(status_code=404, detail="Kõnet ei leitud.")
        return context
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või kõnede tabel ei ole initsialiseeritud.",
        ) from e
    except SQLAlchemyError as e:
        logger.error(
            "Speech context query failed for speech_id %d: %s", speech_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Kõne konteksti päring ebaõnnestus.",
        ) from e


@router.get("/search/export")
def search_export(
    q: str = Query(..., min_length=1, max_length=1000),
    format: str = Query("csv", description="Ekspordi formaat: 'csv' või 'json'"),
    membership: str = Query("all", pattern=r"^(\d+|all)$"),
    faction: str | None = Query(None),
    speaker: str | None = Query(None),
    start_date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    sort_by: str = Query("date_desc", pattern="^(date_desc|date_asc|match_count_desc)$"),
    limit: int = Query(2000, ge=1, le=5000),
):
    if format not in ("csv", "json"):
        raise HTTPException(status_code=400, detail="Formaat peab olema 'csv' või 'json'.")

    try:
        results, total_count = search_by_keyword(
            query=q,
            limit=limit,
            offset=0,
            membership=membership,
            faction=faction,
            speaker=speaker,
            start_date=start_date,
            end_date=end_date,
            sort_by=sort_by,
            include_matched_words=False,
        )

        safe_q = "".join(c for c in q if c.isalnum() or c in ("-", "_")).strip() or "otsing"
        ascii_fallback = (
            "".join(c for c in safe_q if c.isascii() and (c.isalnum() or c in ("-", "_"))).strip()
            or "otsing"
        )
        encoded_json_filename = quote(f"riigikogu_{safe_q}.json")
        encoded_csv_filename = quote(f"riigikogu_{safe_q}.csv")

        is_truncated = "true" if total_count > len(results) else "false"
        common_headers = {
            "X-Total-Count": str(total_count),
            "X-Export-Count": str(len(results)),
            "X-Export-Truncated": is_truncated,
        }

        if format == "json":
            return Response(
                content=json.dumps(results, ensure_ascii=False, indent=2),
                media_type="application/json; charset=utf-8",
                headers={
                    **common_headers,
                    "Content-Disposition": f"attachment; filename=\"riigikogu_{ascii_fallback}.json\"; filename*=UTF-8''{encoded_json_filename}",
                },
            )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "ID",
                "Kuupäev",
                "Kellaaeg",
                "Kõneleja",
                "Roll",
                "Fraktsioon",
                "Leitud märksõnu",
                "Päevakorrapunkt",
                "Allikas",
                "Video",
                "Tekst",
            ]
        )
        for r in results:
            writer.writerow(
                [
                    r.get("id", ""),
                    r.get("date", ""),
                    r.get("time", ""),
                    r.get("speaker", ""),
                    r.get("speaker_role", "") or "",
                    r.get("speaker_faction", "") or "",
                    r.get("count", 0),
                    r.get("agenda_title", "") or "",
                    r.get("source_url", ""),
                    r.get("video_url", "") or "",
                    r.get("text", ""),
                ]
            )

        csv_bytes = output.getvalue().encode("utf-8-sig")
        return Response(
            content=csv_bytes,
            media_type="text/csv; charset=utf-8",
            headers={
                **common_headers,
                "Content-Disposition": f"attachment; filename=\"riigikogu_{ascii_fallback}.csv\"; filename*=UTF-8''{encoded_csv_filename}",
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või otsingutabelid ei ole initsialiseeritud.",
        ) from e
    except SQLAlchemyError as e:
        logger.error("Export query failed for %r: %s", q, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Eksport ebaõnnestus.",
        ) from e
