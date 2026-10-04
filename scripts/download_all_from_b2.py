import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # Basic fallback to read .env if python-dotenv is not installed
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.strip() and not line.startswith("#") and "=" in line:
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def download_all_from_b2() -> bool:
    key_id = os.environ.get("B2_KEY_ID")
    app_key = os.environ.get("B2_APP_KEY")

    if not key_id or not app_key:
        print("=" * 60)
        print("ERROR: Backblaze B2 credentials (B2_KEY_ID, B2_APP_KEY) not found.")
        print("Since the B2 bucket is private, please add your keys to .env:")
        print("  B2_KEY_ID=your_key_id")
        print("  B2_APP_KEY=your_app_key")
        print("Or fetch directly from the free public API:")
        print("  python scripts/fetch_stenograms_api.py")
        print("=" * 60)
        return False

    endpoint = "https://s3.eu-central-003.backblazeb2.com"
    bucket_name = "riigikogu-stenograms"

    Path("data/processed").mkdir(parents=True, exist_ok=True)
    Path("data/sync").mkdir(parents=True, exist_ok=True)

    print("Connecting to Backblaze B2 (private bucket) via S3 API...")

    try:
        import boto3

        s3 = boto3.client(
            "s3", endpoint_url=endpoint, aws_access_key_id=key_id, aws_secret_access_key=app_key
        )

        paginator = s3.get_paginator("list_objects_v2")
        downloaded_count = 0

        for page in paginator.paginate(Bucket=bucket_name):
            if "Contents" not in page:
                continue

            for obj in page["Contents"]:
                key = obj["Key"]
                filename = os.path.basename(key)
                if not filename:
                    continue

                if key.startswith("sync/") or key.endswith(".json"):
                    local_path = os.path.join("data", "sync", filename)
                elif key.endswith(".jsonl"):
                    local_path = os.path.join("data", "processed", filename)
                else:
                    continue

                print(f"Downloading {key} -> {local_path}...")
                s3.download_file(bucket_name, key, local_path)
                print(f"-> Downloaded: {local_path}")
                downloaded_count += 1

        if downloaded_count == 0:
            print("Notice: No matching files found in B2 bucket.")
            return False

        print(f"All {downloaded_count} files successfully downloaded from Backblaze B2.")
        return True

    except Exception as e:
        print(f"Error downloading files from Backblaze B2: {e}")
        return False


if __name__ == "__main__":
    download_all_from_b2()
