import os
import boto3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


def download_current_year_from_b2():
    key_id = os.environ.get('B2_KEY_ID')
    app_key = os.environ.get('B2_APP_KEY')

    if not key_id or not app_key:
        print("ERROR: did not find keys")
        return

    endpoint = 'https://s3.eu-central-003.backblazeb2.com'
    bucket_name = 'riigikogu-stenograms'

    # Find current year
    current_year = datetime.today().strftime('%Y')
    file_name = f"{current_year}.jsonl"

    # Create folder if not exists
    os.makedirs("data/processed", exist_ok=True)
    local_file_path = f"data/processed/{file_name}"

    print(f"Connecting to Backblaze, to download {file_name}...")

    s3 = boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=app_key
    )

    try:
        # Download only current year file
        s3.download_file(bucket_name, file_name, local_file_path)
        print(f"✅ Old file successfully downloaded: {local_file_path}")
    except Exception as e:
        print(f"File not found (normal in beginning of new year): {e}")


if __name__ == "__main__":
    download_current_year_from_b2()