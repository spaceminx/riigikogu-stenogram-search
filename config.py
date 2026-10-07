import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

OUTPUT_DIR_PROCESSED = os.path.join(PROJECT_ROOT, "data", "processed")

DATABASE_DIR = os.path.join(PROJECT_ROOT, "database")
DATABASE_PATH = os.path.join(DATABASE_DIR, "riigikogu.sqlite")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

START_DATE = "2019-04-04"

MEMBERSHIP_DATES: dict[str, tuple[str, str]] = {
    "13": ("2015-03-30", "2019-04-03"),
    "14": ("2019-04-04", "2023-04-09"),
    "15": ("2023-04-10", "2099-12-31"),
}

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
