import json
import os
import subprocess
from unittest.mock import MagicMock

import pytest

import scripts.daily_pipeline as dp
from src.load.lock import sync_lock


def test_step_order_exactly_a_to_h(tmp_path, monkeypatch):
    """Verify daily pipeline executes steps in exact order from a to h."""
    monkeypatch.setattr(dp, "DATABASE_DIR", str(tmp_path / "db"))
    monkeypatch.setattr(dp, "OUTPUT_DIR_PROCESSED", str(tmp_path / "processed"))
    (tmp_path / "processed").mkdir(parents=True, exist_ok=True)

    calls = []

    def mock_run(cmd, *args, **kwargs):
        script_name = os.path.basename(cmd[1])
        calls.append(f"subprocess:{script_name}")
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    def mock_sync(*args, **kwargs):
        assert kwargs.get("skip_download") is True
        assert kwargs.get("skip_lock") is True
        calls.append("inprocess:sync_database")
        return True

    monkeypatch.setattr(dp.subprocess, "run", mock_run)
    monkeypatch.setattr(dp, "sync_database", mock_sync)

    exit_code = dp.run_daily_pipeline(no_upload=False)
    assert exit_code == 0

    expected_order = [
        "subprocess:download_from_b2.py",
        "subprocess:fetch_memberships.py",
        "subprocess:fetch_factions.py",
        "subprocess:fetch_faction_leaders.py",
        "subprocess:fetch_stenograms_api.py",
        "subprocess:fetch_attendance.py",
        "subprocess:fetch_votes.py",
        "subprocess:fetch_agenda.py",
        "subprocess:verify_pipeline_integrity.py",
        "subprocess:upload_to_b2.py",
        "inprocess:sync_database",
    ]
    assert calls == expected_order


def test_lock_held_exits_1_no_step_runs(tmp_path, monkeypatch, capsys):
    """If lock is already held, pipeline prints message and exits 1 without running any steps."""
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    lock_file = db_dir / ".sync.lock"

    monkeypatch.setattr(dp, "DATABASE_DIR", str(db_dir))
    monkeypatch.setattr(dp, "OUTPUT_DIR_PROCESSED", str(tmp_path / "processed"))

    mock_run = MagicMock()
    mock_sync = MagicMock()
    monkeypatch.setattr(dp.subprocess, "run", mock_run)
    monkeypatch.setattr(dp, "sync_database", mock_sync)

    # Another run holds the lock
    with sync_lock(database_dir=str(db_dir)):
        with pytest.raises(SystemExit) as exc_info:
            dp.run_daily_pipeline()
        assert lock_file.exists()

    assert exc_info.value.code == 1
    assert mock_run.call_count == 0
    assert mock_sync.call_count == 0

    captured = capsys.readouterr()
    assert "Sync already running" in captured.out


def test_download_fails_exits_1_no_fetch_upload_sync(tmp_path, monkeypatch):
    """If download_from_b2 fails, pipeline exits 1 immediately and skips later steps."""
    monkeypatch.setattr(dp, "DATABASE_DIR", str(tmp_path / "db"))
    monkeypatch.setattr(dp, "OUTPUT_DIR_PROCESSED", str(tmp_path / "processed"))

    calls = []

    def mock_run(cmd, *args, **kwargs):
        script_name = os.path.basename(cmd[1])
        calls.append(script_name)
        if script_name == "download_from_b2.py":
            return subprocess.CompletedProcess(args=cmd, returncode=1)
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    mock_sync = MagicMock()
    monkeypatch.setattr(dp.subprocess, "run", mock_run)
    monkeypatch.setattr(dp, "sync_database", mock_sync)

    exit_code = dp.run_daily_pipeline()
    assert exit_code == 1
    assert calls == ["download_from_b2.py"]
    assert mock_sync.call_count == 0


def test_fetch_memberships_fails_exit_0_if_all_else_ok(tmp_path, monkeypatch):
    """fetch_memberships failure is warning-only; pipeline uploads and exits 0."""
    monkeypatch.setattr(dp, "DATABASE_DIR", str(tmp_path / "db"))
    monkeypatch.setattr(dp, "OUTPUT_DIR_PROCESSED", str(tmp_path / "processed"))

    calls = []

    def mock_run(cmd, *args, **kwargs):
        script_name = os.path.basename(cmd[1])
        calls.append(script_name)
        if script_name == "fetch_memberships.py":
            return subprocess.CompletedProcess(args=cmd, returncode=1)
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(dp.subprocess, "run", mock_run)
    monkeypatch.setattr(dp, "sync_database", lambda **kw: True)

    exit_code = dp.run_daily_pipeline()
    assert exit_code == 0
    assert "upload_to_b2.py" in calls


