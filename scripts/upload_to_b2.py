import glob
import json
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import B2_BUCKET_NAME, B2_ENDPOINT_URL, OUTPUT_DIR_PROCESSED
from scripts.b2_utils import b2_transfer_config, get_file_md5, make_b2_client

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def upload_to_b2(
    only_files: list[str] | None = None,
    expected_etags: dict[str, str] | None = None,
) -> bool:
    """Upload processed datasets (.jsonl) and sync state files (.json) to Backblaze B2."""
    key_id = os.environ.get("B2_KEY_ID")
    app_key = os.environ.get("B2_APP_KEY")

    if not key_id or not app_key:
        print("ERROR: Backblaze B2 credentials (B2_KEY_ID, B2_APP_KEY) not found in environment.")
        return False

    endpoint = B2_ENDPOINT_URL
    bucket_name = B2_BUCKET_NAME

    print("Connecting to Backblaze B2...")

    try:
        s3 = make_b2_client(endpoint, key_id, app_key)
    except Exception as e:
        print(f"Error initializing B2 client: {e}")
        return False

    # Load stored ETags if not explicitly provided
    if expected_etags is None:
        etags_file = os.path.join(OUTPUT_DIR_PROCESSED, ".b2_etags.json")
        if os.path.exists(etags_file):
            try:
                with open(etags_file, encoding="utf-8") as f:
                    expected_etags = json.load(f)
            except Exception:
                expected_etags = None

    # Load blocked files from integrity_report.json if present
    blocked_files = set()
    report_path = os.path.join(OUTPUT_DIR_PROCESSED, "integrity_report.json")
    if os.path.exists(report_path):
        try:
            with open(report_path, encoding="utf-8") as f:
                report_data = json.load(f)
            blocked_files = set(report_data.get("blocked_files", []))
            if blocked_files:
                print(
                    f"Notice: integrity_report.json specifies blocked files: {sorted(blocked_files)}"
                )
        except Exception as e:
            print(f"Notice: Could not read integrity report {report_path}: {e}")

    # Collect files to upload from OUTPUT_DIR_PROCESSED (.jsonl and .json files)
    files_to_upload = []
    only_basenames = {os.path.basename(f) for f in only_files} if only_files is not None else None
    seen_basenames = set()

    for file_path in glob.glob(os.path.join(OUTPUT_DIR_PROCESSED, "*.*")):
        base_name = os.path.basename(file_path)
        if base_name in {
            "backfill_state.json",
            ".b2_etags.json",
            "integrity_report.json",
        } or base_name.startswith("backfill_"):
            continue
        if only_basenames is not None and base_name not in only_basenames:
            continue
        if file_path.endswith(".jsonl") or file_path.endswith(".json"):
            files_to_upload.append((file_path, base_name))
            seen_basenames.add(base_name)

    if only_files is not None:
        for f in only_files:
            base_name = os.path.basename(f)
            if base_name not in seen_basenames and os.path.exists(f):
                if base_name in {
                    "backfill_state.json",
                    ".b2_etags.json",
                    "integrity_report.json",
                } or base_name.startswith("backfill_"):
                    continue
                if f.endswith(".jsonl") or f.endswith(".json"):
                    files_to_upload.append((f, base_name))
                    seen_basenames.add(base_name)

    if not files_to_upload:
        print(f"No .jsonl or .json files found in {OUTPUT_DIR_PROCESSED} folder.")
        return True

    uploaded_count = 0
    skipped_count = 0
    failed_count = 0

    for local_path, remote_key in files_to_upload:
        if remote_key in blocked_files:
            print(
                f"Skipping {remote_key}: blocked by integrity_report.json due to truncated session."
            )
            skipped_count += 1
            continue

        try:
            local_size = os.path.getsize(local_path)
            if local_size == 0:
                print(f"Error: Refusing to upload 0-byte file {local_path} to B2.")
                failed_count += 1
                continue

            local_md5 = get_file_md5(local_path)

            head = None
            try:
                head = s3.head_object(Bucket=bucket_name, Key=remote_key)
            except Exception as e:
                # If object was expected to exist, report concurrency conflict
                if expected_etags:
                    exp_etag = expected_etags.get(remote_key) or expected_etags.get(
                        os.path.basename(local_path)
                    )
                    if exp_etag is not None:
                        print(
                            f"Error: Concurrency conflict for {remote_key}. Remote object could not be verified: {e}"
                        )
                        failed_count += 1
                        continue

            if head:
                # Concurrency check via ETag
                if expected_etags:
                    exp_etag = expected_etags.get(remote_key) or expected_etags.get(
                        os.path.basename(local_path)
                    )
                    if exp_etag is not None:
                        remote_etag = head.get("ETag", "").strip('"')
                        clean_exp = exp_etag.strip('"')
                        if remote_etag != clean_exp:
                            print(
                                f"Error: Concurrency conflict for {remote_key}. "
                                f"Remote ETag changed ({remote_etag} != {clean_exp})."
                            )
                            failed_count += 1
                            continue

                # Check if remote object already has matching MD5 in metadata
                meta = head.get("Metadata") or {}
                remote_md5 = meta.get("md5") or meta.get("MD5")
                if remote_md5 and remote_md5.lower() == local_md5.lower():
                    print(f"Skipping {remote_key}: muutmata, jätan vahele.")
                    skipped_count += 1
                    continue

                # Safety check: compare against existing remote object size to prevent accidental truncation
                if remote_key.endswith(".jsonl"):
                    remote_size = head.get("ContentLength", 0)
                    if remote_size > 0 and local_size < (remote_size * 0.9):
                        print(
                            f"Error: Refusing to overwrite {remote_key} ({remote_size} bytes) with smaller local file {local_path} ({local_size} bytes)."
                        )
                        failed_count += 1
                        continue

            extra_args = {"Metadata": {"md5": local_md5}}
            print(f"Uploading file to cloud: {local_path} -> {bucket_name}/{remote_key} ...")
            s3.upload_file(
                local_path,
                bucket_name,
                remote_key,
                ExtraArgs=extra_args,
                Config=b2_transfer_config(),
            )
            uploaded_count += 1

            # Fetch fresh ETag after upload and atomically update .b2_etags.json
            try:
                new_head = s3.head_object(Bucket=bucket_name, Key=remote_key)
                new_etag = new_head.get("ETag", "").strip('"')
                if new_etag:
                    etags_file = os.path.join(OUTPUT_DIR_PROCESSED, ".b2_etags.json")
                    current_etags = {}
                    if os.path.exists(etags_file):
                        try:
                            with open(etags_file, encoding="utf-8") as f:
                                current_etags = json.load(f)
                        except Exception:
                            pass
                    current_etags[remote_key] = new_etag
                    base_name = os.path.basename(local_path)
                    current_etags[base_name] = new_etag
                    if expected_etags is not None:
                        expected_etags[remote_key] = new_etag
                        expected_etags[base_name] = new_etag
                    tmp_etags_file = f"{etags_file}.tmp"
                    with open(tmp_etags_file, "w", encoding="utf-8") as f:
                        json.dump(current_etags, f, indent=2)
                    os.replace(tmp_etags_file, etags_file)
            except Exception as e:
                print(f"Notice: Could not refresh post-upload ETag for {remote_key}: {e}")
        except Exception as e:
            print(f"Error uploading {local_path} to B2: {e}")
            failed_count += 1

    if failed_count == 0:
        print(
            f"All {uploaded_count} files successfully uploaded to {bucket_name} "
            f"({skipped_count} unchanged/skipped)."
        )
        return True

    print(
        f"Upload finished with errors: {uploaded_count} uploaded, "
        f"{skipped_count} skipped, {failed_count} failed."
    )
    return False


if __name__ == "__main__":
    success = upload_to_b2()
    sys.exit(0 if success else 1)
