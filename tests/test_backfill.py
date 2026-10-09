import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
import requests

import config
from scripts.backfill_history import get_default_end_date, run_backfill, run_upload_only
from scripts.fetch_stenograms_api import parse_meeting_speeches
from scripts.upload_to_b2 import upload_to_b2


def seed_metadata(tmp_path):
    """Seed minimal valid metadata files required by run_backfill."""
    factions_file = tmp_path / "factions_map.json"
    factions_file.write_text(
        json.dumps(
            {
                "Jüri Ratas": [{"start": "2019-01-01", "end": "2030-01-01", "faction": "KESK"}],
                "Kõneleja": [{"start": "2019-01-01", "end": "2030-01-01", "faction": "REF"}],
                "Saadik 0": [{"start": "2019-01-01", "end": "2030-01-01", "faction": "REF"}],
            }
        ),
        encoding="utf-8",
    )
    persons_file = tmp_path / "persons.json"
    persons_file.write_text(
        json.dumps(
            [
                {"uuid": "uuid-juri", "full_name": "Jüri Ratas"},
                {"uuid": "uuid-koneleja", "full_name": "Kõneleja"},
            ]
        ),
        encoding="utf-8",
    )


def test_backfill_replaces_edited_session_and_preserves_aliases(tmp_path, monkeypatch):
    """Edited session replaces old speeches, linking previous external_ids and speech_keys."""
    monkeypatch.setattr("config.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("scripts.backfill_history.OUTPUT_DIR_PROCESSED", str(tmp_path))
    seed_metadata(tmp_path)

    year_file = tmp_path / "2019.jsonl"
    old_speech = {
        "date": "2019-04-04",
        "time": "1000",
        "source_file": "2019-04-04_1000.api",
        "source_url": "https://stenogrammid.riigikogu.ee/et/201904041000#PKP-1",
        "speaker": "Jüri Ratas",
        "speaker_role": "Peaminister",
        "speaker_uuid": None,
        "external_id": 19414011,
        "speech_key": "201904041000_1000_1_juri-ratas",
        "text": "Auväärt Riigikogu esimees, head rahvasaadikud!",
        "text_lemmas": "auväärt riigikogu esimees hea rahvasaadik",
        "status": "UNEDITED",
    }
    year_file.write_text(json.dumps(old_speech, ensure_ascii=False) + "\n", encoding="utf-8")

    # Mock verbatims response
    mock_verbatims = [
        {
            "link": "https://stenogrammid.riigikogu.ee/201904041000",
            "date": "2019-04-04T10:00:00.000+00:00",
            "title": "Täiskogu istung",
        }
    ]
    monkeypatch.setattr(
        "scripts.backfill_history.fetch_month_verbatims",
        lambda start, end, **kwargs: mock_verbatims,
    )

    # Mock rich meeting details
    mock_rich = {
        "meetingStatus": "EDITED",
        "stenograph": {
            "agendaItems": [
                {
                    "id": 1,
                    "name": "Päevakorrapunkt",
                    "speeches": [
                        {
                            "id": 19415122,
                            "name": "Jüri Ratas",
                            "speechType": "SPEECH",
                            "startTime": "2019-04-04T10:00:00Z",
                            "endTime": "2019-04-04T10:05:00Z",
                            "content": "<p>Auväärt Riigikogu esimees, head rahvasaadikud!</p>",
                        }
                    ],
                }
            ]
        },
    }
    monkeypatch.setattr(
        "scripts.backfill_history.fetch_rich_meeting_data",
        lambda code, **kwargs: mock_rich,
    )

    rep = run_backfill(
        year="2019",
        dry_run=False,
        sleep_delay=0,
        processed_dir=str(tmp_path),
    )

    assert rep["2019"]["replaced"] == 1
    assert rep["2019"]["added"] == 0

    lines = [json.loads(line) for line in year_file.read_text(encoding="utf-8").strip().split("\n")]
    assert len(lines) == 1
    sp = lines[0]
    assert sp["external_id"] == 19415122
    assert sp["status"] == "EDITED"
    assert sp.get("previous_external_ids") == [19414011]
    assert 19415122 not in sp["previous_external_ids"]


def test_backfill_under_90_percent_guard(tmp_path, monkeypatch):
    """Sessions with <90% speech count compared to existing dataset are not replaced and marked suspicious."""
    monkeypatch.setattr("config.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("scripts.backfill_history.OUTPUT_DIR_PROCESSED", str(tmp_path))
    seed_metadata(tmp_path)

    year_file = tmp_path / "2019.jsonl"
    # Seed 10 existing speeches
    existing_speeches = [
        {
            "date": "2019-04-04",
            "time": "1000",
            "source_file": "2019-04-04_1000.api",
            "speaker": f"Saadik {i}",
            "external_id": 1000 + i,
            "text": f"Kõnetekst number {i}",
            "text_lemmas": f"kõnetekst number {i}",
            "status": "UNEDITED",
        }
        for i in range(10)
    ]
    year_file.write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in existing_speeches) + "\n",
        encoding="utf-8",
    )

    mock_verbatims = [
        {
            "link": "https://stenogrammid.riigikogu.ee/201904041000",
            "date": "2019-04-04T10:00:00.000+00:00",
            "title": "Täiskogu istung",
        }
    ]
    monkeypatch.setattr(
        "scripts.backfill_history.fetch_month_verbatims",
        lambda start, end, **kwargs: mock_verbatims,
    )

    # Rich data only has 8 speeches (8 < 10 * 0.9 = 9)
    mock_rich = {
        "meetingStatus": "EDITED",
        "stenograph": {
            "agendaItems": [
                {
                    "id": 1,
                    "name": "Päevakord",
                    "speeches": [
                        {
                            "id": 2000 + i,
                            "name": f"Saadik {i}",
                            "speechType": "SPEECH",
                            "content": f"<p>Kõnetekst number {i}</p>",
                        }
                        for i in range(8)
                    ],
                }
            ]
        },
    }
    monkeypatch.setattr(
        "scripts.backfill_history.fetch_rich_meeting_data",
        lambda code, **kwargs: mock_rich,
    )

    rep = run_backfill(
        year="2019",
        dry_run=False,
        sleep_delay=0,
        processed_dir=str(tmp_path),
    )

    assert rep["2019"]["suspicious"] == 1
    assert rep["2019"]["replaced"] == 0
    assert "201904041000" in rep["2019"]["suspicious_sessions"]

    # File must retain original 10 speeches
    lines = [json.loads(line) for line in year_file.read_text(encoding="utf-8").strip().split("\n")]
    assert len(lines) == 10
    assert lines[0]["external_id"] == 1000


