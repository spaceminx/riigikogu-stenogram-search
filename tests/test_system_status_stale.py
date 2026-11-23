"""/system/status reports datasets whose warning-only pipeline step keeps failing."""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient

from config import WARNING_STEP_FAILURES_FILE
from src.api import routes
from src.api.main import app
from src.load.loader import create_tables

client = TestClient(app)


def status_with_counts(tmp_path, monkeypatch, counts):
    create_tables()
    monkeypatch.setattr(routes, "DATABASE_DIR", str(tmp_path))
    if counts is not None:
        (tmp_path / WARNING_STEP_FAILURES_FILE).write_text(json.dumps(counts), encoding="utf-8")
    res = client.get("/system/status")
    assert res.status_code == 200
    return res.json()


def test_no_counter_file_means_nothing_stale(tmp_path, monkeypatch):
    data = status_with_counts(tmp_path, monkeypatch, None)
    assert data["stale_datasets"] == []


def test_two_failures_are_not_stale_three_are(tmp_path, monkeypatch):
    data = status_with_counts(
        tmp_path, monkeypatch, {"fetch_drafts": 3, "fetch_agenda": 2, "fetch_factions": 0}
    )
    assert data["stale_datasets"] == [
        {"dataset": "eelnõud", "step": "fetch_drafts", "failed_runs_in_a_row": 3}
    ]
    assert "eelnõud" in data["warning"]
    assert "päevakorrad" not in data["warning"]


def test_broken_counter_file_is_ignored(tmp_path, monkeypatch):
    create_tables()
    monkeypatch.setattr(routes, "DATABASE_DIR", str(tmp_path))
    (tmp_path / WARNING_STEP_FAILURES_FILE).write_text("{broken", encoding="utf-8")
    assert client.get("/system/status").json()["stale_datasets"] == []
    (tmp_path / WARNING_STEP_FAILURES_FILE).write_text('{"fetch_drafts": "x"}', encoding="utf-8")
    assert client.get("/system/status").json()["stale_datasets"] == []
