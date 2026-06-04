from datetime import date
from config import START_DATE
from src.extract.download_state import load_last_processed_date
from src.extract.downloader import run_download


def main():
    last_date = load_last_processed_date()

    actual_start = last_date if last_date else START_DATE

    actual_end = date.today().strftime("%Y-%m-%d")

    print(f"Downloading from: {actual_start} to {actual_end}")

    run_download(actual_start, actual_end)


if __name__ == "__main__":
    main()