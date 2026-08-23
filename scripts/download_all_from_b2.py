import os
import sys
from datetime import datetime
import requests
from tqdm import tqdm

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def download_file_http(url: str, dest_path: str):
    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()
    total_size = int(response.headers.get('content-length', 0))
    file_name = os.path.basename(dest_path)

    with open(dest_path, 'wb') as f, tqdm(
        desc=file_name,
        total=total_size,
        unit='iB',
        unit_scale=True,
        unit_divisor=1024,
    ) as pbar:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
                pbar.update(len(chunk))

def download_all_from_b2():
    key_id = os.environ.get('B2_KEY_ID')
    app_key = os.environ.get('B2_APP_KEY')
    os.makedirs("data/processed", exist_ok=True)

    endpoint = 'https://s3.eu-central-003.backblazeb2.com'
    bucket_name = 'riigikogu-stenograms'

    if key_id and app_key:
        import boto3
        print("Connecting to Backblaze B2 via S3 API...")
        s3 = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=key_id,
            aws_secret_access_key=app_key
        )
        try:
            response = s3.list_objects_v2(Bucket=bucket_name)
            if 'Contents' not in response:
                print("Bucket is empty!")
                return

            for obj in response['Contents']:
                file_name = obj['Key']
                if file_name.endswith('.jsonl'):
                    local_file_path = os.path.join("data", "processed", file_name)
                    print(f"Downloading {file_name}...")
                    s3.download_file(bucket_name, file_name, local_file_path)
                    print(f"-> Downloaded: {local_file_path}")
            return
        except Exception as e:
            print(f"B2 S3 listing failed: {e}. Falling back to direct HTTP download...")

    # Fallback to direct HTTP download for 2019..current_year
    current_year = datetime.now().year
    print(f"Downloading yearly stenogram archives (2019-{current_year}) via public endpoint...")

    for year in range(2019, current_year + 1):
        file_name = f"{year}.jsonl"
        url = f"{endpoint}/{bucket_name}/{file_name}"
        local_file_path = os.path.join("data", "processed", file_name)
        try:
            print(f"Fetching {file_name} from {url}...")
            download_file_http(url, local_file_path)
            print(f"-> Saved {local_file_path}")
        except Exception as e:
            print(f"Could not download {file_name}: {e}")

    print("All downloads finished.")

if __name__ == "__main__":
    download_all_from_b2()

