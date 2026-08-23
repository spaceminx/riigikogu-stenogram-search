import os
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip() and not line.startswith("#") and "=" in line:
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def download_current_year_from_b2() -> bool:
    key_id = os.environ.get('B2_KEY_ID')
    app_key = os.environ.get('B2_APP_KEY')

    if not key_id or not app_key:
        print("ERROR: B2_KEY_ID or B2_APP_KEY not found in environment or .env.")
        return False

    endpoint = 'https://s3.eu-central-003.backblazeb2.com'
    bucket_name = 'riigikogu-stenograms'

    current_year = datetime.today().strftime('%Y')
    file_name = f"{current_year}.jsonl"

    os.makedirs("data/processed", exist_ok=True)
    local_file_path = os.path.join("data", "processed", file_name)

    print(f"Connecting to Backblaze B2 to download {file_name}...")

    try:
        import boto3
        s3 = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=key_id,
            aws_secret_access_key=app_key
        )
        s3.download_file(bucket_name, file_name, local_file_path)
        print(f"Successfully downloaded {file_name} -> {local_file_path}")
        return True
    except Exception as e:
        print(f"File not found or error downloading {file_name} from B2: {e}")
        return False


if __name__ == "__main__":
    download_current_year_from_b2()
