import hashlib
import json
from pathlib import Path

from scripts.backfill_b2_md5_metadata import backfill_b2_md5_metadata
from scripts.download_from_b2 import download_from_b2
from scripts.upload_to_b2 import upload_to_b2


def compute_md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


# ---------------------------------------------------------------------------
# Upload Tests
# ---------------------------------------------------------------------------


def test_upload_to_b2_saves_metadata_md5(tmp_path, monkeypatch):
    """upload_to_b2 passes MD5 in ExtraArgs and updates .b2_etags.json."""
    monkeypatch.setattr("scripts.upload_to_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "test_key")
    monkeypatch.setenv("B2_APP_KEY", "test_secret")

    file_content = b'{"speaker": "Test", "text": "Kone"}\n'
    test_file = tmp_path / "2026.jsonl"
    test_file.write_bytes(file_content)
    expected_md5 = compute_md5(file_content)

    uploaded_calls = []

    class MockS3Client:
        def head_object(self, Bucket, Key):
            # Object does not exist yet remotely
            raise Exception("NoSuchKey")

        def upload_file(self, local_path, bucket, remote_key, ExtraArgs=None):
            uploaded_calls.append({"path": local_path, "key": remote_key, "extra_args": ExtraArgs})

    # Secondary head_object for post-upload ETag fetch
    post_upload_etag = '"new-etag-after-upload"'

    def mock_head_object(Bucket, Key):
        if uploaded_calls:
            return {"ETag": post_upload_etag, "ContentLength": len(file_content)}
        raise Exception("NoSuchKey")

    client = MockS3Client()
    client.head_object = mock_head_object
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: client)

    ok = upload_to_b2(only_files=["2026.jsonl"])
    assert ok is True
    assert len(uploaded_calls) == 1
    assert uploaded_calls[0]["key"] == "2026.jsonl"
    assert uploaded_calls[0]["extra_args"] == {"Metadata": {"md5": expected_md5}}

    etags_file = tmp_path / ".b2_etags.json"
    assert etags_file.exists()
    etags = json.loads(etags_file.read_text(encoding="utf-8"))
    assert etags.get("2026.jsonl") == "new-etag-after-upload"


