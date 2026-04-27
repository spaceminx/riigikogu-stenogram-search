const BASE_URL = "http://127.0.0.1:8000";

export async function fetchSearch(query, limit = 50) {
  const res = await fetch(`${BASE_URL}/search?q=${encodeURIComponent(query)}&limit=${limit}`);
  return res.json();
}

export async function fetchActivity(query, interval = "weekly") {
  const res = await fetch(
      `${BASE_URL}/search/activity?q=${encodeURIComponent(query)}&interval=${interval}`
  );
  return res.json();
}

export async function fetchSpeakers(query, limit = 20) {
  const res = await fetch(`${BASE_URL}/search/speakers?q=${encodeURIComponent(query)}&limit=${limit}`);
  return res.json();
}
