import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.load.database import SessionLocal, engine
from src.load.models import Attendance, Base

client = TestClient(app)


@pytest.fixture(autouse=True, scope="session")
def setup_test_database():
    """Ensure database schema and test data exist in CI environment."""
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    if session.query(Attendance).count() == 0:
        test_records = [
            Attendance(
                session_date="2023-05-01T10:00:00",
                voting_uuid="test-uuid-1",
                member_name="Jaan Tamm",
                faction="Eesti 200 fraktsioon",
                status="KOHAL",
            ),
            Attendance(
                session_date="2023-05-01T10:00:00",
                voting_uuid="test-uuid-1",
                member_name="Kati Kask",
                faction="Isamaa fraktsioon",
                status="PUUDUB",
            ),
            Attendance(
                session_date="2021-05-01T10:00:00",
                voting_uuid="test-uuid-2",
                member_name="Jaan Tamm",
                faction="Eesti Keskerakonna fraktsioon",
                status="KOHAL",
            ),
        ]
        session.add_all(test_records)
        session.commit()
    session.close()


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


def test_attendance_stats_default():
    response = client.get("/attendance/stats")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        item = data[0]
        assert "member_name" in item
        assert "faction" in item
        assert "total_sessions" in item
        assert "present_sessions" in item
        assert "attendance_percentage" in item


def test_attendance_stats_membership_filter():
    response_xv = client.get("/attendance/stats?membership=15")
    assert response_xv.status_code == 200
    response_xiv = client.get("/attendance/stats?membership=14")
    assert response_xiv.status_code == 200
    response_all = client.get("/attendance/stats?membership=all")
    assert response_all.status_code == 200


def test_attendance_stats_faction_filter():
    response = client.get("/attendance/stats?faction=Isamaa fraktsioon")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for item in data:
        assert item["faction"] == "Isamaa fraktsioon"


def test_attendance_stats_active_only():
    response = client.get("/attendance/stats?membership=15&active_only=true")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 101


def test_attendance_factions_stats():
    response = client.get("/attendance/factions?membership=15")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if data:
        item = data[0]
        assert "faction" in item
        assert "member_count" in item
        assert "total_sessions" in item
        assert "present_sessions" in item
        assert "attendance_percentage" in item


def test_attendance_factions_list():
    response = client.get("/attendance/factions/list?membership=15")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert "Eesti 200 fraktsioon" in data
