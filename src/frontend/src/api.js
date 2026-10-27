const BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "https://api.riigivaade.me");

async function handleResponse(res) {
  if (!res.ok) {
    let errorDetail = `Päring ebaõnnestus (kood ${res.status})`;
    try {
      const data = await res.json();
      if (data && data.detail) {
        if (typeof data.detail === "string") {
          errorDetail = data.detail;
        } else if (Array.isArray(data.detail)) {
          errorDetail = data.detail.map((d) => (d && d.msg ? d.msg : JSON.stringify(d))).join(", ");
        } else if (typeof data.detail === "object") {
          errorDetail = JSON.stringify(data.detail);
        } else {
          errorDetail = String(data.detail);
        }
      }
    } catch {
      // response body was not JSON
    }
    const err = new Error(errorDetail);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

function buildSearchQueryString({
  query,
  limit,
  offset,
  interval,
  membership = "all",
  faction = null,
  speaker = null,
  speakerUuid = null,
  startDate = null,
  endDate = null,
  sortBy = "date_desc",
  excludeChair = false,
  speechCategory = null,
  expand = true,
} = {}) {
  const params = new URLSearchParams();
  if (query) params.append("q", query);
  if (limit !== undefined && limit !== null) params.append("limit", limit);
  if (offset !== undefined && offset !== null) params.append("offset", offset);
  if (interval) params.append("interval", interval);
  if (membership && membership !== "all") params.append("membership", membership);
  if (faction) params.append("faction", faction);
  if (speaker && speaker.trim()) params.append("speaker", speaker.trim());
  if (speakerUuid) params.append("speaker_uuid", speakerUuid);
  if (startDate) params.append("start_date", startDate);
  if (endDate) params.append("end_date", endDate);
  if (sortBy && sortBy !== "date_desc") params.append("sort_by", sortBy);
  if (excludeChair) params.append("exclude_chair", "true");
  if (speechCategory) params.append("speech_category", speechCategory);
  if (expand === false || expand === "false") params.append("expand", "false");
  return params.toString();
}

export async function fetchDashboardOverview() {
  const res = await fetch(`${BASE_URL}/overview`);
  return handleResponse(res);
}

export async function fetchPlenarySessionDates() {
  const res = await fetch(`${BASE_URL}/sessions/dates`);
  return handleResponse(res);
}

export async function fetchPlenarySession(date) {
  const res = await fetch(`${BASE_URL}/sessions/${encodeURIComponent(date)}`);
  return handleResponse(res);
}

export async function fetchSearch(options, signal) {
  const qs =
    typeof options === "string"
      ? `q=${encodeURIComponent(options)}`
      : buildSearchQueryString(options);
  const res = await fetch(`${BASE_URL}/search?${qs}`, { signal });
  return handleResponse(res);
}

export async function fetchActivity(options, legacyInterval = "monthly", signal) {
  const opts = typeof options === "string" ? { query: options, interval: legacyInterval } : options;
  const qs = buildSearchQueryString(opts);
  const res = await fetch(`${BASE_URL}/search/activity?${qs}`, { signal });
  return handleResponse(res);
}

export async function fetchSpeakers(options, legacyLimit = 20, signal) {
  const opts = typeof options === "string" ? { query: options, limit: legacyLimit } : options;
  const qs = buildSearchQueryString(opts);
  const res = await fetch(`${BASE_URL}/search/speakers?${qs}`, { signal });
  return handleResponse(res);
}

export async function fetchSpeechContext(speechId, query = null, expand = true) {
  const params = new URLSearchParams();
  if (query) params.append("q", query);
  if (expand === false || expand === "false") params.append("expand", "false");
  const qs = params.toString();
  const res = await fetch(`${BASE_URL}/speeches/${speechId}/context${qs ? `?${qs}` : ""}`);
  return handleResponse(res);
}

export function getExportUrl(options) {
  const qs = buildSearchQueryString(options);
  const format = options.format || "csv";
  return `${BASE_URL}/search/export?${qs}&format=${format}`;
}

export async function fetchAttendance({
  membership = null,
  faction = null,
  activeOnly = false,
  excludeInfotund = false,
  role = null,
} = {}) {
  const params = new URLSearchParams();
  if (membership) params.append("membership", membership);
  if (faction) params.append("faction", faction);
  if (activeOnly) params.append("active_only", "true");
  if (excludeInfotund) params.append("exclude_infotund", "true");
  if (role) params.append("role", role);

  const qs = params.toString();
  const res = await fetch(`${BASE_URL}/attendance/stats${qs ? `?${qs}` : ""}`);
  return handleResponse(res);
}

export const fetchAttendanceStats = fetchAttendance;

export async function fetchFactionAttendance({
  membership = null,
  activeOnly = false,
  excludeInfotund = false,
  role = null,
} = {}) {
  const params = new URLSearchParams();
  if (membership) params.append("membership", membership);
  if (activeOnly) params.append("active_only", "true");
  if (excludeInfotund) params.append("exclude_infotund", "true");
  if (role) params.append("role", role);

  const qs = params.toString();
  const res = await fetch(`${BASE_URL}/attendance/factions${qs ? `?${qs}` : ""}`);
  return handleResponse(res);
}

export async function fetchFactions({ membership = null, activeOnly = false } = {}) {
  const params = new URLSearchParams();
  if (membership) params.append("membership", membership);
  if (activeOnly) params.append("active_only", "true");

  const qs = params.toString();
  const res = await fetch(`${BASE_URL}/factions${qs ? `?${qs}` : ""}`);
  return handleResponse(res);
}

export async function fetchFactionsList(membership = null) {
  const params = new URLSearchParams();
  if (membership) params.append("membership", membership);

  const qs = params.toString();
  const res = await fetch(`${BASE_URL}/attendance/factions/list${qs ? `?${qs}` : ""}`);
  return handleResponse(res);
}

export async function fetchMemberships() {
  const res = await fetch(`${BASE_URL}/memberships`);
  return handleResponse(res);
}

export async function fetchSystemStatus() {
  const res = await fetch(`${BASE_URL}/system/status`);
  return handleResponse(res);
}

export async function fetchPersons({ search, activeOnly, limit, offset } = {}) {
  const params = new URLSearchParams();
  if (search) params.append("search", search);
  if (activeOnly) params.append("active_only", "true");
  if (limit) params.append("limit", limit);
  if (offset) params.append("offset", offset);
  const res = await fetch(`${BASE_URL}/persons?${params.toString()}`);
  return handleResponse(res);
}

export async function fetchPerson(uuid) {
  const res = await fetch(`${BASE_URL}/persons/${encodeURIComponent(uuid)}`);
  return handleResponse(res);
}

export async function fetchSpeech(speechId) {
  const res = await fetch(`${BASE_URL}/speeches/${encodeURIComponent(speechId)}`);
  return handleResponse(res);
}

export async function fetchPersonStats(uuid) {
  const res = await fetch(`${BASE_URL}/persons/${encodeURIComponent(uuid)}/stats`);
  return handleResponse(res);
}

export async function fetchPersonSpeeches(
  uuid,
  { roleClass = "mp", speechCategory = null, limit = 20, offset = 0 } = {}
) {
  const params = new URLSearchParams();
  if (roleClass) params.append("role_class", roleClass);
  if (speechCategory) params.append("speech_category", speechCategory);
  if (limit !== undefined && limit !== null) params.append("limit", limit);
  if (offset !== undefined && offset !== null) params.append("offset", offset);
  const res = await fetch(
    `${BASE_URL}/persons/${encodeURIComponent(uuid)}/speeches?${params.toString()}`
  );
  return handleResponse(res);
}

export async function fetchPersonAttendance(uuid, { excludeInfotund = false, role = null } = {}) {
  const params = new URLSearchParams();
  if (excludeInfotund) params.append("exclude_infotund", "true");
  if (role) params.append("role", role);
  const qs = params.toString();
  const res = await fetch(
    `${BASE_URL}/persons/${encodeURIComponent(uuid)}/attendance${qs ? `?${qs}` : ""}`
  );
  return handleResponse(res);
}

export async function fetchGovernments() {
  const res = await fetch(`${BASE_URL}/governments`);
  return handleResponse(res);
}

export async function fetchFactionAlignment(uuid, membership = "all") {
  const params = new URLSearchParams();
  if (membership && membership !== "all") {
    params.append("membership", membership);
  }
  const qs = params.toString();
  const res = await fetch(
    `${BASE_URL}/persons/${encodeURIComponent(uuid)}/faction-alignment${qs ? `?${qs}` : ""}`
  );
  return handleResponse(res);
}

export async function fetchFactionAlignmentDifferences(
  uuid,
  { membership = "all", limit = 10, offset = 0 } = {}
) {
  const params = new URLSearchParams();
  if (membership && membership !== "all") {
    params.append("membership", membership);
  }
  params.append("limit", String(limit));
  params.append("offset", String(offset));
  const res = await fetch(
    `${BASE_URL}/persons/${encodeURIComponent(uuid)}/faction-alignment/differences?${params.toString()}`
  );
  return handleResponse(res);
}

export async function fetchVotings(options = {}) {
  const params = new URLSearchParams();
  const startDate = options.startDate ?? options.start_date;
  const endDate = options.endDate ?? options.end_date;
  const sittingDate = options.sittingDate ?? options.sitting_date;
  const membership = options.membership;
  const q = options.q ?? options.query;
  const documentUuid = options.documentUuid ?? options.document_uuid;
  const type = options.type;
  const includeTechnical = options.includeTechnical ?? options.include_technical;
  const limit = options.limit ?? 50;
  const offset = options.offset ?? 0;

  if (startDate) params.append("start_date", startDate);
  if (endDate) params.append("end_date", endDate);
  if (sittingDate) params.append("sitting_date", sittingDate);
  if (membership && membership !== "all") params.append("membership", membership);
  if (q && q.trim()) params.append("q", q.trim());
  if (documentUuid) params.append("document_uuid", documentUuid);
  if (type) params.append("type", type);
  if (includeTechnical !== undefined && includeTechnical !== null) {
    params.append("include_technical", String(includeTechnical));
  }
  if (limit !== undefined && limit !== null) params.append("limit", String(limit));
  if (offset !== undefined && offset !== null) params.append("offset", String(offset));

  const qs = params.toString();
  const res = await fetch(`${BASE_URL}/votings${qs ? `?${qs}` : ""}`);
  return handleResponse(res);
}

export async function fetchVoting(uuid) {
  const res = await fetch(`${BASE_URL}/votings/${encodeURIComponent(uuid)}`);
  return handleResponse(res);
}

export async function fetchDraft(uuid) {
  const res = await fetch(`${BASE_URL}/drafts/${encodeURIComponent(uuid)}`);
  return handleResponse(res);
}

export async function fetchDraftSpeeches(
  uuid,
  { agendaItemUuid = null, limit = 50, offset = 0 } = {}
) {
  const params = new URLSearchParams();
  if (agendaItemUuid) params.append("agenda_item_uuid", agendaItemUuid);
  if (limit !== undefined && limit !== null) params.append("limit", String(limit));
  if (offset !== undefined && offset !== null) params.append("offset", String(offset));

  const qs = params.toString();
  const res = await fetch(
    `${BASE_URL}/drafts/${encodeURIComponent(uuid)}/speeches${qs ? `?${qs}` : ""}`
  );
  return handleResponse(res);
}

export async function fetchSuggestions(prefix, { limit = 8, signal } = {}) {
  const params = new URLSearchParams();
  if (prefix) params.append("prefix", prefix);
  if (limit !== undefined && limit !== null) params.append("limit", String(limit));

  const qs = params.toString();
  const res = await fetch(`${BASE_URL}/suggest${qs ? `?${qs}` : ""}`, { signal });
  return handleResponse(res);
}
