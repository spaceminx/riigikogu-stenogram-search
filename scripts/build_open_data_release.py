#!/usr/bin/env python3
"""Build an open data release from a SQLite database.

Exports dataset as gzip-compressed JSONL files, JSON reference files,
README.md, DATA_DICTIONARY.md, manifest.json, and SHA256SUMS.
Deterministic output: fixed gzip mtime=0, sorted rows, stable key order.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_git_commit(commit_override: str | None = None) -> str:
    """Return git commit from argument, env GIT_COMMIT, git rev-parse, or 'unknown'."""
    if commit_override and commit_override.strip():
        return commit_override.strip()
    env_commit = os.environ.get("GIT_COMMIT", "").strip()
    if env_commit:
        return env_commit
    try:
        out = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=PROJECT_ROOT,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        return out or "unknown"
    except Exception:
        return "unknown"


def write_deterministic_jsonl_gz(
    file_path: Path, rows: Iterable[dict[str, Any]]
) -> tuple[int, int, str]:
    """Write rows as gzip-compressed JSONL with mtime=0 for reproducibility.

    Streams rows one by one. Returns (row_count, file_size_bytes, sha256_hex).
    """
    hasher = hashlib.sha256()
    count = 0
    with open(file_path, "wb") as f_out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=f_out, mtime=0) as gz:
            for row in rows:
                line = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                gz.write(line.encode("utf-8"))
                count += 1

    # Compute hash and size
    with open(file_path, "rb") as f_in:
        while True:
            chunk = f_in.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    size = file_path.stat().st_size

    return count, size, hasher.hexdigest()


def write_deterministic_json(file_path: Path, data: Any, indent: int = 2) -> tuple[int, str]:
    """Write formatted JSON file. Returns (file_size_bytes, sha256_hex)."""
    content = json.dumps(data, ensure_ascii=False, indent=indent) + "\n"
    encoded = content.encode("utf-8")
    with open(file_path, "wb") as f:
        f.write(encoded)
    sha256 = hashlib.sha256(encoded).hexdigest()
    return len(encoded), sha256


def write_text_file(file_path: Path, text: str) -> tuple[int, str]:
    """Write text file UTF-8. Returns (file_size_bytes, sha256_hex)."""
    encoded = text.encode("utf-8")
    with open(file_path, "wb") as f:
        f.write(encoded)
    sha256 = hashlib.sha256(encoded).hexdigest()
    return len(encoded), sha256


def export_speeches(conn: sqlite3.Connection, out_dir: Path) -> dict[str, dict[str, Any]]:
    """Export speeches grouped by year into speeches_<year>.jsonl.gz.

    Queries database year by year and streams rows to disk to keep memory minimal.
    Fields: id, external_id, speech_key, date, start_time, end_time,
    duration_seconds, speaker, speaker_uuid, speaker_role, speaker_faction,
    speech_type, agenda_title, agenda_item_uuid, draft_uuid, status, text,
    source_url, video_url.
    """
    # Check if agenda_items table exists
    has_agenda_items = (
        conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='agenda_items'"
        ).fetchone()[0]
        > 0
    )

    # Discover speech years
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT substr(date, 1, 4) FROM speeches "
        "WHERE date IS NOT NULL AND date != '' ORDER BY 1"
    )
    years = [r[0] for r in cursor.fetchall() if r[0]]

    results: dict[str, dict[str, Any]] = {}

    for year in years:
        next_year = str(int(year) + 1)
        start_date = f"{year}-01-01"
        end_date = f"{next_year}-01-01"

        query = (
            """
        SELECT
            s.id,
            s.external_id,
            s.speech_key,
            s.date,
            s.start_time,
            s.end_time,
            s.duration_seconds,
            s.speaker,
            s.speaker_uuid,
            s.speaker_role,
            s.speaker_faction,
            s.speech_type,
            s.agenda_title,
            """
            + (
                """a.agenda_item_uuid,
            a.draft_uuid,
            """
                if has_agenda_items
                else """NULL AS agenda_item_uuid,
            NULL AS draft_uuid,
            """
            )
            + """
            s.status,
            s.text,
            s.source_url,
            s.video_url
        FROM speeches s
        """
            + (
                """LEFT JOIN (
            SELECT
                source_file,
                steno_title,
                MIN(agenda_item_uuid) AS agenda_item_uuid,
                MIN(draft_uuid) AS draft_uuid
            FROM agenda_items
            GROUP BY source_file, steno_title
        ) a
            ON a.source_file = s.source_file
           AND a.steno_title = s.agenda_title
        """
                if has_agenda_items
                else ""
            )
            + """
        WHERE s.date >= ? AND s.date < ?
        ORDER BY s.date ASC, s.time ASC, s.id ASC
        """
        )

        def speech_row_generator(
            sql_query: str, yr_start: str, yr_end: str
        ) -> Iterable[dict[str, Any]]:
            cur = conn.cursor()
            cur.execute(sql_query, (yr_start, yr_end))
            for row in cur:
                yield {
                    "id": row[0],
                    "external_id": row[1],
                    "speech_key": row[2],
                    "date": row[3],
                    "start_time": row[4],
                    "end_time": row[5],
                    "duration_seconds": row[6],
                    "speaker": row[7],
                    "speaker_uuid": row[8],
                    "speaker_role": row[9],
                    "speaker_faction": row[10],
                    "speech_type": row[11],
                    "agenda_title": row[12],
                    "agenda_item_uuid": row[13],
                    "draft_uuid": row[14],
                    "status": row[15],
                    "text": row[16],
                    "source_url": row[17],
                    "video_url": row[18],
                }

        file_name = f"speeches_{year}.jsonl.gz"
        file_path = out_dir / file_name
        count, size, sha256 = write_deterministic_jsonl_gz(
            file_path, speech_row_generator(query, start_date, end_date)
        )
        results[file_name] = {
            "count": count,
            "size": size,
            "sha256": sha256,
        }

    return results


def export_votings(conn: sqlite3.Connection, out_dir: Path) -> dict[str, Any]:
    """Export votings.jsonl.gz."""
    cursor = conn.cursor()
    cursor.execute("""
    SELECT
        uuid,
        voting_number,
        type,
        description,
        date,
        start_time,
        end_time,
        sitting_date,
        sitting_datetime,
        membership,
        sitting_uuid,
        sitting_title,
        related_document_uuid,
        related_document_reference,
        related_document_title,
        related_document_type,
        chairman_uuid,
        present,
        absent,
        in_favor,
        against,
        neutral,
        abstained
    FROM votings
    ORDER BY date ASC, start_time ASC, uuid ASC
    """)

    rows = []
    for r in cursor.fetchall():
        v_type = r[2]
        in_fav = r[19] or 0
        ag = r[20] or 0
        neu = r[21] or 0
        is_tech = (v_type == "AVALIK") and ((in_fav + ag + neu) == 0)

        rows.append(
            {
                "uuid": r[0],
                "voting_number": r[1],
                "type": r[2],
                "description": r[3],
                "date": r[4],
                "start_time": r[5],
                "end_time": r[6],
                "sitting_date": r[7],
                "sitting_datetime": r[8],
                "membership": r[9],
                "sitting_uuid": r[10],
                "sitting_title": r[11],
                "related_document_uuid": r[12],
                "related_document_reference": r[13],
                "related_document_title": r[14],
                "related_document_type": r[15],
                "chairman_uuid": r[16],
                "present": r[17],
                "absent": r[18],
                "in_favor": r[19],
                "against": r[20],
                "neutral": r[21],
                "abstained": r[22],
                "is_technical": is_tech,
            }
        )

    file_name = "votings.jsonl.gz"
    count, size, sha256 = write_deterministic_jsonl_gz(out_dir / file_name, rows)
    return {"count": count, "size": size, "sha256": sha256}


def export_votes(conn: sqlite3.Connection, out_dir: Path) -> dict[str, Any]:
    """Export votes.jsonl.gz (streamed)."""
    cursor = conn.cursor()
    # Check if votes table has member_name or join with persons
    has_member_name_in_votes = False
    for col in cursor.execute("PRAGMA table_info(votes)").fetchall():
        if col[1] == "member_name":
            has_member_name_in_votes = True

    if has_member_name_in_votes:
        query = """
        SELECT v.voting_uuid, v.member_uuid, v.member_name, v.faction, v.decision
        FROM votes v
        ORDER BY v.voting_uuid ASC, v.member_uuid ASC
        """
    else:
        query = """
        SELECT v.voting_uuid, v.member_uuid, p.full_name AS member_name, v.faction, v.decision
        FROM votes v
        LEFT JOIN persons p ON p.uuid = v.member_uuid
        ORDER BY v.voting_uuid ASC, v.member_uuid ASC
        """

    def vote_generator() -> Iterable[dict[str, Any]]:
        cur = conn.cursor()
        cur.execute(query)
        for r in cur:
            yield {
                "voting_uuid": r[0],
                "member_uuid": r[1],
                "member_name": r[2] or "",
                "faction": r[3],
                "decision": r[4],
            }

    file_name = "votes.jsonl.gz"
    count, size, sha256 = write_deterministic_jsonl_gz(out_dir / file_name, vote_generator())
    return {"count": count, "size": size, "sha256": sha256}


def export_attendance(conn: sqlite3.Connection, out_dir: Path) -> dict[str, Any]:
    """Export attendance.jsonl.gz (+ sitting_type from attendance_checks, streamed)."""
    has_checks = (
        conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='attendance_checks'"
        ).fetchone()[0]
        > 0
    )

    query = (
        """
    SELECT
        a.id,
        a.session_date,
        a.voting_uuid,
        a.member_uuid,
        a.member_name,
        a.faction,
        a.status,
        """
        + ("c.sitting_type " if has_checks else "NULL AS sitting_type ")
        + """
    FROM attendance a
    """
        + ("LEFT JOIN attendance_checks c ON c.voting_uuid = a.voting_uuid " if has_checks else "")
        + """
    ORDER BY a.session_date ASC, a.voting_uuid ASC, a.member_name ASC, a.id ASC
    """
    )

    def attendance_generator() -> Iterable[dict[str, Any]]:
        cur = conn.cursor()
        cur.execute(query)
        for r in cur:
            yield {
                "id": r[0],
                "session_date": r[1],
                "voting_uuid": r[2],
                "member_uuid": r[3],
                "member_name": r[4],
                "faction": r[5],
                "status": r[6],
                "sitting_type": r[7],
            }

    file_name = "attendance.jsonl.gz"
    count, size, sha256 = write_deterministic_jsonl_gz(out_dir / file_name, attendance_generator())
    return {"count": count, "size": size, "sha256": sha256}


def export_attendance_checks(conn: sqlite3.Connection, out_dir: Path) -> dict[str, Any] | None:
    """Export attendance_checks.jsonl.gz."""
    has_table = (
        conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='attendance_checks'"
        ).fetchone()[0]
        > 0
    )
    if not has_table:
        return None

    cursor = conn.cursor()
    cursor.execute("""
    SELECT voting_uuid, sitting_uuid, sitting_title, sitting_datetime, sitting_type
    FROM attendance_checks
    ORDER BY sitting_datetime ASC, voting_uuid ASC
    """)
    rows = []
    for r in cursor.fetchall():
        rows.append(
            {
                "voting_uuid": r[0],
                "sitting_uuid": r[1],
                "sitting_title": r[2],
                "sitting_datetime": r[3],
                "sitting_type": r[4],
            }
        )

    file_name = "attendance_checks.jsonl.gz"
    count, size, sha256 = write_deterministic_jsonl_gz(out_dir / file_name, rows)
    return {"count": count, "size": size, "sha256": sha256}


def export_persons(conn: sqlite3.Connection, out_dir: Path) -> dict[str, Any]:
    """Export persons.jsonl.gz (uuid, first_name, last_name, full_name, gender, birth_year, electoral_district, photo_url, factions).

    Excludes exact date_of_birth and email, exposes birth_year (int).
    """
    # Load faction history from processed files if available
    factions_map: dict[str, list[Any]] = {}
    pf_path = PROJECT_ROOT / "data" / "processed" / "person_factions.json"
    if pf_path.exists():
        try:
            with open(pf_path, encoding="utf-8") as f:
                factions_map = json.load(f)
        except Exception:
            pass

    cursor = conn.cursor()
    cursor.execute("""
    SELECT uuid, first_name, last_name, full_name, gender, date_of_birth, electoral_district, photo_url
    FROM persons
    ORDER BY last_name ASC, first_name ASC, uuid ASC
    """)

    rows = []
    for r in cursor.fetchall():
        p_uuid = r[0]
        dob = r[5]
        birth_year = int(dob[:4]) if dob and len(dob) >= 4 and dob[:4].isdigit() else None
        person_obj: dict[str, Any] = {
            "uuid": p_uuid,
            "first_name": r[1],
            "last_name": r[2],
            "full_name": r[3],
            "gender": r[4],
            "birth_year": birth_year,
            "electoral_district": r[6],
            "photo_url": r[7],
        }
        if p_uuid in factions_map:
            normalized_factions = []
            for fac in factions_map[p_uuid]:
                f_copy = dict(fac)
                if f_copy.get("end") == "2099-12-31":
                    f_copy["end"] = None
                normalized_factions.append(f_copy)
            person_obj["factions"] = normalized_factions
        rows.append(person_obj)

    file_name = "persons.jsonl.gz"
    count, size, sha256 = write_deterministic_jsonl_gz(out_dir / file_name, rows)
    return {"count": count, "size": size, "sha256": sha256}


def export_agenda_items(conn: sqlite3.Connection, out_dir: Path) -> dict[str, Any] | None:
    """Export agenda_items.jsonl.gz."""
    has_table = (
        conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='agenda_items'"
        ).fetchone()[0]
        > 0
    )
    if not has_table:
        return None

    cursor = conn.cursor()
    cursor.execute("""
    SELECT
        agenda_item_uuid,
        sitting_uuid,
        sitting_date,
        sitting_datetime,
        source_file,
        "order",
        steno_title,
        api_title,
        document_type,
        type_code,
        stage,
        decision_code,
        decision_value,
        draft_uuid,
        draft_mark,
        draft_title,
        voting_uuids,
        match_method
    FROM agenda_items
    ORDER BY sitting_date ASC, "order" ASC, agenda_item_uuid ASC
    """)

    rows = []
    for r in cursor.fetchall():
        rows.append(
            {
                "agenda_item_uuid": r[0],
                "sitting_uuid": r[1],
                "sitting_date": r[2],
                "sitting_datetime": r[3],
                "source_file": r[4],
                "order": r[5],
                "steno_title": r[6],
                "api_title": r[7],
                "document_type": r[8],
                "type_code": r[9],
                "stage": r[10],
                "decision_code": r[11],
                "decision_value": r[12],
                "draft_uuid": r[13],
                "draft_mark": r[14],
                "draft_title": r[15],
                "voting_uuids": r[16],
                "match_method": r[17],
            }
        )

    file_name = "agenda_items.jsonl.gz"
    count, size, sha256 = write_deterministic_jsonl_gz(out_dir / file_name, rows)
    return {"count": count, "size": size, "sha256": sha256}


def export_reference_json_files(out_dir: Path) -> dict[str, dict[str, Any]]:
    """Copy/export memberships.json and governments.json."""
    results: dict[str, dict[str, Any]] = {}

    # 1. memberships.json
    src_mems = PROJECT_ROOT / "data" / "processed" / "memberships.json"
    if src_mems.exists():
        with open(src_mems, encoding="utf-8") as f:
            mems_data = json.load(f)
    else:
        # Fallback to standard memberships if file not found in test env
        mems_data = [
            {"id": 14, "number": 14, "start_date": "2019-04-04", "end_date": "2023-04-10"},
            {"id": 15, "number": 15, "start_date": "2023-04-10", "end_date": None},
        ]
    size, sha256 = write_deterministic_json(out_dir / "memberships.json", mems_data)
    results["memberships.json"] = {
        "count": len(mems_data) if isinstance(mems_data, list) else 1,
        "size": size,
        "sha256": sha256,
    }

    # 2. governments.json (copy from src/data/governments.json)
    src_govs = PROJECT_ROOT / "src" / "data" / "governments.json"
    if src_govs.exists():
        shutil.copy2(src_govs, out_dir / "governments.json")
    else:
        # Fallback empty list
        write_deterministic_json(out_dir / "governments.json", [])

    with open(out_dir / "governments.json", "rb") as f:
        gov_content = f.read()
        gov_size = len(gov_content)
        gov_sha256 = hashlib.sha256(gov_content).hexdigest()
        try:
            gov_count = len(json.loads(gov_content))
        except Exception:
            gov_count = 1

    results["governments.json"] = {
        "count": gov_count,
        "size": gov_size,
        "sha256": gov_sha256,
    }

    return results


def generate_readme(date_str: str) -> str:
    """Generate README.md for the open data release."""
    return f"""# Riigikogu kõnede ja avaandmete andmestik (Riigivaade Open Data)

