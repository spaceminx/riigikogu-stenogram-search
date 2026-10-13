import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import B2_BUCKET_NAME, B2_ENDPOINT_URL, OUTPUT_DIR_PROCESSED

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.strip() and not line.startswith("#") and "=" in line:
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def get_file_md5(file_path: str) -> str:
    """Compute hex MD5 digest of a local file."""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def backfill_b2_md5_metadata(
    dry_run: bool = True,
    trust_local: bool = False,
    only_files: list[str] | None = None,
) -> bool:
    """Backfill md5 metadata on existing Backblaze B2 objects using server-side copy_object.

    Defaults to dry_run=True. Pass dry_run=False (via --apply) to perform server-side updates.
    Local MD5 is only trusted if single-part ETag matches local MD5 or trust_local=True.
    Updates .b2_etags.json after each copy_object to keep ETags in sync.
    """
    key_id = os.environ.get("B2_KEY_ID")
    app_key = os.environ.get("B2_APP_KEY")

    if not key_id or not app_key:
        print("ERROR: B2_KEY_ID or B2_APP_KEY not found in environment or .env.")
        return False

    endpoint = B2_ENDPOINT_URL
    bucket_name = B2_BUCKET_NAME

    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)

    print("Connecting to Backblaze B2...")
    try:
        import boto3

        s3 = boto3.client(
            "s3", endpoint_url=endpoint, aws_access_key_id=key_id, aws_secret_access_key=app_key
        )
    except Exception as e:
        print(f"Error initializing B2 client: {e}")
        return False

    only_basenames = {os.path.basename(f) for f in only_files} if only_files else None

    updated_count = 0
    would_update_count = 0
    already_has_md5_count = 0
    skipped_missing_local_count = 0
    skipped_untrusted_count = 0

    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket_name):
            for obj in page.get("Contents", []):
                key = obj.get("Key")
                if not key or not (key.endswith(".jsonl") or key.endswith(".json")):
                    continue

                filename = os.path.basename(key)
                if filename in {".b2_etags.json", "backfill_state.json"} or filename.startswith(
                    "backfill_"
                ):
                    continue

                if only_basenames is not None and filename not in only_basenames:
                    continue

                head_resp = s3.head_object(Bucket=bucket_name, Key=key)
                meta = head_resp.get("Metadata") or {}
                existing_md5 = meta.get("md5") or meta.get("MD5")

                if existing_md5:
                    already_has_md5_count += 1
                    continue

                local_path = os.path.join(OUTPUT_DIR_PROCESSED, filename)
                if not os.path.exists(local_path):
                    print(f"Skipping {key}: kohalikku faili {filename} ei leitud.")
                    skipped_missing_local_count += 1
                    continue

                try:
                    local_md5 = get_file_md5(local_path)
                except Exception as e:
                    print(f"Skipping {key}: viga kohaliku faili MD5 arvutamisel: {e}")
                    skipped_missing_local_count += 1
                    continue

                remote_etag = (head_resp.get("ETag") or obj.get("ETag") or "").strip('"')
                is_single_part_match = bool(
                    remote_etag
                    and "-" not in remote_etag
                    and remote_etag.lower() == local_md5.lower()
                )

                if not is_single_part_match and not trust_local:
                    print(
                        f"Skipping {key}: kohalik fail pole tõestatult identne B2 objektiga "
                        f"(ETag={remote_etag}, kohalik MD5={local_md5}). "
                        f"Kasuta --trust-local kui fail on värskelt alla laaditud."
                    )
                    skipped_untrusted_count += 1
                    continue

                if dry_run:
                    print(
                        f"[DRY-RUN] Uuendaks {key}: md5={local_md5} "
                        f"(B2 ETag={remote_etag}, usaldatud={'single-part' if is_single_part_match else 'trust-local'})."
                    )
                    would_update_count += 1
                    continue

                # Server-side copy_object to replace metadata
                print(f"Uuendan {key} metaandmeid: md5={local_md5} ...")
                copy_kwargs = {
                    "Bucket": bucket_name,
                    "Key": key,
                    "CopySource": {"Bucket": bucket_name, "Key": key},
                    "Metadata": {"md5": local_md5},
                    "MetadataDirective": "REPLACE",
                }
                content_type = head_resp.get("ContentType")
                if content_type:
                    copy_kwargs["ContentType"] = content_type

                resp = s3.copy_object(**copy_kwargs)

                # Extract new ETag from copy response or head_object
                new_etag = ""
                if isinstance(resp, dict):
                    if "CopyObjectResult" in resp and "ETag" in resp["CopyObjectResult"]:
                        new_etag = resp["CopyObjectResult"]["ETag"].strip('"')
                    elif "ETag" in resp:
                        new_etag = resp["ETag"].strip('"')

                if not new_etag:
                    try:
                        fresh_head = s3.head_object(Bucket=bucket_name, Key=key)
                        new_etag = fresh_head.get("ETag", "").strip('"')
                    except Exception:
                        pass

                # Atomically update .b2_etags.json with new ETag
                if new_etag:
                    etags_file = os.path.join(OUTPUT_DIR_PROCESSED, ".b2_etags.json")
                    current_etags = {}
                    if os.path.exists(etags_file):
                        try:
                            with open(etags_file, encoding="utf-8") as f:
                                current_etags = json.load(f)
                        except Exception:
                            pass
                    current_etags[key] = new_etag
                    current_etags[filename] = new_etag
                    tmp_file = f"{etags_file}.tmp"
                    with open(tmp_file, "w", encoding="utf-8") as f:
                        json.dump(current_etags, f, indent=2)
                    os.replace(tmp_file, etags_file)

                print(f"Uuendatud {key}: md5={local_md5}, uus ETag={new_etag}")
                updated_count += 1

    except Exception as e:
        print(f"Error backfilling metadata in B2: {e}")
        return False

    if dry_run:
        print(
            f"B2 MD5 metaandmete dry-run valmis: "
            f"{would_update_count} uuendataks, "
            f"{already_has_md5_count} juba olemas, "
            f"{skipped_untrusted_count} mitteusaldusväärset vahele jäetud, "
            f"{skipped_missing_local_count} puuduvat kohalikku faili."
        )
    else:
        print(
            f"B2 MD5 metaandmete lisamine valmis: "
            f"{updated_count} uuendatud, "
            f"{already_has_md5_count} juba olemas, "
            f"{skipped_untrusted_count} mitteusaldusväärset vahele jäetud, "
            f"{skipped_missing_local_count} puuduvat kohalikku faili."
        )
    return True


