from datetime import datetime

from config import START_DATE
from src.extract.downloader import run_download
from src.extract.download_state import load_last_processed_date


def get_today_date():
    return datetime.today().strftime("%Y-%m-%d")

def main():
    start_date = load_last_processed_date() or START_DATE
    end_date = get_today_date()

    run_download(start_date, end_date)

if __name__ == "__main__":
    main()