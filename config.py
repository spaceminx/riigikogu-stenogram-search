import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

OUTPUT_DIR_PROCESSED = os.path.join(PROJECT_ROOT, "data", "processed")

DATABASE_DIR = os.path.join(PROJECT_ROOT, "database")
DATABASE_PATH = os.path.join(DATABASE_DIR, "riigikogu.sqlite")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

START_DATE = "2019-04-04"

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
    "nad",
    "meie",
    "teie",
    "mina",
    "sina",
    "nemad",
}
