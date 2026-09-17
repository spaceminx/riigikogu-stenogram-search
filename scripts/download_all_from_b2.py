import os

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


def download_all_from_b2():
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
    os.makedirs("data/processed", exist_ok=True)

    print("Connecting to Backblaze B2 (private bucket) via S3 API...")

    try:
        import boto3

        s3 = boto3.client(
            "s3", endpoint_url=endpoint, aws_access_key_id=key_id, aws_secret_access_key=app_key
        )

        response = s3.list_objects_v2(Bucket=bucket_name)
        if "Contents" not in response:
            print("Bucket is empty!")
            return False

        for obj in response["Contents"]:
            file_name = obj["Key"]
            if file_name.endswith(".jsonl"):
                local_file_path = os.path.join("data", "processed", file_name)
                print(f"Downloading {file_name} from {bucket_name}...")
                s3.download_file(bucket_name, file_name, local_file_path)
                print(f"-> Downloaded: {local_file_path}")

        print("All files successfully downloaded from Backblaze B2.")
        return True

    except Exception as e:
        print(f"Error downloading files from Backblaze B2: {e}")
        return False


if __name__ == "__main__":
    download_all_from_b2()