def test_fetch_faction_leaders_fails_exit_0_if_all_else_ok(tmp_path, monkeypatch):
    """fetch_faction_leaders failure is warning-only; the previous faction_roles.json stays."""
    monkeypatch.setattr(dp, "DATABASE_DIR", str(tmp_path / "db"))
    monkeypatch.setattr(dp, "OUTPUT_DIR_PROCESSED", str(tmp_path / "processed"))

    def mock_run(cmd, *args, **kwargs):
        if os.path.basename(cmd[1]) == "fetch_faction_leaders.py":
            return subprocess.CompletedProcess(args=cmd, returncode=1)
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(dp.subprocess, "run", mock_run)
    monkeypatch.setattr(dp, "sync_database", lambda **kw: True)

    assert dp.run_daily_pipeline() == 0


def test_fetch_agenda_fails_exit_0_if_all_else_ok(tmp_path, monkeypatch):
    """fetch_agenda failure is warning-only; pipeline exits 0 if everything else succeeds."""
    monkeypatch.setattr(dp, "DATABASE_DIR", str(tmp_path / "db"))
    monkeypatch.setattr(dp, "OUTPUT_DIR_PROCESSED", str(tmp_path / "processed"))

    def mock_run(cmd, *args, **kwargs):
        script_name = os.path.basename(cmd[1])
        if script_name == "fetch_agenda.py":
            return subprocess.CompletedProcess(args=cmd, returncode=1)
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(dp.subprocess, "run", mock_run)
    monkeypatch.setattr(dp, "sync_database", lambda **kw: True)

    exit_code = dp.run_daily_pipeline()
    assert exit_code == 0


@pytest.mark.parametrize(
    "failing_script",
    [
        "fetch_stenograms_api.py",
        "fetch_attendance.py",
        "fetch_votes.py",
        "verify_pipeline_integrity.py",
    ],
)
def test_required_step_fails_skips_upload_still_syncs_exits_1(
    tmp_path, monkeypatch, failing_script
):
    """A failed required step skips the B2 upload; later steps and the DB sync still run."""
    monkeypatch.setattr(dp, "DATABASE_DIR", str(tmp_path / "db"))
    monkeypatch.setattr(dp, "OUTPUT_DIR_PROCESSED", str(tmp_path / "processed"))

    calls = []

    def mock_run(cmd, *args, **kwargs):
        script_name = os.path.basename(cmd[1])
        calls.append(script_name)
        if script_name == failing_script:
            return subprocess.CompletedProcess(args=cmd, returncode=1)
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    sync_called = False

    def mock_sync(**kw):
        nonlocal sync_called
        sync_called = True
        return True

    monkeypatch.setattr(dp.subprocess, "run", mock_run)
    monkeypatch.setattr(dp, "sync_database", mock_sync)

    exit_code = dp.run_daily_pipeline()
    assert exit_code == 1
    assert "verify_pipeline_integrity.py" in calls
    assert "upload_to_b2.py" not in calls
    assert sync_called is True


def test_integrity_reports_blocked_file_upload_skipped_and_restored_before_sync(
    tmp_path, monkeypatch
):
    """Blocked file from integrity_report is restored to pre-run snapshot before DB sync."""
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(dp, "DATABASE_DIR", str(db_dir))
    monkeypatch.setattr(dp, "OUTPUT_DIR_PROCESSED", str(processed_dir))

    # Pre-run file state
    sample_file = processed_dir / "2026.jsonl"
    sample_file.write_text("ORIGINAL_VALID_SPEECHES\n", encoding="utf-8")

    upload_called = False
    verified_content_during_sync = None

    def mock_run(cmd, *args, **kwargs):
        nonlocal upload_called
        script_name = os.path.basename(cmd[1])
        if script_name == "fetch_stenograms_api.py":
            # Simulate corrupted/truncated fetch during pipeline
            sample_file.write_text("CORRUPTED_TRUNCATED_SPEECHES\n", encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0)
        elif script_name == "verify_pipeline_integrity.py":
            # Report blocked file and return failure code
            report_path = processed_dir / "integrity_report.json"
            report_path.write_text(json.dumps({"blocked_files": ["2026.jsonl"]}), encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=1)
        elif script_name == "upload_to_b2.py":
            upload_called = True
            return subprocess.CompletedProcess(args=cmd, returncode=0)
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    def mock_sync(**kw):
        nonlocal verified_content_during_sync
        # Check that file content was restored to pre-run snapshot before sync
        verified_content_during_sync = sample_file.read_text(encoding="utf-8")
        return True

    monkeypatch.setattr(dp.subprocess, "run", mock_run)
    monkeypatch.setattr(dp, "sync_database", mock_sync)

    exit_code = dp.run_daily_pipeline()
    assert exit_code == 1  # Integrity failed
    assert upload_called is False
    assert verified_content_during_sync == "ORIGINAL_VALID_SPEECHES\n"


