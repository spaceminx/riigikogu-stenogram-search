import argparse
import glob
import json
import os
import re
import shutil
import sqlite3
import sys
import time

import requests

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import OUTPUT_DIR_PROCESSED

TARMO_TAMM_CUTOFF = "2023-04-10"
TARMO_TAMM_UUID_OLD = "76afbcdc-b41d-4fc6-b5eb-d0cce01e94d5"
TARMO_TAMM_UUID_NEW = "236e49d6-eecb-4562-8ad4-bedd586bb149"


def load_persons_name_map(data_dir: str) -> tuple[dict[str, str], set[str]]:
    """Load canonical full_name to UUID mapping from persons.json for unique names."""
    persons_file = os.path.join(data_dir, "persons.json")
    if not os.path.exists(persons_file):
        try:
            from scripts.download_from_b2 import download_from_b2

            print("Kohalik persons.json puudub, laadin B2-st...")
            download_from_b2(include_all_history=False)
        except Exception as e:
            print(f"Hoiatus: Ei saanud persons.json B2-st alla laadida: {e}")

    if not os.path.exists(persons_file):
        return {}, set()

    with open(persons_file, encoding="utf-8") as f:
        persons = json.load(f)

    name_counts: dict[str, int] = {}
    name_to_uuid: dict[str, str] = {}
    known_uuids: set[str] = set()

    for p in persons:
        full_name = p.get("full_name") or p.get("fullName")
        uuid_val = p.get("uuid")
        if full_name and uuid_val:
            name_counts[full_name] = name_counts.get(full_name, 0) + 1
            name_to_uuid[full_name] = uuid_val
            known_uuids.add(uuid_val)

    # Keep only uniquely occurring names
    unique_name_map = {name: uid for name, uid in name_to_uuid.items() if name_counts[name] == 1}
    return unique_name_map, known_uuids


def build_old_names_map(
    data_dir: str, db_path: str | None, known_uuids: set[str]
) -> dict[str, str]:
    """Build mapping for historical name changes (e.g. Siret Kotka-Repinski, Luisa Rõivas) from speeches data."""
    old_names: dict[str, set[str]] = {}

    # 1. Check sqlite database if available
    if db_path and os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            for spkr, uid in c.execute(
                "SELECT speaker, COALESCE(NULLIF(speaker_uuid, ''), NULLIF(ems_id, '')) "
                "FROM speeches "
                "WHERE speaker IS NOT NULL AND COALESCE(NULLIF(speaker_uuid, ''), NULLIF(ems_id, '')) IS NOT NULL"
            ):
                if uid and uid in known_uuids:
                    old_names.setdefault(spkr, set()).add(uid)
            conn.close()
        except Exception as e:
            print(f"Hoiatus: Speeches andmete lugemine andmebaasist ebaõnnestus: {e}")

    # 2. Check 20*.jsonl processed transcripts as supplementary / fallback source
    jsonl_files = sorted(glob.glob(os.path.join(data_dir, "20*.jsonl")))
    for fpath in jsonl_files:
        if (
            not re.match(r"^\d{4}\.jsonl$", os.path.basename(fpath))
            or fpath.endswith(".bak")
            or fpath.endswith(".tmp")
        ):
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    spkr = d.get("speaker")
                    uid = d.get("speaker_uuid") or d.get("ems_id")
                    if spkr and uid and str(uid) in known_uuids:
                        old_names.setdefault(spkr, set()).add(str(uid))
        except Exception:
            continue

    # Keep unambiguous mappings where speaker maps to exactly 1 known UUID
    return {name: list(uids)[0] for name, uids in old_names.items() if len(uids) == 1}


