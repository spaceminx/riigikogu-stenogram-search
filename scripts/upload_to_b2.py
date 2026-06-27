import os
import glob
import boto3
from dotenv import load_dotenv

load_dotenv()


def upload_to_b2():
    # Read app_key info from env
    key_id = os.environ.get('B2_KEY_ID')
    app_key = os.environ.get('B2_APP_KEY')

    if not key_id or not app_key:
        print("ERROR: Backblaze key not found in environment variables.")
        return


    endpoint = 'https://s3.eu-central-003.backblazeb2.com'
    bucket_name = 'riigikogu-stenograms'


    print("Connecting to Backblaze B2...")

    # S3 client
    s3 = boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=app_key
    )

    # Finding all .jsonl fails
    files_to_upload = glob.glob("data/processed/*.jsonl")

    if not files_to_upload:
        print("No jsonl found in data/processed/ folder")
        return

    for file_path in files_to_upload:
        file_name = os.path.basename(file_path)
        print(f"Uploading file to cloud: {file_name} -> {bucket_name} ...")

        # Uploading
        s3.upload_file(file_path, bucket_name, file_name)

    print("✅ All files successfully uploaded to cloud!")


if __name__ == "__main__":
    upload_to_b2()