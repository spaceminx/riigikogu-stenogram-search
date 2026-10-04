import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_root_status():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_missing_query():
    # Calling /search without 'q' parameter should return 422 Unprocessable Entity
    response = client.get("/search")
    assert response.status_code == 422


def test_search_empty_query():
    # Calling /search with empty 'q' should return 422 (min_length=1)
    response = client.get("/search?q=")
    assert response.status_code == 422


def test_search_query_too_long():
    # Calling /search with >1000 characters should return 422 (max_length=1000)
    huge_query = "a" * 1001
    response = client.get(f"/search?q={huge_query}")
    assert response.status_code == 422


def test_search_activity_invalid_interval():
    # Invalid interval parameter should return 400 Bad Request
    response = client.get("/search/activity?q=mets&interval=hourly")
    assert response.status_code == 400
    assert "Intervall peab olema" in response.json()["detail"]
