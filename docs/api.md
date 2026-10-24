# API

API documentation is available at:
- Swagger UI: `http://127.0.0.1:8000/docs`
- Redoc: `http://127.0.0.1:8000/redoc`

## Key API Endpoints
- **Search & Analytics:**
  - `GET /search?q={query}` — Full-text keyword search across speeches (filters: `speaker_uuid`, `membership`, `faction`, `start_date`, `end_date`, `exclude_chair`, `speech_category`).
  - `GET /search/activity?q={query}` — Keyword frequency grouped by day, week, or month (supports `speaker_uuid`).
  - `GET /search/speakers?q={query}` — Most active speakers for a topic (supports `speaker_uuid`).
  - `GET /search/export?q={query}&format={csv|json}` — Export search results in CSV or JSON (supports `speaker_uuid`; includes CC BY-SA 3.0 license metadata and `X-License` header).
- **MP Profiles & Statistics:**
  - `GET /persons` — List parliament members with optional name search and active status filter.
  - `GET /persons/{uuid}` — Individual MP profile, metadata, and faction history.
  - `GET /persons/{uuid}/stats` — Activity breakdown, speech durations, and counts by term and year.
  - `GET /persons/{uuid}/speeches` — Speeches by MP with pagination and `role_class` filter (`all`, `mp`, `chair`, `minister`, `candidate`, `director`, `other`).
  - `GET /persons/{uuid}/attendance` — MP attendance statistics and voting breakdown.
  - `GET /persons/{uuid}/votes` — Voting history for an individual MP.
- **Attendance & Factions:**
  - `GET /attendance/stats` — Attendance statistics aggregated by member.
  - `GET /attendance/factions` — Attendance statistics aggregated by faction.
  - `GET /attendance/factions/list` — Distinct faction names for a parliamentary term.
- **Transcripts, Sessions & Voting:**
  - `GET /speeches/{id}` and `GET /speeches/{id}/context` — Specific speech and session context.
  - `GET /speeches/by-external-id/{id}` — Retrieve speech by Riigikogu verbatim external ID.
  - `GET /sessions/dates` — Dates with recorded parliamentary sessions.
  - `GET /sessions/{date}` — Speeches and agenda items for a specific date session.
  - `GET /votings` — List parliamentary votings with filters.
  - `GET /votings/{uuid}` — Specific voting details and individual member votes.
- **System Info & Overview:**
  - `GET /overview` — Platform summary metrics, active MPs, and recent speech count.
  - `GET /system/status` and `GET /memberships` — System health, data bounds, and parliamentary memberships.
