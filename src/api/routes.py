import csv
import io
import json
import logging
import os
from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import and_, case, func, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from config import MEMBERSHIP_DATES, OUTPUT_DIR_PROCESSED
from src.api.attendance import (
    get_attendance_stats,
    get_faction_attendance_stats,
    get_factions_list,
    get_person_attendance,
)
from src.api.search import (
    SPEECH_TYPE_CATEGORIES,
    get_dashboard_overview,
    get_plenary_session_dates,
    get_session_speeches,
    get_speech_context,
    keyword_activity,
    keyword_top_speakers,
    normalize_source_url,
    search_by_keyword,
)
from src.load.database import SessionLocal
from src.load.models import Attendance, Person, Speech, SpeechAlias

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_SQLITE_INT = 2**63 - 1
MIN_SQLITE_INT = -(2**63)


def validate_membership(membership: str | None) -> None:
    """Validate membership against dynamic configuration. Raise 422 if unknown."""
    if membership and membership != "all" and membership not in MEMBERSHIP_DATES:
        raise HTTPException(status_code=422, detail="Tundmatu koosseis")


@router.get("/")
def root():
    session = SessionLocal()
    try:
        session.execute(text("SELECT id, status FROM speeches LIMIT 1"))
        return {"status": "ok"}
    except Exception as e:
        logger.error("Healthcheck database query failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Andmebaasi ühendus puudub või tabelid on vigased.",
        ) from e
    finally:
        session.close()