if __name__ == "__main__":
    print(
        "====================================================================\n"
        "HOIATUS: Ära käivita seda skripti uisapäisa!\n"
        "Serveripoolne copy_object muudab kõigi töödeldud objektide ETag-e.\n"
        "Veendu, et kohalikud failid on värsked või vastavad B2 sisule.\n"
        "Vaikimisi töötab skript turvalises --dry-run režiimis.\n"
        "Muudatuste tegemiseks kasuta --apply lippu.\n"
        "===================================================================="
    )

    parser = argparse.ArgumentParser(
        description="Ühekordne MD5 metaandmete lisamine B2 objektidele serveripoolse copy_object abil."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        dest="apply",
        help="Rakenda muudatused B2-s (vaikimisi tehakse dry-run).",
    )
    parser.add_argument(
        "--trust-local",
        action="store_true",
        dest="trust_local",
        help="Usalda kohaliku faili MD5-d ka mitmeosaliste (multipart) ETag-ide puhul.",
    )
    parser.add_argument(
        "--only-file",
        nargs="*",
        dest="only_files",
        default=None,
        help="Töötle ainult määratud faili(d) (nt 2024.jsonl).",
    )
    args = parser.parse_args()

    success = backfill_b2_md5_metadata(
        dry_run=not args.apply,
        trust_local=args.trust_local,
        only_files=args.only_files,
    )
    sys.exit(0 if success else 1)
