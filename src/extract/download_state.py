import os
import json

from config import DOWNLOAD_SYNC_FILE


def load_last_processed_date():
    if not os.path.exists(DOWNLOAD_SYNC_FILE):
        return None

    with open(DOWNLOAD_SYNC_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("last_processed_date")


def save_last_processed_date(date_str, filename):
    os.makedirs(os.path.dirname(DOWNLOAD_SYNC_FILE), exist_ok=True)

    data = {
        "last_processed_date": date_str,
        "last_processed_file": filename
    }

    with open(DOWNLOAD_SYNC_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)