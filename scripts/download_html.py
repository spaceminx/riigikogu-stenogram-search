from datetime import date, timedelta, datetime
from config import START_DATE
# Assuming we will add two new functions to download_state.py
from src.extract.download_state import (
    load_last_processed_date,
    load_last_checked_date,
    save_last_checked_date
)
from src.extract.downloader import run_download


def main():
    today = date.today()
    actual_end = today.strftime("%Y-%m-%d")

    last_processed_str = load_last_processed_date()
    last_checked_str = load_last_checked_date()

    # Default fallback
    actual_start = last_processed_str if last_processed_str else START_DATE

    # Apply your summer optimization logic
    if last_processed_str and last_checked_str:
        last_processed_dt = datetime.strptime(last_processed_str, "%Y-%m-%d").date()
        last_checked_dt = datetime.strptime(last_checked_str, "%Y-%m-%d").date()

        # If the last actual stenogram was more than 2 days ago...
        if (today - last_processed_dt).days > 2:
            # ...start checking from the last checked date minus 24 hours
            actual_start = (last_checked_dt - timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"Downloading from: {actual_start} to {actual_end}")

    # Run the scraper
    run_download(actual_start, actual_end)

    # Update the controlled/checked date after a successful run
    save_last_checked_date(actual_end)


if __name__ == "__main__":
    main()