"""Helpers for generating mock API response dictionaries in tests."""

from __future__ import annotations

from typing import Any


def make_voting_detail(
    uuid: str = "mock-voting-uuid",
    voting_number: int | str = 1,
    start_date_time: str = "2026-10-15T10:00:00",
    type_code: str = "KOHALOLEKU_KONTROLL",
    voters: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Generate a realistic mock response for /api/votings/{uuid}."""
    base: dict[str, Any] = {
        "uuid": uuid,
        "votingNumber": voting_number,
        "type": {"code": type_code},
        "startDateTime": start_date_time,
        "voters": voters if voters is not None else [],
    }
    base.update(overrides)
    return base


def make_verbatim(
    date: str = "2026-10-15T10:00:00.000+00:00",
    link: str = "https://stenogrammid.riigikogu.ee/202610151000",
    edited: bool = True,
    agenda_items: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Generate a realistic mock response for an item in /api/steno/verbatims."""
    base: dict[str, Any] = {
        "date": date,
        "link": link,
        "edited": edited,
        "agendaItems": agenda_items if agenda_items is not None else [],
    }
    base.update(overrides)
    return base
