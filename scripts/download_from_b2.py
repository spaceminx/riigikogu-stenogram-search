import os
from datetime import datetime
from pathlib import Path

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
    """Download current year data, attendance, and sync state files from Backblaze B2."""
    key_id = os.environ.get("B2_KEY_ID")
    app_key = os.environ.get("B2_APP_KEY")

    if not key_id or not app_key:
        print("ERROR: B2_KEY_ID or B2_APP_KEY not found in environment or .env.")
        return False

    endpoint = "https://s3.eu-central-003.backblazeb2.com"
    bucket_name = "riigikogu-stenograms"

    Path("data/processed").mkdir(parents=True, exist_ok=True)

    print("Connecting to Backblaze B2...")

    try:
        import boto3

        s3 = boto3.client(
            "s3", endpoint_url=endpoint, aws_access_key_id=key_id, aws_secret_access_key=app_key
        )
    except Exception as e:
        print(f"Error initializing B2 client: {e}")
        return False

    # 1. Download current year processed file
    current_year = datetime.today().strftime("%Y")
    year_file = f"{current_year}.jsonl"
    local_year_path = os.path.join("data", "processed", year_file)
    try:
        print(f"Downloading {year_file} from {bucket_name}...")
        s3.download_file(bucket_name, year_file, local_year_path)
        print(f"Downloaded: {local_year_path}")
    except Exception as e:
        print(f"Notice: Could not download {year_file} from B2 (might be new year): {e}")

    # 2. Download attendance.jsonl if present in B2
    attendance_file = "attendance.jsonl"
    local_attendance_path = os.path.join("data", "processed", attendance_file)
    try:
        print(f"Downloading {attendance_file} from {bucket_name}...")
        s3.download_file(bucket_name, attendance_file, local_attendance_path)
        print(f"Downloaded: {local_attendance_path}")
    except Exception as e:
        print(f"Notice: Could not download {attendance_file} from B2: {e}")

    # 3. Download factions_map.json if present in B2
    factions_file = "factions_map.json"
    local_factions_path = os.path.join("data", "processed", factions_file)
    try:
        print(f"Downloading {factions_file} from {bucket_name}...")
        s3.download_file(bucket_name, factions_file, local_factions_path)
        print(f"Downloaded: {local_factions_path}")
    except Exception as e:
        print(f"Notice: Could not download {factions_file} from B2: {e}")

    print("Daily data download step completed.")
    return True


if __name__ == "__main__":
    download_from_b2()
