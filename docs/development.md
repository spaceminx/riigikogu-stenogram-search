# Development

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
