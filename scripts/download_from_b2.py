import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from config import B2_BUCKET_NAME, B2_ENDPOINT_URL, OUTPUT_DIR_PROCESSED
from scripts.b2_utils import get_file_md5, matches_multipart_etag

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


def is_active_daily_file(filename: str, active_years: set[str]) -> bool:
    """Return True if the file is part of daily active sync (metadata, attendance, current year)."""
    if filename.endswith(".json"):
        return True
    if filename == "attendance.jsonl":
        return True
    for y in active_years:
        if filename == f"{y}.jsonl" or filename == f"votes_{y}.jsonl":
            return True
    return False


def download_from_b2(
    active_year: str | None = None,
    include_all_history: bool = False,
    dry_run: bool = False,
) -> bool:
    """Download daily active datasets (active year window, attendance, metadata) from Backblaze B2.

    By default, only active/frequently updated files are downloaded:
    - Active year transcripts (current year and recent unedited window from previous year)
    - Attendance records (attendance.jsonl)
    - Metadata and sync state files (*.json)

    Files with identical MD5 are skipped (both active and historical).
    Pass include_all_history=True (or CLI flag --all) to check all historical files.
    Pass dry_run=True (or CLI flag --dry-run) to inspect without downloading.
    """
    key_id = os.environ.get("B2_KEY_ID")
    app_key = os.environ.get("B2_APP_KEY")

    if not key_id or not app_key:
        print("ERROR: B2_KEY_ID or B2_APP_KEY not found in environment or .env.")
        return False

    endpoint = B2_ENDPOINT_URL
    bucket_name = B2_BUCKET_NAME

    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)

    active_years = {str(active_year)} if active_year is not None else set(config.active_years())

    print("Connecting to Backblaze B2...")

    try:
        import boto3

        s3 = boto3.client(
            "s3", endpoint_url=endpoint, aws_access_key_id=key_id, aws_secret_access_key=app_key
        )
    except Exception as e:
        print(f"Error initializing B2 client: {e}")
        return False

    # ETags from the last successful download/upload, to detect local changes not yet uploaded
    last_synced_etags: dict[str, str] = {}
    etags_path = os.path.join(OUTPUT_DIR_PROCESSED, ".b2_etags.json")
    if os.path.exists(etags_path):
        try:
            with open(etags_path, encoding="utf-8") as f:
                last_synced_etags = json.load(f)
        except Exception:
            last_synced_etags = {}

    downloaded_count = 0
    downloaded_bytes = 0
    skipped_count = 0
    saved_etags: dict[str, str] = {}
    try:
        # List and download matching dataset files in the bucket
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket_name):
            for obj in page.get("Contents", []):
                key = obj.get("Key")
                if not key or not (key.endswith(".jsonl") or key.endswith(".json")):
                    continue

                filename = os.path.basename(key)
                if not filename:
                    continue

                etag = obj.get("ETag")
                cleaned_etag = etag.strip('"') if etag else ""
                remote_size = obj.get("Size") or 0

                is_active = is_active_daily_file(filename, active_years)

                # Filter active vs historical files
                if not include_all_history and not is_active:
                    skipped_count += 1
                    continue

                local_path = os.path.join(OUTPUT_DIR_PROCESSED, filename)
                local_exists = os.path.exists(local_path)

                should_download = True
                skip_reason = ""
                download_reason = "new file" if not local_exists else "updated"

                if local_exists:
                    try:
                        local_md5 = get_file_md5(local_path)
                    except Exception:
                        local_md5 = None

                    if local_md5:
                        b2_md5 = None
                        if cleaned_etag and "-" not in cleaned_etag:
                            b2_md5 = cleaned_etag
                        else:
                            try:
                                head_resp = s3.head_object(Bucket=bucket_name, Key=key)
                                meta = head_resp.get("Metadata") or {}
                                b2_md5 = meta.get("md5") or meta.get("MD5")
                            except Exception:
                                b2_md5 = None

                        if b2_md5 is not None:
                            if b2_md5.lower() == local_md5.lower():
                                should_download = False
                                skip_reason = f"MD5 matches ({b2_md5})"
                                if cleaned_etag:
                                    saved_etags[filename] = cleaned_etag
                            else:
                                should_download = True
                                download_reason = f"MD5 mismatch (local={local_md5}, B2={b2_md5})"
                        elif (
                            cleaned_etag
                            and "-" in cleaned_etag
                            and matches_multipart_etag(local_path, cleaned_etag)
                        ):
                            should_download = False
                            skip_reason = f"multipart ETag matches ({cleaned_etag})"
                            saved_etags[filename] = cleaned_etag
                        else:
                            print(f"Hoiatus: md5 metaandmed puuduvad: {filename}")
                            if not is_active and remote_size == os.path.getsize(local_path):
                                should_download = False
                                skip_reason = f"size matches ({remote_size} bytes, no MD5 metadata)"
                                if cleaned_etag and "-" not in cleaned_etag:
                                    saved_etags[filename] = cleaned_etag
                            else:
                                should_download = True
                                download_reason = (
                                    "active file without MD5 metadata"
                                    if is_active
                                    else f"size mismatch without MD5 metadata (local={os.path.getsize(local_path)}, B2={remote_size})"
                                )

                    # B2 is unchanged since the last sync but the local file differs: these are local
                    # changes a failed upload did not send. Keep them for the upload step instead of
                    # replacing them with the older B2 copy.
                    last_etag = str(last_synced_etags.get(filename) or "").strip('"')
                    if should_download and last_etag and cleaned_etag == last_etag:
                        should_download = False
                        skip_reason = (
                            "local changes not yet uploaded (B2 unchanged since last sync)"
                        )
                        print(f"Keeping local {filename}: {skip_reason}")

                if not should_download:
                    skipped_count += 1
                    if dry_run:
                        print(f"[DRY-RUN] Skip {filename}: {skip_reason}")
                    continue

                if dry_run:
                    print(f"[DRY-RUN] Download {filename}: {download_reason} ({remote_size} bytes)")
                    downloaded_count += 1
                    downloaded_bytes += remote_size
                    continue

                # Atomic download to temporary file, then atomic rename
                tmp_path = os.path.join(OUTPUT_DIR_PROCESSED, f"{filename}.tmp.{os.getpid()}")
                try:
                    print(
                        f"Downloading {key} from {bucket_name} -> {local_path} ({remote_size} bytes)..."
                    )
                    s3.download_file(bucket_name, key, tmp_path)
                    if os.path.exists(tmp_path):
                        os.replace(tmp_path, local_path)
                    print(f"Downloaded: {local_path}")
                    downloaded_count += 1
                    downloaded_bytes += remote_size
                    if cleaned_etag:
                        saved_etags[filename] = cleaned_etag
                except Exception as e:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass
                    print(f"Error downloading {key}: {e}")
                    raise

        if saved_etags and not dry_run:
            etags_file = os.path.join(OUTPUT_DIR_PROCESSED, ".b2_etags.json")
            existing_etags = {}
            if os.path.exists(etags_file):
                try:
                    with open(etags_file, encoding="utf-8") as f:
                        existing_etags = json.load(f)
                except Exception:
                    pass
            existing_etags.update(saved_etags)
            try:
                tmp_etags_file = etags_file + ".tmp"
                with open(tmp_etags_file, "w", encoding="utf-8") as f:
                    json.dump(existing_etags, f, indent=2)
                os.replace(tmp_etags_file, etags_file)
            except Exception:
                pass
    except Exception as e:
        print(f"Error listing/downloading files from B2: {e}")
        return False

    mode_label = (
        "all historical files"
        if include_all_history
        else f"active files ({', '.join(sorted(active_years))})"
    )
    if dry_run:
        print(
            f"Dry-run data download step completed ({mode_label}): "
            f"{downloaded_count} would be downloaded ({downloaded_bytes} bytes), "
            f"{skipped_count} skipped."
        )
    else:
        print(
            f"Daily data download step completed ({mode_label}): "
            f"{downloaded_count} downloaded ({downloaded_bytes} bytes), "
            f"{skipped_count} skipped."
        )
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download dataset files from Backblaze B2.")
    parser.add_argument(
        "--all",
        action="store_true",
        dest="include_all",
        help="Download all historical datasets (default is active year and metadata only).",
    )
    parser.add_argument(
        "--year",
        type=str,
        default=None,
        help="Specific active year to download (default: current year).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Perform dry-run inspection without downloading files.",
    )
    args = parser.parse_args()

    success = download_from_b2(
        active_year=args.year,
        include_all_history=args.include_all,
        dry_run=args.dry_run,
    )
    sys.exit(0 if success else 1)
