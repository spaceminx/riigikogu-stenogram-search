const YOUTUBE_ID_REGEX = /^[A-Za-z0-9_-]{11}$/;

/**
 * Parses a YouTube video URL (e.g. from speech.video_url).
 *
 * Supports formats:
 * - https://www.youtube.com/watch?v=<11-char id>&t=<seconds>
 * - https://youtu.be/<11-char id>?t=<seconds>
 * - https://www.youtube-nocookie.com/embed/<11-char id>?start=<seconds>
 *
 * Returns { videoId, start } where:
 * - videoId is an 11-character string matching /^[A-Za-z0-9_-]{11}$/
 * - start is an integer >= 0 (defaults to 0 if missing or invalid)
 * Returns null if the URL is not a valid YouTube URL with an 11-char videoId.
 *
 * @param {string|null|undefined} url
 * @returns {{ videoId: string, start: number } | null}
 */
export function parseVideoUrl(url) {
  if (!url || typeof url !== "string") {
    return null;
  }

  try {
    const parsed = new URL(url);
    const hostname = parsed.hostname.toLowerCase();

    let videoId = null;
    let startParam = null;

    if (
      hostname === "www.youtube.com" ||
      hostname === "youtube.com" ||
      hostname === "m.youtube.com"
    ) {
      if (parsed.pathname === "/watch") {
        videoId = parsed.searchParams.get("v");
        startParam = parsed.searchParams.get("t") ?? parsed.searchParams.get("start");
      } else if (parsed.pathname.startsWith("/embed/")) {
        videoId = parsed.pathname.split("/")[2];
        startParam = parsed.searchParams.get("start") ?? parsed.searchParams.get("t");
      }
    } else if (hostname === "youtu.be") {
      videoId = parsed.pathname.slice(1).split("/")[0];
      startParam = parsed.searchParams.get("t") ?? parsed.searchParams.get("start");
    } else if (hostname === "www.youtube-nocookie.com" || hostname === "youtube-nocookie.com") {
      if (parsed.pathname.startsWith("/embed/")) {
        videoId = parsed.pathname.split("/")[2];
        startParam = parsed.searchParams.get("start") ?? parsed.searchParams.get("t");
      }
    }

    if (!videoId || !YOUTUBE_ID_REGEX.test(videoId)) {
      return null;
    }

    let start = 0;
    if (startParam) {
      // Clean possible trailing 's', e.g. "120s"
      const cleaned = String(startParam).replace(/s$/i, "");
      const parsedInt = parseInt(cleaned, 10);
      if (!Number.isNaN(parsedInt) && parsedInt > 0) {
        start = parsedInt;
      }
    }

    return { videoId, start };
  } catch {
    return null;
  }
}

/**
 * Builds an embed URL for YouTube with privacy-friendly youtube-nocookie.com.
 *
 * Format:
 * https://www.youtube-nocookie.com/embed/<id>?start=<s>&end=<e>&autoplay=1&rel=0
 * (end is omitted when null, undefined, or <= start)
 *
 * @param {{ videoId: string, start?: number, end?: number|null }} options
 * @returns {string}
 */
export function buildEmbedUrl({ videoId, start = 0, end = null } = {}) {
  if (!videoId || !YOUTUBE_ID_REGEX.test(videoId)) {
    throw new Error(`Invalid YouTube video ID: "${videoId}"`);
  }

  const s = Math.max(0, parseInt(start, 10) || 0);
  const params = new URLSearchParams();
  params.set("start", String(s));

  if (end !== null && end !== undefined) {
    const e = parseInt(end, 10);
    if (!Number.isNaN(e) && e > s) {
      params.set("end", String(e));
    }
  }

  params.set("autoplay", "1");
  params.set("rel", "0");

  return `https://www.youtube-nocookie.com/embed/${videoId}?${params.toString()}`;
}
