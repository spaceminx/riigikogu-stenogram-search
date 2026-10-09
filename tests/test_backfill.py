import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import config
from scripts.backfill_history import get_default_end_date, run_backfill
from scripts.fetch_stenograms_api import parse_meeting_speeches
from scripts.upload_to_b2 import upload_to_b2


def test_backfill_replaces_edited_session_and_preserves_aliases(tmp_path, monkeypatch):
    """Edited session replaces old speeches, linking previous external_ids and speech_keys."""
    monkeypatch.setattr("config.OUTPUT_DIR_PROCESSED", str(tmp_path))
    monkeypatch.setattr("scripts.backfill_history.OUTPUT_DIR_PROCESSED", str(tmp_path))

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
