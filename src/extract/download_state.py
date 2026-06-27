import os
import json

from config import DOWNLOAD_SYNC_FILE


def _load_state():
    """Helper function to load the existing state to prevent overwriting keys."""
    if not os.path.exists(DOWNLOAD_SYNC_FILE):
        return {}

    try:
        with open(DOWNLOAD_SYNC_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def _save_state(data):
    """Helper function to save the state dictionary back to JSON."""
    os.makedirs(os.path.dirname(DOWNLOAD_SYNC_FILE), exist_ok=True)
    with open(DOWNLOAD_SYNC_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_last_processed_date():
    data = _load_state()
    return data.get("last_processed_date")


def save_last_processed_date(date_str, filename):
    data = _load_state()
    data["last_processed_date"] = date_str
    data["last_processed_file"] = filename
    _save_state(data)


def load_last_checked_date():
    data = _load_state()
    return data.get("last_checked_date")


def save_last_checked_date(date_str):
    data = _load_state()
    data["last_checked_date"] = date_str
    _save_state(data)