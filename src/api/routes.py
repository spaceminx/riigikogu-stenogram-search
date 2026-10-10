import csv
import io
import json
import logging
import os
from datetime import date, datetime
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import func, or_, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from config import MEMBERSHIP_DATES, OUTPUT_DIR_PROCESSED
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
from src.load.models import Attendance, Person, Speech, SpeechAlias

logger = logging.getLogger(__name__)

router = APIRouter()


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
    exclude_chair: bool = Query(False, description="Jäta istungi juhataja välja"),
    speech_category: str | None = Query(
        None,
        description="Filtreeri sõnavõtu liigi järgi (speeches, questions, procedural)",
        pattern=r"^(speeches|questions|procedural)$",
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
                exclude_chair=exclude_chair,
                speech_category=speech_category,
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
    exclude_chair: bool = Query(False, description="Jäta istungi juhataja välja"),
    speech_category: str | None = Query(
        None,
        description="Filtreeri sõnavõtu liigi järgi (speeches, questions, procedural)",
        pattern=r"^(speeches|questions|procedural)$",
    ),
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
                exclude_chair=exclude_chair,
                speech_category=speech_category,
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
    exclude_chair: bool = Query(False, description="Jäta istungi juhataja välja"),
    speech_category: str | None = Query(
        None,
        description="Filtreeri sõnavõtu liigi järgi (speeches, questions, procedural)",
        pattern=r"^(speeches|questions|procedural)$",
    ),
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


@router.get("/persons/{person_uuid}")
def get_person(person_uuid: str):
    """Get MP profile, parliamentary faction history and total speech count."""
    session = SessionLocal()
    try:
        person = session.query(Person).filter(Person.uuid == person_uuid).first()
        if not person:
            raise HTTPException(status_code=404, detail="Isikut ei leitud.")

        same_name_count = session.query(Person).filter(Person.full_name == person.full_name).count()
        if same_name_count > 1:
            speeches_count = (
                session.query(Speech).filter(Speech.speaker_uuid == person_uuid).count()
            )
        else:
            speeches_count = (
                session.query(Speech)
                .filter(or_(Speech.speaker_uuid == person_uuid, Speech.speaker == person.full_name))
                .count()
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


@router.get("/speeches/{speech_identifier}")
def get_speech_by_id(speech_identifier: str):
    """Get single speech by internal database ID, Riigikogu permalink external_id, historical alias, or stable speech_key."""
    session = SessionLocal()
    try:
        speech = None
        if speech_identifier.isdigit():
            num_id = int(speech_identifier)
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
    except SQLAlchemyError as e:
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
                "duration": "Kõneaeg on arvutatud Riigikogu stenogrammi algus- ja lõpuajast ning on saadaval alates 2021. aastast; 2019–2020 kõnedel puudub algallikas algusaeg.",
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
