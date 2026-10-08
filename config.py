import json
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

OUTPUT_DIR_PROCESSED = os.environ.get(
    "OUTPUT_DIR_PROCESSED", os.path.join(PROJECT_ROOT, "data", "processed")
)

DATABASE_DIR = os.environ.get("DATABASE_DIR", os.path.join(PROJECT_ROOT, "database"))
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(DATABASE_DIR, "riigikogu.sqlite"))
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")

B2_ENDPOINT_URL = os.environ.get("B2_ENDPOINT_URL", "https://s3.eu-central-003.backblazeb2.com")
B2_BUCKET_NAME = os.environ.get("B2_BUCKET_NAME", "riigikogu-stenograms")

START_DATE = "2019-04-04"

DEFAULT_MEMBERSHIP_DATES: dict[str, tuple[str, str]] = {
    "13": ("2015-03-30", "2019-04-03"),
    "14": ("2019-04-04", "2023-04-09"),
    "15": ("2023-04-10", "2027-02-25"),
}


def load_membership_dates() -> dict[str, tuple[str, str]]:
    """Load membership dates from memberships.json cache, or fallback to defaults."""
    cache_path = os.path.join(OUTPUT_DIR_PROCESSED, "memberships.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            dates = {}
            for k, v in data.items():
                if isinstance(v, dict) and "startDate" in v and "endDate" in v:
                    dates[str(k)] = (v["startDate"], v["endDate"])
            if dates:
                return dates
        except Exception:
            pass
    return DEFAULT_MEMBERSHIP_DATES


MEMBERSHIP_DATES: dict[str, tuple[str, str]] = load_membership_dates()

STOPWORDS = {
    "ja",
    "ning",
    "ega",
    "ehk",
    "nii",
    "või",
    "et",
    "on",
    "oli",
    "olema",
    "see",
    "seda",
    "selle",
    "siis",
    "ka",
    "kui",
    "me",
    "ma",
    "sa",
    "ta",
    "tema",
    "nad",
    "meie",
    "teie",
    "mina",
    "sina",
    "nemad",
}
