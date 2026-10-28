# Deployment & Operations

Production deployments run automatically on push to `master` (after CI succeeds) or via manual trigger (`workflow_dispatch`) through `.github/workflows/deploy.yml`.

## Deployment Configuration
The self-hosted deployment runner requires the repository secret `DEPLOY_DIR` to be configured in GitHub:
- Go to repository **Settings** -> **Secrets and variables** -> **Actions** -> **Secrets**.
- Add secret `DEPLOY_DIR` pointing to the repository clone path on the deployment host.

## Schema Changes
Database schema changes are managed via numbered migrations recorded in the `schema_migrations` table:
- Add a new numbered migration tuple `(version, name, up(conn), verify(conn))` in `src/load/migrations.py`.
- Never edit an applied migration; always add a new numbered migration.
- Database indexes stay outside migrations for bulk-load performance; add or drop indexes in `INDEXES` and `REDUNDANT_INDEXES` in `src/load/indexes.py`.
- Migrations run automatically and idempotently at API startup and during daily database sync (`apply_migrations()`).

## Production Database Migration
When deploying updates with schema additions, the deployment applies pending migrations and creates missing indexes upon backend initialization via `apply_migrations()` and `create_indexes()`. No image rebuild or downtime is required.

## Server Daily Pipeline
The daily pipeline runs on the server under a single sync lock (`database/.sync.lock`, a kernel `flock` that is released if the process dies, so a leftover file never blocks the next run) inside a dedicated, one-off `pipeline` container:
`B2 download → fetch API data → integrity verification → B2 upload → in-process DB sync`.

B2 is the source for full rebuilds, so only a run without failures uploads. If a required step fails (the stenogram, attendance or votes fetch, or the integrity check, which exits 1 for missing or truncated sessions and 3 when it cannot reach the Riigikogu API), the run is marked failed and the B2 upload is skipped, while the DB sync still runs. The local changes are not lost: the next B2 download keeps local files that changed since the last sync while B2 did not, and the next green run uploads them. An upstream schema change (exit code 2) fails the run and skips the upload in every fetch step, including the otherwise warning-only memberships, factions, faction leaders and agenda steps; their other failures are warnings only.

This replaces the previous standalone `docker exec … sync_database.py` cron job.

### Configuration (`.env.pipeline`)
The `pipeline` service loads `.env` for baseline configuration and overrides credentials using `.env.pipeline`:
- `B2_KEY_ID`
- `B2_APP_KEY`

Because the pipeline runs in a separate one-off container (`profiles: ["jobs"]`), Backblaze B2 write credentials never live inside the long-running API backend container.

### Scheduled Cron Job
The intended server cron command (replacing the old `sync_database.py` cron line):
```bash
cd <DEPLOY_DIR> && docker compose run --rm -T pipeline python scripts/daily_pipeline.py >> logs/daily_pipeline.log 2>&1; curl -fsS -m 10 --retry 3 https://hc-ping.com/<uuid>/$? >> logs/daily_pipeline.log 2>&1
```

### Running by Hand
To run the full pipeline manually on the server:
```bash
cd <DEPLOY_DIR>
docker compose run --rm pipeline python scripts/daily_pipeline.py
```
To run locally or without uploading to Backblaze B2:
```bash
docker compose run --rm pipeline python scripts/daily_pipeline.py --no-upload
```

### Manual GitHub Actions Fallback
The GitHub Actions workflow (`.github/workflows/daily_pipeline.yml`) remains available as a manual fallback (`workflow_dispatch`). It runs the same `daily_pipeline.py` with `--no-sync` (there is no database in Actions), so it fails and skips the upload in the same cases as the server. Any data uploaded by a manual GitHub run is automatically picked up by the server on its next scheduled run during the initial B2 download step.

## Database Backup
A rebuild from B2 is limited by the 1 GB/day download cap, so the database is also backed up weekly outside the WSL disk. `scripts/backup_database.py` uses only the standard library and runs with the host's `python3`: it copies the database with the SQLite online backup API, runs `PRAGMA quick_check` on the copy, writes `riigikogu-YYYY-MM-DD.sqlite.gz` and keeps the newest `--keep` files.

Root crontab (Sunday 05:00, away from the 07:00 pipeline):
```cron
0 5 * * 0 python3 <DEPLOY_DIR>/scripts/backup_database.py --dest /mnt/c/Users/<user>/RiigivaadeBackups --keep 4 >> <DEPLOY_DIR>/logs/backup.log 2>&1; curl -fsS -m 10 --retry 3 https://hc-ping.com/<uuid>/$? >> <DEPLOY_DIR>/logs/backup.log 2>&1
```

Restore:
```bash
cd <DEPLOY_DIR>
docker compose stop backend
gunzip -c /mnt/c/Users/<user>/RiigivaadeBackups/riigikogu-YYYY-MM-DD.sqlite.gz > database/riigikogu.sqlite.restore
mv database/riigikogu.sqlite database/riigikogu.sqlite.old
rm -f database/riigikogu.sqlite-wal database/riigikogu.sqlite-shm
mv database/riigikogu.sqlite.restore database/riigikogu.sqlite
chown 999:999 database/riigikogu.sqlite
docker compose start backend
```
The next daily run then fetches anything newer than the backup.
