import hashlib
import json
from pathlib import Path

import pytest

from scripts.b2_utils import compute_multipart_etag, matches_multipart_etag
from scripts.backfill_b2_md5_metadata import backfill_b2_md5_metadata
from scripts.download_from_b2 import download_from_b2
from scripts.upload_to_b2 import upload_to_b2


def compute_md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


# ---------------------------------------------------------------------------
# Multipart ETag Helper Tests
# ---------------------------------------------------------------------------


def test_compute_multipart_etag_two_parts(tmp_path):
    """compute_multipart_etag correctly computes md5(md5(osa1) + md5(osa2))-2."""
    part1 = b"First 8 MiB part dummy data"
    part2 = b"Second part data"
    content = part1 + part2

    test_file = tmp_path / "multi_part.bin"
    test_file.write_bytes(content)

    d1 = hashlib.md5(part1).digest()
    d2 = hashlib.md5(part2).digest()
    expected_etag = f"{hashlib.md5(d1 + d2).hexdigest()}-2"

    calculated = compute_multipart_etag(str(test_file), part_size=len(part1))
    assert calculated == expected_etag
    assert matches_multipart_etag(str(test_file), expected_etag, part_size=len(part1))
    assert not matches_multipart_etag(
        str(test_file), f"{expected_etag[:-1]}3", part_size=len(part1)
    )
    assert not matches_multipart_etag(str(test_file), "wrong-etag-2", part_size=len(part1))


# ---------------------------------------------------------------------------
# Upload Tests
# ---------------------------------------------------------------------------


def test_upload_to_b2_saves_metadata_md5(tmp_path, monkeypatch):
    """upload_to_b2 calls upload_file strictly with ExtraArgs containing md5 metadata."""
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
            if uploaded_calls:
                return {"ETag": '"new-etag-after-upload"', "ContentLength": len(file_content)}
            raise Exception("NoSuchKey")

        # Mock rejects any call without ExtraArgs
        def upload_file(self, local_path, bucket, remote_key, ExtraArgs):
            assert ExtraArgs is not None
            assert ExtraArgs.get("Metadata", {}).get("md5") == expected_md5
            uploaded_calls.append({"path": local_path, "key": remote_key, "extra_args": ExtraArgs})

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

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

        def upload_file(self, local_path, bucket, remote_key, ExtraArgs=None):
            uploaded_calls.append(remote_key)

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

    ok = upload_to_b2(only_files=["2026.jsonl"])
    assert ok is True
    assert len(uploaded_calls) == 0

    out = capsys.readouterr().out
    assert "muutmata, jätan vahele" in out

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

        def head_object(self, Bucket, Key):
            return {"Metadata": {}}

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

        def head_object(self, Bucket, Key):
            return {"Metadata": {}}

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


def test_download_from_b2_skips_when_multipart_etag_matches(tmp_path, monkeypatch):
    """download_from_b2 skips download when remote multipart ETag matches local multipart ETag."""
    monkeypatch.setattr("scripts.download_from_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "test_key")
    monkeypatch.setenv("B2_APP_KEY", "test_secret")

    # Generate 16 MiB data (2 parts of 8 MiB)
    part_size = 8 * 1024 * 1024
    content = b"A" * part_size + b"B" * 100
    local_file = tmp_path / "2020.jsonl"
    local_file.write_bytes(content)

    d1 = hashlib.md5(content[:part_size]).digest()
    d2 = hashlib.md5(content[part_size:]).digest()
    multipart_etag = f"{hashlib.md5(d1 + d2).hexdigest()}-2"

    downloaded = []

    class MockPaginator:
        def paginate(self, Bucket):
            return [
                {
                    "Contents": [
                        {"Key": "2020.jsonl", "Size": len(content), "ETag": f'"{multipart_etag}"'},
                    ]
                }
            ]

    class MockS3Client:
        def get_paginator(self, operation):
            return MockPaginator()

        def head_object(self, Bucket, Key):
            # No md5 metadata
            return {"Metadata": {}, "ContentLength": len(content)}

        def download_file(self, bucket, key, dest):
            downloaded.append(key)

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

    ok = download_from_b2(active_year="2026", include_all_history=True)
    assert ok is True
    assert len(downloaded) == 0

    etags = json.loads((tmp_path / ".b2_etags.json").read_text(encoding="utf-8"))
    assert etags.get("2020.jsonl") == multipart_etag


def test_download_from_b2_missing_metadata_warning_and_fallback(tmp_path, monkeypatch, capsys):
    """download_from_b2 logs warning when MD5 metadata and multipart match are absent and applies fallback."""
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
                        {"Key": "2020.jsonl", "Size": len(data), "ETag": '"nonmatching-123-2"'},
                        {"Key": "2026.jsonl", "Size": len(data), "ETag": '"nonmatching-456-2"'},
                    ]
                }
            ]

    class MockS3Client:
        def get_paginator(self, operation):
            return MockPaginator()

        def head_object(self, Bucket, Key):
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

        def head_object(self, Bucket, Key):
            return {"Metadata": {}}

        def download_file(self, bucket, key, tmp_dest):
            Path(tmp_dest).write_bytes(b"corrupt partial bytes")
            raise ConnectionResetError("Connection lost during download")

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

    ok = download_from_b2(active_year="2026", include_all_history=False)
    assert ok is False

    assert target_file.read_bytes() == orig_content
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

        def head_object(self, Bucket, Key):
            return {"Metadata": {}}

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
    assert "tõend: single-part" in out_dry

    # 2. Apply
    ok_apply = backfill_b2_md5_metadata(dry_run=False)
    assert ok_apply is True
    assert len(copied) == 1
    assert copied[0]["Metadata"] == {"md5": content_md5}
    assert copied[0]["MetadataDirective"] == "REPLACE"

    etags = json.loads((tmp_path / ".b2_etags.json").read_text(encoding="utf-8"))
    assert etags.get("2024.jsonl") == "new-copied-etag"


