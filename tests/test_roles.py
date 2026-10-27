"""Tests for governments.json and coalition/opposition role helper."""

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, literal, select

from src.api.roles import load_governments, role, role_expression

KNOWN_FACTIONS = {
    "Eesti Keskerakonna fraktsioon",
    "Eesti Konservatiivse Rahvaerakonna fraktsioon",
    "Eesti Reformierakonna fraktsioon",
    "Isamaa fraktsioon",
    "Isamaa ja Res Publica Liidu fraktsioon",
    "Sotsiaaldemokraatliku Erakonna fraktsioon",
    "Eesti 200 fraktsioon",
    "Fraktsiooni mittekuuluvad Riigikogu liikmed",
}


def test_governments_json_structure():
    """Verify governments.json periods: contiguous, sorted, non-overlapping, valid factions."""
    governments = load_governments()
    assert len(governments) >= 8

    for i, gov in enumerate(governments):
        assert "from" in gov
        assert "to" in gov
        assert "government" in gov
        assert "coalition" in gov
        assert "source" in gov

        sources = gov["source"] if isinstance(gov["source"], list) else [gov["source"]]
        assert len(sources) > 0
        for src in sources:
            assert isinstance(src, str)
            assert src.startswith("https://"), f"Source must be an https URL: {src}"

        # All coalition factions must be in known factions
        for fac in gov["coalition"]:
            assert fac in KNOWN_FACTIONS, f"Unknown faction: {fac}"

        # Periods must be sorted
        if i > 0:
            prev = governments[i - 1]
            assert prev["to"] == gov["from"], (
                f"Periods not contiguous: {prev['government']} to={prev['to']} != {gov['government']} from={gov['from']}"
            )
            assert prev["from"] < gov["from"], "Periods not sorted"

        # Only the last period may have to=None
        if i < len(governments) - 1:
            assert gov["to"] is not None, f"Intermediate period {gov['government']} has to=None"
        else:
            assert gov["to"] is None, f"Last period {gov['government']} should have to=None"


def test_role_boundary_dates():
    """Test role() on critical boundary dates."""
    # 2025-03-10: SDE was in Michal I coalition
    assert role("Sotsiaaldemokraatliku Erakonna fraktsioon", "2025-03-10") == "coalition"
    # 2025-03-11: SDE was excluded from Michal II government
    assert role("Sotsiaaldemokraatliku Erakonna fraktsioon", "2025-03-11") == "opposition"

    # 2022-06-02: Keskerakond was in Kallas I coalition
    assert role("Eesti Keskerakonna fraktsioon", "2022-06-02") == "coalition"
    # 2022-06-03: Keskerakond ministers were dismissed (Kallas I minority government)
    assert role("Eesti Keskerakonna fraktsioon", "2022-06-03") == "opposition"

    # Reformierakond stayed in coalition on 2022-06-03
    assert role("Eesti Reformierakonna fraktsioon", "2022-06-03") == "coalition"


def test_role_isamaa_before_and_after_its_rename():
    """IRL's faction took the name Isamaa on 2018-07-31; both names were in Ratas I coalition."""
    assert role("Isamaa ja Res Publica Liidu fraktsioon", "2018-07-30") == "coalition"
    assert role("Isamaa fraktsioon", "2018-07-31") == "coalition"
    # Before Ratas I, IRL had no listed government period
    assert role("Isamaa ja Res Publica Liidu fraktsioon", "2016-11-22") == "opposition"


def test_role_fraktsioonitud_and_empty():
    """Non-aligned and empty factions must always yield 'none'."""
    assert role("Fraktsiooni mittekuuluvad Riigikogu liikmed", "2023-05-15") == "none"
    assert role("", "2023-05-15") == "none"
    assert role(None, "2023-05-15") == "none"
    assert role("Eesti Reformierakonna fraktsioon", None) == "none"


KESK = "Eesti Keskerakonna fraktsioon"
EKRE = "Eesti Konservatiivse Rahvaerakonna fraktsioon"
REF = "Eesti Reformierakonna fraktsioon"
ISAMAA = "Isamaa fraktsioon"
SDE = "Sotsiaaldemokraatliku Erakonna fraktsioon"
E200 = "Eesti 200 fraktsioon"

# Every government change in 2019–2026 (verified against valitsus.ee / ERR, see roadmap C4):
# (date the new period starts, factions entering the coalition, factions leaving it).
TRANSITIONS = [
    ("2019-04-29", {EKRE}, {SDE}),  # Ratas II
    ("2021-01-26", {REF}, {EKRE, ISAMAA}),  # Kallas I
    ("2022-06-03", set(), {KESK}),  # Kallas I, Centre ministers dismissed
    ("2022-07-18", {ISAMAA, SDE}, set()),  # Kallas II
    ("2023-04-17", {E200}, {ISAMAA}),  # Kallas III
    ("2024-07-23", set(), set()),  # Michal, same coalition
    ("2025-03-11", set(), {SDE}),  # Michal, SDE expelled
]


@pytest.mark.parametrize("start, entering, leaving", TRANSITIONS)
def test_role_switches_on_transition_start_date(start, entering, leaving):
    """The role changes on the start date of the new period, not a day earlier or later."""
    day_before = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
    for fac in entering:
        assert role(fac, day_before) == "opposition", (fac, day_before)
        assert role(fac, start) == "coalition", (fac, start)
    for fac in leaving:
        assert role(fac, day_before) == "coalition", (fac, day_before)
        assert role(fac, start) == "opposition", (fac, start)


def test_transition_table_matches_governments_json():
    """TRANSITIONS lists every period change in governments.json since XIV started."""
    starts = [g["from"] for g in load_governments() if g["from"] >= "2019-04-04"]
    assert starts == [t[0] for t in TRANSITIONS]


def test_role_expression_matches_role_on_boundary_dates():
    """The SQL CASE used in queries agrees with role() on both sides of every boundary."""
    engine = create_engine("sqlite://")
    factions = [KESK, EKRE, REF, ISAMAA, SDE, E200, "Fraktsiooni mittekuuluvad Riigikogu liikmed"]
    dates = []
    for start, _, _ in TRANSITIONS:
        dates.append((date.fromisoformat(start) - timedelta(days=1)).isoformat())
        dates.append(start)
    with engine.connect() as conn:
        for fac in factions:
            for d in dates:
                sql_role = conn.execute(select(role_expression(literal(fac), literal(d)))).scalar()
                assert sql_role == role(fac, d), (fac, d)
