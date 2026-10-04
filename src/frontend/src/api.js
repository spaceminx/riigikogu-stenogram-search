const BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "https://karmarv.tail60892b.ts.net";

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

export async function fetchSearch(query, limit = 50) {
  const res = await fetch(`${BASE_URL}/search?q=${encodeURIComponent(query)}&limit=${limit}`);
  return handleResponse(res);
}

export async function fetchActivity(query, interval = "monthly") {
  const res = await fetch(
    `${BASE_URL}/search/activity?q=${encodeURIComponent(query)}&interval=${interval}`
  );
  return handleResponse(res);
}

export async function fetchSpeakers(query, limit = 20) {
  const res = await fetch(
    `${BASE_URL}/search/speakers?q=${encodeURIComponent(query)}&limit=${limit}`
  );
  return handleResponse(res);
}

export async function fetchAttendance() {
  const res = await fetch(`${BASE_URL}/attendance/stats`);
  return handleResponse(res);
}