def test_no_upload_flag_skips_upload(tmp_path, monkeypatch):
    """When no_upload=True is specified, upload_to_b2.py is not executed."""
    monkeypatch.setattr(dp, "DATABASE_DIR", str(tmp_path / "db"))
    monkeypatch.setattr(dp, "OUTPUT_DIR_PROCESSED", str(tmp_path / "processed"))

    calls = []

    def mock_run(cmd, *args, **kwargs):
        script_name = os.path.basename(cmd[1])
        calls.append(script_name)
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(dp.subprocess, "run", mock_run)
    monkeypatch.setattr(dp, "sync_database", lambda **kw: True)

    exit_code = dp.run_daily_pipeline(no_upload=True)
    assert exit_code == 0
    assert "upload_to_b2.py" not in calls


def test_step_timeout_recorded_as_failed_and_lock_released(tmp_path, monkeypatch):
    """Step timeout is recorded as a failure and the sync lock is cleanly released."""
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    lock_file = db_dir / ".sync.lock"

    monkeypatch.setattr(dp, "DATABASE_DIR", str(db_dir))
    monkeypatch.setattr(dp, "OUTPUT_DIR_PROCESSED", str(tmp_path / "processed"))

    def mock_run(cmd, *args, **kwargs):
        script_name = os.path.basename(cmd[1])
        if script_name == "fetch_votes.py":
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=1800)
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(dp.subprocess, "run", mock_run)
    monkeypatch.setattr(dp, "sync_database", lambda **kw: True)

    exit_code = dp.run_daily_pipeline()
    assert exit_code == 1
    # Ensure lock was released
    assert not lock_file.exists()


def test_cli_main_argument_parsing(monkeypatch):
    """Verify CLI main() dispatches --no-upload and --no-sync to run_daily_pipeline."""
    dispatched = {}

    def mock_pipeline(no_upload=False, no_sync=False):
        dispatched["no_upload"] = no_upload
        dispatched["no_sync"] = no_sync
        return 0

    monkeypatch.setattr(dp, "run_daily_pipeline", mock_pipeline)
    monkeypatch.setattr(dp.sys, "argv", ["daily_pipeline.py", "--no-upload"])
    assert dp.main() == 0
    assert dispatched == {"no_upload": True, "no_sync": False}

    monkeypatch.setattr(dp.sys, "argv", ["daily_pipeline.py", "--no-sync"])
    assert dp.main() == 0
    assert dispatched == {"no_upload": False, "no_sync": True}


def test_no_sync_flag_uploads_but_skips_sync(tmp_path, monkeypatch):
    """no_sync=True (the GitHub Actions fallback) still uploads but never touches the database."""
    monkeypatch.setattr(dp, "DATABASE_DIR", str(tmp_path / "db"))
    monkeypatch.setattr(dp, "OUTPUT_DIR_PROCESSED", str(tmp_path / "processed"))

    calls = []

    def mock_run(cmd, *args, **kwargs):
        calls.append(os.path.basename(cmd[1]))
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    mock_sync = MagicMock(return_value=True)
    monkeypatch.setattr(dp.subprocess, "run", mock_run)
    monkeypatch.setattr(dp, "sync_database", mock_sync)

    assert dp.run_daily_pipeline(no_sync=True) == 0
    assert "upload_to_b2.py" in calls
    assert mock_sync.call_count == 0


def test_snapshot_only_active_years_speech_files(tmp_path, monkeypatch):
    """Snapshot only copies {year}.jsonl for active years and skips missing or other files."""
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()

    # Create various files
    (source_dir / "2026.jsonl").write_text("2026 speeches\n", encoding="utf-8")
    (source_dir / "2021.jsonl").write_text("historical speeches\n", encoding="utf-8")
    (source_dir / "attendance.jsonl").write_text("attendance\n", encoding="utf-8")
    (source_dir / "factions.json").write_text("factions\n", encoding="utf-8")

    monkeypatch.setattr(dp, "active_years", lambda: ["2026", "2025"])  # 2025 is missing

    count = dp.snapshot_processed_files(str(source_dir), str(target_dir))
    assert count == 1
    assert (target_dir / "2026.jsonl").exists()
    assert not (target_dir / "2025.jsonl").exists()
    assert not (target_dir / "2021.jsonl").exists()
    assert not (target_dir / "attendance.jsonl").exists()
    assert not (target_dir / "factions.json").exists()


