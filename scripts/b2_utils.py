import hashlib
import os

DEFAULT_PART_SIZE = 8 * 1024 * 1024  # 8 MiB


def get_file_md5(file_path: str) -> str:
    """Compute hex MD5 digest of a local file."""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_multipart_etag(file_path: str, part_size: int = DEFAULT_PART_SIZE) -> str:
    """Compute S3-style multipart ETag for a local file using given part_size (default 8 MiB).

    For N parts: md5(md5(part_1) + md5(part_2) + ... + md5(part_N)) + f"-{N}"
    where each md5(part_i) is the binary 16-byte MD5 digest.
    """
    digests = []
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(part_size)
            if not chunk:
                break
            digests.append(hashlib.md5(chunk).digest())

    if not digests:
        return f"{hashlib.md5(b'').hexdigest()}-0"

    num_parts = len(digests)
    combined_md5 = hashlib.md5(b"".join(digests)).hexdigest()
    return f"{combined_md5}-{num_parts}"


def matches_multipart_etag(
    file_path: str, remote_etag: str, part_size: int = DEFAULT_PART_SIZE
) -> bool:
    """Check if local file matches remote S3/B2 multipart ETag.

    Verifies that remote ETag has suffix '-N', that N matches the number
    of parts produced with part_size, and that the combined MD5 matches.
    """
    if not os.path.exists(file_path):
        return False
    cleaned = remote_etag.strip('"')
    if "-" not in cleaned:
        return False
    parts = cleaned.split("-")
    if len(parts) != 2 or not parts[1].isdigit():
        return False
    expected_n = int(parts[1])
    try:
        local_etag = compute_multipart_etag(file_path, part_size=part_size)
    except Exception:
        return False
    local_parts = local_etag.split("-")
    if len(local_parts) != 2 or int(local_parts[1]) != expected_n:
        return False
    return local_etag.lower() == cleaned.lower()
