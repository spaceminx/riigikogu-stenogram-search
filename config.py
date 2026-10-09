import json
import os
from datetime import datetime, timedelta

UNEDITED_REFETCH_DAYS = 60


def active_years(now: datetime | None = None) -> list[str]:
    """Jooksev aasta ja aasta, kuhu jääb kuupäev UNEDITED_REFETCH_DAYS päeva tagasi."""
    now = now or datetime.now()
    return sorted({str(now.year), str((now - timedelta(days=UNEDITED_REFETCH_DAYS)).year)})


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


class _DynamicMembershipDates(dict):
    """Dynamic mapping that reloads from memberships.json cache on access."""

    def _get_current(self) -> dict[str, tuple[str, str]]:
        return load_membership_dates()

    def __contains__(self, key: object) -> bool:
        return key in self._get_current()

    def __getitem__(self, key: str) -> tuple[str, str]:
        return self._get_current()[key]

    def get(self, key: str, default=None):
        return self._get_current().get(key, default)

    def items(self):
        return self._get_current().items()

    def keys(self):
        return self._get_current().keys()

    def values(self):
        return self._get_current().values()

    def __iter__(self):
        return iter(self._get_current())

    def __len__(self) -> int:
        return len(self._get_current())

    def copy(self) -> dict[str, tuple[str, str]]:
        return dict(self._get_current())

    def __eq__(self, other: object) -> bool:
        if isinstance(other, dict):
            return dict(self._get_current()) == other
        return False

    def __repr__(self) -> str:
        return repr(self._get_current())


MEMBERSHIP_DATES: dict[str, tuple[str, str]] = _DynamicMembershipDates()


def get_membership_dates() -> dict[str, tuple[str, str]]:
    """Return dictionary of membership code -> (start_date, end_date)."""
    return MEMBERSHIP_DATES.copy()


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
