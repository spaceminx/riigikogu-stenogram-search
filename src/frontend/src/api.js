const BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? "http://127.0.0.1:8000" : "https://karmarv.tail60892b.ts.net");

async function handleResponse(res) {
  if (!res.ok) {
    let errorDetail = `Päring ebaõnnestus (kood ${res.status})`;
    try {
      const data = await res.json();
      if (data && data.detail) {
        errorDetail = data.detail;
      }
    } catch {
      // response body was not JSON
    }
    throw new Error(errorDetail);
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
  startDate = null,
  endDate = null,
  sortBy = "date_desc",
} = {}) {
  const params = new URLSearchParams();
  if (query) params.append("q", query);
  if (limit !== undefined && limit !== null) params.append("limit", limit);
  if (offset !== undefined && offset !== null) params.append("offset", offset);
  if (interval) params.append("interval", interval);
  if (membership && membership !== "all") params.append("membership", membership);
  if (faction) params.append("faction", faction);
  if (speaker && speaker.trim()) params.append("speaker", speaker.trim());
  if (startDate) params.append("start_date", startDate);
  if (endDate) params.append("end_date", endDate);
  if (sortBy && sortBy !== "date_desc") params.append("sort_by", sortBy);
  return params.toString();
}

export async function fetchDashboardOverview() {
  const res = await fetch(`${BASE_URL}/overview`);
  return handleResponse(res);
}

export async function fetchSearch(options) {
  const qs =
    typeof options === "string"
      ? `q=${encodeURIComponent(options)}`
      : buildSearchQueryString(options);
  const res = await fetch(`${BASE_URL}/search?${qs}`);
  return handleResponse(res);
}

export async function fetchActivity(options, legacyInterval = "monthly") {
  const opts = typeof options === "string" ? { query: options, interval: legacyInterval } : options;
  const qs = buildSearchQueryString(opts);
  const res = await fetch(`${BASE_URL}/search/activity?${qs}`);
  return handleResponse(res);
}

export async function fetchSpeakers(options, legacyLimit = 20) {
  const opts = typeof options === "string" ? { query: options, limit: legacyLimit } : options;
  const qs = buildSearchQueryString(opts);
  const res = await fetch(`${BASE_URL}/search/speakers?${qs}`);
  return handleResponse(res);
}

export async function fetchSpeechContext(speechId, query = null) {
  const qs = query ? `?q=${encodeURIComponent(query)}` : "";
  const res = await fetch(`${BASE_URL}/speeches/${speechId}/context${qs}`);
  return handleResponse(res);
}

export function getExportUrl(options) {
  const qs = buildSearchQueryString(options);
  const format = options.format || "csv";
  return `${BASE_URL}/search/export?${qs}&format=${format}`;
}

export async function fetchAttendance({
  membership = "15",
  faction = null,
  activeOnly = false,
} = {}) {
  const params = new URLSearchParams();
  if (membership) params.append("membership", membership);
  if (faction) params.append("faction", faction);
  if (activeOnly) params.append("active_only", "true");

  const res = await fetch(`${BASE_URL}/attendance/stats?${params.toString()}`);
  return handleResponse(res);
}

export async function fetchFactionAttendance({ membership = "15", activeOnly = false } = {}) {
  const params = new URLSearchParams();
  if (membership) params.append("membership", membership);
  if (activeOnly) params.append("active_only", "true");

  const res = await fetch(`${BASE_URL}/attendance/factions?${params.toString()}`);
  return handleResponse(res);
}

export async function fetchFactionsList(membership = "15") {
  const params = new URLSearchParams();
  if (membership) params.append("membership", membership);

  const res = await fetch(`${BASE_URL}/attendance/factions/list?${params.toString()}`);
  return handleResponse(res);
}
