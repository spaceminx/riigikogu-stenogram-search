"""Input validation on API query parameters (audit SEC-4)."""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.load.loader import create_tables

create_tables()
client = TestClient(app)


@pytest.mark.parametrize(
    "url",
    [
        "/votings?start_date=garbage",
        "/votings?end_date=2024-13-99",
        "/votings?sitting_date=2024-02-30",
        "/search?q=eelarve&start_date=2024-13-99",
        "/search/activity?q=eelarve&end_date=2024-02-30",
    ],
)
def test_invalid_dates_are_rejected(url):
    assert client.get(url).status_code == 422


def test_valid_dates_are_accepted():
    assert client.get("/votings?start_date=2024-02-29&end_date=2024-03-01").status_code == 200


@pytest.mark.parametrize(
    "url",
    [
        "/votings?q=" + "a" * 201,
        "/persons?search=" + "a" * 101,
        "/drafts/some-uuid/speeches?offset=1000001",
    ],
)
def test_oversized_parameters_are_rejected(url):
    assert client.get(url).status_code == 422