def test_backfill_b2_md5_metadata_uses_multipart_evidence(tmp_path, monkeypatch, capsys):
    """backfill_b2_md5_metadata accepts matching multipart ETag as valid evidence without trust_local."""
    monkeypatch.setattr("scripts.backfill_b2_md5_metadata.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "test_key")
    monkeypatch.setenv("B2_APP_KEY", "test_secret")

    part_size = 8 * 1024 * 1024
    content = b"X" * part_size + b"Y" * 100
    content_md5 = compute_md5(content)
    (tmp_path / "2022.jsonl").write_bytes(content)

    d1 = hashlib.md5(content[:part_size]).digest()
    d2 = hashlib.md5(content[part_size:]).digest()
    multipart_etag = f"{hashlib.md5(d1 + d2).hexdigest()}-2"

    copied = []

    class MockPaginator:
        def paginate(self, Bucket):
            return [
                {
                    "Contents": [
                        {"Key": "2022.jsonl", "Size": len(content), "ETag": f'"{multipart_etag}"'},
                    ]
                }
            ]

    class MockS3Client:
        def get_paginator(self, operation):
            return MockPaginator()

        def head_object(self, Bucket, Key):
            return {"ETag": f'"{multipart_etag}"', "Metadata": {}}

        def copy_object(self, **kwargs):
            copied.append(kwargs)
            return {"CopyObjectResult": {"ETag": '"new-etag-copied"'}}

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

    # Dry run shows multipart-etag evidence
    ok_dry = backfill_b2_md5_metadata(dry_run=True)
    assert ok_dry is True
    out_dry = capsys.readouterr().out
    assert "tõend: multipart-etag" in out_dry

    # Apply succeeds without trust_local flag
    ok_apply = backfill_b2_md5_metadata(dry_run=False, trust_local=False)
    assert ok_apply is True
    assert len(copied) == 1
    assert copied[0]["Metadata"] == {"md5": content_md5}


def test_backfill_trust_local_without_only_file_or_confirmation_errors(tmp_path, monkeypatch):
    """--trust-local without --only-file or without confirmation raises ValueError."""
    monkeypatch.setattr("scripts.backfill_b2_md5_metadata.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "test_key")
    monkeypatch.setenv("B2_APP_KEY", "test_secret")

    # 1. trust_local without only_files -> error
    with pytest.raises(ValueError, match="--only-file"):
        backfill_b2_md5_metadata(trust_local=True, only_files=None)

    # 2. trust_local with only_files but without confirmation in non-interactive environment -> error
    with pytest.raises(ValueError, match="kinnitust"):
        backfill_b2_md5_metadata(
            trust_local=True, only_files=["2023.jsonl"], i_know_local_is_fresh=False
        )

    # 3. trust_local with only_files AND i_know_local_is_fresh -> permitted
    class MockPaginator:
        def paginate(self, Bucket):
            return [{"Contents": []}]

    class MockS3Client:
        def get_paginator(self, operation):
            return MockPaginator()

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

    ok = backfill_b2_md5_metadata(
        dry_run=True,
        trust_local=True,
        only_files=["2023.jsonl"],
        i_know_local_is_fresh=True,
    )
    assert ok is True
