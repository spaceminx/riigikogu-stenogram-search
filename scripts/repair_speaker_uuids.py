import argparse
import glob
import json
import os
import re
import shutil
import sqlite3
import sys
from collections import Counter

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import OUTPUT_DIR_PROCESSED
from scripts.fetch_stenograms_api import (
    get_faction_for_date,
    load_persons_metadata,
    resolve_speaker_uuid,
    split_speaker_role,
)


def repair_speaker_uuids(
    data_dir: str = OUTPUT_DIR_PROCESSED,
    dry_run: bool = True,
    db_path: str | None = None,
    upload: bool = False,
) -> dict:
    """Repair speaker roles, UUIDs, and factions across processed datasets."""
    persons_file = os.path.join(data_dir, "persons.json")
    factions_file = os.path.join(data_dir, "factions_map.json")

    # Attempt download from B2 if metadata files do not exist locally
    if not os.path.exists(persons_file) or not os.path.exists(factions_file):
        try:
            from scripts.download_from_b2 import download_from_b2

            print("Kohalikud metaandmefailid puuduvad, laadin B2-st...")
            download_from_b2(include_all_history=False)
        except Exception as e:
            print(f"Hoiatus: Ei saanud metaandmeid B2-st alla laadida: {e}")

    known_uuids, person_name_map, uuid_to_name_map = load_persons_metadata(data_dir)
    ambiguous_names = {
        name for name, cnt in Counter(uuid_to_name_map.values()).items() if cnt > 1
    } | {"Tarmo Tamm"}

    if os.path.exists(factions_file):
        with open(factions_file, encoding="utf-8") as f:
            faction_map = json.load(f)
    else:
        faction_map = {}

    pattern = os.path.join(data_dir, "20*.jsonl")
    raw_files = sorted(glob.glob(pattern))
    jsonl_files = [
        f
        for f in raw_files
        if re.match(r"^\d{4}\.jsonl$", os.path.basename(f))
        and not f.endswith(".bak")
        and not f.endswith(".tmp")
    ]

    # Pre-load database rows to compare with JSONL even if JSONL is already repaired
    db_rows_by_ext_id: dict[int, tuple[str, str | None, str | None, str | None]] = {}
    db_rows_by_key: dict[str, tuple[str, str | None, str | None, str | None]] = {}
    if db_path and os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        for row in cursor.execute(
            "SELECT external_id, speech_key, speaker, speaker_role, speaker_uuid, speaker_faction FROM speeches"
        ):
            ext_id_val, sp_key_val, spkr_val, role_val, u_val, f_val = row
            if ext_id_val is not None:
                db_rows_by_ext_id[ext_id_val] = (spkr_val, role_val, u_val, f_val)
            elif sp_key_val:
                db_rows_by_key[sp_key_val] = (spkr_val, role_val, u_val, f_val)
        conn.close()

    total_checked = 0
    needed_repair = 0
    name_change_counts: dict[str, int] = {}
    role_split_counts: dict[str, int] = {}
    unresolved_counts: dict[str, int] = {}
    changed_rows: list[dict] = []
    modified_files: list[str] = []

    db_diff_fields: dict[str, int] = {
        "speaker": 0,
        "speaker_role": 0,
        "speaker_uuid": 0,
        "speaker_faction": 0,
    }
    db_updates_by_ext_id: list[tuple[str, str | None, str | None, str | None, int]] = []
    db_updates_by_key: list[tuple[str, str | None, str | None, str | None, str]] = []

    for file_path in jsonl_files:
        file_modified = False
        new_lines: list[str] = []

        with open(file_path, encoding="utf-8") as f:
            for line in f:
                total_checked += 1
                if not line.strip():
                    new_lines.append(line)
                    continue

                row = json.loads(line)
                role = row.get("speaker_role")
                uuid_val = row.get("speaker_uuid")
                faction_val = row.get("speaker_faction")
                speaker = row.get("speaker") or ""
                ems_id = row.get("ems_id")
                date_str = row.get("date") or ""

                # Step 1: Split speaker role if role is None and speaker contains a title/role
                new_speaker, new_role = split_speaker_role(speaker)
                if role is None and new_role is not None:
                    effective_speaker = new_speaker
                    effective_role = new_role
                else:
                    effective_speaker = speaker
                    effective_role = role

                # Step 2: Check if role splitting changed, UUID/faction needs resolution, or speaker is ambiguous
                is_ambiguous = (effective_speaker in ambiguous_names) or (
                    speaker in ambiguous_names
                )
                needs_resolution = (
                    (effective_speaker != speaker or effective_role != role)
                    or (effective_role is None and (uuid_val is None or faction_val is None))
                    or is_ambiguous
                )

                if needs_resolution:
                    resolved_uuid, method = resolve_speaker_uuid(
                        speaker_name=effective_speaker,
                        ems_id=ems_id,
                        date=date_str,
                        known_uuids=known_uuids,
                        uuid_to_name_map=uuid_to_name_map,
                        person_name_map=person_name_map,
                    )
                    effective_uuid = resolved_uuid if resolved_uuid is not None else uuid_val
                    canon_name = (
                        uuid_to_name_map.get(effective_uuid)
                        if (effective_uuid and uuid_to_name_map)
                        else effective_speaker
                    )
                    new_faction = get_faction_for_date(faction_map, canon_name, date_str)
                else:
                    effective_uuid = uuid_val
                    new_faction = faction_val

                # Check if JSONL values changed
                if (
                    effective_speaker != speaker
                    or effective_role != role
                    or effective_uuid != uuid_val
                    or new_faction != faction_val
                ):
                    needed_repair += 1
                    file_modified = True
                    row["speaker"] = effective_speaker
                    row["speaker_role"] = effective_role
                    row["speaker_uuid"] = effective_uuid
                    row["speaker_faction"] = new_faction

                    changed_rows.append(
                        {
                            "file": os.path.basename(file_path),
                            "external_id": row.get("external_id"),
                            "speech_key": row.get("speech_key"),
                            "date": date_str,
                            "speaker": effective_speaker,
                            "old_uuid": uuid_val,
                            "new_uuid": effective_uuid,
                            "old_role": role,
                            "new_role": effective_role,
                            "old_faction": faction_val,
                            "new_faction": new_faction,
                            "method": method if needs_resolution else "none",
                        }
                    )

                    if effective_speaker != speaker:
                        pair = f"{speaker} -> {effective_speaker} ({effective_role})"
                        role_split_counts[pair] = role_split_counts.get(pair, 0) + 1

                    if needs_resolution and method == "ems_name_change":
                        pair = f"{effective_speaker} -> {canon_name}"
                        name_change_counts[pair] = name_change_counts.get(pair, 0) + 1

                if effective_role is None and effective_uuid is None:
                    unresolved_counts[effective_speaker] = (
                        unresolved_counts.get(effective_speaker, 0) + 1
                    )

                # Database difference check against final row values
                if db_path:
                    ext_id = row.get("external_id")
                    sp_key = row.get("speech_key")
                    db_vals = None
                    if ext_id is not None:
                        db_vals = db_rows_by_ext_id.get(ext_id)
                    elif sp_key:
                        db_vals = db_rows_by_key.get(sp_key)

                    if db_vals is not None:
                        db_speaker, db_role, db_uuid, db_faction = db_vals
                        if (
                            row["speaker"] != db_speaker
                            or row["speaker_role"] != db_role
                            or row["speaker_uuid"] != db_uuid
                            or row["speaker_faction"] != db_faction
                        ):
                            if row["speaker"] != db_speaker:
                                db_diff_fields["speaker"] += 1
                            if row["speaker_role"] != db_role:
                                db_diff_fields["speaker_role"] += 1
                            if row["speaker_uuid"] != db_uuid:
                                db_diff_fields["speaker_uuid"] += 1
                            if row["speaker_faction"] != db_faction:
                                db_diff_fields["speaker_faction"] += 1

                            if ext_id is not None:
                                db_updates_by_ext_id.append(
                                    (
                                        row["speaker"],
                                        row["speaker_role"],
                                        row["speaker_uuid"],
                                        row["speaker_faction"],
                                        int(ext_id),
                                    )
                                )
                            elif sp_key:
                                db_updates_by_key.append(
                                    (
                                        row["speaker"],
                                        row["speaker_role"],
                                        row["speaker_uuid"],
                                        row["speaker_faction"],
                                        str(sp_key),
                                    )
                                )

                new_lines.append(json.dumps(row, ensure_ascii=False) + "\n")

        if file_modified:
            modified_files.append(file_path)
            if not dry_run:
                bak_path = file_path + ".bak"
                try:
                    shutil.copy(file_path, bak_path)
                except (PermissionError, OSError):
                    shutil.copyfile(file_path, bak_path)
                tmp_path = file_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as out_f:
                    out_f.writelines(new_lines)
                os.replace(tmp_path, file_path)

    # 1. B2 Upload (kui apply ja upload)
    if not dry_run and upload and modified_files:
        from scripts.upload_to_b2 import upload_to_b2

        upload_ok = upload_to_b2(only_files=modified_files)
        if not upload_ok:
            print("VIGA: B2 üleslaadimine ebaõnnestus. Andmebaasi ei uuendata.")
            sys.exit(1)

    # 2. Database updates (alles pärast edukat üleslaadimist)
    db_updated_count = 0
    if not dry_run and db_path and (db_updates_by_ext_id or db_updates_by_key):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        batch_size = 500

        for i in range(0, len(db_updates_by_ext_id), batch_size):
            batch = db_updates_by_ext_id[i : i + batch_size]
            cursor.executemany(
                "UPDATE speeches SET speaker = ?, speaker_role = ?, speaker_uuid = ?, speaker_faction = ? WHERE external_id = ?",
                batch,
            )
            db_updated_count += len(batch)

        for i in range(0, len(db_updates_by_key), batch_size):
            batch = db_updates_by_key[i : i + batch_size]
            cursor.executemany(
                "UPDATE speeches SET speaker = ?, speaker_role = ?, speaker_uuid = ?, speaker_faction = ? WHERE speech_key = ?",
                batch,
            )
            db_updated_count += len(batch)

        conn.commit()
        conn.close()

    total_db_diff = len(db_updates_by_ext_id) + len(db_updates_by_key)

    # Print Report
    print("=" * 60)
    print("KÕNELEJATE JA ROLLIDE PARANDAMISE RAPORT")
    print("=" * 60)
    mode_str = "KUIVKÄIVITUS (--dry-run, faile ei muudetud)" if dry_run else "RAKENDATUD (--apply)"
    print(f"Režiim: {mode_str}")
    print(f"Kontrollitud ridu kokku: {total_checked}")
    print(f"Parandamist vajavaid ridu (JSONL): {needed_repair}")
    print(
        f"Muudatustega failid ({len(modified_files)}): {[os.path.basename(f) for f in modified_files]}"
    )

    if role_split_counts:
        print("\nEraldatud rollid (kandidaadid ja järelrollid):")
        for pair, count in sorted(role_split_counts.items(), key=lambda x: -x[1]):
            print(f"  - {pair}: {count} kõnet")

    print("\nTuvastatud nimevahetused:")
    if name_change_counts:
        for pair, count in sorted(name_change_counts.items(), key=lambda x: -x[1]):
            print(f"  - {pair}: {count} kõnet")
    else:
        print("  (puuduvad)")

    print("\nLahendamata jäänud kõnelejad (speaker_uuid puudub):")
    if unresolved_counts:
        for spkr, cnt in sorted(unresolved_counts.items(), key=lambda x: -x[1]):
            reason = "Külaline / ekspert / puudub saadiku UUID"
            if "Jõuluvana" in spkr:
                reason = "Jõulurahu külaline"
            elif spkr == "Luisa Rõivas":
                reason = "Jõuluistungi kõned, kus emsId oli algses API-s null"
            elif spkr == "Ülle Madise":
                reason = "Õiguskantsler / presidendikandidaat, mitte Riigikogu liige"
            elif "koor" in spkr.lower():
                reason = "Muusikaline etteaste"
            print(f"  - {spkr}: {cnt} kõnet ({reason})")
    else:
        print("  (kõik lahendatud)")

    if changed_rows:
        print(f"\nMuutuvad read ({len(changed_rows)} rida):")
        for r in changed_rows:
            uuid_change = (
                f"{r['old_uuid']} -> {r['new_uuid']}"
                if r["old_uuid"] != r["new_uuid"]
                else f"{r['new_uuid']} (muutmata)"
            )
            role_change = (
                f", roll: {r['old_role']} -> {r['new_role']}"
                if r["old_role"] != r["new_role"]
                else ""
            )
            print(
                f"  - {r['file']}: ext_id={r['external_id']}, sp_key={r['speech_key']}, kpv={r['date']}, kõneleja={r['speaker']}: UUID {uuid_change}{role_change} (meetod: {r['method']})"
            )

    if db_path:
        action_label = (
            "SQLite andmebaasis uuendatud ridu"
            if not dry_run
            else "SQLite andmebaasis uuendamist vajavaid ridu"
        )
        print(f"\n{action_label}: {db_updated_count if not dry_run else total_db_diff}")
        print("Väljade kaupa:")
        print(f"  - speaker: {db_diff_fields['speaker']} rida")
        print(f"  - speaker_role: {db_diff_fields['speaker_role']} rida")
        print(f"  - speaker_uuid: {db_diff_fields['speaker_uuid']} rida")
        print(f"  - speaker_faction: {db_diff_fields['speaker_faction']} rida")

    print("=" * 60)

    return {
        "total_checked": total_checked,
        "needed_repair": needed_repair,
        "modified_files": modified_files,
        "name_changes": name_change_counts,
        "role_splits": role_split_counts,
        "unresolved": unresolved_counts,
        "changed_rows": changed_rows,
        "dry_run": dry_run,
        "db_updated_count": db_updated_count if not dry_run else total_db_diff,
        "db_diff_fields": db_diff_fields,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Paranda saadikute rollid, speaker_uuid ja speaker_faction."
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
        help="Rakenda parandused JSONL failidesse (loob .bak varukoopiad)",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        default=False,
        help="Laadi muudetud failid Backblaze B2-sse tagasi eTag kontrolliga",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="SQLite andmebaasi failitee (uuendab tabelit speeches)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=OUTPUT_DIR_PROCESSED,
        help="Töödeldud andmete kaust (vaikimisi data/processed)",
    )

    args = parser.parse_args()
    is_dry_run = not args.apply or args.dry_run

    repair_speaker_uuids(
        data_dir=args.data_dir,
        dry_run=is_dry_run,
        db_path=args.db,
        upload=args.upload,
    )


if __name__ == "__main__":
    main()
