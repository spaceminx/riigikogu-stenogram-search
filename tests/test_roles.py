"""Tests for governments.json and coalition/opposition role helper."""

from src.api.roles import load_governments, role

KNOWN_FACTIONS = {
    "Eesti Keskerakonna fraktsioon",
    "Eesti Konservatiivse Rahvaerakonna fraktsioon",
    "Eesti Reformierakonna fraktsioon",
    "Isamaa fraktsioon",
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
        assert gov["source"].startswith("http")

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


def test_role_fraktsioonitud_and_empty():
    """Non-aligned and empty factions must always yield 'none'."""
    assert role("Fraktsiooni mittekuuluvad Riigikogu liikmed", "2023-05-15") == "none"
    assert role("", "2023-05-15") == "none"
    assert role(None, "2023-05-15") == "none"
    assert role("Eesti Reformierakonna fraktsioon", None) == "none"
