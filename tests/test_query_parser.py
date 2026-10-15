import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.fetch_stenograms_api import split_speaker_role
from src.api.search import (
    fill_missing_periods,
    is_only_stopwords,
    parse_query_groups,
    week_key_to_monday,
)


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


def test_fill_missing_periods_weekly():
    data = [("2024-10", 5), ("2024-12", 10)]
    filled = fill_missing_periods(data, "weekly", "week")
    assert len(filled) == 3
    assert filled[0] == {"week": "2024-10", "week_start": "2024-03-04", "count": 5}
    assert filled[1] == {"week": "2024-11", "week_start": "2024-03-11", "count": 0}
    assert filled[2] == {"week": "2024-12", "week_start": "2024-03-18", "count": 10}


def test_week_key_to_monday_edge_cases():
    # Standard week
    m1 = week_key_to_monday("2025-18")
    assert m1.isoformat() == "2025-05-05"

    # Week 00 in 2025 (Jan 1, 2025 is Wednesday; Monday of that week is 2024-12-30)
    m2 = week_key_to_monday("2025-00")
    assert m2.isoformat() == "2024-12-30"

    # Week 01 in 2025 (First Monday of 2025 is 2025-01-06)
    m3 = week_key_to_monday("2025-01")
    assert m3.isoformat() == "2025-01-06"

    # Year where Jan 1 is Monday (2024)
    m4 = week_key_to_monday("2024-01")
    assert m4.isoformat() == "2024-01-01"


def test_duplicate_lemmas_deduplicated_in_group():
    # 'maks' and 'maksud' both lemmatize to 'maks'. The AND group should deduplicate lemmas.
    groups = parse_query_groups("maks maksud")
    assert len(groups) == 1
    assert groups[0] == ["maks"]


def test_pronoun_stopwords_filtered():
    # 'tema', 'ta', 'nad' should be filtered out
    assert is_only_stopwords("tema ta nad") is True
    groups = parse_query_groups("tema räägib")
    assert len(groups) == 1
    assert "tema" not in groups[0]


def test_parse_query_groups_limit_and_messages():
    import pytest

    with pytest.raises(
        ValueError, match="Liiga palju otsingurühmi: lubatud kuni 10 komaga eraldatud rühma."
    ):
        parse_query_groups("g1,g2,g3,g4,g5,g6,g7,g8,g9,g10,g11")

    with pytest.raises(ValueError, match="Liiga palju sõnu ühes rühmas: lubatud kuni 10 sisusõna."):
        parse_query_groups("üks kaks kolm neli viis kuus seitse kaheksa üheksa kümme üksteist")

    groups = parse_query_groups("ja see on üks väga pikk lause mis räägib riigi eelarvest täna")
    assert len(groups) == 1
    assert "eelarve" in groups[0]

    groups_empty = parse_query_groups("eelarve,,")
    assert len(groups_empty) == 1
    assert groups_empty[0] == ["eelarve"]


def test_is_only_stopwords_limits():
    import pytest

    with pytest.raises(
        ValueError, match="Liiga palju otsingurühmi: lubatud kuni 10 komaga eraldatud rühma."
    ):
        is_only_stopwords("g1,g2,g3,g4,g5,g6,g7,g8,g9,g10,g11")

    with pytest.raises(ValueError, match="Liiga palju sõnu ühes rühmas: lubatud kuni 10 sisusõna."):
        is_only_stopwords("üks kaks kolm neli viis kuus seitse kaheksa üheksa kümme üksteist")

    assert (
        is_only_stopwords("ja see on üks väga pikk lause mis räägib riigi eelarvest täna") is False
    )
    assert is_only_stopwords("eelarve,,") is False
