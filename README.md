# Riigikogu Stenogram Search

[![CI](https://github.com/spaceminx/riigikogu-stenogram-search/actions/workflows/ci.yml/badge.svg)](https://github.com/spaceminx/riigikogu-stenogram-search/actions/workflows/ci.yml)

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
- **Pipeline Integrity & Statistics Verification:** Daily pipeline verifies transcripts directly against Riigikogu API verbatims (`verify_pipeline_integrity.py`), supports on-demand cross-checks against official statistics (`verify_statistics.py`), and reports health via `/system/status`.
- **Methodology & Transparency:** Clear user-facing methodology modal detailing attendance controls, speech typologies, and verbatim vs edited transcripts.
- **Modern UI:** Responsive single-page application with Dark / Light mode toggle.
- **Automated Daily Pipeline:** Daily server pipeline fetches new transcripts, validates integrity, syncs to Backblaze B2, and updates the database under a unified lock (with manual GitHub Actions fallback).

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

### 3. Build the Database
Build the full SQLite database (downloads data from B2, lemmatizes speeches with multiprocessing, builds term indexes):
```bash
python scripts/build_full_database.py
```

Rebuilding the production database, history backfills and repair scripts are described in [docs/data-maintenance.md](docs/data-maintenance.md).

### 4. Start the FastAPI Backend Server
```bash
uvicorn src.api.main:app --reload --port 8000
```
API documentation is available at:
- Swagger UI: `http://127.0.0.1:8000/docs`
- Redoc: `http://127.0.0.1:8000/redoc`

Key endpoints are listed in [docs/api.md](docs/api.md).

### 5. Frontend Setup & Run
In a separate terminal:
```bash
cd src/frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## Documentation

- [Development](docs/development.md): tests, linting, Python dependency updates, E2E tests, live and upstream API checks
- [Deployment & Operations](docs/operations.md): deploy, schema changes, server daily pipeline, cron, database backup
- [Data Maintenance](docs/data-maintenance.md): database rebuild, history backfill, voting initial load, UUID repair, B2 sync
- [Open Data](docs/open-data.md): building, publishing and the monthly release
- [API](docs/api.md): key endpoints

---

## Project Structure

```text
riigikogu-stenogram-search/
├── .github/
│   ├── dependabot.yml             # Dependabot automated weekly dependency monitoring
│   └── workflows/
│       ├── ci.yml                 # Automated CI (Ruff, ESLint, Prettier, Pytest, Vite build)
│       ├── deploy.yml             # Auto-deploy to self-hosted server on master CI success
│       └── daily_pipeline.yml     # Manual fallback data pipeline (GitHub Actions)
├── config.py                      # Global configuration & dynamic membership dates
├── docker-compose.yml             # Multi-container Docker deployment
├── Dockerfile                     # Multi-stage production backend Docker container
├── pyproject.toml                 # Ruff, pytest, and project configuration
├── requirements.in                # Direct Python runtime dependencies
├── requirements.txt               # Locked Python runtime dependencies (generated by uv)
├── requirements-dev.txt           # Development and testing dependencies
├── scripts/
│   ├── add_indexes.py             # Creates database performance indexes
│   ├── b2_utils.py                # Backblaze B2 cryptographic utilities (MD5, multipart ETag)
│   ├── backfill_history.py        # History backfill script for rich Riigikogu stenograms
│   ├── build_full_database.py     # End-to-end parallel DB build pipeline (--allow-partial)
│   ├── build_lemmas.py            # Standalone lemma builder script
│   ├── build_terms.py             # Standalone term index builder script
│   ├── daily_pipeline.py          # Unified server daily data pipeline
│   ├── download_all_from_b2.py    # Downloads all data & sync states from Backblaze B2
│   ├── download_from_b2.py        # Incremental daily B2 downloader (--all)
│   ├── fetch_attendance.py        # Voting & attendance scraper
│   ├── fetch_factions.py          # MP faction history and person metadata scraper
│   ├── fetch_memberships.py       # Membership terms scraper from Riigikogu API
│   ├── fetch_stenograms_api.py    # Stenogram scraper from Riigikogu API
│   ├── load_database.py           # Standalone JSONL to SQLite loader script
│   ├── remove_ignored_sessions.py # Purges duplicate/ignored verbatims from JSONL and database
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
