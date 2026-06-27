import os
import boto3
from dotenv import load_dotenv

load_dotenv()

def download_all_from_b2():
    key_id = os.environ.get('B2_KEY_ID')
    app_key = os.environ.get('B2_APP_KEY')

    if not key_id or not app_key:
        print("ERROR: did not find keys")
        return

    endpoint = 'https://s3.eu-central-003.backblazeb2.com'
    bucket_name = 'riigikogu-stenograms'

    os.makedirs("data/processed", exist_ok=True)

    print("Connecting to Backblaze to fetch all files...")

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
                local_file_path = f"data/processed/{file_name}"
                print(f"Downloading {file_name}...")
                s3.download_file(bucket_name, file_name, local_file_path)
                print(f"✅ Downloaded: {local_file_path}")
                
    except Exception as e:
        print(f"Error listing or downloading files: {e}")

if __name__ == "__main__":
    download_all_from_b2()
