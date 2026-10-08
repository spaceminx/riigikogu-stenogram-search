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
    """Fetch official speech statistics from Riigikogu API with rate limit backoff."""
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


def get_local_speech_counts(
    session,
    uuid: str,
    full_name: str,
    start_date: str,
    end_date: str,
) -> dict:
    """Query local database for speeches by MP UUID or full name within date range."""
    query = session.query(Speech.speech_type, text("count(*)")).filter(
        Speech.date >= start_date,
        Speech.date <= end_date,
    )

    if uuid:
        query = query.filter((Speech.speaker_uuid == uuid) | (Speech.speaker == full_name))
    else:
        query = query.filter(Speech.speaker == full_name)

    rows = query.group_by(Speech.speech_type).all()

    speeches = 0
    questions = 0
    procedural = 0
    unknown = 0
    total = 0

    for st_type, count in rows:
        total += count
        if st_type == "SPEECH":
            speeches += count
        elif st_type == "QUESTION":
            questions += count
        elif st_type == "PROCEDURAL":
            procedural += count
        else:
            unknown += count

    return {
        "speeches": speeches,
        "questions": questions,
        "procedural": procedural,
        "unknown": unknown,
        "total": total,
    }


def verify_statistics(
    start_date: str,
    end_date: str,
    sample_size: int = 5,
    target_uuid: str | None = None,
    target_name: str | None = None,
    check_all: bool = False,
    delay: float = 1.5,
    tolerance_ratio: float = 0.35,
    output_path: str | None = None,
) -> bool:
    """Compare Riigikogu official statistics with local SQLite speeches database."""
    print("=" * 70)
    print("RIIGIKOGU SPEECH STATISTICS VERIFICATION")
    print(f"Period: {start_date} to {end_date}")
    print("=" * 70)

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

    print(f"Testing {len(candidates)} MPs (delay between queries: {delay}s)...\n")

    session = SessionLocal()
    results = []
    has_critical_error = False

    header = f"{'Saadiku nimi':<28} | {'Ametlik':<8} | {'Kohalik':<8} | {'Vahe':<6} | {'Olek':<14}"
    print(header)
    print("-" * len(header))

    try:
        for mp in candidates:
            mp_uuid = mp.get("uuid")
            full_name = mp.get("full_name", "Tundmatu")

            if not mp_uuid:
                continue

            official_data = fetch_official_stats(
                uuid=mp_uuid, start_date=start_date, end_date=end_date
            )
            time.sleep(delay)

            if official_data is None:
                print(f"{full_name:<28} | {'API viga':<8} | {'-':<8} | {'-':<6} | {'VIGA':<14}")
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
            )
            loc_total = local_counts["total"]
            diff = loc_total - off_total

            # Status evaluation
            if off_total > 0 and loc_total == 0:
                status = "PUUDU (0)"
                has_critical_error = True
            elif off_total == 0 and loc_total == 0:
                status = "OK (0)"
            elif off_total == 0 and loc_total > 0:
                status = "AINULT KOHALIK"
            else:
                ratio = abs(diff) / max(off_total, 1)
                if ratio <= tolerance_ratio:
                    status = "OK"
                else:
                    status = "ERINEVUS"

            print(f"{full_name:<28} | {off_total:<8} | {loc_total:<8} | {diff:+6} | {status:<14}")

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
                    "diff": diff,
                    "status": status,
                }
            )

    finally:
        session.close()

    print("-" * len(header))
    passed_count = sum(1 for r in results if r["status"] in ("OK", "OK (0)"))
    alert_count = sum(1 for r in results if "PUUDU" in r["status"])
    print(
        f"\nKokkuvõte: {len(results)} testitud | {passed_count} vastavuses | {alert_count} puudumisteatist"
    )

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        report = {
            "period": {"start_date": start_date, "end_date": end_date},
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tested": len(results),
                "passed": passed_count,
                "alerts": alert_count,
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
        default=0.35,
        help="Lubatud hälbe suhe (vaikimisi: 0.35)",
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
    )
    sys.exit(0 if success else 1)