@router.get("/memberships")
def list_memberships():
    """Return available parliamentary memberships with names and date ranges."""
    cache_path = os.path.join(OUTPUT_DIR_PROCESSED, "memberships.json")
    today_str = datetime.today().strftime("%Y-%m-%d")
    results = []

    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if isinstance(v, dict):
                    num = v.get("number") or int(k)
                    start = v.get("startDate")
                    end = v.get("endDate")
                    name = v.get("name") or f"{k}. Riigikogu"
                    is_current = bool(start and end and start <= today_str <= end)
                    results.append(
                        {
                            "id": str(k),
                            "number": num,
                            "name": name,
                            "start_date": start,
                            "end_date": end,
                            "is_current": is_current,
                        }
                    )
        except Exception as e:
            logger.warning("Failed to load memberships cache: %s", e)

    if not results:
        for k, (start, end) in sorted(MEMBERSHIP_DATES.items(), key=lambda x: int(x[0])):
            results.append(
                {
                    "id": str(k),
                    "number": int(k),
                    "name": f"{k}. Riigikogu",
                    "start_date": start,
                    "end_date": end,
                    "is_current": start <= today_str <= end,
                }
            )

    results.sort(key=lambda x: x["number"], reverse=True)
    return results


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
    validate_membership(membership)
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
    validate_membership(membership)
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
    validate_membership(membership)
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
    speaker_uuid: str | None = Query(None, description="Filtreeri esineja UUID järgi"),
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
    exclude_chair: bool = Query(False, description="Jäta istungi juhataja välja"),
    speech_category: str | None = Query(
        None,
        description="Filtreeri sõnavõtu liigi järgi (speeches, questions, procedural)",
        pattern=r"^(speeches|questions|procedural)$",
    ),
):
    validate_membership(membership)
    try:
        results, total_count = search_by_keyword(
            query=q,
            limit=limit,
            offset=offset,
            membership=membership,
            faction=faction,
            speaker=speaker,
            speaker_uuid=speaker_uuid,
            start_date=start_date,
            end_date=end_date,
            sort_by=sort_by,
            exclude_chair=exclude_chair,
            speech_category=speech_category,
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
        status_code = 422 if str(e) == "Tundmatu koosseis" else 400
        raise HTTPException(
            status_code=status_code,
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
    speaker_uuid: str | None = Query(None, description="Filtreeri esineja UUID järgi"),
    start_date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    exclude_chair: bool = Query(False, description="Jäta istungi juhataja välja"),
    speech_category: str | None = Query(
        None,
        description="Filtreeri sõnavõtu liigi järgi (speeches, questions, procedural)",
        pattern=r"^(speeches|questions|procedural)$",
    ),
):
    if interval not in ("daily", "weekly", "monthly"):
        raise HTTPException(
            status_code=400,
            detail="Intervall peab olema üks järgmistest: 'daily', 'weekly', 'monthly'.",
        )
    validate_membership(membership)
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
                speaker_uuid=speaker_uuid,
                start_date=start_date,
                end_date=end_date,
                exclude_chair=exclude_chair,
                speech_category=speech_category,
            ),
        }
    except ValueError as e:
        status_code = 422 if str(e) == "Tundmatu koosseis" else 400
        raise HTTPException(
            status_code=status_code,
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
    speaker_uuid: str | None = Query(None, description="Filtreeri esineja UUID järgi"),
    start_date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    exclude_chair: bool = Query(False, description="Jäta istungi juhataja välja"),
    speech_category: str | None = Query(
        None,
        description="Filtreeri sõnavõtu liigi järgi (speeches, questions, procedural)",
        pattern=r"^(speeches|questions|procedural)$",
    ),
):
    validate_membership(membership)
    try:
        return {
            "query": q,
            "speakers": keyword_top_speakers(
                query=q,
                limit=limit,
                membership=membership,
                faction=faction,
                speaker=speaker,
                speaker_uuid=speaker_uuid,
                start_date=start_date,
                end_date=end_date,
                exclude_chair=exclude_chair,
                speech_category=speech_category,
            ),
        }
    except ValueError as e:
        status_code = 422 if str(e) == "Tundmatu koosseis" else 400
        raise HTTPException(
            status_code=status_code,
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
    if speech_id > MAX_SQLITE_INT or speech_id < MIN_SQLITE_INT:
        raise HTTPException(status_code=404, detail="Kõnet ei leitud.")
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
    except (SQLAlchemyError, OverflowError) as e:
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
    speaker_uuid: str | None = Query(None, description="Filtreeri esineja UUID järgi"),
    start_date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    sort_by: str = Query("date_desc", pattern="^(date_desc|date_asc|match_count_desc)$"),
    limit: int = Query(2000, ge=1, le=5000),
    exclude_chair: bool = Query(False, description="Jäta istungi juhataja välja"),
    speech_category: str | None = Query(
        None,
        description="Filtreeri sõnavõtu liigi järgi (speeches, questions, procedural)",
        pattern=r"^(speeches|questions|procedural)$",
    ),
):
    if format not in ("csv", "json"):
        raise HTTPException(status_code=400, detail="Formaat peab olema 'csv' või 'json'.")
    validate_membership(membership)

    try:
        results, total_count = search_by_keyword(
            query=q,
            limit=limit,
            offset=0,
            membership=membership,
            faction=faction,
            speaker=speaker,
            speaker_uuid=speaker_uuid,
            start_date=start_date,
            end_date=end_date,
            sort_by=sort_by,
            include_matched_words=False,
            exclude_chair=exclude_chair,
            speech_category=speech_category,
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
        status_code = 422 if str(e) == "Tundmatu koosseis" else 400
        raise HTTPException(status_code=status_code, detail=str(e)) from e
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


@router.get("/persons")
def list_persons(
    search: str | None = Query(None, description="Otsi nime järgi"),
    active_only: bool = Query(False, description="Ainult praegu aktiivsed saadikud"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Return parliament members with optional name search and active status filter."""
    session = SessionLocal()
    try:
        query = session.query(Person)
        if active_only:
            query = query.filter(Person.active == 1)
        if search:
            search_clean = f"%{search.strip()}%"
            query = query.filter(Person.full_name.ilike(search_clean))

        total_count = query.count()
        results = (
            query.order_by(Person.last_name.asc(), Person.first_name.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {
            "total_count": total_count,
            "count": len(results),
            "offset": offset,
            "limit": limit,
            "results": [
                {
                    "uuid": p.uuid,
                    "first_name": p.first_name,
                    "last_name": p.last_name,
                    "full_name": p.full_name,
                    "gender": p.gender,
                    "date_of_birth": p.date_of_birth,
                    "email": p.email,
                    "photo_url": p.photo_url,
                    "electoral_district": p.electoral_district,
                    "seniority_days": p.seniority_days,
                    "active": bool(p.active),
                }
                for p in results
            ],
        }
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või saadikute tabel ei ole initsialiseeritud.",
        ) from e
    except SQLAlchemyError as e:
        logger.error("Persons query failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Saadikute päring ebaõnnestus.",
        ) from e
    finally:
        session.close()


def classify_role(speaker_role: str | None) -> str:
    """Classify speaker role into standardized classes."""
    if speaker_role is None or speaker_role == "":
        return "mp"
    role_lower = speaker_role.lower()
    if speaker_role in ("Esimees", "Aseesimees"):
        return "chair"
    if "kandidaat" in role_lower:
        return "candidate"
    if "minister" in role_lower:
        return "minister"
    return "other"


def classify_speech_category(speech_type: str | None) -> str:
    """Classify speech type into standardized categories."""
    if speech_type == "DIRECTOR":
        return "director"
    if speech_type in ("SPEECH", "SPEECH_CONTINUE"):
        return "speeches"
    if speech_type == "SMALL_SPEECH":
        return "questions"
    if speech_type == "PROCEDURAL":
        return "procedural"
    return "speeches"


@router.get("/persons/{person_uuid}")
def get_person(person_uuid: str):
    """Get MP profile, parliamentary faction history and speech counts (MP role and all roles)."""
    session = SessionLocal()
    try:
        person = session.query(Person).filter(Person.uuid == person_uuid).first()
        if not person:
            raise HTTPException(status_code=404, detail="Isikut ei leitud.")

        speeches_count = (
            session.query(Speech)
            .filter(
                Speech.speaker_uuid == person_uuid,
                Speech.speaker_role.is_(None),
            )
            .count()
        )
        speeches_count_all = (
            session.query(Speech).filter(Speech.speaker_uuid == person_uuid).count()
        )

        person_factions_path = os.path.join(OUTPUT_DIR_PROCESSED, "person_factions.json")
        factions_cache_path = os.path.join(OUTPUT_DIR_PROCESSED, "factions_map.json")
        faction_history = []
        if os.path.exists(person_factions_path):
            try:
                with open(person_factions_path, encoding="utf-8") as f:
                    pfmap = json.load(f)
                    if person_uuid and person_uuid in pfmap:
                        faction_history = pfmap[person_uuid]
            except Exception:
                pass

        if not faction_history and os.path.exists(factions_cache_path):
            try:
                with open(factions_cache_path, encoding="utf-8") as f:
                    fmap = json.load(f)
                    faction_history = fmap.get(person.full_name, [])
            except Exception:
                pass

        return {
            "uuid": person.uuid,
            "first_name": person.first_name,
            "last_name": person.last_name,
            "full_name": person.full_name,
            "gender": person.gender,
            "date_of_birth": person.date_of_birth,
            "email": person.email,
            "photo_url": person.photo_url,
            "electoral_district": person.electoral_district,
            "seniority_days": person.seniority_days,
            "active": bool(person.active),
            "speeches_count": speeches_count,
            "speeches_count_all": speeches_count_all,
            "factions": faction_history,
        }
    except HTTPException:
        raise
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või saadikute tabel ei ole initsialiseeritud.",
        ) from e
    except SQLAlchemyError as e:
        logger.error("Person query failed for %s: %s", person_uuid, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Isiku päring ebaõnnestus.",
        ) from e
    finally:
        session.close()


@router.get("/persons/{person_uuid}/stats")
def get_person_stats(person_uuid: str):
    """Get aggregated speech statistics for a person by UUID across roles, years, and memberships."""
    session = SessionLocal()
    try:
        person = session.query(Person).filter(Person.uuid == person_uuid).first()
        if not person:
            raise HTTPException(status_code=404, detail="Isikut ei leitud.")

        membership_cases = []
        for mem_id, (start_d, end_d) in sorted(MEMBERSHIP_DATES.items(), key=lambda x: int(x[0])):
            membership_cases.append(
                (and_(Speech.date >= start_d, Speech.date <= end_d), str(mem_id))
            )
        membership_expr = case(*membership_cases, else_="other")

        rows = (
            session.query(
                func.strftime("%Y", Speech.date).label("year"),
                membership_expr.label("membership"),
                Speech.speaker_role,
                Speech.speech_type,
                func.count(Speech.id).label("cnt"),
                func.sum(Speech.duration_seconds).label("duration"),
                func.min(Speech.date).label("min_date"),
                func.max(Speech.date).label("max_date"),
            )
            .filter(Speech.speaker_uuid == person_uuid)
            .group_by(
                func.strftime("%Y", Speech.date),
                membership_expr,
                Speech.speaker_role,
                Speech.speech_type,
            )
            .all()
        )

        role_classes = ("mp", "chair", "minister", "candidate", "other")
        totals = {
            rc: {"speeches": 0, "questions": 0, "procedural": 0, "total": 0} for rc in role_classes
        }
        total_director = 0
        mp_duration_seconds = 0
        first_speech_date = None
        last_speech_date = None

        by_year_map: dict[str, dict] = {}
        by_membership_map: dict[str, dict] = {}

        def _init_breakdown():
            return {
                "mp": {"speeches": 0, "questions": 0, "procedural": 0, "total": 0},
                "chair": 0,
                "minister": 0,
                "candidate": 0,
                "other": 0,
                "other_roles_total": 0,
                "director": 0,
            }

        for yr, mem, sp_role, sp_type, cnt, duration, min_d, max_d in rows:
            cnt_val = int(cnt) if cnt else 0
            if cnt_val == 0:
                continue

            r_class = classify_role(sp_role)
            s_cat = classify_speech_category(sp_type)

            if min_d and (first_speech_date is None or min_d < first_speech_date):
                first_speech_date = min_d
            if max_d and (last_speech_date is None or max_d > last_speech_date):
                last_speech_date = max_d

            yr_str = str(yr) if yr else "unknown"
            mem_str = str(mem) if mem else "other"

            if yr_str not in by_year_map:
                by_year_map[yr_str] = _init_breakdown()
            if mem_str not in by_membership_map:
                by_membership_map[mem_str] = _init_breakdown()

            if s_cat == "director":
                total_director += cnt_val
                by_year_map[yr_str]["director"] += cnt_val
                by_membership_map[mem_str]["director"] += cnt_val
            else:
                totals[r_class][s_cat] += cnt_val
                totals[r_class]["total"] += cnt_val

                if r_class == "mp":
                    by_year_map[yr_str]["mp"][s_cat] += cnt_val
                    by_year_map[yr_str]["mp"]["total"] += cnt_val
                    by_membership_map[mem_str]["mp"][s_cat] += cnt_val
                    by_membership_map[mem_str]["mp"]["total"] += cnt_val
                else:
                    by_year_map[yr_str][r_class] += cnt_val
                    by_year_map[yr_str]["other_roles_total"] += cnt_val
                    by_membership_map[mem_str][r_class] += cnt_val
                    by_membership_map[mem_str]["other_roles_total"] += cnt_val

            if r_class == "mp" and s_cat != "director" and duration:
                mp_duration_seconds += int(duration)

        by_year = [
            {"year": y, **stats_obj}
            for y, stats_obj in sorted(by_year_map.items(), key=lambda x: x[0], reverse=True)
        ]

        valid_mems = sorted(MEMBERSHIP_DATES.keys(), key=lambda x: int(x), reverse=True)
        by_membership = [
            {"membership": m, **by_membership_map[m]} for m in valid_mems if m in by_membership_map
        ]

        return {
            "uuid": person_uuid,
            "full_name": person.full_name,
            "totals": totals,
            "director": total_director,
            "by_year": by_year,
            "by_membership": by_membership,
            "duration": {
                "mp_seconds": mp_duration_seconds,
                "available_from": "2020-09-14",
            },
            "first_speech_date": first_speech_date,
            "last_speech_date": last_speech_date,
        }
    except HTTPException:
        raise
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või tabelid ei ole initsialiseeritud.",
        ) from e
    except SQLAlchemyError as e:
        logger.error("Person stats query failed for %s: %s", person_uuid, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Saadiku statistika päring ebaõnnestus.",
        ) from e
    finally:
        session.close()


@router.get("/persons/{person_uuid}/speeches")
def get_person_speeches(
    person_uuid: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    role_class: str = Query("mp", pattern=r"^(mp|chair|minister|candidate|other|all)$"),
    speech_category: str | None = Query(
        None,
        description="Filtreeri sõnavõtu liigi järgi (speeches, questions, procedural, all)",
        pattern=r"^(speeches|questions|procedural|all)$",
    ),
    start_date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
):
    """Return paginated speeches for a specific person by UUID with role and category filters."""
    session = SessionLocal()
    try:
        person = session.query(Person).filter(Person.uuid == person_uuid).first()
        if not person:
            raise HTTPException(status_code=404, detail="Isikut ei leitud.")

        filters = [Speech.speaker_uuid == person_uuid]

        if role_class == "mp":
            filters.append(Speech.speaker_role.is_(None))
        elif role_class == "chair":
            filters.append(Speech.speaker_role.in_(("Esimees", "Aseesimees")))
        elif role_class == "candidate":
            filters.append(Speech.speaker_role.ilike("%kandidaat%"))
        elif role_class == "minister":
            filters.append(
                Speech.speaker_role.ilike("%minister%") & ~Speech.speaker_role.ilike("%kandidaat%")
            )
        elif role_class == "other":
            filters.append(
                Speech.speaker_role.isnot(None)
                & Speech.speaker_role.notin_(("Esimees", "Aseesimees"))
                & ~Speech.speaker_role.ilike("%minister%")
                & ~Speech.speaker_role.ilike("%kandidaat%")
            )

        if speech_category and speech_category != "all":
            if speech_category in SPEECH_TYPE_CATEGORIES:
                filters.append(Speech.speech_type.in_(SPEECH_TYPE_CATEGORIES[speech_category]))

        if start_date:
            filters.append(Speech.date >= start_date)
        if end_date:
            filters.append(Speech.date <= end_date)

        query = session.query(Speech).filter(*filters)
        total_count = query.count()

        speeches = (
            query.order_by(Speech.date.desc(), Speech.time.desc(), Speech.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        results = [
            {
                "id": s.id,
                "speech_key": s.speech_key,
                "speaker": s.speaker,
                "speaker_role": s.speaker_role,
                "speaker_faction": s.speaker_faction,
                "speaker_uuid": s.speaker_uuid,
                "speech_type": s.speech_type,
                "external_id": s.external_id,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "duration_seconds": s.duration_seconds,
                "text": s.text[:400] if s.text else "",
                "date": s.date,
                "time": s.time,
                "source_file": s.source_file,
                "source_url": normalize_source_url(s.source_url),
                "agenda_title": s.agenda_title,
                "video_url": s.video_url,
            }
            for s in speeches
        ]

        return {
            "total_count": total_count,
            "count": len(results),
            "offset": offset,
            "limit": limit,
            "results": results,
        }
    except HTTPException:
        raise
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või kõnede tabel ei ole initsialiseeritud.",
        ) from e
    except SQLAlchemyError as e:
        logger.error("Person speeches query failed for %s: %s", person_uuid, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Kõnede päring ebaõnnestus.",
        ) from e
    finally:
        session.close()


@router.get("/persons/{person_uuid}/attendance")
def person_attendance(person_uuid: str):
    """Get MP attendance statistics by UUID, both overall and broken down by parliamentary membership."""
    try:
        return get_person_attendance(person_uuid)
    except ValueError as e:
        if str(e) == "Isikut ei leitud.":
            raise HTTPException(status_code=404, detail=str(e)) from e
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või kohalolekutabel ei ole initsialiseeritud.",
        ) from e
    except SQLAlchemyError as e:
        logger.error("Person attendance query failed for %s: %s", person_uuid, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Kohaloleku päring ebaõnnestus.",
        ) from e


@router.get("/speeches/by-external-id/{external_id}")
def get_speech_by_external_id(external_id: str):
    """Get single speech specifically by Riigikogu permalink external_id."""
    session = SessionLocal()
    try:
        if not external_id.isdigit():
            raise HTTPException(status_code=404, detail="Kõnet ei leitud.")
        num_id = int(external_id)
        if num_id > MAX_SQLITE_INT or num_id < MIN_SQLITE_INT:
            raise HTTPException(status_code=404, detail="Kõnet ei leitud.")

        speech = session.query(Speech).filter(Speech.external_id == num_id).first()
        if not speech:
            speech = (
                session.query(Speech)
                .join(SpeechAlias, Speech.id == SpeechAlias.speech_id)
                .filter(SpeechAlias.alias_external_id == num_id)
                .first()
            )

        if not speech:
            raise HTTPException(status_code=404, detail="Kõnet ei leitud.")

        return {
            "id": speech.id,
            "external_id": speech.external_id,
            "speech_key": speech.speech_key,
            "speaker_uuid": speech.speaker_uuid,
            "ems_id": speech.ems_id,
            "speaker": speech.speaker,
            "speaker_role": speech.speaker_role,
            "speaker_faction": speech.speaker_faction,
            "speech_type": speech.speech_type,
            "start_time": speech.start_time,
            "end_time": speech.end_time,
            "duration_seconds": speech.duration_seconds,
            "date": speech.date,
            "time": speech.time,
            "source_file": speech.source_file,
            "source_url": speech.source_url,
            "agenda_title": speech.agenda_title,
            "video_url": speech.video_url,
            "status": speech.status,
            "text": speech.text,
        }
    except HTTPException:
        raise
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või kõnede tabel ei ole initsialiseeritud.",
        ) from e
    except (SQLAlchemyError, OverflowError) as e:
        logger.error("Speech query by external_id failed for %s: %s", external_id, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Kõne päring ebaõnnestus.",
        ) from e
    finally:
        session.close()


@router.get("/speeches/{speech_identifier}")
def get_speech_by_id(speech_identifier: str):
    """Get single speech by internal database ID, Riigikogu permalink external_id, historical alias, or stable speech_key."""
    session = SessionLocal()
    try:
        speech = None
        if speech_identifier.isdigit():
            num_id = int(speech_identifier)
            if num_id > MAX_SQLITE_INT or num_id < MIN_SQLITE_INT:
                pass
            else:
                # Prioritize official Riigikogu permalink external_id and editorial aliases
                speech = session.query(Speech).filter(Speech.external_id == num_id).first()
                if not speech:
                    speech = (
                        session.query(Speech)
                        .join(SpeechAlias, Speech.id == SpeechAlias.speech_id)
                        .filter(SpeechAlias.alias_external_id == num_id)
                        .first()
                    )
                if not speech:
                    speech = session.query(Speech).filter(Speech.id == num_id).first()

        if not speech:
            speech = session.query(Speech).filter(Speech.speech_key == speech_identifier).first()
            if not speech:
                speech = (
                    session.query(Speech)
                    .join(SpeechAlias, Speech.id == SpeechAlias.speech_id)
                    .filter(SpeechAlias.alias_speech_key == speech_identifier)
                    .first()
                )

        if not speech:
            raise HTTPException(status_code=404, detail="Kõnet ei leitud.")

        return {
            "id": speech.id,
            "external_id": speech.external_id,
            "speech_key": speech.speech_key,
            "speaker_uuid": speech.speaker_uuid,
            "ems_id": speech.ems_id,
            "speaker": speech.speaker,
            "speaker_role": speech.speaker_role,
            "speaker_faction": speech.speaker_faction,
            "speech_type": speech.speech_type,
            "start_time": speech.start_time,
            "end_time": speech.end_time,
            "duration_seconds": speech.duration_seconds,
            "date": speech.date,
            "time": speech.time,
            "source_file": speech.source_file,
            "source_url": speech.source_url,
            "agenda_title": speech.agenda_title,
            "video_url": speech.video_url,
            "status": speech.status,
            "text": speech.text,
        }
    except HTTPException:
        raise
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või kõnede tabel ei ole initsialiseeritud.",
        ) from e
    except (SQLAlchemyError, OverflowError) as e:
        logger.error("Speech query failed for %s: %s", speech_identifier, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Kõne päring ebaõnnestus.",
        ) from e
    finally:
        session.close()


@router.get("/system/status")
def system_status():
    """Return archive sync status, latest session date, and methodology metadata."""
    session = SessionLocal()
    try:
        latest_date = session.query(func.max(Speech.date)).scalar()
        total_sessions = session.query(func.count(func.distinct(Speech.source_file))).scalar() or 0
        total_speeches = session.query(func.count(Speech.id)).scalar() or 0
        total_persons = session.query(func.count(Person.uuid)).scalar() or 0
        total_attendance = session.query(func.count(Attendance.id)).scalar() or 0

        latest_session = (
            session.query(Speech.source_file).order_by(Speech.date.desc(), Speech.id.desc()).first()
        )
        latest_session_file = latest_session[0] if latest_session else None

        days_since_latest = None
        warning = None
        if latest_date:
            try:
                latest_dt = datetime.strptime(latest_date, "%Y-%m-%d").date()
                days_since_latest = (date.today() - latest_dt).days
                if days_since_latest > 4:
                    warning = (
                        f"Viimane istung toimus {days_since_latest} päeva tagasi ({latest_date}). "
                        "Istungijärgu ajal võib see viidata andmeallika viivitusele."
                    )
            except ValueError:
                pass

        return {
            "status": "ok",
            "data_as_of": latest_date,
            "days_since_latest_session": days_since_latest,
            "latest_session": latest_session_file,
            "total_sessions": total_sessions,
            "total_speeches": total_speeches,
            "total_persons": total_persons,
            "warning": warning,
            "totals": {
                "sessions": total_sessions,
                "speeches": total_speeches,
                "persons": total_persons,
                "attendance_records": total_attendance,
            },
            "methodology": {
                "attendance": "Kohalolek mõõdab kohalolekukontrolle (hääletussüsteemis registreeritud kohalolekuid), mitte füüsilist saalis viibimist väljaspool kontrollihetki.",
                "speeches": "Kõned, repliigid ja küsimused pärinevad Riigikogu stenogrammidest. Istungi juhataja roll (Esimees, Aseesimees) on stenogrammis märgitud eraldi ametinimetusena.",
                "speech_types": "Kategooriad põhinevad Riigikogu stenogrammi sõnavõtu liigist; juhatajasõnavõtud tuvastatakse ametinimetuse (Esimees, Aseesimees) järgi, mitte liigi järgi, sest Riigikogu liigitus on selles osas ebajärjekindel.",
                "duration": "Kõneaeg on arvutatud Riigikogu stenogrammi algus- ja lõpuajast ning on saadaval alates 14.09.2020 (2020. aasta sügisistungjärk); varasematel kõnedel puudub algallikas algusaeg.",
                "transcripts": "Toimetamata esialgsed stenogrammid asendatakse andmetorus automaatselt Riigikogu kantselei kinnitatud lõplike stenogrammidega järgmise öise andmetoru käivituse ja andmebaasi sünkroonimisega.",
                "impartiality": "Riigivaade on erapooletu ja automatiseeritud analüütiline tööriist, mis ei muuda ega hinda algandmete sisu.",
                "sources": [
                    "Riigikogu avatud API (api.riigikogu.ee)",
                    "Riigikogu stenogrammide portaal (stenogrammid.riigikogu.ee)",
                ],
            },
        }
    except OperationalError as e:
        raise HTTPException(
            status_code=503,
            detail="Andmebaas või süsteemitabelid ei ole initsialiseeritud.",
        ) from e
    except SQLAlchemyError as e:
        logger.error("System status query failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Süsteemi oleku päring ebaõnnestus.",
        ) from e
    finally:
        session.close()