def test_lemma_cache_bypasses_lemmatize_text(monkeypatch):
    """When speech text matches cache, lemmatize_text is bypassed."""

    def fail_lemmatize(text):
        raise AssertionError("lemmatize_text must not be called when text is cached!")

    monkeypatch.setattr("scripts.fetch_stenograms_api.lemmatize_text", fail_lemmatize)

    rich_meeting = {
        "meetingStatus": "EDITED",
        "stenograph": {
            "agendaItems": [
                {
                    "id": 1,
                    "name": "Teema",
                    "speeches": [
                        {
                            "id": 555,
                            "name": "Jüri Ratas",
                            "speechType": "SPEECH",
                            "startTime": "2020-05-05T10:00:00Z",
                            "content": "<p>Tuntud kõnetekst.</p>",
                        }
                    ],
                }
            ]
        },
    }

    speeches, status = parse_meeting_speeches(
        rich_meeting=rich_meeting,
        verbatim=None,
        meeting_code="202005051000",
        verbatim_link="https://stenogrammid.riigikogu.ee/202005051000",
        date_formatted="2020-05-05",
        time_formatted="1000",
        source_file_key="2020-05-05_1000.api",
        faction_map={},
        lemma_cache={"Tuntud kõnetekst.": "tuntud kõnetekst cached"},
    )

    assert len(speeches) == 1
    assert speeches[0]["text_lemmas"] == "tuntud kõnetekst cached"


def test_default_end_date_boundary():
    """Default end-date is today minus UNEDITED_REFETCH_DAYS."""
    ref_date = datetime(2026, 10, 9, 12, 0, 0)
    expected = (ref_date - timedelta(days=config.UNEDITED_REFETCH_DAYS)).strftime("%Y-%m-%d")
    assert get_default_end_date(ref_date) == expected
    assert get_default_end_date(ref_date) == "2026-08-10"


