import json
from pathlib import Path

from config import PARSE_SYNC_FILE


def load_parse_state():
    if not Path(PARSE_SYNC_FILE).exists():
        return {"processed_files": []}

    with open(PARSE_SYNC_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_parse_state(state):
    with open(PARSE_SYNC_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def mark_file_processed(state, filename):
    if filename not in state["processed_files"]:
        state["processed_files"].append(filename)