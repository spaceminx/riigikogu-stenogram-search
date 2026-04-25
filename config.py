import os

BASE_URL = "https://stenogrammid.riigikogu.ee/"

PROJECT_ROOT = os.path.dirname((os.path.abspath(__file__)))

DOWNLOAD_SYNC_FILE = os.path.join(PROJECT_ROOT, "data","sync", "download_state.json")
PARSE_SYNC_FILE = os.path.join(PROJECT_ROOT, "data","sync", "parse_state.json")

OUTPUT_DIR_PROCESSED = os.path.join(
    PROJECT_ROOT,
    "data",
    "processed"
)

OUTPUT_DIR_JSON = os.path.join(
    PROJECT_ROOT,
    "data",
    "raw",
    "json"
)

OUTPUT_DIR_HTML = os.path.join(
    PROJECT_ROOT,
    "data",
    "raw",
    "html"
)

DATABASE_DIR = os.path.join(PROJECT_ROOT, "database")
DATABASE_PATH = os.path.join(DATABASE_DIR, "riigikogu.sqlite")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

CRAWL_DELAY_SECONDS = 200

START_DATE = "2025-12-31"
END_DATE = "2026-02-01"

START_HOUR = 9
END_HOUR = 16