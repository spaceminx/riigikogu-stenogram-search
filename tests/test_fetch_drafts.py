"""Tests for fetching the draft list from the Riigikogu API."""

import json
from pathlib import Path

import pytest

import scripts.fetch_drafts as fd
from src.fetch_models import UpstreamSchemaError

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "riigikogu_api"
PAGE = json.loads((FIXTURES_DIR / "drafts_list.json").read_text(encoding="utf-8"))
ITEMS = PAGE["_embedded"]["content"]


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _page(items, total, total_pages):
    return {
        "_embedded": {"content": items},
        "page": {
            "size": len(items),
            "totalElements": total,
            "totalPages": total_pages,
            "number": 0,
        },
    }


def _item(uuid, mark, membership):
    return {**ITEMS[0], "uuid": uuid, "mark": mark, "membership": membership}


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(fd.time, "sleep", lambda *_: None)


@pytest.fixture
def two_memberships(monkeypatch):
    monkeypatch.setattr(fd, "site_memberships", lambda: [14, 15])


def test_site_memberships_start_from_the_archive_start(monkeypatch):
    monkeypatch.setattr(
        fd,
        "load_membership_dates",
        lambda: {
            "13": ("2015-03-30", "2019-04-03"),
            "15": ("2023-04-10", "2099-12-31"),
            "14": ("2019-04-04", "2023-04-09"),
        },
    )
    # The archive starts with the XIII Riigikogu
    assert fd.site_memberships() == [13, 14, 15]
    monkeypatch.setattr(fd, "START_DATE", "2019-04-04")
    assert fd.site_memberships() == [14, 15]


def test_normalize_draft_keeps_the_list_fields():
    with_committee = next(i for i in ITEMS if i["leadingCommittee"])
    record = fd.normalize_draft(with_committee)

    assert record["uuid"] == with_committee["uuid"]
    assert record["membership"] == 14
    assert record["mark"] == with_committee["mark"]
    assert record["type_code"] == "OE"
    assert record["stage"] == with_committee["activeDraftStage"]
    assert record["status_date"] == with_committee["activeDraftStatusDate"]
    assert record["leading_committee"] == with_committee["leadingCommittee"]["name"]
    assert record["leading_committee_uuid"] == with_committee["leadingCommittee"]["uuid"]
    assert set(record) == {
        "uuid",
        "membership",
        "mark",
        "type_code",
        "title",
        "stage",
        "status",
        "status_date",
        "proceeding_status",
        "initiated",
        "leading_committee_uuid",
        "leading_committee",
    }

    no_committee = next(i for i in ITEMS if i["leadingCommittee"] is None)
    assert fd.normalize_draft(no_committee)["leading_committee"] is None


def test_writes_every_page_of_every_membership(tmp_path, monkeypatch, no_sleep, two_memberships):
    monkeypatch.setattr(fd, "OUTPUT_DIR_PROCESSED", str(tmp_path))
    requested = []
    pages = {
        ("14", "0"): _page([_item("a", 2, 14), _item("b", 1, 14)], 3, 2),
        ("14", "1"): _page([_item("c", 3, 14)], 3, 2),
        ("15", "0"): _page([_item("d", 1, 15)], 1, 1),
    }

    def fake_get(url, timeout=None):
        requested.append(url)
        query = dict(part.split("=") for part in url.split("?")[1].split("&"))
        return FakeResponse(200, pages[(query["membership"], query["page"])])

    monkeypatch.setattr(fd.requests, "get", fake_get)

    assert fd.fetch_drafts() is True
    saved = json.loads((tmp_path / "drafts.json").read_text(encoding="utf-8"))
    assert [(d["membership"], d["mark"]) for d in saved] == [(14, 1), (14, 2), (14, 3), (15, 1)]
    assert len(requested) == 3
    assert all("sort=mark,asc" in url for url in requested)


def test_an_empty_membership_is_not_an_error(tmp_path, monkeypatch, no_sleep):
    monkeypatch.setattr(fd, "OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr(fd, "site_memberships", lambda: [15, 16])

    def fake_get(url, timeout=None):
        if "membership=16" in url:
            return FakeResponse(200, _page([], 0, 0))
        return FakeResponse(200, _page([_item("d", 1, 15)], 1, 1))

    monkeypatch.setattr(fd.requests, "get", fake_get)

    assert fd.fetch_drafts() is True
    assert len(json.loads((tmp_path / "drafts.json").read_text(encoding="utf-8"))) == 1


def test_keeps_the_previous_file_when_a_page_fails(
    tmp_path, monkeypatch, no_sleep, two_memberships
):
    monkeypatch.setattr(fd, "OUTPUT_DIR_PROCESSED", str(tmp_path))
    previous = tmp_path / "drafts.json"
    previous.write_text('[{"kept": true}]', encoding="utf-8")

    def fake_get(url, timeout=None):
        if "membership=15" in url:
            return FakeResponse(429)
        return FakeResponse(200, _page([_item("a", 1, 14)], 1, 1))

    monkeypatch.setattr(fd.requests, "get", fake_get)

    assert fd.fetch_drafts() is False
    assert previous.read_text(encoding="utf-8") == '[{"kept": true}]'


def test_keeps_the_previous_file_when_drafts_are_missing(
    tmp_path, monkeypatch, no_sleep, two_memberships
):
    """A draft added while paging shifts the pages; fewer drafts than listed is a failed run."""
    monkeypatch.setattr(fd, "OUTPUT_DIR_PROCESSED", str(tmp_path))
    previous = tmp_path / "drafts.json"
    previous.write_text('[{"kept": true}]', encoding="utf-8")
    monkeypatch.setattr(
        fd.requests,
        "get",
        lambda url, timeout=None: FakeResponse(200, _page([_item("a", 1, 14)], 2, 1)),
    )

    assert fd.fetch_drafts() is False
    assert previous.read_text(encoding="utf-8") == '[{"kept": true}]'


def test_a_changed_response_shape_raises(tmp_path, monkeypatch, no_sleep, two_memberships):
    monkeypatch.setattr(fd, "OUTPUT_DIR_PROCESSED", str(tmp_path))
    broken = _page([{**ITEMS[0], "uuid": None}], 1, 1)
    monkeypatch.setattr(fd.requests, "get", lambda url, timeout=None: FakeResponse(200, broken))

    with pytest.raises(UpstreamSchemaError):
        fd.fetch_drafts()
    assert not (tmp_path / "drafts.json").exists()
