#!/usr/bin/env python3
"""Server daily data pipeline for Riigikogu stenogram search.

Executes under a single database/.sync.lock:
1. download_from_b2.py (skip all later steps on failure)
2. Snapshot processed files
3. fetch_memberships.py, fetch_factions.py (warning-only on failure)
4. fetch_stenograms_api.py, fetch_attendance.py, fetch_votes.py
5. verify_pipeline_integrity.py
6. upload_to_b2.py (skipped with --no-upload)
7. Restore blocked_files from snapshot before DB sync
8. sync_database(skip_download=True, skip_lock=True) in-process
9. Print summary and exit (0 only if all required steps succeeded, else 1)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import DATABASE_DIR, OUTPUT_DIR_PROCESSED, PROJECT_ROOT, active_years
from scripts.sync_database import sync_database
from scripts.verify_pipeline_integrity import INTEGRITY_UNVERIFIED_EXIT_CODE
from src.load.lock import sync_lock

STEP_TIMEOUT_SECONDS = 30 * 60  # 30 minutes per step
UPSTREAM_SCHEMA_EXIT_CODE = 2  # fetchers exit 2 on UpstreamSchemaError
SCHEMA_CHANGE_ERROR = f"upstream API schema changed (exit code {UPSTREAM_SCHEMA_EXIT_CODE})"
INTEGRITY_UNVERIFIED_ERROR = (
    f"integrity could not be verified (exit code {INTEGRITY_UNVERIFIED_EXIT_CODE})"
)


def run_subprocess_step(
    script_rel_path: str,
    args: list[str] | None = None,
    timeout: int = STEP_TIMEOUT_SECONDS,
) -> tuple[bool, float, str]:
    """Run a Python script as a subprocess with timeout.

    Returns:
        (success, duration_seconds, error_message)
    """
    script_path = os.path.join(PROJECT_ROOT, script_rel_path)
    cmd = [sys.executable, script_path] + (args or [])
    env = dict(os.environ)
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{PROJECT_ROOT}:{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = PROJECT_ROOT

    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env, timeout=timeout)
        duration = time.time() - t0
        if proc.returncode == 0:
            return True, duration, ""
        if proc.returncode == UPSTREAM_SCHEMA_EXIT_CODE:
            return False, duration, SCHEMA_CHANGE_ERROR
        if proc.returncode == INTEGRITY_UNVERIFIED_EXIT_CODE:
            return False, duration, INTEGRITY_UNVERIFIED_ERROR
        return False, duration, f"exited with code {proc.returncode}"
    except subprocess.TimeoutExpired:
        duration = time.time() - t0
        err = f"timed out after {timeout}s"
        print(f"Error: Step {script_rel_path} {err}")
        return False, duration, err
    except Exception as e:
        duration = time.time() - t0
        err = str(e)
        print(f"Error: Step {script_rel_path} raised exception: {err}")
        return False, duration, err


def warning_step_note(ok: bool, err: str) -> str:
    """Step note for warning-only steps; a schema change is a failure, not a warning."""
    if ok:
        return ""
    return err if err == SCHEMA_CHANGE_ERROR else "warning only"


def snapshot_processed_files(source_dir: str, target_dir: str) -> int:
    """Copy active-year speech JSONL files from source_dir to target_dir. Returns file count."""
    count = 0
    if not os.path.exists(source_dir):
        return count
    for yr in active_years():
        fname = f"{yr}.jsonl"
        src_file = os.path.join(source_dir, fname)
        if os.path.isfile(src_file):
            shutil.copy2(src_file, os.path.join(target_dir, fname))
            count += 1
    return count


def restore_blocked_files_from_snapshot(snapshot_dir: str, processed_dir: str) -> list[str]:
    """Restore files listed in integrity_report.json blocked_files from snapshot."""
    report_path = os.path.join(processed_dir, "integrity_report.json")
    blocked_files: list[str] = []
    if os.path.exists(report_path):
        try:
            with open(report_path, encoding="utf-8") as f:
                report_data = json.load(f)
            blocked_files = report_data.get("blocked_files", [])
        except Exception as e:
            print(f"Warning: Could not read integrity report {report_path}: {e}")

    restored = []
    for fname in blocked_files:
        snap_file = os.path.join(snapshot_dir, fname)
        target_file = os.path.join(processed_dir, fname)
        if os.path.exists(snap_file):
            shutil.copy2(snap_file, target_file)
            restored.append(fname)
            print(f"Notice: Restored blocked file {fname} from snapshot before DB sync.")
        elif os.path.exists(target_file):
            os.remove(target_file)
            restored.append(fname)
            print(f"Notice: Removed blocked file {fname} (not present in snapshot) before DB sync.")
    return restored


def print_pipeline_summary(step_records: list[dict], overall_success: bool) -> None:
    """Print structured summary table of all pipeline steps."""
    print("\n" + "=" * 60)
    print("DAILY PIPELINE SUMMARY")
    print("=" * 60)
    for s in step_records:
        dur = f"({s['duration']:.2f}s)"
        note = f" [{s['note']}]" if s.get("note") else ""
        print(f"  {s['name']:<30} {s['status']:<10} {dur:>10}{note}")
    print("=" * 60)
    if overall_success:
        print("PIPELINE RESULT: SUCCESS")
    else:
        print("PIPELINE RESULT: FAILED")
    print("=" * 60)


def run_daily_pipeline(no_upload: bool = False) -> int:
    """Run the daily pipeline. Returns exit code (0 on success, 1 on failure)."""
    step_records: list[dict] = []
    required_failures: list[str] = []

    # a. Acquire lock
    print("Acquiring sync lock for daily pipeline...")
    with sync_lock(database_dir=DATABASE_DIR):
        print("Sync lock acquired.")

        # b. download_from_b2.py
        print("\n--- Step 1: Download from Backblaze B2 ---")
        ok, dur, err = run_subprocess_step("scripts/download_from_b2.py")
        step_records.append(
            {
                "name": "download_from_b2",
                "status": "ok" if ok else "failed",
                "duration": dur,
                "note": err,
            }
        )
        if not ok:
            print("Error: B2 download failed. Skipping all remaining pipeline steps.")
            required_failures.append("download_from_b2")
            print_pipeline_summary(step_records, overall_success=False)
            return 1

        # c. Snapshot data/processed
        snapshot_dir = tempfile.mkdtemp(prefix="pipeline_snapshot_")
        try:
            snap_count = snapshot_processed_files(OUTPUT_DIR_PROCESSED, snapshot_dir)
            print(f"Snapshotted {snap_count} files from processed directory to {snapshot_dir}")

            # d. Fetch steps
            # Warning only steps:
            print("\n--- Step 2: Fetch Parliamentary Memberships ---")
            m_ok, m_dur, m_err = run_subprocess_step("scripts/fetch_memberships.py")
            step_records.append(
                {
                    "name": "fetch_memberships",
                    "status": "ok" if m_ok else "failed",
                    "duration": m_dur,
                    "note": warning_step_note(m_ok, m_err),
                }
            )
            if not m_ok:
                print(f"Warning: fetch_memberships failed ({m_err}). Continuing.")
                if m_err == SCHEMA_CHANGE_ERROR:
                    required_failures.append("fetch_memberships")

            print("\n--- Step 3: Fetch Member Factions ---")
            f_ok, f_dur, f_err = run_subprocess_step("scripts/fetch_factions.py")
            step_records.append(
                {
                    "name": "fetch_factions",
                    "status": "ok" if f_ok else "failed",
                    "duration": f_dur,
                    "note": warning_step_note(f_ok, f_err),
                }
            )
            if not f_ok:
                print(f"Warning: fetch_factions failed ({f_err}). Continuing.")
                if f_err == SCHEMA_CHANGE_ERROR:
                    required_failures.append("fetch_factions")

            # Required fetch steps (continue on error, but record failure):
            print("\n--- Step 4: Fetch Stenograms API ---")
            st_ok, st_dur, st_err = run_subprocess_step("scripts/fetch_stenograms_api.py")
            step_records.append(
                {
                    "name": "fetch_stenograms_api",
                    "status": "ok" if st_ok else "failed",
                    "duration": st_dur,
                    "note": st_err,
                }
            )
            if not st_ok:
                required_failures.append("fetch_stenograms_api")

            print("\n--- Step 5: Fetch Attendance ---")
            att_ok, att_dur, att_err = run_subprocess_step("scripts/fetch_attendance.py")
            step_records.append(
                {
                    "name": "fetch_attendance",
                    "status": "ok" if att_ok else "failed",
                    "duration": att_dur,
                    "note": att_err,
                }
            )
            if not att_ok:
                required_failures.append("fetch_attendance")

            print("\n--- Step 6: Fetch Votes ---")
            vt_ok, vt_dur, vt_err = run_subprocess_step("scripts/fetch_votes.py")
            step_records.append(
                {
                    "name": "fetch_votes",
                    "status": "ok" if vt_ok else "failed",
                    "duration": vt_dur,
                    "note": vt_err,
                }
            )
            if not vt_ok:
                required_failures.append("fetch_votes")

            print("\n--- Step 6b: Fetch Agenda Items ---")
            ag_ok, ag_dur, ag_err = run_subprocess_step("scripts/fetch_agenda.py")
            step_records.append(
                {
                    "name": "fetch_agenda",
                    "status": "ok" if ag_ok else "failed",
                    "duration": ag_dur,
                    "note": warning_step_note(ag_ok, ag_err),
                }
            )
            if not ag_ok:
                print(f"Warning: fetch_agenda failed ({ag_err}). Continuing.")
                if ag_err == SCHEMA_CHANGE_ERROR:
                    required_failures.append("fetch_agenda")

            # e. verify_pipeline_integrity.py (failure recorded, but continue)
            print("\n--- Step 7: Verify Pipeline Integrity ---")
            stale_report = os.path.join(OUTPUT_DIR_PROCESSED, "integrity_report.json")
            if os.path.exists(stale_report):
                try:
                    os.remove(stale_report)
                    print(f"Removed stale integrity report: {stale_report}")
                except Exception as e:
                    print(f"Warning: Could not remove stale integrity report {stale_report}: {e}")
            int_ok, int_dur, int_err = run_subprocess_step("scripts/verify_pipeline_integrity.py")
            step_records.append(
                {
                    "name": "verify_pipeline_integrity",
                    "status": "ok" if int_ok else "failed",
                    "duration": int_dur,
                    "note": int_err,
                }
            )
            if not int_ok:
                required_failures.append("verify_pipeline_integrity")

            # f. upload_to_b2.py (skips blocked_files automatically)
            print("\n--- Step 8: Upload to Backblaze B2 ---")
            if no_upload:
                print("Skipping upload_to_b2 (--no-upload specified).")
                step_records.append(
                    {
                        "name": "upload_to_b2",
                        "status": "skipped",
                        "duration": 0.0,
                        "note": "--no-upload",
                    }
                )
            elif int_err == INTEGRITY_UNVERIFIED_ERROR:
                # B2 is the rebuild source; only verified data goes there. The next run uploads.
                print("Skipping upload_to_b2: integrity could not be verified.")
                step_records.append(
                    {
                        "name": "upload_to_b2",
                        "status": "skipped",
                        "duration": 0.0,
                        "note": "integrity unverified",
                    }
                )
            else:
                up_ok, up_dur, up_err = run_subprocess_step("scripts/upload_to_b2.py")
                step_records.append(
                    {
                        "name": "upload_to_b2",
                        "status": "ok" if up_ok else "failed",
                        "duration": up_dur,
                        "note": up_err,
                    }
                )
                if not up_ok:
                    required_failures.append("upload_to_b2")

            # g. Restore blocked files from snapshot so bad data never reaches DB
            print("\n--- Step 9: Restore Blocked Files from Snapshot ---")
            restored = restore_blocked_files_from_snapshot(snapshot_dir, OUTPUT_DIR_PROCESSED)
            if restored:
                print(f"Restored files: {restored}")
            else:
                print("No blocked files required restoring.")

            # h. DB sync in-process with skip_download=True, skip_lock=True
            print("\n--- Step 10: In-Process Database Sync ---")
            t_sync_start = time.time()
            try:
                sync_ok = sync_database(skip_download=True, skip_lock=True)
                sync_dur = time.time() - t_sync_start
                step_records.append(
                    {
                        "name": "sync_database",
                        "status": "ok" if sync_ok else "failed",
                        "duration": sync_dur,
                        "note": "" if sync_ok else "sync reported errors",
                    }
                )
                if not sync_ok:
                    required_failures.append("sync_database")
            except Exception as sync_e:
                sync_dur = time.time() - t_sync_start
                step_records.append(
                    {
                        "name": "sync_database",
                        "status": "failed",
                        "duration": sync_dur,
                        "note": str(sync_e),
                    }
                )
                required_failures.append("sync_database")

        finally:
            shutil.rmtree(snapshot_dir, ignore_errors=True)

        overall_success = len(required_failures) == 0
        print_pipeline_summary(step_records, overall_success=overall_success)
        return 0 if overall_success else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Riigikogu daily data pipeline")
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip uploading processed data to Backblaze B2",
    )
    args = parser.parse_args()
    return run_daily_pipeline(no_upload=args.no_upload)


if __name__ == "__main__":
    sys.exit(main())
