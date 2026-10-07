import glob
import os
import sys

import boto3

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import OUTPUT_DIR_PROCESSED

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def upload_to_b2() -> bool:
    """Upload processed datasets (.jsonl) and sync state files (.json) to Backblaze B2."""
    key_id = os.environ.get("B2_KEY_ID")
    app_key = os.environ.get("B2_APP_KEY")

    if not key_id or not app_key:
        print("ERROR: Backblaze B2 credentials (B2_KEY_ID, B2_APP_KEY) not found in environment.")
        return False

    endpoint = "https://s3.eu-central-003.backblazeb2.com"
    bucket_name = "riigikogu-stenograms"

    print("Connecting to Backblaze B2...")

    try:
        s3 = boto3.client(
            "s3", endpoint_url=endpoint, aws_access_key_id=key_id, aws_secret_access_key=app_key
        )
    except Exception as e:
        print(f"Error initializing B2 client: {e}")
        return False

    # Collect files to upload from OUTPUT_DIR_PROCESSED (.jsonl and .json files)
    files_to_upload = []
    for file_path in glob.glob(os.path.join(OUTPUT_DIR_PROCESSED, "*.*")):
        if file_path.endswith(".jsonl") or file_path.endswith(".json"):
            files_to_upload.append((file_path, os.path.basename(file_path)))

    if not files_to_upload:
        print(f"No .jsonl or .json files found in {OUTPUT_DIR_PROCESSED} folder.")
        return True

    uploaded_count = 0
    failed_count = 0

    for local_path, remote_key in files_to_upload:
        print(f"Uploading file to cloud: {local_path} -> {bucket_name}/{remote_key} ...")

        try:
            s3.upload_file(local_path, bucket_name, remote_key)
            uploaded_count += 1
        except Exception as e:
            print(f"Error uploading {local_path} to B2: {e}")
            failed_count += 1

    if failed_count == 0:
        print(f"All {uploaded_count} files successfully uploaded to {bucket_name}.")
        return True

    print(f"Upload finished with errors: {uploaded_count} uploaded, {failed_count} failed.")
    return False


if __name__ == "__main__":
    success = upload_to_b2()
    sys.exit(0 if success else 1)
