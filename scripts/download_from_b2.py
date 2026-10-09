import argparse
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
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


def is_active_daily_file(filename: str, active_years: set[str]) -> bool:
    """Return True if the file is part of daily active sync (metadata, attendance, current year)."""
    if filename.endswith(".json"):
        return True
    if filename == "attendance.jsonl":
        return True
    for y in active_years:
        if filename == f"{y}.jsonl":
            return True
    return False


def download_from_b2(
    active_year: str | None = None,
    include_all_history: bool = False,
) -> bool:
    """Download daily active datasets (active year window, attendance, metadata) from Backblaze B2.

    By default, only active/frequently updated files are downloaded:
    - Active year transcripts (current year and recent unedited window from previous year)
    - Attendance records (attendance.jsonl)
    - Metadata and sync state files (*.json)

    Historical years outside the active window are static and not re-downloaded
    daily to stay safely within Backblaze B2's daily free bandwidth tier (1 GB/day).
    Pass include_all_history=True (or CLI flag --all) to download all historical files.
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

    downloaded_count = 0
    skipped_count = 0
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

                # Filter active vs historical files
                if not include_all_history and not is_active_daily_file(filename, active_years):
                    skipped_count += 1
                    continue

                local_path = os.path.join(OUTPUT_DIR_PROCESSED, filename)
                remote_size = obj.get("Size")

                # If historical file already exists locally with matching size, skip re-download
                if (
                    include_all_history
                    and not is_active_daily_file(filename, active_years)
                    and os.path.exists(local_path)
                    and remote_size is not None
                    and os.path.getsize(local_path) == remote_size
                ):
                    skipped_count += 1
                    continue

                print(f"Downloading {key} from {bucket_name} -> {local_path}...")
                s3.download_file(bucket_name, key, local_path)
                print(f"Downloaded: {local_path}")
                downloaded_count += 1
    except Exception as e:
        print(f"Error listing/downloading files from B2: {e}")
        return False

    mode_label = (
        "all historical files"
        if include_all_history
        else f"active files ({', '.join(sorted(active_years))})"
    )
    print(
        f"Daily data download step completed ({mode_label}): {downloaded_count} downloaded, {skipped_count} skipped."
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
    args = parser.parse_args()

    success = download_from_b2(active_year=args.year, include_all_history=args.include_all)
    sys.exit(0 if success else 1)
