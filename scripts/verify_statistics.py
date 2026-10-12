import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta

import requests
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import OUTPUT_DIR_PROCESSED
from src.load.database import SessionLocal
from src.load.models import Person, Speech


def fetch_official_stats(
    uuid: str,
    start_date: str,
    end_date: str,
    max_retries: int = 3,
) -> dict | None:
    """Fetch official speech statistics from Riigikogu API (/api/statistics) with rate limit backoff."""
    url = f"https://api.riigikogu.ee/api/statistics/speeches/member/{uuid}"
    params = {"startDate": start_date, "endDate": end_date}

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=(5, 20))
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait_time = 3 * attempt
                print(f"Notice: Rate limited (429) for {uuid}, sleeping {wait_time}s...")
                time.sleep(wait_time)
            elif resp.status_code == 404:
                return None
            else:
                print(f"Warning: HTTP {resp.status_code} fetching stats for {uuid}")
        except requests.exceptions.RequestException as e:
            print(f"Warning: Network error fetching stats for {uuid} ({e})")

        if attempt < max_retries:
            time.sleep(2 * attempt)

    return None


def fetch_steno_stats(
    uuids: list[str],
    start_date: str,
    end_date: str,
    max_retries: int = 3,
) -> dict[str, dict]:
    """Fetch official speech statistics in batch from Riigikogu API (/api/steno/speeches)."""
    if not uuids:
        return {}

    url = "https://api.riigikogu.ee/api/steno/speeches"
    params = {
        "uuids": ",".join(uuids),
        "startDate": start_date,
        "endDate": end_date,
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=(5, 30))
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return {
                        item["uuid"]: item
                        for item in data
                        if isinstance(item, dict) and "uuid" in item
                    }
                return {}
            elif resp.status_code == 429:
                wait_time = 3 * attempt
                print(f"Notice: Rate limited (429) on steno API, sleeping {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"Warning: HTTP {resp.status_code} fetching steno stats")
        except requests.exceptions.RequestException as e:
            print(f"Warning: Network error fetching steno stats ({e})")

        if attempt < max_retries:
            time.sleep(2 * attempt)

    return {}


CHAIR_ROLES = ("Esimees", "Aseesimees", "Riigikogu esimees")


def get_local_speech_counts(
    session,
    uuid: str,
    full_name: str,
    start_date: str,
    end_date: str,
    source: str = "steno",
) -> dict:
    """Query local database for speeches by MP UUID or full name within date range.

    Category mapping semantics:
    1. source == "steno" (Riigikogu /api/steno/speeches endpoint):
       - Counts MP speeches (speaker_role IS NULL) and chair speeches (speaker_role IN CHAIR_ROLES).
       - Ministers (speaker_role LIKE '%minister%') and external guest roles are excluded from
         category counts because the Riigikogu steno endpoint attributes speeches to parliamentary
         members and plenary activities, not ministerial duties.
       - SMALL_SPEECH -> questions
       - PROCEDURAL -> procedural
       - SPEECH + SPEECH_CONTINUE -> speeches (plus DIRECTOR when speaker_role IN CHAIR_ROLES,
         where the stenogram system records chair interventions as DIRECTOR)
       - DIRECTOR for non-chairs is tracked in the director counter.
    2. source == "statistics" (Riigikogu /api/statistics/speeches/member endpoint):
       - Counts only speeches where speaker_role IS NULL towards categories.
       - SPEECH + SPEECH_CONTINUE -> speeches
       - SMALL_SPEECH -> questions
       - PROCEDURAL -> procedural
       - DIRECTOR -> director
       - Chair and minister speeches tracked in info counters.
    """
    query = session.query(Speech.speech_type, Speech.speaker_role, text("count(*)")).filter(
        Speech.date >= start_date,
        Speech.date <= end_date,
    )

    if uuid:
        query = query.filter(
            (Speech.speaker_uuid == uuid)
            | (Speech.speaker_uuid.is_(None) & (Speech.speaker == full_name))
        )
    else:
        query = query.filter(Speech.speaker == full_name)

    rows = query.group_by(Speech.speech_type, Speech.speaker_role).all()

    speeches = 0
    questions = 0
    procedural = 0
    director = 0
    unknown = 0
    chair = 0
    minister = 0
    other_roles = 0

    for st_type, role, count in rows:
        is_chair = role in CHAIR_ROLES
        is_minister = bool(role and ("minister" in role.lower()))
        is_other = bool(role and not is_chair and not is_minister)

        if is_chair:
            chair += count
        elif is_minister:
            minister += count
        elif is_other:
            other_roles += count

        if source == "steno":
            if role is not None and not is_chair:
                continue

            if st_type in ("SPEECH", "SPEECH_CONTINUE"):
                speeches += count
            elif st_type == "DIRECTOR":
                if is_chair:
                    speeches += count
                else:
                    director += count
            elif st_type == "SMALL_SPEECH":
                questions += count
            elif st_type == "PROCEDURAL":
                procedural += count
            else:
                unknown += count
        else:
            if role is not None:
                continue

            if st_type in ("SPEECH", "SPEECH_CONTINUE"):
                speeches += count
            elif st_type == "SMALL_SPEECH":
                questions += count
            elif st_type == "PROCEDURAL":
                procedural += count
            elif st_type == "DIRECTOR":
                director += count
            else:
                unknown += count

    total = speeches + questions + procedural

    return {
        "speeches": speeches,
        "questions": questions,
        "procedural": procedural,
        "director": director,
        "unknown": unknown,
        "total": total,
        "chair": chair,
        "minister": minister,
        "other_roles": other_roles,
    }


def verify_statistics(
    start_date: str,
    end_date: str,
    sample_size: int = 5,
    target_uuid: str | None = None,
    target_name: str | None = None,
    check_all: bool = False,
    delay: float = 1.5,
    tolerance_ratio: float = 0.02,
    output_path: str | None = None,
    source: str = "steno",
) -> bool:
    """Compare Riigikogu official statistics with local SQLite speeches database."""
    print("=" * 115)
    print(f"RIIGIKOGU SPEECH STATISTICS VERIFICATION (source: {source})")
    print(f"Period: {start_date} to {end_date}")
    print("=" * 115)

    # Load person profiles
    persons_file = os.path.join(OUTPUT_DIR_PROCESSED, "persons.json")
    persons = []
    if os.path.exists(persons_file):
        with open(persons_file, encoding="utf-8") as f:
            persons = json.load(f)

    if not persons:
        # Fallback to querying Person table
        session = SessionLocal()
        db_persons = session.query(Person).all()
        persons = [
            {"uuid": p.uuid, "full_name": p.full_name, "active": bool(p.active)} for p in db_persons
        ]
        session.close()

    if not persons:
        print("Error: No person records found in persons.json or database.")
        return False

    candidates = persons
    if target_uuid:
        candidates = [p for p in persons if p.get("uuid") == target_uuid]
    elif target_name:
        candidates = [p for p in persons if target_name.lower() in p.get("full_name", "").lower()]
    elif not check_all:
        # Prefer active MPs
        active_mps = [p for p in persons if p.get("active")]
        pool = active_mps if len(active_mps) >= sample_size else persons
        candidates = random.sample(pool, min(sample_size, len(pool)))

    print(f"Testing {len(candidates)} MPs (source: {source}, delay: {delay}s)...\n")

    steno_cache = {}
    if source == "steno":
        chunk_size = 25
        valid_candidates = [c for c in candidates if c.get("uuid")]
        chunks = [
            valid_candidates[i : i + chunk_size]
            for i in range(0, len(valid_candidates), chunk_size)
        ]
        for i, chunk in enumerate(chunks):
            chunk_uuids = [c["uuid"] for c in chunk]
            batch_result = fetch_steno_stats(chunk_uuids, start_date=start_date, end_date=end_date)
            steno_cache.update(batch_result)
            if i < len(chunks) - 1 and delay > 0:
                time.sleep(delay)

    session = SessionLocal()
    results = []
    has_critical_error = False

    if source == "steno":
        header = f"{'Saadiku nimi':<26} | {'Questions (Off/Loc/Diff)':<24} | {'Procedural (Off/Loc/Diff)':<25} | {'Speeches (Off/Loc/Diff)':<24} | {'Olek':<22}"
    else:
        header = f"{'Saadiku nimi':<26} | {'Questions (Off/Loc/Diff)':<24} | {'Procedural (Off/Loc)':<20} | {'Speeches (Off/Loc, Suh)':<23} | {'Olek':<16}"

    print(header)
    print("-" * len(header))

    try:
        for mp in candidates:
            mp_uuid = mp.get("uuid")
            full_name = mp.get("full_name", "Tundmatu")

            if not mp_uuid:
                continue

            if source == "steno":
                official_data = steno_cache.get(mp_uuid)
            else:
                official_data = fetch_official_stats(
                    uuid=mp_uuid, start_date=start_date, end_date=end_date
                )
                if delay > 0:
                    time.sleep(delay)

            if official_data is None:
                print(f"{full_name:<26} | {'API viga':<24} | {'-':<20} | {'-':<23} | {'VIGA':<16}")
                continue

            off_total = official_data.get("total", 0)
            off_speeches = official_data.get("speeches", 0)
            off_questions = official_data.get("questions", 0)
            off_procedural = official_data.get("procedural", 0)

            local_counts = get_local_speech_counts(
                session=session,
                uuid=mp_uuid,
                full_name=full_name,
                start_date=start_date,
                end_date=end_date,
                source=source,
            )
            loc_speeches = local_counts["speeches"]
            loc_questions = local_counts["questions"]
            loc_procedural = local_counts["procedural"]
            loc_total = local_counts["total"]

            q_diff = loc_questions - off_questions
            p_diff = loc_procedural - off_procedural
            s_diff = loc_speeches - off_speeches
            tot_diff = loc_total - off_total

            if source == "steno":
                tol_q = max(1.0, tolerance_ratio * off_questions)
                tol_p = max(1.0, tolerance_ratio * off_procedural)
                tol_s = max(1.0, tolerance_ratio * off_speeches)

                q_ok = abs(q_diff) <= tol_q
                p_ok = abs(p_diff) <= tol_p
                s_ok = abs(s_diff) <= tol_s
                all_ok = q_ok and p_ok and s_ok

                if all_ok:
                    status = "OK (0)" if off_total == 0 and loc_total == 0 else "OK"
                else:
                    diff_parts = []
                    if not s_ok:
                        diff_parts.append(f"S:{s_diff:+d}")
                    if not q_ok:
                        diff_parts.append(f"Q:{q_diff:+d}")
                    if not p_ok:
                        diff_parts.append(f"P:{p_diff:+d}")
                    status = f"ERINEVUS ({', '.join(diff_parts)})"
                    has_critical_error = True

                q_str = f"{off_questions:>3} / {loc_questions:>3} ({q_diff:+3d})"
                p_str = f"{off_procedural:>3} / {loc_procedural:>3} ({p_diff:+3d})"
                s_str = f"{off_speeches:>3} / {loc_speeches:>3} ({s_diff:+3d})"
                print(f"{full_name:<26} | {q_str:<24} | {p_str:<25} | {s_str:<24} | {status:<22}")
            else:
                tol = max(1.0, tolerance_ratio * off_questions)
                q_ok = (
                    (loc_questions - tol) <= off_questions <= (loc_questions + loc_procedural + tol)
                )

                ratio_str = (
                    f"{loc_speeches / off_speeches:.1f}x"
                    if off_speeches > 0
                    else f"{loc_speeches}/0"
                )

                if q_ok:
                    status = "OK (0)" if off_total == 0 and loc_total == 0 else "OK"
                else:
                    status = f"ERINEVUS (Q:{q_diff:+d})"
                    has_critical_error = True

                q_str = f"{off_questions:>3} / {loc_questions:>3} ({q_diff:+3d})"
                p_str = f"{off_procedural:>2} / {loc_procedural:>2} ({p_diff:+2d})"
                s_str = f"{off_speeches:>3} / {loc_speeches:>3} ({ratio_str:>5})"
                print(f"{full_name:<26} | {q_str:<24} | {p_str:<20} | {s_str:<23} | {status:<16}")

            results.append(
                {
                    "uuid": mp_uuid,
                    "full_name": full_name,
                    "official": {
                        "total": off_total,
                        "speeches": off_speeches,
                        "questions": off_questions,
                        "procedural": off_procedural,
                    },
                    "local": local_counts,
                    "diff": {
                        "questions": q_diff,
                        "procedural": p_diff,
                        "speeches": s_diff,
                        "total": tot_diff,
                    },
                    "speeches_ratio": (
                        round(loc_speeches / off_speeches, 2) if off_speeches > 0 else None
                    ),
                    "questions_ok": q_ok,
                    "status": status,
                }
            )

    finally:
        session.close()

    print("-" * len(header))
    passed_count = sum(1 for r in results if r["status"] in ("OK", "OK (0)"))
    discrepancy_count = sum(1 for r in results if "ERINEVUS" in r["status"])
    print(
        f"\nKokkuvõte: {len(results)} testitud | {passed_count} vastavuses | {discrepancy_count} lahknevust"
    )

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        report = {
            "source": source,
            "period": {"start_date": start_date, "end_date": end_date},
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tested": len(results),
                "passed": passed_count,
                "alerts": discrepancy_count,
                "discrepancies": discrepancy_count,
                "category_sums": {
                    "official": {
                        "speeches": sum(r["official"]["speeches"] for r in results),
                        "questions": sum(r["official"]["questions"] for r in results),
                        "procedural": sum(r["official"]["procedural"] for r in results),
                        "total": sum(r["official"]["total"] for r in results),
                    },
                    "local": {
                        "speeches": sum(r["local"]["speeches"] for r in results),
                        "questions": sum(r["local"]["questions"] for r in results),
                        "procedural": sum(r["local"]["procedural"] for r in results),
                        "total": sum(r["local"]["total"] for r in results),
                    },
                },
            },
            "results": results,
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"Aruanne salvestatud: {output_path}")

    return not has_critical_error


