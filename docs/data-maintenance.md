# Data Maintenance

## Build / Initialize the Database
Build the full SQLite database (downloads data from B2, lemmatizes speeches with multiprocessing, builds term indexes):
```bash
python scripts/build_full_database.py
```

*Note on historical data updates:*
The server daily pipeline (`daily_pipeline.py` via cron) only downloads data for active years from B2 (the current year, plus the previous year as long as it falls within the 60-day window until around March 1st) and only updates new or unedited sessions. If historical data from previous years is backfilled or modified, `build_full_database.py` will skip already existing sessions in the database. To apply historical updates, you must build a new database file, stop the API, swap the file, and check for WAL temporary files:
```bash
docker compose run --rm pipeline python scripts/download_from_b2.py --all

# 1. Build the new database in the pipeline container (where B2 credentials live)
docker compose run --rm -e DATABASE_URL=sqlite:///database/riigikogu_new.sqlite pipeline python scripts/build_full_database.py

# 2. Stop the API and clean up old WAL temporary files
docker compose stop backend
rm -f database/riigikogu.sqlite-wal database/riigikogu.sqlite-shm

# 3. Ensure the new database file also doesn't have an orphaned .sqlite-wal next to it
if [ -f database/riigikogu_new.sqlite-wal ]; then echo "ERROR: New database WAL file exists, data is not fully committed!"; exit 1; fi

# 4. Swap the database file and restart
mv database/riigikogu_new.sqlite database/riigikogu.sqlite
docker compose start backend
```

## Historical Data Backfill (`backfill_history.py`)
To backfill rich metadata (`external_id`, `ems_id`, `speech_type`, `start_time`, `end_time`, `duration_seconds`) for historical sessions (2019–2026):
1. Download all historical dataset files from B2:
   ```bash
   python scripts/download_from_b2.py --all
   ```
2. Run a dry run for a specific year to inspect changes and the summary report:
   ```bash
   python scripts/backfill_history.py --year 2021 --dry-run
   ```
3. Run the backfill year by year with `--upload`, or run backfill first and upload separately:
   ```bash
   python scripts/backfill_history.py --year 2021 --upload
   # or run backfill first, then upload separately:
   # python scripts/backfill_history.py --year 2021
   # python scripts/backfill_history.py --upload-only --year 2021
   ```
4. On the server: rebuild the database following the instructions above under "Build / Initialize the Database" -> "Note on historical data updates" (build new file with `DATABASE_URL` in container, `docker compose stop backend`, verify WAL, `mv`, `docker compose start backend`).

> [!NOTE]
> The default end date (today minus `UNEDITED_REFETCH_DAYS`) skips recently edited sessions that old code already saved as edited (e.g. September 2026). The daily pipeline will also not touch them. To backfill these recent sessions, run explicitly:
> ```bash
> python scripts/backfill_history.py --start-date 2026-09-01 --end-date <today> --upload
> ```
> The current year dataset file in B2 is protected against concurrency conflicts by ETag validation.

## Historical Voting Data Initial Load (One-Off)

Initial loading of voting history (2019 to present) is performed on the server inside container services.

Exact sequence:
1. Load 2019 votings (from the start of the 14th Riigikogu on 2019-04-01) and upload to Backblaze B2:
   ```bash
   docker compose run --rm pipeline python scripts/fetch_votes.py --start-date 2019-04-01 --end-date 2019-12-31 --upload
   ```
2. Load years 2020–2025 in a yearly loop and upload to B2:
   ```bash
   for y in {2020..2025}; do
     docker compose run --rm pipeline python scripts/fetch_votes.py --start-date ${y}-01-01 --end-date ${y}-12-31 --upload
   done
   ```
3. Load current 2026 votings and upload to B2:
   ```bash
   docker compose run --rm pipeline python scripts/fetch_votes.py --start-date 2026-01-01 --upload
   ```
4. Load all votings into the server SQLite database:
   ```bash
   docker compose exec backend python scripts/load_votes.py
   ```
5. Verification:
   ```bash
   curl http://127.0.0.1:8000/system/status
   # votings = 3621 + added after Oct 13

   curl "http://127.0.0.1:8000/votings?start_date=2026-09-29&end_date=2026-09-29"
   ```

