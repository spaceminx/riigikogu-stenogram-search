import os
import requests
from bs4 import BeautifulSoup

from config import OUTPUT_DIR_HTML
from src.extract.url_generator import generate_stenogram_urls
from src.extract.download_state import (
    load_last_processed_date,
    save_last_processed_date,
)


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR_HTML, exist_ok=True)


def already_downloaded(filepath):
    return os.path.exists(filepath)


def is_stenogram_page(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    speech_blocks = soup.select("div.speech-area")
    return bool(speech_blocks)


def download_html(url, output_path):
    try:
        print(f"--- REQUEST: {url}")
        response = requests.get(url, timeout=15)

        print(f"--- STATUS: {response.status_code}")

        if response.status_code != 200:
            return False

        if not is_stenogram_page(response.text):
            print("No speech-area blocks")
            return False

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(response.text)

        return True

    except Exception as e:
        print(f"ERROR: {e}")
        return False


def run_download(start_date, end_date):
    ensure_output_dir()

    last_processed_date = load_last_processed_date()
    print("Last processed date:", last_processed_date)

    for item in generate_stenogram_urls(start_date, end_date):
        output_path = os.path.join(OUTPUT_DIR_HTML, item["filename"])

        if already_downloaded(output_path):
            print(f"--- EXIST: {output_path}")
            continue

        success = download_html(
            url=item["url"],
            output_path=output_path
        )

        if success:
            print(f"SAVED: {item['filename']}")

            save_last_processed_date(
                item["date"],
                item["filename"]
            )
        else:
            print(f"NO STENOGRAM: {item['url']}")