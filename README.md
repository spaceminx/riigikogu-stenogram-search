# Riigikogu Stenogram Search

[![CI](https://github.com/spaceminx/riigikogu-stenogram-search/actions/workflows/ci.yml/badge.svg)](https://github.com/spaceminx/riigikogu-stenogram-search/actions/workflows/ci.yml)
[![Riigikogu Daily Data Pipeline](https://github.com/spaceminx/riigikogu-stenogram-search/actions/workflows/daily_pipeline.yml/badge.svg)](https://github.com/spaceminx/riigikogu-stenogram-search/actions/workflows/daily_pipeline.yml)

[Eestikeelne README](README.et.md)

A fast, full-text search and analytical web application for Estonian Parliament (Riigikogu) stenograms and transcripts (data from 2019 to present).

Powered by FastAPI, React + Vite, EstNLTK (Estonian morphological analysis and lemmatization), and SQLite.

---

## Features

- **Intelligent Lemma-Based Search:** Searches across base word forms (lemmas) powered by EstNLTK.
- **Advanced Query Logic:**
  - Multi-word `AND` queries: `tartu ülikool`
  - Comma-separated `OR` queries: `kliima, ilm`
  - Combined `AND`/`OR` logic: `kliima muutus, taastuv energia`
- **Activity Over Time:** Visualizes keyword mentions by month, week, or day with continuous timeline smoothing.
- **Top Speakers:** Identifies members of parliament who speak most about given topics.
- **Attendance & Voting Stats:** Cross-references transcripts with MP attendance records.
- **Persistent MP UUIDs & Permalinks:** All MP speeches are linked to canonical member UUIDs (with raw `ems_id` tracking and minister-to-MP resolution), stable `speech_key` identifiers, and permanent link aliases (`speech_aliases`) that resolve historical IDs after transcripts are officially edited.
- **Dynamic Parliamentary Memberships:** Automatically synchronizes membership dates and terms directly from the Riigikogu API with dynamic runtime reloading.
- **Pipeline Integrity & Statistics Verification:** Nightly pipeline verifies transcripts directly against Riigikogu API verbatims (`verify_pipeline_integrity.py`), supports on-demand cross-checks against official statistics (`verify_statistics.py`), and reports health via `/system/status`.
- **Methodology & Transparency:** Clear user-facing methodology modal detailing attendance controls, speech typologies, and verbatim vs edited transcripts.
- **Modern UI:** Responsive single-page application with Dark / Light mode toggle.
- **Automated Daily Pipeline:** Nightly GitHub Actions workflow fetches new transcripts, validates integrity, and syncs data to Backblaze B2.

---

## Tech Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | React 19, Vite, Recharts, ESLint 10, Prettier |
| **Backend & API** | Python 3.10+, FastAPI, Uvicorn, SQLAlchemy, SQLite |
| **NLP & Lemmatization** | EstNLTK, NLTK |
| **Data Pipelines & Storage** | GitHub Actions, Backblaze B2, Requests |
| **Deployment & Containers** | Docker, Docker Compose, Cloudflare Tunnel |
| **Code Quality & CI** | Ruff (Python), ESLint + Prettier (JS/React), Pytest, Dependabot, GitHub Actions CI |

---

## Getting Started

### Prerequisites
- Python 3.10+ (Python 3.13 recommended)
- Node.js 20+ & npm
- Docker (optional, for containerized run)

### 1. Clone the repository
```bash
git clone https://github.com/spaceminx/riigikogu-stenogram-search.git
cd riigikogu-stenogram-search
```

### 2. Backend Setup
```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Build / Initialize the Database
Build the full SQLite database (downloads data from B2, lemmatizes speeches with multiprocessing, builds term indexes):
```bash
python scripts/build_full_database.py
```

*Note on historical data updates:*
The daily database sync (`sync_database.py`) running on the server only downloads data for active years from B2 (the current year, plus the previous year as long as it falls within the 60-day window until around March 1st) and only updates new or unedited sessions. If historical data from previous years is backfilled or modified, `build_full_database.py` will skip already existing sessions in the database. To apply historical updates, you must build a new database file, stop the API, swap the file, and check for WAL temporary files:
```bash
python scripts/download_from_b2.py --all

# 1. Build the new database (preferably in a container to ensure correct file permissions)
docker compose run --rm -e DATABASE_URL=sqlite:///database/riigikogu_new.sqlite backend python scripts/build_full_database.py
# If building on the host, ensure the container's appuser has rw permissions to the new file (chown if needed):
# DATABASE_URL=sqlite:///database/riigikogu_new.sqlite python scripts/build_full_database.py

# 2. Stop the API and clean up old WAL temporary files
docker compose stop backend
rm -f database/riigikogu.sqlite-wal database/riigikogu.sqlite-shm

# 3. Ensure the new database file also doesn't have an orphaned .sqlite-wal next to it
if [ -f database/riigikogu_new.sqlite-wal ]; then echo "ERROR: New database WAL file exists, data is not fully committed!"; exit 1; fi

# 4. Swap the database file and restart
mv database/riigikogu_new.sqlite database/riigikogu.sqlite
docker compose start backend
```

### 4. Historical Data Backfill (`backfill_history.py`)
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
4. On the server: rebuild the database following the instructions above under "3. Build / Initialize the Database" -> "Note on historical data updates" (build new file with `DATABASE_URL` in container, `docker compose stop backend`, verify WAL, `mv`, `docker compose start backend`).

> [!NOTE]
> The default end date (today minus `UNEDITED_REFETCH_DAYS`) skips recently edited sessions that old code already saved as edited (e.g. September 2026). The daily pipeline will also not touch them. To backfill these recent sessions, run explicitly:
> ```bash
> python scripts/backfill_history.py --start-date 2026-09-01 --end-date <today> --upload
> ```
> The current year dataset file in B2 is protected against concurrency conflicts by ETag validation.

### 5. Maintenance & UUID Repair

To resolve and maintain canonical member UUIDs across speeches and attendance records:

#### Speaker UUIDs (`repair_speaker_uuids.py`)
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

#### Attendance UUIDs (`repair_attendance_uuids.py`)
Populates `member_uuid` across historical attendance records (`data/processed/attendance.jsonl`) and the SQLite `attendance` table:
1. Run a dry run to inspect mapping statistics without modifying files:
   ```bash
   python scripts/repair_attendance_uuids.py --dry-run
   ```
2. Apply changes locally, upload updated `attendance.jsonl` to Backblaze B2, and migrate the database:
   ```bash
   python scripts/repair_attendance_uuids.py --apply --upload --db database/riigikogu.sqlite
   ```
   *Note:* The schema migration (`ensure_schema()`) runs automatically and idempotently on table initialization, adding column `member_uuid TEXT` and index `idx_attendance_member_uuid` if they do not yet exist.

#### Backblaze B2 Content-Based Synchronization (`download_from_b2.py`, `upload_to_b2.py`, `backfill_b2_md5_metadata.py`)
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
- **Metadata Backfill for Existing B2 Objects (`backfill_b2_md5_metadata.py`):**
  One-time server-side metadata tagging for objects uploaded before MD5 metadata was introduced:
  - Uses S3 server-side `copy_object` with `MetadataDirective="REPLACE"`, consuming zero download bandwidth.
  - Validates local MD5 against single-part ETags, or requires `--trust-local` for multipart objects if verified locally.
  - Automatically updates `.b2_etags.json` with new post-copy ETags so future uploads avoid false concurrency conflicts.
  - Dry run by default:
    ```bash
    # Inspect what would be updated:
    python scripts/backfill_b2_md5_metadata.py

    # Apply server-side copy (caution: changes remote ETags):
    python scripts/backfill_b2_md5_metadata.py --apply

    # Trust local files for multipart objects:
    python scripts/backfill_b2_md5_metadata.py --apply --trust-local
    ```

### 6. Start the FastAPI Backend Server
```bash
uvicorn src.api.main:app --reload --port 8000
```
API documentation is available at:
- Swagger UI: `http://127.0.0.1:8000/docs`
- Redoc: `http://127.0.0.1:8000/redoc`

#### Key API Endpoints
- **Search & Analytics:**
  - `GET /search?q={query}` — Full-text keyword search across speeches (filters: `speaker_uuid`, `membership`, `faction`, `start_date`, `end_date`, `exclude_chair`, `speech_category`).
  - `GET /search/activity?q={query}` — Keyword frequency grouped by day, week, or month (supports `speaker_uuid`).
  - `GET /search/speakers?q={query}` — Most active speakers for a topic (supports `speaker_uuid`).
  - `GET /search/export?q={query}&format={csv|json}` — Export search results in CSV or JSON (supports `speaker_uuid`).
- **MP Profiles & Statistics:**
  - `GET /persons` — List parliament members with optional name search and active status filter.
  - `GET /persons/{uuid}` — Individual MP profile, metadata, and faction history.
  - `GET /persons/{uuid}/stats` — Activity breakdown, speech durations, and counts by term and year.
  - `GET /persons/{uuid}/speeches` — Speeches by MP with pagination and `role_class` filter (`all`, `mp`, `chair`, `minister`, `candidate`, `director`, `other`).
  - `GET /persons/{uuid}/attendance` — MP attendance statistics and voting breakdown.
- **Transcripts & System Info:**
  - `GET /speeches/{id}` and `GET /speeches/{id}/context` — Specific speech and session context.
  - `GET /attendance/stats` and `GET /attendance/sessions` — Attendance aggregations by faction and member.
  - `GET /system/status` and `GET /memberships` — System health, data bounds, and parliamentary memberships.

### 7. Frontend Setup & Run
In a separate terminal:
```bash
cd src/frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## Deployment & Continuous Integration

Production deployments run automatically on push to `master` (after CI succeeds) or via manual trigger (`workflow_dispatch`) through `.github/workflows/deploy.yml`.

### Deployment Configuration
The self-hosted deployment runner requires the repository secret `DEPLOY_DIR` to be configured in GitHub:
- Go to repository **Settings** -> **Secrets and variables** -> **Actions** -> **Secrets**.
- Add secret `DEPLOY_DIR` pointing to the repository clone path on the deployment host.

### Production Database Migration
When deploying updates with schema or data additions (such as the attendance `member_uuid` column):
1. Code deployment automatically creates missing columns and indexes upon backend initialization via `ensure_schema()`.
2. To populate historical attendance member UUIDs in production:
   ```bash
   docker compose run --rm backend python scripts/repair_attendance_uuids.py --apply --upload --db database/riigikogu.sqlite
   ```
   No image rebuild or downtime is required.

---

## Testing & Code Quality

The codebase uses Ruff for Python, ESLint + Prettier for frontend, and Pytest for automated testing.

### Automated Tests
```bash
# Run backend and API tests
pytest -v
```

### Python Linting & Formatting
```bash
# Check and auto-fix linting issues & sort imports
ruff check . --fix

# Format code
ruff format .
```

### Frontend Linting & Formatting
```bash
cd src/frontend

# Lint checks
npm run lint
npm run lint:fix

# Format code with Prettier
npm run format
npm run format:check
```

---

## Project Structure

```text
riigikogu-stenogram-search/
├── .github/
│   ├── dependabot.yml             # Dependabot automated weekly dependency monitoring
│   └── workflows/
│       ├── ci.yml                 # Automated CI (Ruff, ESLint, Prettier, Pytest, Vite build)
│       ├── deploy.yml             # Auto-deploy to self-hosted server on master CI success
│       └── daily_pipeline.yml     # Nightly data pipeline (B2 sync, API fetch, integrity verification)
├── config.py                      # Global configuration & dynamic membership dates
├── docker-compose.yml             # Multi-container Docker deployment
├── Dockerfile                     # Multi-stage production backend Docker container
├── pyproject.toml                 # Ruff, pytest, and project configuration
├── requirements.txt               # Pinned Python runtime dependencies
├── requirements-dev.txt           # Development and testing dependencies
├── scripts/
│   ├── add_indexes.py             # Creates database performance indexes
│   ├── backfill_b2_md5_metadata.py # Server-side MD5 metadata backfill for B2 objects
│   ├── backfill_history.py        # History backfill script for rich Riigikogu stenograms
│   ├── build_full_database.py     # End-to-end parallel DB build pipeline (--allow-partial)
│   ├── build_lemmas.py            # Standalone lemma builder script
│   ├── build_terms.py             # Standalone term index builder script
│   ├── download_all_from_b2.py    # Downloads all data & sync states from Backblaze B2
│   ├── download_from_b2.py        # Incremental daily B2 downloader (--all)
│   ├── fetch_attendance.py        # Voting & attendance scraper
│   ├── fetch_factions.py          # MP faction history and person metadata scraper
│   ├── fetch_memberships.py       # Membership terms scraper from Riigikogu API
│   ├── fetch_stenograms_api.py    # Stenogram scraper from Riigikogu API
│   ├── load_database.py           # Standalone JSONL to SQLite loader script
│   ├── repair_attendance_uuids.py # Populates member_uuid in attendance records and database
│   ├── repair_speaker_uuids.py    # Speaker UUID resolution and repair script
│   ├── sync_database.py           # SQLite database update with speech aliases
│   ├── upload_to_b2.py            # Backblaze B2 uploader for data and sync states
│   ├── verify_pipeline_integrity.py # Direct pipeline data integrity verification
│   └── verify_statistics.py       # Cross-verification script against official statistics
├── src/
│   ├── api/                       # FastAPI routes & endpoints
│   │   ├── main.py                # App entrypoint & CORS config
│   │   ├── routes.py              # API router definitions
│   │   ├── search.py              # Search & analytics logic
│   │   └── attendance.py          # Attendance query endpoints
│   ├── transform/                 # NLP & lemmatization
│   │   ├── lemmatizer.py          # EstNLTK multiprocessing lemmatizer
│   │   └── term_builder.py        # Term frequency & index builder
│   ├── load/                      # Database models and table definitions
│   │   ├── database.py            # Database engine and session factory
│   │   ├── indexes.py             # Database SQL index creation
│   │   ├── models.py              # SQLAlchemy ORM models (Speech, SpeechAlias, Attendance, Person)
│   │   └── loader.py              # Bulk JSONL to SQLite loader with alias mapping
│   └── frontend/                  # React + Vite application
│       ├── eslint.config.js       # ESLint configuration
│       ├── package.json
│       ├── src/
│       │   ├── App.jsx            # Main app router & layout component
│       │   ├── App.css            # Application stylesheets & themes
│       │   ├── api.js             # API client functions
│       │   ├── components/        # UI components
│       │   │   ├── ActivityChart.jsx
│       │   │   ├── AttendanceFactionsTable.jsx
│       │   │   ├── AttendanceMembersTable.jsx
│       │   │   ├── ContextModal.jsx
│       │   │   ├── Footer.jsx
│       │   │   ├── Header.jsx
│       │   │   ├── MethodologyModal.jsx
│       │   │   ├── Pagination.jsx
│       │   │   ├── SearchFilters.jsx
│       │   │   ├── SearchQueryInput.jsx
│       │   │   ├── SpeakersPanel.jsx
│       │   │   ├── SpeechCard.jsx
│       │   │   └── SpeechesHeader.jsx
│       │   ├── routes/            # Page route views
│       │   │   ├── AttendanceView.jsx
│       │   │   ├── DashboardView.jsx
│       │   │   ├── NotFoundView.jsx
│       │   │   ├── PersonView.jsx
│       │   │   ├── SearchView.jsx
│       │   │   ├── SessionView.jsx
│       │   │   └── SpeechView.jsx
│       │   └── lib/               # Shared frontend utility modules
│       │       ├── api.js
│       │       ├── calendarUtils.js
│       │       └── formatters.jsx
├── tests/
│   ├── test_api.py                # FastAPI endpoint integration tests
│   ├── test_backfill.py           # Historical backfill and B2 upload tests
│   ├── test_pipeline.py           # Pipeline, dynamic dates, and integrity verification tests
│   └── test_query_parser.py       # Query parser and search logic unit tests
```

---

## License

This project is open source and available under the [MIT License](LICENSE).

