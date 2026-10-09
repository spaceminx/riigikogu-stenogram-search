import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.download_from_b2 import download_from_b2


def download_all_from_b2() -> bool:
    """Download all historical datasets and sync state files from Backblaze B2."""
    return download_from_b2(include_all_history=True)


if __name__ == "__main__":
    ok = download_all_from_b2()
    sys.exit(0 if ok else 1)