def test_stale_integrity_report_cleared_before_verify_step(tmp_path, monkeypatch):
    """Stale integrity report is deleted before verify step; if verify fails without writing report, file is not restored."""
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(dp, "DATABASE_DIR", str(db_dir))
    monkeypatch.setattr(dp, "OUTPUT_DIR_PROCESSED", str(processed_dir))
    monkeypatch.setattr(dp, "active_years", lambda: ["2026"])

    sample_file = processed_dir / "2026.jsonl"
    sample_file.write_text("OLD_INITIAL_DATA\n", encoding="utf-8")

    # Stale report from yesterday
    stale_report = processed_dir / "integrity_report.json"
    stale_report.write_text(json.dumps({"blocked_files": ["2026.jsonl"]}), encoding="utf-8")

    verified_sync_data = None
    report_existed_during_sync = None

    def mock_run(cmd, *args, **kwargs):
        script_name = os.path.basename(cmd[1])
        if script_name == "fetch_stenograms_api.py":
            sample_file.write_text("NEW_FETCHED_DATA\n", encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0)
        elif script_name == "verify_pipeline_integrity.py":
            # Crashes without writing a new integrity_report.json
            return subprocess.CompletedProcess(args=cmd, returncode=1)
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    def mock_sync(**kw):
        nonlocal verified_sync_data, report_existed_during_sync
        verified_sync_data = sample_file.read_text(encoding="utf-8")
        report_existed_during_sync = stale_report.exists()
        return True

    monkeypatch.setattr(dp.subprocess, "run", mock_run)
    monkeypatch.setattr(dp, "sync_database", mock_sync)

    exit_code = dp.run_daily_pipeline()
    assert exit_code == 1
    assert report_existed_during_sync is False
    assert verified_sync_data == "NEW_FETCHED_DATA\n"


@pytest.mark.parametrize(
    "script_name",
    ["fetch_memberships.py", "fetch_factions.py", "fetch_faction_leaders.py", "fetch_agenda.py"],
)
def test_schema_change_in_warning_step_fails_run(tmp_path, monkeypatch, script_name):
    """Exit code 2 (upstream schema change) fails the run and skips the upload, even in
    warning-only steps."""
    monkeypatch.setattr(dp, "DATABASE_DIR", str(tmp_path / "db"))
    monkeypatch.setattr(dp, "OUTPUT_DIR_PROCESSED", str(tmp_path / "processed"))

    calls = []

    def mock_run(cmd, *args, **kwargs):
        calls.append(os.path.basename(cmd[1]))
        if os.path.basename(cmd[1]) == script_name:
            return subprocess.CompletedProcess(args=cmd, returncode=2)
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr(dp.subprocess, "run", mock_run)
    monkeypatch.setattr(dp, "sync_database", lambda **kw: True)

    assert dp.run_daily_pipeline() == 1
    assert "upload_to_b2.py" not in calls


def test_unverified_integrity_fails_run_and_skips_upload(tmp_path, monkeypatch):
    """Integrity exit 3 (unverified) fails the run, skips the B2 upload and still syncs."""
    monkeypatch.setattr(dp, "DATABASE_DIR", str(tmp_path / "db"))
    monkeypatch.setattr(dp, "OUTPUT_DIR_PROCESSED", str(tmp_path / "processed"))

    upload_called = False
    sync_called = False

    def mock_run(cmd, *args, **kwargs):
        nonlocal upload_called
        script_name = os.path.basename(cmd[1])
        if script_name == "verify_pipeline_integrity.py":
            return subprocess.CompletedProcess(args=cmd, returncode=3)
        if script_name == "upload_to_b2.py":
            upload_called = True
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    def mock_sync(**kw):
        nonlocal sync_called
        sync_called = True
        return True

    monkeypatch.setattr(dp.subprocess, "run", mock_run)
    monkeypatch.setattr(dp, "sync_database", mock_sync)

    assert dp.run_daily_pipeline() == 1
    assert upload_called is False
    assert sync_called is True