> [!NOTE]
> **Important deployment notes:**
> - Until step 3 is completed, the daily pipeline only fetches the last 14 days.
> - **Execution timing:** Years 2019–2025 can be run at any time, as the server daily pipeline only downloads active-year files and does not overwrite older votes files in B2. Only the 2026 run (step 3) must not run around 07:00 server local time (when the server daily pipeline runs).
> - **Fault tolerance:** The script saves checkpoints every 25 votes and handles interruptions (Ctrl-C / SIGTERM). If any year exits with code 1 (e.g. temporary API network error), re-run the command for that year — already saved votes are skipped and loading resumes from where it left off.
> - **Estimated runtimes by year** (~5.1 s per vote):
>   - 2019: 172 votes → ~15 min
>   - 2020: 356 votes → ~30 min
>   - 2021: 533 votes → ~45 min
>   - 2022: 718 votes → ~61 min
>   - 2023: 436 votes → ~37 min
>   - 2024: 692 votes → ~59 min
>   - 2025: 402 votes → ~34 min
>   - 2026: 312 votes → ~27 min

## Maintenance & UUID Repair

To resolve and maintain canonical member UUIDs across speeches (attendance records get theirs from the API):

### Speaker UUIDs (`repair_speaker_uuids.py`)
Resolves MP UUIDs across speeches in historical JSONL datasets and the SQLite database:
1. Ensure all historical datasets are downloaded locally:
   ```bash
   python scripts/download_from_b2.py --all
   ```
2. Run a dry run to inspect changes without modifying files:
   ```bash
   python scripts/repair_speaker_uuids.py --dry-run
   ```
3. Apply repairs to JSONL files, upload updated datasets to B2, and sync database:
   ```bash
   python scripts/repair_speaker_uuids.py --apply --upload --db database/riigikogu.sqlite
   ```

### Ignored Sessions Removal (`remove_ignored_sessions.py`)
Removes duplicate or ignored session verbatims (e.g. verbatim `202103250048` covering the night of 2021-03-24) from yearly JSONL datasets and the SQLite database:
1. Download target year dataset from Backblaze B2:
   ```bash
   docker compose run --rm pipeline python scripts/download_from_b2.py --year 2021
   ```
2. Inspect rows to be removed (dry run, expected 79 speeches):
   ```bash
   docker compose exec backend python scripts/remove_ignored_sessions.py --year 2021
   ```
3. Apply changes, upload updated dataset to Backblaze B2, and delete database records:
   ```bash
   docker compose run --rm pipeline python scripts/remove_ignored_sessions.py --year 2021 --apply
   ```

### Backblaze B2 Content-Based Synchronization (`download_from_b2.py`, `upload_to_b2.py`)
Dataset synchronization between local storage and Backblaze B2 uses content MD5 digests rather than file size:
- **Content Matching (MD5):**
  - Before uploading, `upload_to_b2.py` calculates local hex MD5 digests and attaches them as object metadata (`Metadata={"md5": "<hex>"}`). If remote metadata already matches the local file MD5, the upload is skipped ("muutmata, jätan vahele").
  - On download (`download_from_b2.py`), single-part objects use the ETag as MD5 digest, while multipart objects retrieve MD5 from object metadata via `head_object` (without consuming download quota).
  - If MD5 matches locally, the download is skipped (both for active and historical files), and remote ETags are recorded in `.b2_etags.json`.
  - If MD5 differs, the file is downloaded even when local and remote file sizes are identical (e.g. replacing UUIDs of identical string length).
  - If a legacy remote object lacks MD5 metadata, historical files fall back to size-based comparison with a logged warning, and active files are downloaded.
- **Atomic Downloads:** Files are streamed to a temporary file (`<filename>.tmp.<pid>`) in the target directory and atomically moved via `os.replace` on completion, preventing corrupt partial files if a download is interrupted.
- **Bandwidth Tracking & Dry Run:**
  - Every run reports total downloaded file count and byte volume to monitor the 1 GB daily egress limit.
  - Inspect sync decisions and byte volume without downloading:
    ```bash
    python scripts/download_from_b2.py --dry-run
    # Inspect all historical files:
    python scripts/download_from_b2.py --all --dry-run
    ```
