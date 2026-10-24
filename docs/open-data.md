# Open Data

The project periodically exports and releases public machine-readable datasets (gzipped JSONL) under CC BY-SA 3.0 on [GitHub Releases](https://github.com/spaceminx/riigikogu-stenogram-search/releases). The release includes speeches, votings, individual votes, attendance records, agenda items, and member details (including birth year, while excluding exact birth dates and email addresses).

## Building a release

```bash
python3 scripts/build_open_data_release.py --db /path/to/riigikogu.sqlite --out data/release/YYYY-MM-DD/
```

Inside container environments where `.git` is omitted, supply the commit hash via `--commit` or `GIT_COMMIT`:
```bash
python3 scripts/build_open_data_release.py --db /path/to/riigikogu.sqlite --commit "$(git rev-parse HEAD)"
# or in Docker:
docker run -e GIT_COMMIT="$(git rev-parse HEAD)" ...
```

## Publishing a release to GitHub

```bash
python3 scripts/publish_open_data_release.py --dir data/release/YYYY-MM-DD/
```

## Automated Monthly Release & Retention

The script `scripts/monthly_release.py` automates the end-to-end monthly release process:
1. Skips execution if today's release tag (`data-YYYY-MM-DD`) already exists on GitHub (unless `--force` is given).
2. Acquires the database sync lock (`sync_lock`) temporarily to create a safe backup (`database/release_copy.sqlite`) using the SQLite backup API, and releases the lock immediately.
3. Builds the dataset into `data/release/<date>` using `build_open_data_release`.
4. Publishes the release to GitHub Releases using `publish_release`.
5. Enforces retention: keeps the newest 12 releases plus the earliest release of each calendar year. Obsolete releases and their git tag refs are deleted (with a safety guard aborting if >3 releases would be deleted).
6. Cleans up the temporary database copy and older local release directories.

Server cron job (runs on the 1st of every month at 09:00):
```cron
0 9 1 * * cd <DEPLOY_DIR> && docker compose run --rm -T -e GIT_COMMIT=$(git -C <DEPLOY_DIR> -c safe.directory=<DEPLOY_DIR> rev-parse HEAD) pipeline python scripts/monthly_release.py >> logs/monthly_release.log 2>&1; curl -fsS -m 10 --retry 3 https://hc-ping.com/<uuid>/$? >> logs/monthly_release.log 2>&1
```
