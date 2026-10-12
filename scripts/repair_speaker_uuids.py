import argparse
import glob
import json
import os
import shutil
import sqlite3
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import OUTPUT_DIR_PROCESSED
from scripts.fetch_stenograms_api import (
    get_faction_for_date,
    load_persons_metadata,
    resolve_speaker_uuid,
)


def repair_speaker_uuids(
    data_dir: str = OUTPUT_DIR_PROCESSED,
    dry_run: bool = True,
    db_path: str | None = None,
    upload: bool = False,
) -> dict:
    """Repair speaker UUIDs and factions for MP name changes across processed datasets."""
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
        if os.path.basename(f) != "attendance.jsonl"
        and not f.endswith(".bak")
        and not f.endswith(".tmp")
    ]

    total_checked = 0
    needed_repair = 0
    name_change_counts: dict[str, int] = {}
    unresolved_counts: dict[str, int] = {}
    modified_files: list[str] = []
    db_updates_by_ext_id: list[tuple[str | None, str | None, int]] = []
    db_updates_by_key: list[tuple[str | None, str | None, str]] = []

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

                if role is None and (uuid_val is None or faction_val is None):
                    speaker = row.get("speaker") or ""
                    ems_id = row.get("ems_id")
                    date_str = row.get("date") or ""

                    resolved_uuid, method = resolve_speaker_uuid(
                        speaker_name=speaker,
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
                        else speaker
                    )
                    new_faction = get_faction_for_date(faction_map, canon_name, date_str)

                    if effective_uuid != uuid_val or new_faction != faction_val:
                        needed_repair += 1
                        file_modified = True
                        row["speaker_uuid"] = effective_uuid
                        row["speaker_faction"] = new_faction

                        ext_id = row.get("external_id")
                        sp_key = row.get("speech_key")
                        if ext_id is not None:
                            db_updates_by_ext_id.append((effective_uuid, new_faction, int(ext_id)))
                        elif sp_key:
                            db_updates_by_key.append((effective_uuid, new_faction, str(sp_key)))

                        if method == "ems_name_change":
                            pair = f"{speaker} -> {canon_name}"
                            name_change_counts[pair] = name_change_counts.get(pair, 0) + 1

                    if effective_uuid is None:
                        unresolved_counts[speaker] = unresolved_counts.get(speaker, 0) + 1

                new_lines.append(json.dumps(row, ensure_ascii=False) + "\n")

        if file_modified:
            modified_files.append(file_path)
            if not dry_run:
                bak_path = file_path + ".bak"
                shutil.copy2(file_path, bak_path)
                tmp_path = file_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as out_f:
                    out_f.writelines(new_lines)
                os.replace(tmp_path, file_path)

    # Database updates
    db_updated_count = 0
    if not dry_run and db_path and (db_updates_by_ext_id or db_updates_by_key):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        batch_size = 500

        for i in range(0, len(db_updates_by_ext_id), batch_size):
            batch = db_updates_by_ext_id[i : i + batch_size]
            cursor.executemany(
                "UPDATE speeches SET speaker_uuid = ?, speaker_faction = ? WHERE external_id = ?",
                batch,
            )
            db_updated_count += len(batch)

        for i in range(0, len(db_updates_by_key), batch_size):
            batch = db_updates_by_key[i : i + batch_size]
            cursor.executemany(
                "UPDATE speeches SET speaker_uuid = ?, speaker_faction = ? WHERE speech_key = ?",
                batch,
            )
            db_updated_count += len(batch)

        conn.commit()
        conn.close()

    # B2 Upload
    if not dry_run and upload and modified_files:
        from scripts.upload_to_b2 import upload_to_b2

        upload_to_b2(only_files=modified_files)

    # Print Report
    print("=" * 60)
    print("KÕNELEJATE UUID JA FRAKTSIOONIDE PARANDAMISE RAPORT")
    print("=" * 60)
    mode_str = "KUIVKÄIVITUS (--dry-run, faile ei muudetud)" if dry_run else "RAKENDATUD (--apply)"
    print(f"Režiim: {mode_str}")
    print(f"Kontrollitud ridu kokku: {total_checked}")
    print(f"Parandamist vajavaid ridu: {needed_repair}")
    print(
        f"Muudatustega failid ({len(modified_files)}): {[os.path.basename(f) for f in modified_files]}"
    )

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
            elif "Peaministrikandidaat" in spkr:
                reason = "Peaministrikandidaadi tiitel nimes, puudub roll või emsId"
            elif spkr == "Luisa Rõivas":
                reason = "Jõuluistungi kõned, kus emsId oli algses API-s null"
            elif "koor" in spkr.lower():
                reason = "Muusikaline etteaste"
            print(f"  - {spkr}: {cnt} kõnet ({reason})")
    else:
        print("  (kõik lahendatud)")

    if not dry_run and db_path:
        print(f"\nSQLite andmebaasis uuendatud ridu: {db_updated_count}")

    print("=" * 60)

    return {
        "total_checked": total_checked,
        "needed_repair": needed_repair,
        "modified_files": modified_files,
        "name_changes": name_change_counts,
        "unresolved": unresolved_counts,
        "dry_run": dry_run,
        "db_updated_count": db_updated_count,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Paranda saadikute nimevahetustega seotud speaker_uuid ja speaker_faction."
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
