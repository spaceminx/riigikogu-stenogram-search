# Development

## Running Locally

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

Rebuilding the production database, history backfills and repair scripts are described in [data-maintenance.md](data-maintenance.md).

### 4. Start the FastAPI Backend Server
```bash
uvicorn src.api.main:app --reload --port 8000
```
API documentation is available at:
- Swagger UI: `http://127.0.0.1:8000/docs`
- Redoc: `http://127.0.0.1:8000/redoc`

Key endpoints are listed in [api.md](api.md).

### 5. Frontend Setup & Run
In a separate terminal:
```bash
cd src/frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

### README screenshots
The screenshots in `docs/images/` come from the live site in the light theme. Refresh them after visible changes:
```bash
node scripts/capture_readme_screenshots.mjs
```
The examples (search topic, member, vote, bill, sitting) are set at the top of the script; keep them impartial.

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

### Updating Python Dependencies
`requirements.in` lists the direct runtime dependencies. `requirements.txt` is the generated lock with every transitive package pinned, and Docker, CI and the pipeline all install from it. Regenerate it after changing `requirements.in`:
```bash
# Keep current pins, add or remove what requirements.in changed
uv pip compile requirements.in --universal --python-version 3.13 -o requirements.txt

# Upgrade everything to the latest compatible versions
uv pip compile requirements.in --universal --python-version 3.13 -o requirements.txt --upgrade
```
Dependabot bumps the pins in `requirements.txt` directly; CI installs the result, so a conflicting bump fails there.

### Frontend Linting & Formatting
```bash
cd src/frontend

# Lint checks
npm run lint
npm run lint:fix

# Format code with Prettier
npm run format
npm run format:check

# Unit tests and the CSS variable check
npm test
npm run check:css-vars
```

## End-to-End Tests

The frontend includes Playwright smoke tests that run against a mock API serving recorded fixtures:

- Intercepts all API calls to `http://api.e2e.test` and responds from fixtures in `src/frontend/e2e/fixtures/`.
- Verifies that all 10 core routes load without crashing (no ErrorBoundary trigger).
- Verifies client-side navigation between routes without full page reload.
- Verifies search pill logic (phrase quoting, `+JA`, `+VÕI`, removing pills, and 390px mobile responsiveness).
- Verifies responsive layout on mobile viewport (no horizontal scrollbar / overflow).
- Verifies dark mode toggle persistence in `localStorage` and WCAG AA contrast compliance.

### Running E2E tests locally

```bash
cd src/frontend
npx playwright install chromium
npm run e2e
```

### Capturing fixtures

To refresh recorded fixtures from the production API:

```bash
node scripts/capture_e2e_fixtures.mjs
```

### Weekly live API shape check

A scheduled workflow (`.github/workflows/live_api_check.yml`) runs weekly (every Monday at 10:00 UTC) to verify that the live API at `https://api.riigivaade.me` matches the expected contract in `src/frontend/e2e/fixtures/index.json`.

Run the check manually:

```bash
python3 scripts/check_live_api.py
```

### Upstream API validation

All external API responses from `api.riigikogu.ee` and `stenogrammid.riigikogu.ee` are validated with Pydantic models at the fetcher boundary (`src/fetch_models/riigikogu.py`). If upstream renames, removes, or retypes an expected field, the fetcher immediately raises `UpstreamSchemaError`, prints a readable path-level error to `stderr`, and terminates with exit code 2. The record that failed validation is never written; records the fetcher had already validated and saved earlier in the same run (fetchers save in batches) are kept. In the daily pipeline, an exit code 2 is recorded as a pipeline failure and alerts Healthchecks, also in the otherwise warning-only memberships, factions and agenda steps. Upstream API shape is also checked weekly and manually via:

```bash
python3 scripts/check_upstream_api.py
```

The Pydantic models are tested against small real responses in `tests/fixtures/riigikogu_api/`. To refresh them after an upstream change, run `python scripts/capture_riigikogu_fixtures.py` and review the diff (lists are trimmed to about five items and faction contact details are dropped).

### Agenda link coverage

`python scripts/agenda_coverage.py` reports per year how many speeches are linked to an agenda item and lists the most common unlinked agenda titles. It reads the database set by `DATABASE_URL`; run it after changing the agenda matching.