def repair_attendance_uuids(
    data_dir: str = OUTPUT_DIR_PROCESSED,
    dry_run: bool = True,
    db_path: str | None = None,
    upload: bool = False,
    refetch_unmapped: bool = False,
) -> dict:
    """Repair member_uuid in attendance.jsonl and optionally the SQLite database."""
    attendance_file = os.path.join(data_dir, "attendance.jsonl")
    if not os.path.exists(attendance_file):
        print(f"Viga: Faili {attendance_file} ei leitud.")
        return {}

    unique_name_map, known_uuids = load_persons_name_map(data_dir)
    old_names_map = build_old_names_map(data_dir, db_path, known_uuids)

    total_records = 0
    needed_repair = 0
    resolved_canonical = 0
    resolved_tarmo_tamm = 0
    resolved_old_names = 0
    resolved_refetched = 0
    unresolved_names: dict[str, int] = {}

    modified_lines: list[str] = []
    file_modified = False

    # Records needing refetch grouped by voting_uuid: voting_uuid -> list of record indices
    unmapped_by_voting: dict[str, list[int]] = {}
    parsed_records: list[dict] = []

    with open(attendance_file, encoding="utf-8") as f:
        for line in f:
            total_records += 1
            if not line.strip():
                parsed_records.append({})
                continue

            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                parsed_records.append({})
                continue

            parsed_records.append(rec)
            member_name = rec.get("member_name", "").strip()
            session_date = rec.get("session_date", "")[:10]

            target_uuid = None
            resolution_type = None

            if member_name == "Tarmo Tamm":
                target_uuid = (
                    TARMO_TAMM_UUID_OLD if session_date < TARMO_TAMM_CUTOFF else TARMO_TAMM_UUID_NEW
                )
                resolution_type = "tarmo_tamm"
            elif member_name in unique_name_map:
                target_uuid = unique_name_map[member_name]
                resolution_type = "canonical"
            elif member_name in old_names_map:
                target_uuid = old_names_map[member_name]
                resolution_type = "old_name"
            else:
                resolution_type = "unresolved"

            if resolution_type == "unresolved":
                unmapped_by_voting.setdefault(rec.get("voting_uuid", ""), []).append(
                    len(parsed_records) - 1
                )
            else:
                if resolution_type == "canonical":
                    resolved_canonical += 1
                elif resolution_type == "tarmo_tamm":
                    resolved_tarmo_tamm += 1
                elif resolution_type == "old_name":
                    resolved_old_names += 1

            if "member_uuid" not in rec or rec.get("member_uuid") != target_uuid:
                rec["member_uuid"] = target_uuid
                needed_repair += 1
                file_modified = True

    # Optional refetch of unmapped voting checks from Riigikogu API
    if refetch_unmapped and unmapped_by_voting:
        print(f"Refetching voters for {len(unmapped_by_voting)} unmapped voting checks...")
        for v_uuid, rec_indices in unmapped_by_voting.items():
            if not v_uuid:
                continue
            time.sleep(5.1)
            try:
                resp = requests.get(
                    f"https://api.riigikogu.ee/api/votings/{v_uuid}", timeout=(5, 25)
                )
                if resp.status_code == 200:
                    voters = resp.json().get("voters", [])
                    voter_map = {
                        v.get("fullName", "").strip(): v.get("uuid", "").strip()
                        for v in voters
                        if v.get("fullName") and v.get("uuid")
                    }
                    for idx in rec_indices:
                        rec = parsed_records[idx]
                        m_name = rec.get("member_name", "").strip()
                        if m_name in voter_map:
                            api_uuid = voter_map[m_name]
                            if rec.get("member_uuid") != api_uuid:
                                rec["member_uuid"] = api_uuid
                                needed_repair += 1
                                file_modified = True
                            resolved_refetched += 1
            except Exception as e:
                print(f"Hoiatus: Hääletuse {v_uuid} toomine ebaõnnestus: {e}")

    # Final pass to tally unresolved names and serialize JSONL lines
    db_updates: list[tuple[str | None, str, str]] = []
    for rec in parsed_records:
        if not rec:
            modified_lines.append("\n")
            continue
        m_uuid = rec.get("member_uuid")
        m_name = rec.get("member_name", "").strip()
        v_uuid = rec.get("voting_uuid", "")
        if not m_uuid:
            unresolved_names[m_name] = unresolved_names.get(m_name, 0) + 1
        db_updates.append((m_uuid, v_uuid, m_name))
        modified_lines.append(json.dumps(rec, ensure_ascii=False) + "\n")

    # 1. Apply file updates
    if not dry_run and file_modified:
        bak_path = attendance_file + ".bak"
        try:
            shutil.copy(attendance_file, bak_path)
        except (PermissionError, OSError):
            shutil.copyfile(attendance_file, bak_path)

        tmp_path = attendance_file + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as out_f:
            out_f.writelines(modified_lines)
        os.replace(tmp_path, attendance_file)

    # 2. Upload to Backblaze B2 if requested
    if not dry_run and upload and file_modified:
        from scripts.upload_to_b2 import upload_to_b2

        upload_ok = upload_to_b2(only_files=[attendance_file])
        if not upload_ok:
            print("VIGA: B2 üleslaadimine ebaõnnestus. Andmebaasi ei uuendata.")
            sys.exit(1)

    # 3. Apply SQLite database updates
    db_updated_count = 0
    if not dry_run and db_path and os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # Idempotent schema migration for SQLite
        cols = {row[1] for row in c.execute("PRAGMA table_info(attendance)")}
        if "member_uuid" not in cols:
            c.execute("ALTER TABLE attendance ADD COLUMN member_uuid TEXT;")
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_attendance_member_uuid ON attendance(member_uuid);"
        )

        batch_size = 2000
        for i in range(0, len(db_updates), batch_size):
            batch = db_updates[i : i + batch_size]
            c.executemany(
                "UPDATE attendance SET member_uuid = ? WHERE voting_uuid = ? AND member_name = ?",
                batch,
            )
            db_updated_count += len(batch)
        conn.commit()
        conn.close()

    # Print Report
    print("=" * 60)
    print("KOHALOLEKU UUID-DE PARANDAMISE RAPORT")
    print("=" * 60)
    mode_str = "KUIVKÄIVITUS (--dry-run, faile ei muudetud)" if dry_run else "RAKENDATUD (--apply)"
    print(f"Režiim: {mode_str}")
    print(f"Kontrollitud ridu kokku: {total_records}")
    print(f"Uuendatud / parandatud ridu (JSONL): {needed_repair}")
    print(f"  - Kanoonilise nime kaudu: {resolved_canonical}")
    print(f"  - Tarmo Tamm kuupäevareegliga: {resolved_tarmo_tamm}")
    print(f"  - Speeches vanade nimede kaudu: {resolved_old_names}")
    if refetch_unmapped:
        print(f"  - API refetch kaudu: {resolved_refetched}")

    if unresolved_names:
        print(f"\nLahendamata nimed ({len(unresolved_names)} nime, jäävad NULL-iks):")
        for name, cnt in sorted(unresolved_names.items(), key=lambda x: -x[1]):
            print(f"  - {name}: {cnt} rida")
    else:
        print("\nKõik kohaloleku nimed on edukalt UUID-ga seotud!")

    if db_path:
        action_label = (
            "SQLite andmebaasis uuendatud ridu"
            if not dry_run
            else "SQLite andmebaasis uuendamist vajavaid ridu"
        )
        print(f"\n{action_label}: {db_updated_count if not dry_run else needed_repair}")

    print("=" * 60)

    return {
        "total_records": total_records,
        "needed_repair": needed_repair,
        "resolved_canonical": resolved_canonical,
        "resolved_tarmo_tamm": resolved_tarmo_tamm,
        "resolved_old_names": resolved_old_names,
        "resolved_refetched": resolved_refetched,
        "unresolved_names": unresolved_names,
        "dry_run": dry_run,
        "db_updated_count": db_updated_count,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Täida attendance.jsonl ja andmebaasi tabeli attendance member_uuid."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Kuivkäivitus ilma faile muutmata (vaikimisi)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Rakenda parandused faili attendance.jsonl (loob .bak varukoopia)",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        default=False,
        help="Laadi muudetud fail Backblaze B2-sse tagasi eTag kontrolliga",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="SQLite andmebaasi failitee (uuendab tabelit attendance)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=OUTPUT_DIR_PROCESSED,
        help="Töödeldud andmete kaust (vaikimisi data/processed)",
    )
    parser.add_argument(
        "--refetch-unmapped",
        action="store_true",
        default=False,
        help="Too lahendamata hääletuste voters API-st uuesti (5,1 s paus)",
    )

    args = parser.parse_args()
    is_dry_run = not args.apply or args.dry_run

    repair_attendance_uuids(
        data_dir=args.data_dir,
        dry_run=is_dry_run,
        db_path=args.db,
        upload=args.upload,
        refetch_unmapped=args.refetch_unmapped,
    )


if __name__ == "__main__":
    main()