- **Versioon / kuupäev:** {date_str}
- **Litsents:** Creative Commons Attribution-ShareAlike 3.0 Unported (CC BY-SA 3.0)
- **Allikas:** Riigikogu Kantselei avaandmete API (`https://api.riigikogu.ee`) ja Riigikogu stenogrammid (`https://stenogrammid.riigikogu.ee`).

Kohustuslik viitamine / Required attribution:
> Andmed pärinevad Riigikogu avaandmetest (api.riigikogu.ee) ja projekti Riigivaade (https://www.riigivaade.me) töödeldud andmestikust.

---

### Mis see on? / About this dataset

Käesolev andmestik koondab struktureeritud kujul Riigikogu XIV ja XV koosseisu (alates 2019. aastast) kõned, hääletused, saadikute hääled, kohalolekukontrollid, saadikute metaandmed ja valitsuskoalitsioonide perioodid.

Kõik andmefailid on pakitud gzip-vormingus JSON Lines (`.jsonl.gz`) või JSON (`.json`) failidena ning kodeeritud UTF-8 vormingus.

Andmestikust on teadlikult eemaldatud ebavajalikud isikuandmed nagu sünnikuupäevad ja e-posti aadressid.

### Teadaolevad piirangud / Known limitations
1. **Redigeerimata stenogrammid (UNEDITED):** Värskete istungite stenogrammid võivad esialgu olla staatusega `UNEDITED` ning neid parandatakse ja toimetatakse Riigikogu Kantselei poolt tagantjärele.
2. **Kõnede kestused:** Väga pikkade sõnavõttude või tehniliste salvestusvigade puhul võivad üksikud kestused olla piiratud maksimaalse ülempiiriga.
3. **Päevakorrapunktide sidumine:** Osa vanemate või mittesisuliste päevakorrapunktide pealkirju ei ole otseselt seotud konkreetse seaduseelnõuga.
4. **Koalitsiooniperioodid:** Valitsuste koalitsiooni ja opositsiooni kuuluvused (`governments.json`) on kontrollitud ametlike allikate (valitsus.ee, ERR) põhjal ja käsitsi hooldatud.

### English Summary
This open dataset provides structured transcripts, votes, voting results, attendance records, MP profiles, agenda items, and parliamentary metadata of the Estonian Parliament (Riigikogu) since 2019.
Licensed under CC BY-SA 3.0 with source attribution to Riigikogu Kantselei (api.riigikogu.ee) and Riigivaade (https://www.riigivaade.me).
"""


def generate_data_dictionary() -> str:
    """Generate DATA_DICTIONARY.md describing every file and field."""
    return """# Andmesõnastik / Data Dictionary

### 1. `speeches_<year>.jsonl.gz`
Riigikogu saalis peetud kõned ja sõnavõtud aastate kaupa.
- `id` (int): Kõne unikaalne identifikaator andmebaasis.
- `external_id` (int | null): Riigikogu API välise kõne identifikaator.
- `speech_key` (string | null): Stabiilne unikaalne kõne võti.
- `date` (string, YYYY-MM-DD): Istungi kuupäev.
- `start_time` (string | null, ISO datetime): Kõne algusaeg.
- `end_time` (string | null, ISO datetime): Kõne lõpuaeg.
- `duration_seconds` (int | null): Kõne kestus sekundites.
- `speaker` (string): Kõneleja nimi.
- `speaker_uuid` (string | null): Kõneleja isiku UUID.
- `speaker_role` (string | null): Kõneleja ametlik roll kõne hetkel (nt minister, komisjoni esindaja).
- `speaker_faction` (string | null): Fraktsioon kõne toimumise ajal.
- `speech_type` (string | null): Kõne liik (SPEECH, SMALL_SPEECH, QUESTION, ANSWER jne).
- `agenda_title` (string | null): Päevakorrapunkti pealkiri.
- `agenda_item_uuid` (string | null): Seotud päevakorrapunkti UUID (kui tuvastatud).
- `draft_uuid` (string | null): Seotud seaduseelnõu UUID (kui tuvastatud).
- `status` (string): Kõne toimetuslik staatus (EDITED või UNEDITED).
- `text` (string): Kõne täistekst.
- `source_url` (string): Stenogrammi algallika URL ametlikus veebis.
- `video_url` (string | null): Salvestise YouTube video URL algusaja parameetriga.

### 2. `votings.jsonl.gz`
Täiskogu hääletused.
- `uuid` (string): Hääletuse unikaalne identifikaator.
- `voting_number` (int | null): Hääletuse järjekorranumber istungil.
- `type` (string): Hääletuse tüüp (AVALIK või SALAJANE).
- `description` (string): Hääletuse teema ja kirjeldus.
- `date` (string, YYYY-MM-DD): Hääletuse toimumise kuupäev.
- `start_time` (string, ISO datetime): Hääletuse algusaeg.
- `end_time` (string, ISO datetime): Hääletuse lõpuaeg.
- `sitting_date` (string, YYYY-MM-DD): Istungi kuupäev.
- `sitting_datetime` (string, ISO datetime): Istungi algusaeg.
- `membership` (int): Riigikogu koosseisu number (14 või 15).
- `sitting_uuid` (string | null): Istungi UUID.
- `sitting_title` (string | null): Istungi ametlik pealkiri.
- `related_document_uuid` (string | null): Seotud eelnõu või dokumendi UUID.
- `related_document_reference` (string | null): Dokumendi viitekood (nt "123 SE").
- `related_document_title` (string | null): Dokumendi pealkiri.
- `related_document_type` (string | null): Dokumendi liik (DRAFT jne).
- `chairman_uuid` (string | null): Hääletuse ajal istungit juhatanud saadiku UUID.
- `present` (int): Kohalolevate saadikute arv.
- `absent` (int): Puuduvate saadikute arv.
- `in_favor` (int): Poolthääled.
- `against` (int): Vastuhääled.
- `neutral` (int): Erapooletud hääled.
- `abstained` (int): Ei hääletanud saadikud.
- `is_technical` (boolean): Kas hääletus oli tehniline (AVALIK ilma poolt/vastu/erapooletu häälteta).

### 3. `votes.jsonl.gz`
Saadikute individuaalsed hääled igal hääletusel.
- `voting_uuid` (string): Hääletuse UUID.
- `member_uuid` (string): Saadiku isiku UUID.
- `member_name` (string): Saadiku nimi.
- `faction` (string | null): Saadiku fraktsioon hääletuse ajal.
- `decision` (string): Saadiku otsus (POOLT, VASTU, ERAPOOLETU, EI_HAALETANUD, PUUDUB).

### 4. `attendance.jsonl.gz`
Kohalolekukontrollide individuaalsed kirjed.
- `id` (int): Kirje ID.
- `session_date` (string, ISO datetime): Istungi toimumise aeg.
- `voting_uuid` (string): Kohalolekukontrolli unikaalne identifikaator.
- `member_uuid` (string | null): Saadiku UUID.
- `member_name` (string): Saadiku nimi.
- `faction` (string | null): Saadiku fraktsioon.
- `status` (string): Staatus (KOHAL või PUUDUB).
- `sitting_type` (string | null): Istungi liik (KORRALINE, ERAKORRALINE, INFOTUND jne).

### 5. `attendance_checks.jsonl.gz`
Kohalolekukontrollide üldandmed.
- `voting_uuid` (string): Kontrolli identifikaator.
- `sitting_uuid` (string | null): Istungi UUID.
- `sitting_title` (string | null): Istungi pealkiri.
- `sitting_datetime` (string | null, ISO datetime): Istungi toimumise aeg.
- `sitting_type` (string): Istungi liik.

### 6. `persons.jsonl.gz`
Saadikute profiiliandmed (isikuandmetest on eemaldatud täpsed sünnikuupäevad ja e-post, avaldatud on sünniaasta).
- `uuid` (string): Saadiku unikaalne identifikaator.
- `first_name` (string): Eesnimi.
- `last_name` (string): Perekonnanimi.
- `full_name` (string): Täisnimi.
- `gender` (string | null): Sugu.
- `birth_year` (int | null): Sünniaasta (nt 1978).
- `electoral_district` (string | null): Valimisringkond.
- `photo_url` (string | null): Ametliku portreefoto URL.
- `factions` (array | optional): Fraktsioonide ajalugu (`factions[].end = null` tähistab kehtivat kuuluvust).

### 7. `agenda_items.jsonl.gz`
Istungite päevakorrapunktid ja seosed seaduseelnõudega.
- `agenda_item_uuid` (string): Päevakorrapunkti UUID.
- `sitting_uuid` (string | null): Istungi UUID.
- `sitting_date` (string | null, YYYY-MM-DD): Istungi kuupäev.
- `sitting_datetime` (string | null, ISO datetime): Istungi algusaeg.
- `source_file` (string | null): Seotud stenogrammifail.
- `order` (int | null): Järjekorranumber istungil.
- `steno_title` (string | null): Pealkiri stenogrammis.
- `api_title` (string | null): Pealkiri avaandmete API-s.
- `document_type` (string | null): Dokumendi liik.
- `type_code` (string | null): Eelnõu tüübikood.
- `stage` (string | null): Menetlusjärk (nt ESIMENE_LUGEMINE).
- `decision_code` (string | null): Otsuse kood.
- `decision_value` (string | null): Otsuse tekst.
- `draft_uuid` (string | null): Seaduseelnõu UUID.
- `draft_mark` (string | null): Eelnõu tähis (nt "123 SE").
- `draft_title` (string | null): Eelnõu pealkiri.
- `voting_uuids` (string | null): Seotud hääletuste identifikaatorid.
- `match_method` (string | null): Tuvastusmeetod.

### 8. `memberships.json`
Riigikogu koosseisude algus- ja lõpukuupäevad.

### 9. `governments.json`
Vabariigi Valitsuste koosseisude ja koalitsioonierakondade ametlikud perioodid.
"""


def build_open_data_release(
    db_path: Path,
    out_dir: Path,
    release_date: str | None = None,
    commit_override: str | None = None,
) -> dict[str, Any]:
    """Execute the full open data release build."""
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = release_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Open SQLite read-only URI
    abs_db = db_path.resolve()
    uri = f"file:{abs_db}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)

    manifest_files: dict[str, dict[str, Any]] = {}

    try:
        # 1. Speeches by year
        speeches_res = export_speeches(conn, out_dir)
        manifest_files.update(speeches_res)

        # 2. Votings
        votings_res = export_votings(conn, out_dir)
        manifest_files["votings.jsonl.gz"] = votings_res

        # 3. Votes
        votes_res = export_votes(conn, out_dir)
        manifest_files["votes.jsonl.gz"] = votes_res

        # 4. Attendance
        attendance_res = export_attendance(conn, out_dir)
        manifest_files["attendance.jsonl.gz"] = attendance_res

        # 5. Attendance checks
        checks_res = export_attendance_checks(conn, out_dir)
        if checks_res:
            manifest_files["attendance_checks.jsonl.gz"] = checks_res

        # 6. Persons
        persons_res = export_persons(conn, out_dir)
        manifest_files["persons.jsonl.gz"] = persons_res

        # 7. Agenda items
        agenda_res = export_agenda_items(conn, out_dir)
        if agenda_res:
            manifest_files["agenda_items.jsonl.gz"] = agenda_res

        # 8. Reference json files
        ref_res = export_reference_json_files(out_dir)
        manifest_files.update(ref_res)

        # Date range
        min_speech_date, max_speech_date = conn.execute(
            "SELECT min(date), max(date) FROM speeches"
        ).fetchone()
        min_voting_date, max_voting_date = conn.execute(
            "SELECT min(date), max(date) FROM votings"
        ).fetchone()

        # Schema migrations
        has_migrations = (
            conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()[0]
            > 0
        )
        migrations = []
        if has_migrations:
            migrations = [
                {"version": r[0], "name": r[1]}
                for r in conn.execute(
                    "SELECT version, name FROM schema_migrations ORDER BY version"
                ).fetchall()
            ]

    finally:
        conn.close()

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 9. README.md & DATA_DICTIONARY.md
    readme_text = generate_readme(date_str)
    readme_size, readme_sha256 = write_text_file(out_dir / "README.md", readme_text)
    manifest_files["README.md"] = {
        "size": readme_size,
        "sha256": readme_sha256,
    }

    dict_text = generate_data_dictionary()
    dict_size, dict_sha256 = write_text_file(out_dir / "DATA_DICTIONARY.md", dict_text)
    manifest_files["DATA_DICTIONARY.md"] = {
        "size": dict_size,
        "sha256": dict_sha256,
    }

    # 10. manifest.json
    manifest_data = {
        "version": date_str,
        "git_commit": get_git_commit(commit_override),
        "created_at": f"{date_str}T00:00:00Z"
        if release_date
        else datetime.now(timezone.utc).isoformat(),
        "date_range": {
            "speeches": {
                "start": min_speech_date,
                "end": max_speech_date,
            },
            "votings": {
                "start": min_voting_date,
                "end": max_voting_date,
            },
        },
        "schema_migrations": migrations,
        "files": manifest_files,
    }
    manifest_size, manifest_sha256 = write_deterministic_json(
        out_dir / "manifest.json", manifest_data
    )

    # 11. SHA256SUMS (for all files in directory except SHA256SUMS itself)
    sha_lines = []
    for file_name in sorted(os.listdir(out_dir)):
        if file_name == "SHA256SUMS":
            continue
        file_path = out_dir / file_name
        if file_path.is_file():
            with open(file_path, "rb") as f:
                h = hashlib.sha256(f.read()).hexdigest()
            sha_lines.append(f"{h}  {file_name}")

    sums_text = "\n".join(sha_lines) + "\n"
    write_text_file(out_dir / "SHA256SUMS", sums_text)

    return manifest_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Riigivaade open data release.")
    parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="Path to source SQLite database file.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: data/release/<YYYY-MM-DD>/).",
    )
    parser.add_argument(
        "--commit",
        type=str,
        default=None,
        help="Git commit hash override (defaults to env GIT_COMMIT, git rev-parse HEAD, or 'unknown').",
    )
    args = parser.parse_args()

    if not args.db.exists():
        print(f"Error: Database file not found: {args.db}", file=sys.stderr)
        sys.exit(1)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = args.out or (PROJECT_ROOT / "data" / "release" / date_str)

    print(f"Exporting open data release from {args.db} to {out_dir}...")
    manifest = build_open_data_release(args.db, out_dir, commit_override=args.commit)
    print("Build complete! Manifest summary:")
    for fn, meta in manifest["files"].items():
        cnt = f"{meta['count']} rows, " if "count" in meta else ""
        print(f"  - {fn}: {cnt}{meta['size']} bytes, sha256: {meta['sha256'][:10]}...")


if __name__ == "__main__":
    main()