def test_upload_to_b2_skips_unchanged_file(tmp_path, monkeypatch, capsys):
    """upload_to_b2 skips upload if remote Metadata.md5 matches local MD5 and preserves .b2_etags.json."""
    monkeypatch.setattr("scripts.upload_to_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "test_key")
    monkeypatch.setenv("B2_APP_KEY", "test_secret")

    file_content = b'{"speaker": "Unchanged", "text": "Sisu"}\n'
    test_file = tmp_path / "2026.jsonl"
    test_file.write_bytes(file_content)
    local_md5 = compute_md5(file_content)

    # Initial .b2_etags.json
    etags_file = tmp_path / ".b2_etags.json"
    etags_file.write_text(json.dumps({"2026.jsonl": "original-etag"}), encoding="utf-8")

    uploaded_calls = []

    class MockS3Client:
        def head_object(self, Bucket, Key):
            return {
                "ETag": '"original-etag"',
                "ContentLength": len(file_content),
                "Metadata": {"md5": local_md5},
            }

        def upload_file(self, local_path, bucket, remote_key, **kwargs):
            uploaded_calls.append(remote_key)

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

    ok = upload_to_b2(only_files=["2026.jsonl"])
    assert ok is True
    assert len(uploaded_calls) == 0

    out = capsys.readouterr().out
    assert "muutmata, jätan vahele" in out

    # .b2_etags.json was unchanged
    etags = json.loads(etags_file.read_text(encoding="utf-8"))
    assert etags.get("2026.jsonl") == "original-etag"


# ---------------------------------------------------------------------------
# Download Tests
# ---------------------------------------------------------------------------


def test_download_from_b2_skips_same_md5_active_and_historical(tmp_path, monkeypatch):
    """download_from_b2 skips download when MD5 matches for both active and historical files."""
    monkeypatch.setattr("scripts.download_from_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "test_key")
    monkeypatch.setenv("B2_APP_KEY", "test_secret")

    active_content = b'{"year": 2026}\n'
    active_md5 = compute_md5(active_content)
    (tmp_path / "2026.jsonl").write_bytes(active_content)

    hist_content = b'{"year": 2020}\n'
    hist_md5 = compute_md5(hist_content)
    (tmp_path / "2020.jsonl").write_bytes(hist_content)

    downloaded = []

    class MockPaginator:
        def paginate(self, Bucket):
            return [
                {
                    "Contents": [
                        {
                            "Key": "2026.jsonl",
                            "Size": len(active_content),
                            "ETag": f'"{active_md5}"',
                        },
                        {"Key": "2020.jsonl", "Size": len(hist_content), "ETag": f'"{hist_md5}"'},
                    ]
                }
            ]

    class MockS3Client:
        def get_paginator(self, operation):
            return MockPaginator()

        def download_file(self, bucket, key, local_path):
            downloaded.append(key)

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

    ok = download_from_b2(active_year="2026", include_all_history=True)
    assert ok is True
    assert len(downloaded) == 0

    etags_file = tmp_path / ".b2_etags.json"
    assert etags_file.exists()
    etags = json.loads(etags_file.read_text(encoding="utf-8"))
    assert etags.get("2026.jsonl") == active_md5
    assert etags.get("2020.jsonl") == hist_md5


def test_download_from_b2_downloads_when_md5_differs_same_size(tmp_path, monkeypatch):
    """download_from_b2 downloads when MD5 differs even if file size matches."""
    monkeypatch.setattr("scripts.download_from_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "test_key")
    monkeypatch.setenv("B2_APP_KEY", "test_secret")

    local_bytes = b"abcdefghij"  # 10 bytes
    remote_bytes = b"0123456789"  # 10 bytes, different MD5
    remote_md5 = compute_md5(remote_bytes)

    local_file = tmp_path / "2020.jsonl"
    local_file.write_bytes(local_bytes)

    downloaded = []

    class MockPaginator:
        def paginate(self, Bucket):
            return [
                {
                    "Contents": [
                        {"Key": "2020.jsonl", "Size": 10, "ETag": f'"{remote_md5}"'},
                    ]
                }
            ]

    class MockS3Client:
        def get_paginator(self, operation):
            return MockPaginator()

        def download_file(self, bucket, key, tmp_path_arg):
            downloaded.append(key)
            Path(tmp_path_arg).write_bytes(remote_bytes)

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

    ok = download_from_b2(active_year="2026", include_all_history=True)
    assert ok is True
    assert downloaded == ["2020.jsonl"]
    assert local_file.read_bytes() == remote_bytes

    etags = json.loads((tmp_path / ".b2_etags.json").read_text(encoding="utf-8"))
    assert etags.get("2020.jsonl") == remote_md5


def test_download_from_b2_missing_metadata_warning_and_fallback(tmp_path, monkeypatch, capsys):
    """download_from_b2 logs warning when MD5 metadata is absent on multipart object and applies fallback."""
    monkeypatch.setattr("scripts.download_from_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "test_key")
    monkeypatch.setenv("B2_APP_KEY", "test_secret")

    data = b"sample-bytes"
    (tmp_path / "2020.jsonl").write_bytes(data)  # Historical, matching size
    (tmp_path / "2026.jsonl").write_bytes(data)  # Active

    downloaded = []

    class MockPaginator:
        def paginate(self, Bucket):
            return [
                {
                    "Contents": [
                        {"Key": "2020.jsonl", "Size": len(data), "ETag": '"multipart-123-2"'},
                        {"Key": "2026.jsonl", "Size": len(data), "ETag": '"multipart-456-2"'},
                    ]
                }
            ]

    class MockS3Client:
        def get_paginator(self, operation):
            return MockPaginator()

        def head_object(self, Bucket, Key):
            # No metadata!
            return {"Metadata": {}, "ContentLength": len(data)}

        def download_file(self, bucket, key, tmp_dest):
            downloaded.append(key)
            Path(tmp_dest).write_bytes(data)

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

    ok = download_from_b2(active_year="2026", include_all_history=True)
    assert ok is True

    out = capsys.readouterr().out
    assert "md5 metaandmed puuduvad: 2020.jsonl" in out
    assert "md5 metaandmed puuduvad: 2026.jsonl" in out

    # Historical file with matching size was skipped by legacy fallback; active file was downloaded
    assert downloaded == ["2026.jsonl"]


def test_download_from_b2_multipart_uses_metadata(tmp_path, monkeypatch):
    """download_from_b2 retrieves MD5 from head_object metadata for multipart ETag."""
    monkeypatch.setattr("scripts.download_from_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "test_key")
    monkeypatch.setenv("B2_APP_KEY", "test_secret")

    data = b"large-multipart-dataset-content"
    data_md5 = compute_md5(data)
    (tmp_path / "2026.jsonl").write_bytes(data)

    downloaded = []

    class MockPaginator:
        def paginate(self, Bucket):
            return [
                {
                    "Contents": [
                        {"Key": "2026.jsonl", "Size": len(data), "ETag": '"multipart-hash-4"'},
                    ]
                }
            ]

    class MockS3Client:
        def get_paginator(self, operation):
            return MockPaginator()

        def head_object(self, Bucket, Key):
            return {"Metadata": {"md5": data_md5}, "ContentLength": len(data)}

        def download_file(self, bucket, key, dest):
            downloaded.append(key)

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

    ok = download_from_b2(active_year="2026", include_all_history=False)
    assert ok is True
    # MD5 matched in metadata -> skipped!
    assert len(downloaded) == 0

    etags = json.loads((tmp_path / ".b2_etags.json").read_text(encoding="utf-8"))
    assert etags.get("2026.jsonl") == "multipart-hash-4"


def test_download_from_b2_atomic_failure_cleans_tmp_and_preserves_target(tmp_path, monkeypatch):
    """download_from_b2 preserves existing local file and deletes tmp file if download fails."""
    monkeypatch.setattr("scripts.download_from_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "test_key")
    monkeypatch.setenv("B2_APP_KEY", "test_secret")

    orig_content = b"original untouched content"
    target_file = tmp_path / "2026.jsonl"
    target_file.write_bytes(orig_content)

    class MockPaginator:
        def paginate(self, Bucket):
            return [
                {
                    "Contents": [
                        {"Key": "2026.jsonl", "Size": 100, "ETag": '"different-md5-hex"'},
                    ]
                }
            ]

    class MockS3Client:
        def get_paginator(self, operation):
            return MockPaginator()

        def download_file(self, bucket, key, tmp_dest):
            # Create a partial corrupt tmp file then raise
            Path(tmp_dest).write_bytes(b"corrupt partial bytes")
            raise ConnectionResetError("Connection lost during download")

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

    ok = download_from_b2(active_year="2026", include_all_history=False)
    assert ok is False

    # Original target file remains untouched
    assert target_file.read_bytes() == orig_content

    # No leftover .tmp files
    tmp_files = list(tmp_path.glob("*.tmp*"))
    assert len(tmp_files) == 0


def test_download_from_b2_dry_run(tmp_path, monkeypatch, capsys):
    """download_from_b2 --dry-run prints decisions without downloading or modifying .b2_etags.json."""
    monkeypatch.setattr("scripts.download_from_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "test_key")
    monkeypatch.setenv("B2_APP_KEY", "test_secret")

    downloaded = []

    class MockPaginator:
        def paginate(self, Bucket):
            return [
                {
                    "Contents": [
                        {"Key": "2026.jsonl", "Size": 500, "ETag": '"etag-2026"'},
                    ]
                }
            ]

    class MockS3Client:
        def get_paginator(self, operation):
            return MockPaginator()

        def download_file(self, bucket, key, dest):
            downloaded.append(key)

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

    ok = download_from_b2(active_year="2026", dry_run=True)
    assert ok is True
    assert len(downloaded) == 0

    etags_file = tmp_path / ".b2_etags.json"
    assert not etags_file.exists()

    out = capsys.readouterr().out
    assert "[DRY-RUN] Download 2026.jsonl: new file (500 bytes)" in out
    assert "500 bytes" in out


# ---------------------------------------------------------------------------
# Metadata Backfill Tests
# ---------------------------------------------------------------------------


def test_backfill_b2_md5_metadata_dry_run_vs_apply(tmp_path, monkeypatch, capsys):
    """backfill_b2_md5_metadata performs dry run by default and executes copy_object on --apply."""
    monkeypatch.setattr("scripts.backfill_b2_md5_metadata.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "test_key")
    monkeypatch.setenv("B2_APP_KEY", "test_secret")

    content = b"valid content"
    content_md5 = compute_md5(content)
    (tmp_path / "2024.jsonl").write_bytes(content)

    copied = []

    class MockPaginator:
        def paginate(self, Bucket):
            return [
                {
                    "Contents": [
                        {"Key": "2024.jsonl", "Size": len(content), "ETag": f'"{content_md5}"'},
                    ]
                }
            ]

    class MockS3Client:
        def get_paginator(self, operation):
            return MockPaginator()

        def head_object(self, Bucket, Key):
            return {"ETag": f'"{content_md5}"', "Metadata": {}}

        def copy_object(self, **kwargs):
            copied.append(kwargs)
            return {"CopyObjectResult": {"ETag": '"new-copied-etag"'}}

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

    # 1. Dry run
    ok_dry = backfill_b2_md5_metadata(dry_run=True)
    assert ok_dry is True
    assert len(copied) == 0
    out_dry = capsys.readouterr().out
    assert "[DRY-RUN] Uuendaks 2024.jsonl" in out_dry

    # 2. Apply
    ok_apply = backfill_b2_md5_metadata(dry_run=False)
    assert ok_apply is True
    assert len(copied) == 1
    assert copied[0]["Metadata"] == {"md5": content_md5}
    assert copied[0]["MetadataDirective"] == "REPLACE"

    # .b2_etags.json was updated with new ETag from copy_object
    etags = json.loads((tmp_path / ".b2_etags.json").read_text(encoding="utf-8"))
    assert etags.get("2024.jsonl") == "new-copied-etag"


def test_backfill_b2_md5_metadata_untrusted_requires_flag(tmp_path, monkeypatch, capsys):
    """backfill_b2_md5_metadata skips multipart objects unless trust_local is True."""
    monkeypatch.setattr("scripts.backfill_b2_md5_metadata.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "test_key")
    monkeypatch.setenv("B2_APP_KEY", "test_secret")

    content = b"multipart local content"
    content_md5 = compute_md5(content)
    (tmp_path / "2023.jsonl").write_bytes(content)

    copied = []

    class MockPaginator:
        def paginate(self, Bucket):
            return [
                {
                    "Contents": [
                        {"Key": "2023.jsonl", "Size": len(content), "ETag": '"multipart-etag-3"'},
                    ]
                }
            ]

    class MockS3Client:
        def get_paginator(self, operation):
            return MockPaginator()

        def head_object(self, Bucket, Key):
            return {"ETag": '"multipart-etag-3"', "Metadata": {}}

        def copy_object(self, **kwargs):
            copied.append(kwargs)
            return {"CopyObjectResult": {"ETag": '"copied-etag-4"'}}

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

    # Without trust_local -> skipped
    ok1 = backfill_b2_md5_metadata(dry_run=False, trust_local=False)
    assert ok1 is True
    assert len(copied) == 0
    out1 = capsys.readouterr().out
    assert "pole tõestatult identne" in out1

    # With trust_local -> updated
    ok2 = backfill_b2_md5_metadata(dry_run=False, trust_local=True)
    assert ok2 is True
    assert len(copied) == 1
    assert copied[0]["Metadata"] == {"md5": content_md5}
