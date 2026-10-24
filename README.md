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
- Node.js 24 & npm
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
├── .github/            # CI, deploy, live API check and fallback pipeline workflows; Dependabot
├── docs/               # Development, operations, data maintenance, open data and API docs
├── scripts/            # Data pipeline, fetchers, B2 sync, repairs, releases, backup
├── src/
│   ├── api/            # FastAPI app, routes, search and attendance queries
│   ├── data/           # Static reference data (governments)
│   ├── fetch_models/   # Pydantic models for upstream Riigikogu API responses
│   ├── load/           # SQLAlchemy models, migrations, indexes, JSONL loader
│   ├── transform/      # EstNLTK lemmatizer and term index builder
│   └── frontend/       # React + Vite app (Vercel)
│       ├── e2e/        # Playwright tests and recorded API fixtures
│       ├── src/        # Components, routes, lib, styles
│       └── test/       # Unit tests (node --test)
├── tests/              # Pytest backend, API and pipeline tests
├── config.py           # Global configuration & dynamic membership dates
├── docker-compose.yml  # Backend and one-off pipeline containers
├── Dockerfile          # Multi-stage production backend image
├── requirements.in     # Direct Python runtime dependencies
├── requirements.txt    # Locked Python runtime dependencies (generated by uv)
└── requirements-dev.txt
```

---

## License

This project is open source and available under the [MIT License](LICENSE).
