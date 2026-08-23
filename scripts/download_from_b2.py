import os
from datetime import datetime
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass



def download_current_year_from_b2() -> bool:
    key_id = os.environ.get('B2_KEY_ID')
    app_key = os.environ.get('B2_APP_KEY')

    endpoint = 'https://s3.eu-central-003.backblazeb2.com'
    bucket_name = 'riigikogu-stenograms'

    current_year = datetime.today().strftime('%Y')
    file_name = f"{current_year}.jsonl"

    os.makedirs("data/processed", exist_ok=True)
    local_file_path = os.path.join("data", "processed", file_name)

    if key_id and app_key:
        try:
            import boto3
            s3 = boto3.client(
                's3',
                endpoint_url=endpoint,
                aws_access_key_id=key_id,
                aws_secret_access_key=app_key
            )
            s3.download_file(bucket_name, file_name, local_file_path)
            print(f"Downloaded via S3: {local_file_path}")
            return True
        except Exception as e:
            print(f"S3 download failed: {e}. Trying direct HTTP...")

    # Fallback to direct HTTP download
    url = f"{endpoint}/{bucket_name}/{file_name}"
    print(f"Connecting to Backblaze to download {file_name} from {url}...")
    try:
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        with open(local_file_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
        print(f"Successfully downloaded {file_name} -> {local_file_path}")
        return True
    except Exception as e:
        print(f"File not found or error downloading {file_name}: {e}")
        return False


if __name__ == "__main__":
    download_current_year_from_b2()