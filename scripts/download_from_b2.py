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


def download_from_b2() -> bool:
    """Download all processed datasets, attendance, and faction maps from Backblaze B2."""
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

    downloaded_count = 0
    try:
        # List and download all available dataset files in the bucket
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket_name):
            for obj in page.get("Contents", []):
                key = obj.get("Key")
                if not key or not (key.endswith(".jsonl") or key.endswith(".json")):
                    continue
                local_path = os.path.join(OUTPUT_DIR_PROCESSED, key)
                print(f"Downloading {key} from {bucket_name}...")
                s3.download_file(bucket_name, key, local_path)
                print(f"Downloaded: {local_path}")
                downloaded_count += 1
    except Exception as e:
        print(f"Error listing/downloading files from B2: {e}")
        return False

    print(f"Daily data download step completed. ({downloaded_count} files downloaded)")
    return True


if __name__ == "__main__":
    success = download_from_b2()
    sys.exit(0 if success else 1)
