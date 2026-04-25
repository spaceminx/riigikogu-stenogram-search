from datetime import datetime, timedelta

from config import START_HOUR, END_HOUR, BASE_URL


def generate_stenogram_urls(start_date, end_date):
    base_url = BASE_URL
    start_hour = START_HOUR
    end_hour = END_HOUR

    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    while current <= end:
        date_str = current.strftime("%Y%m%d")
        pretty_date = current.strftime("%Y-%m-%d")

        for hour in range(start_hour, end_hour + 1):
            hhmm = f"{hour:02d}00"
            stamp = date_str + hhmm
            url = base_url + stamp

            yield {
                "url": url,
                "date": pretty_date,
                "hhmm": hhmm,
                "filename": f"{pretty_date}_{hhmm}.html",
            }

        current += timedelta(days=1)