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
- **Modern UI:** Responsive single-page application with Dark / Light mode toggle.
- **Automated Daily Pipeline:** Nightly GitHub Actions workflow fetches new transcripts and syncs them to Backblaze B2.

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

### 4. Start the FastAPI Backend Server
```bash
uvicorn src.api.main:app --reload --port 8000
```
API documentation is available at:
- Swagger UI: `http://127.0.0.1:8000/docs`
- Redoc: `http://127.0.0.1:8000/redoc`

### 5. Frontend Setup & Run
In a separate terminal:
```bash
cd src/frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

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
│       └── daily_pipeline.yml     # Nightly data pipeline (B2 sync & API fetch)
├── config.py                      # Global configuration & paths
├── docker-compose.yml             # Multi-container Docker deployment
├── Dockerfile                     # Production backend Docker container
├── pyproject.toml                 # Ruff, pytest, and project configuration
├── requirements.txt               # Python backend dependencies
├── scripts/
│   ├── build_full_database.py     # End-to-end parallel DB build pipeline
│   ├── download_all_from_b2.py    # Downloads all data & sync states from Backblaze B2
│   ├── download_from_b2.py        # Incremental daily B2 downloader
│   ├── fetch_stenograms_api.py    # Stenogram scraper from Riigikogu API
│   ├── fetch_factions.py          # MP faction history scraper
│   ├── fetch_attendance.py        # Voting & attendance scraper
│   └── upload_to_b2.py            # Backblaze B2 uploader for data and sync states
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
│   │   ├── models.py              # SQLAlchemy ORM models
│   │   └── loader.py              # Bulk JSONL to SQLite loader
│   └── frontend/                  # React + Vite application
│       ├── eslint.config.js       # ESLint flat configuration
│       ├── package.json
│       └── src/
│           ├── App.jsx            # Main dashboard component
│           └── api.js             # Frontend API client
├── tests/
│   ├── test_api.py                # FastAPI endpoint integration tests
│   └── test_query_parser.py       # Query parser and search logic unit tests
└── HOSTING.md                     # Hosting & architecture notes
```

---

## License

This project is open source and available under the [MIT License](LICENSE).
