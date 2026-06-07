import json
from pathlib import Path
from bs4 import BeautifulSoup

from config import (
    OUTPUT_DIR_HTML,
    OUTPUT_DIR_PROCESSED,
    BASE_URL,
)

from src.transform.parser import parse_stenogram_speeches
from src.transform.parse_state import (
    load_parse_state,
    save_parse_state,
    mark_file_processed,
)
from src.transform.lemmatizer import lemmatize_text

def ensure_parse_dirs():
    Path(OUTPUT_DIR_PROCESSED).mkdir(parents=True, exist_ok=True)


def parse_filename(filename: str):
    stem = Path(filename).stem

    date = stem[:10]
    time = stem[11:]

    stamp = date.replace("-", "") + time
    source_url = BASE_URL + stamp

    return date, time, source_url


def load_html_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return BeautifulSoup(f.read(), "html.parser")


def append_speeches_jsonl(speeches, output_file):
    with open(output_file, "a", encoding="utf-8") as f:
        for speech in speeches:
            f.write(json.dumps(speech, ensure_ascii=False) + "\n")


def enrich_speeches(speeches, filename):
    date, time, source_url = parse_filename(filename)

    enriched = []

    for speech in speeches:
        lemmas = lemmatize_text(speech["text"])

        enriched.append(
            {
                "date": date,
                "time": time,
                "source_file": filename,
                "source_url": source_url,
                "speaker": speech["speaker"],
                "text": speech["text"],
                "text_lemmas": lemmas,
            }
        )

    return enriched


def run_parse():
    ensure_parse_dirs()

    state = load_parse_state()
    processed_files = set(state["processed_files"])

    html_files = sorted(Path(OUTPUT_DIR_HTML).glob("*.html"))

    for html_file in html_files:
        filename = html_file.name

        if filename in processed_files:
            print(f"--- EXIST: {filename}")
            continue

        print(f"--- PARSE: {filename}")

        soup = load_html_file(html_file)
        speeches = parse_stenogram_speeches(soup)

        if not speeches:
            print(f"NO SPEECHES: {filename}")
            mark_file_processed(state, filename)
            save_parse_state(state)
            continue

        enriched_speeches = enrich_speeches(speeches, filename)

        year = filename[:4]
        yearly_output_file = Path(OUTPUT_DIR_PROCESSED) / f"{year}.jsonl"
        append_speeches_jsonl(enriched_speeches, yearly_output_file)

        mark_file_processed(state, filename)
        save_parse_state(state)

        print(f"SAVED: {filename} ({len(enriched_speeches)} speeches)")