def parse_args():
    parser = argparse.ArgumentParser(
        description="Võrdle Riigikogu ametlikku sõnavõttude statistikat kohaliku andmebaasiga."
    )
    today = datetime.today()
    default_start = (today - timedelta(days=60)).strftime("%Y-%m-%d")
    default_end = today.strftime("%Y-%m-%d")

    parser.add_argument(
        "--source",
        choices=["steno", "statistics"],
        default="steno",
        help="Statistika allikas: steno (/api/steno/speeches) või statistics (/api/statistics) (vaikimisi: steno)",
    )
    parser.add_argument(
        "--start-date",
        default=default_start,
        help=f"Perioodi algus YYYY-MM-DD (vaikimisi: {default_start})",
    )
    parser.add_argument(
        "--end-date",
        default=default_end,
        help=f"Perioodi lõpp YYYY-MM-DD (vaikimisi: {default_end})",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=5,
        help="Testitavate saadikute arv juhuslikus valimis (vaikimisi: 5)",
    )
    parser.add_argument("--uuid", help="Kontrolli konkreetset saadikut UUID järgi")
    parser.add_argument("--name", help="Kontrolli konkreetset saadikut nime järgi")
    parser.add_argument("--all", action="store_true", help="Kontrolli kõiki saadikuid (vajab aega)")
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Päringute vaheline ooteaeg sekundites (vaikimisi: 1.5)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.02,
        help="Lubatud hälbe suhe kategooriate kohta (vaikimisi: 0.02)",
    )
    parser.add_argument(
        "--output",
        help="Valikuline tee JSON aruande salvestamiseks",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    success = verify_statistics(
        start_date=args.start_date,
        end_date=args.end_date,
        sample_size=args.sample_size,
        target_uuid=args.uuid,
        target_name=args.name,
        check_all=args.all,
        delay=args.delay,
        tolerance_ratio=args.tolerance,
        output_path=args.output,
        source=args.source,
    )
    sys.exit(0 if success else 1)
