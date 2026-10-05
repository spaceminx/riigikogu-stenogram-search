import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.fetch_stenograms_api import split_speaker_role
from src.api.search import fill_missing_periods, is_only_stopwords, parse_query_groups


def test_parse_single_keyword():
    groups = parse_query_groups("kliima")
    assert len(groups) == 1
    assert "kliima" in groups[0]


def test_parse_and_condition():
    # Space between words means AND within same group
    groups = parse_query_groups("roheline energia")
    assert len(groups) == 1
    assert "roheline" in groups[0]
    assert "energia" in groups[0]


def test_parse_or_condition():
    # Comma means OR (separate groups)
    groups = parse_query_groups("tuuleenergia, päikeseenergia")
    assert len(groups) == 2
    assert "tuuleenergia" in groups[0]
    assert "päikeseenergia" in groups[1]


def test_stopwords_filtered():
    # 'ja', 'on', 'see' are in STOPWORDS and should be filtered out
    groups = parse_query_groups("ja see on mets")
    assert len(groups) == 1
    assert groups[0] == ["mets"]


def test_is_only_stopwords():
    assert is_only_stopwords("ja") is True
    assert is_only_stopwords("see on") is True
    assert is_only_stopwords("ja, ning, ehk") is True
    assert is_only_stopwords("mets") is False
    assert is_only_stopwords("ja mets") is False
    assert is_only_stopwords("") is False


def test_split_speaker_role():
    name, role = split_speaker_role("Peaminister Kaja Kallas")
    assert name == "Kaja Kallas"
    assert role == "Peaminister"

    name, role = split_speaker_role("Jüri Ratas")
    assert name == "Jüri Ratas"
    assert role is None


def test_fill_missing_periods_monthly():
    data = [("2024-01", 5), ("2024-03", 10)]
    filled = fill_missing_periods(data, "monthly", "month")
    assert len(filled) == 3
    assert filled[0] == {"month": "2024-01", "count": 5}
    assert filled[1] == {"month": "2024-02", "count": 0}
    assert filled[2] == {"month": "2024-03", "count": 10}