def test_backfill_dry_run(tmp_path, monkeypatch):
    """In dry-run mode, disk files remain untouched while reports are generated."""
    monkeypatch.setattr("config.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("scripts.backfill_history.OUTPUT_DIR_PROCESSED", str(tmp_path))
    seed_metadata(tmp_path)

    year_file = tmp_path / "2019.jsonl"
    orig_content = json.dumps({"source_file": "2019-04-04_1000.api", "text": "Vana"}) + "\n"
    year_file.write_text(orig_content, encoding="utf-8")

    mock_verbatims = [
        {
            "link": "https://stenogrammid.riigikogu.ee/201904041000",
            "date": "2019-04-04T10:00:00.000+00:00",
        }
    ]
    monkeypatch.setattr(
        "scripts.backfill_history.fetch_month_verbatims",
        lambda start, end, **kwargs: mock_verbatims,
    )
    mock_rich = {
        "meetingStatus": "EDITED",
        "stenograph": {
            "agendaItems": [
                {
                    "id": 1,
                    "speeches": [
                        {
                            "id": 999,
                            "name": "Kõneleja",
                            "speechType": "SPEECH",
                            "content": "<p>Uus</p>",
                        }
                    ],
                }
            ]
        },
    }
    monkeypatch.setattr(
        "scripts.backfill_history.fetch_rich_meeting_data",
        lambda code, **kwargs: mock_rich,
    )

    rep = run_backfill(
        year="2019",
        dry_run=True,
        sleep_delay=0,
        processed_dir=str(tmp_path),
    )

    assert rep["2019"]["replaced"] == 1
    # File must not change on disk
    assert year_file.read_text(encoding="utf-8") == orig_content
    # State file must not be created
    assert not (tmp_path / "backfill_state.json").exists()


def test_backfill_resumption(tmp_path, monkeypatch):
    """Meetings listed in backfill_state.json are skipped on restart."""
    monkeypatch.setattr("config.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("scripts.backfill_history.OUTPUT_DIR_PROCESSED", str(tmp_path))
    seed_metadata(tmp_path)

    state_file = tmp_path / "backfill_state.json"
    state_file.write_text(
        json.dumps({"processed_meeting_codes": ["201904041000"]}),
        encoding="utf-8",
    )

    mock_verbatims = [
        {
            "link": "https://stenogrammid.riigikogu.ee/201904041000",
            "date": "2019-04-04T10:00:00.000+00:00",
        }
    ]
    monkeypatch.setattr(
        "scripts.backfill_history.fetch_month_verbatims",
        lambda start, end, **kwargs: mock_verbatims,
    )

    fetch_rich_mock = MagicMock()
    monkeypatch.setattr("scripts.backfill_history.fetch_rich_meeting_data", fetch_rich_mock)

    run_backfill(
        year="2019",
        dry_run=False,
        sleep_delay=0,
        processed_dir=str(tmp_path),
    )

    # Rich data must never be fetched because meeting code was already in state
    assert fetch_rich_mock.call_count == 0


def test_upload_to_b2_only_files_filter(tmp_path, monkeypatch):
    """upload_to_b2(only_files=...) only uploads specified files and ignores others."""
    monkeypatch.setattr("scripts.upload_to_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "test_key")
    monkeypatch.setenv("B2_APP_KEY", "test_secret")

    # Create local files
    (tmp_path / "2019.jsonl").write_text('{"text": "2019"}\n', encoding="utf-8")
    (tmp_path / "2026.jsonl").write_text('{"text": "2026"}\n', encoding="utf-8")
    (tmp_path / "attendance.jsonl").write_text('{"text": "att"}\n', encoding="utf-8")
    (tmp_path / "memberships.json").write_text("{}", encoding="utf-8")

    uploaded = []

    class MockS3Client:
        def head_object(self, Bucket, Key):
            return {"ContentLength": 10, "ETag": '"etag123"'}

        def upload_file(self, local_path, bucket, remote_key):
            uploaded.append(remote_key)

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

    ok = upload_to_b2(only_files=["2019.jsonl"])
    assert ok is True
    assert uploaded == ["2019.jsonl"]
    assert "2026.jsonl" not in uploaded
    assert "attendance.jsonl" not in uploaded


def test_upload_to_b2_etag_mismatch_refuses(tmp_path, monkeypatch):
    """upload_to_b2 refuses upload if remote ETag does not match expected ETag."""
    monkeypatch.setattr("scripts.upload_to_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "test_key")
    monkeypatch.setenv("B2_APP_KEY", "test_secret")

    (tmp_path / "2026.jsonl").write_text('{"text": "2026"}\n', encoding="utf-8")

    uploaded = []

    class MockS3Client:
        def head_object(self, Bucket, Key):
            # Remote file has changed in the meantime!
            return {"ContentLength": 10, "ETag": '"remote-has-new-etag"'}

        def upload_file(self, local_path, bucket, remote_key):
            uploaded.append(remote_key)

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: MockS3Client())

    ok = upload_to_b2(
        only_files=["2026.jsonl"],
        expected_etags={"2026.jsonl": "original-initial-etag"},
    )
    assert ok is False
    assert len(uploaded) == 0


def test_upload_only_with_year(tmp_path, monkeypatch):
    """--upload-only --year 2019 calls upload_to_b2(only_files=['2019.jsonl']) and makes NO HTTP requests."""
    monkeypatch.setattr("scripts.backfill_history.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("scripts.upload_to_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))

    requests_mock = MagicMock()
    monkeypatch.setattr(requests, "get", requests_mock)

    uploaded_calls = []

    def mock_upload_to_b2(only_files=None, expected_etags=None):
        uploaded_calls.append(only_files)
        return True

    monkeypatch.setattr("scripts.backfill_history.upload_to_b2", mock_upload_to_b2)

    ok = run_upload_only(year="2019", processed_dir=str(tmp_path))
    assert ok is True
    assert uploaded_calls == [["2019.jsonl"]]
    assert requests_mock.call_count == 0


def test_upload_only_without_year_from_report(tmp_path, monkeypatch):
    """--upload-only without --year reads backfill_report.json for modified files; fails with False if none."""
    monkeypatch.setattr("scripts.backfill_history.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("scripts.upload_to_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))

    report_file = tmp_path / "backfill_report.json"
    report_file.write_text(
        json.dumps(
            {
                "2020": {"replaced": 5, "added": 0},
                "2021": {"replaced": 0, "added": 1},
                "2022": {"replaced": 0, "added": 0},
            }
        ),
        encoding="utf-8",
    )

    uploaded_calls = []

    def mock_upload_to_b2(only_files=None, expected_etags=None):
        uploaded_calls.append(only_files)
        return True

    monkeypatch.setattr("scripts.backfill_history.upload_to_b2", mock_upload_to_b2)

    ok = run_upload_only(year=None, processed_dir=str(tmp_path))
    assert ok is True
    assert len(uploaded_calls) == 1
    assert set(uploaded_calls[0]) == {"2020.jsonl", "2021.jsonl"}

    # When report has no modified files, returns False
    report_file.write_text(json.dumps({"2022": {"replaced": 0, "added": 0}}), encoding="utf-8")
    assert run_upload_only(year=None, processed_dir=str(tmp_path)) is False

    # When report file is completely missing, returns False
    report_file.unlink()
    assert run_upload_only(year=None, processed_dir=str(tmp_path)) is False


def test_backfill_fails_on_missing_or_empty_metadata(tmp_path, monkeypatch):
    """run_backfill aborts immediately if factions_map.json or persons.json is missing or empty."""
    monkeypatch.setattr("config.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("scripts.backfill_history.OUTPUT_DIR_PROCESSED", str(tmp_path))

    requests_mock = MagicMock()
    monkeypatch.setattr(requests, "get", requests_mock)

    # 1. Missing factions_map.json
    with pytest.raises(RuntimeError, match="Missing required metadata file.*factions_map.json"):
        run_backfill(year="2019", processed_dir=str(tmp_path))
    assert requests_mock.call_count == 0

    # 2. Empty factions_map.json
    (tmp_path / "factions_map.json").write_text("{}", encoding="utf-8")
    (tmp_path / "persons.json").write_text(
        json.dumps([{"uuid": "u1", "full_name": "Saadik"}]), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="Metadata file.*factions_map.json is empty or invalid"):
        run_backfill(year="2019", processed_dir=str(tmp_path))
    assert requests_mock.call_count == 0

    # 3. Valid factions_map.json, but missing persons.json
    (tmp_path / "factions_map.json").write_text(
        json.dumps({"Saadik": [{"start": "2019", "end": "2030"}]}), encoding="utf-8"
    )
    (tmp_path / "persons.json").unlink()
    with pytest.raises(RuntimeError, match="Missing required metadata file.*persons.json"):
        run_backfill(year="2019", processed_dir=str(tmp_path))
    assert requests_mock.call_count == 0

    # 4. Empty persons.json
    (tmp_path / "persons.json").write_text("[]", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Metadata file.*persons.json is empty or invalid"):
        run_backfill(year="2019", processed_dir=str(tmp_path))
    assert requests_mock.call_count == 0


def test_skipped_no_rich_not_in_state_but_suspicious_is(tmp_path, monkeypatch):
    """Transient missing rich data is not saved to backfill_state.json; suspicious session is saved."""
    monkeypatch.setattr("config.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("scripts.backfill_history.OUTPUT_DIR_PROCESSED", str(tmp_path))
    seed_metadata(tmp_path)

    # Seed existing 2019.jsonl with session B (10 speeches)
    existing_speeches = [
        {
            "date": "2019-04-10",
            "time": "1000",
            "source_file": "2019-04-10_1000.api",
            "speaker": f"Saadik {i}",
            "external_id": 1000 + i,
            "text": f"Tekst {i}",
            "text_lemmas": f"tekst {i}",
            "status": "UNEDITED",
        }
        for i in range(10)
    ]
    (tmp_path / "2019.jsonl").write_text(
        "\n".join(json.dumps(s) for s in existing_speeches) + "\n",
        encoding="utf-8",
    )

    def mock_fetch_month(start, end, **kwargs):
        if "2019-04" in start:
            return [
                {
                    "link": "https://stenogrammid.riigikogu.ee/201904041000",
                    "date": "2019-04-04T10:00:00.000+00:00",
                },
                {
                    "link": "https://stenogrammid.riigikogu.ee/201904101000",
                    "date": "2019-04-10T10:00:00.000+00:00",
                },
            ]
        return []

    monkeypatch.setattr("scripts.backfill_history.fetch_month_verbatims", mock_fetch_month)

    def mock_fetch_rich(code, **kwargs):
        if code == "201904041000":
            # Session A has no rich data (skipped_no_rich)
            return None
        # Session B has 5 speeches (<90% of 10 -> suspicious)
        return {
            "meetingStatus": "EDITED",
            "stenograph": {
                "agendaItems": [
                    {
                        "id": 1,
                        "speeches": [
                            {
                                "id": 2000 + i,
                                "name": f"Saadik {i}",
                                "speechType": "SPEECH",
                                "content": f"<p>{i}</p>",
                            }
                            for i in range(5)
                        ],
                    }
                ]
            },
        }

    monkeypatch.setattr("scripts.backfill_history.fetch_rich_meeting_data", mock_fetch_rich)

    rep = run_backfill(year="2019", dry_run=False, sleep_delay=0, processed_dir=str(tmp_path))

    assert rep["2019"]["skipped_no_rich"] == 1
    assert rep["2019"]["suspicious"] == 1

    state_file = tmp_path / "backfill_state.json"
    assert state_file.exists()
    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    processed = state_data.get("processed_meeting_codes", [])

    # Session A must NOT be in state (so it is retried on resume)
    assert "201904041000" not in processed
    # Suspicious session B MUST be in state (awaiting human inspection)
    assert "201904101000" in processed


def test_multi_year_memory_cleanup(tmp_path, monkeypatch):
    """When crossing year boundary, previous year's dataset is written to file and evicted from memory."""
    monkeypatch.setattr("config.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("scripts.backfill_history.OUTPUT_DIR_PROCESSED", str(tmp_path))
    seed_metadata(tmp_path)

    # Seed 2019.jsonl and 2020.jsonl
    (tmp_path / "2019.jsonl").write_text(
        json.dumps(
            {"source_file": "2019-12-15_1000.api", "text": "2019 vana", "speaker": "Jüri Ratas"}
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "2020.jsonl").write_text(
        json.dumps(
            {"source_file": "2020-01-15_1000.api", "text": "2020 vana", "speaker": "Jüri Ratas"}
        )
        + "\n",
        encoding="utf-8",
    )

    def mock_fetch_month(start, end, **kwargs):
        if "2019-12" in start:
            return [
                {
                    "link": "https://stenogrammid.riigikogu.ee/201912151000",
                    "date": "2019-12-15T10:00:00.000+00:00",
                }
            ]
        if "2020-01" in start:
            return [
                {
                    "link": "https://stenogrammid.riigikogu.ee/202001151000",
                    "date": "2020-01-15T10:00:00.000+00:00",
                }
            ]
        return []

    monkeypatch.setattr("scripts.backfill_history.fetch_month_verbatims", mock_fetch_month)

    def mock_fetch_rich(code, **kwargs):
        return {
            "meetingStatus": "EDITED",
            "stenograph": {
                "agendaItems": [
                    {
                        "id": 1,
                        "speeches": [
                            {
                                "id": 111,
                                "name": "Jüri Ratas",
                                "speechType": "SPEECH",
                                "content": f"<p>{code}</p>",
                            }
                        ],
                    }
                ]
            },
        }

    monkeypatch.setattr("scripts.backfill_history.fetch_rich_meeting_data", mock_fetch_rich)

    tracked_year_speeches = {}
    rep = run_backfill(
        start_date="2019-12-01",
        end_date="2020-01-31",
        dry_run=False,
        sleep_delay=0,
        processed_dir=str(tmp_path),
        year_speeches_dict=tracked_year_speeches,
    )

    # Both years are reported in final report
    assert "2019" in rep
    assert "2020" in rep
    assert rep["2019"]["replaced"] == 1
    assert rep["2020"]["replaced"] == 1

    # After year transition and finalization, memory must be freed (tracked_year_speeches is empty)
    assert "2019" not in tracked_year_speeches
    assert "2020" not in tracked_year_speeches

    # Files must have been written to disk
    sp_2019 = json.loads((tmp_path / "2019.jsonl").read_text(encoding="utf-8").strip())
    assert sp_2019["external_id"] == 111
    sp_2020 = json.loads((tmp_path / "2020.jsonl").read_text(encoding="utf-8").strip())
    assert sp_2020["external_id"] == 111


def test_upload_to_b2_updates_etag_and_subsequent_upload_succeeds(tmp_path, monkeypatch):
    """After successful upload, .b2_etags.json is refreshed with new ETag; second upload does not conflict."""
    monkeypatch.setattr("scripts.upload_to_b2.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setenv("B2_KEY_ID", "test_key")
    monkeypatch.setenv("B2_APP_KEY", "test_secret")

    year_file = tmp_path / "2026.jsonl"
    year_file.write_text('{"text": "val"}\n', encoding="utf-8")

    etags_file = tmp_path / ".b2_etags.json"
    etags_file.write_text(json.dumps({"2026.jsonl": "initial-etag"}), encoding="utf-8")

    class StateMockS3Client:
        def __init__(self):
            self.current_remote_etag = "initial-etag"
            self.upload_count = 0

        def head_object(self, Bucket, Key):
            return {"ContentLength": 15, "ETag": f'"{self.current_remote_etag}"'}

        def upload_file(self, local_path, bucket, remote_key):
            self.upload_count += 1
            # Remote file now gets a new ETag in B2
            self.current_remote_etag = f"remote-etag-v{self.upload_count}"

    mock_client = StateMockS3Client()
    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: mock_client)

    # 1. First upload: matches initial-etag, succeeds, updates .b2_etags.json to remote-etag-v1
    ok1 = upload_to_b2(only_files=["2026.jsonl"])
    assert ok1 is True
    assert mock_client.upload_count == 1

    stored_etags = json.loads(etags_file.read_text(encoding="utf-8"))
    assert stored_etags["2026.jsonl"] == "remote-etag-v1"

    # 2. Second upload from same client: should read refreshed ETag, match remote-etag-v1, and succeed!
    ok2 = upload_to_b2(only_files=["2026.jsonl"])
    assert ok2 is True
    assert mock_client.upload_count == 2
    stored_etags_v2 = json.loads(etags_file.read_text(encoding="utf-8"))
    assert stored_etags_v2["2026.jsonl"] == "remote-etag-v2"
