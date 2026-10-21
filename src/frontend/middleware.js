// Known bot user-agent pattern (Facebook, Twitter/X, Slack, LinkedIn, Discord, Telegram, WhatsApp, search engine crawlers)
export const KNOWN_BOT_UA_REGEX =
  /(facebookexternalhit|Facebot|Twitterbot|Slackbot|LinkedInBot|Discordbot|TelegramBot|WhatsApp|Pinterest|Googlebot|bingbot|Applebot|DuckDuckBot|YandexBot)/i;

const DATE_REGEX = /^\d{4}-\d{2}-\d{2}$/;

export function isBotUserAgent(userAgent) {
  if (!userAgent || typeof userAgent !== "string") return false;
  return KNOWN_BOT_UA_REGEX.test(userAgent);
}

export function isValidSittingDate(dateStr) {
  if (!dateStr || typeof dateStr !== "string" || !DATE_REGEX.test(dateStr)) {
    return false;
  }
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function formatDate(isoDate) {
  if (!isoDate) return "";
  const [y, m, d] = String(isoDate).slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
}

export function injectOpenGraphTags(html, meta) {
  if (!html || !meta) return html;

  const tags = [
    meta.title ? `<meta property="og:title" content="${escapeHtml(meta.title)}" />` : "",
    meta.description
      ? `<meta property="og:description" content="${escapeHtml(meta.description)}" />`
      : "",
    meta.url ? `<meta property="og:url" content="${escapeHtml(meta.url)}" />` : "",
    meta.type ? `<meta property="og:type" content="${escapeHtml(meta.type)}" />` : "",
    '<meta property="og:site_name" content="Riigivaade" />',
    meta.image ? `<meta property="og:image" content="${escapeHtml(meta.image)}" />` : "",
  ].filter(Boolean);

  if (tags.length === 0) return html;

  const injection = `\n    ${tags.join("\n    ")}`;
  if (html.includes("</head>")) {
    return html.replace("</head>", `${injection}\n  </head>`);
  }
  return html + injection;
}

export function resolveOgMetadata(routeType, id, data) {
  const base = "https://www.riigivaade.me";

  if (routeType === "saadik") {
    const name = data?.full_name || "Saadik";
    const title = `${name} — Riigivaade`;
    const description = `Riigikogu saadiku ${name} kõned, hääletused, kohalolek ja profiil.`;
    return {
      title,
      description,
      url: `${base}/saadik/${id}`,
      type: "profile",
      image: data?.photo_url || null,
    };
  }

  if (routeType === "kone") {
    const speaker = data?.speaker || "Kõneleja";
    const dateFormatted = data?.date ? formatDate(data.date) : "";
    const title = dateFormatted
      ? `${speaker}, ${dateFormatted} — Riigivaade`
      : `${speaker} — Riigivaade`;
    const snippet = data?.text ? data.text.slice(0, 150).trim() + "..." : "";
    const description =
      snippet ||
      (dateFormatted
        ? `Riigikogu saadiku ${speaker} sõnavõtt ${dateFormatted} toimunud istungil.`
        : "Riigikogu istungi kõne stenogramm.");
    return {
      title,
      description,
      url: `${base}/kone/${id}`,
      type: "article",
      image: null,
    };
  }

  if (routeType === "haaletus") {
    const desc = data?.description || "Hääletus";
    const title = `${desc} — Riigivaade`;
    const description = `Riigikogu hääletuse „${desc}“ tulemused ja saadikute otsused.`;
    return {
      title,
      description,
      url: `${base}/haaletus/${id}`,
      type: "article",
      image: null,
    };
  }

  if (routeType === "eelnou") {
    const titleRaw = data?.title || "Eelnõu";
    const title = `${titleRaw} — Riigivaade`;
    const mark = data?.mark ? `${data.mark} ` : "";
    const description = `Riigikogu eelnõu ${mark}„${titleRaw}“ lugemised ja hääletused.`;
    return {
      title,
      description,
      url: `${base}/eelnou/${id}`,
      type: "article",
      image: null,
    };
  }

  if (routeType === "istung") {
    const dateFormatted = formatDate(id);
    const title = dateFormatted ? `Istung ${dateFormatted} — Riigivaade` : "Istung — Riigivaade";
    const description = dateFormatted
      ? `Riigikogu ${dateFormatted} täiskogu istungi stenogramm, päevakord ja hääletused.`
      : "Riigikogu täiskogu istungi stenogramm.";
    return {
      title,
      description,
      url: `${base}/istung/${id}`,
      type: "article",
      image: null,
    };
  }

  return null;
}

export function parseRouteInfo(pathname) {
  const match = pathname.match(/^\/(kone|saadik|eelnou|haaletus|istung)\/([^/]+)\/?$/);
  if (!match) return null;
  return { routeType: match[1], id: match[2] };
}

export function getApiPath(routeType, id) {
  if (routeType === "kone") return `/speeches/${id}`;
  if (routeType === "saadik") return `/persons/${id}`;
  if (routeType === "haaletus") return `/votings/${id}`;
  if (routeType === "eelnou") return `/drafts/${id}`;
  // istung does not use an API call
  return null;
}

/**
 * Vercel Routing Middleware handler for Edge Runtime.
 */
export default async function middleware(request) {
  const url = new URL(request.url);
  const route = parseRouteInfo(url.pathname);

  // If not one of the targeted shared link routes, continue
  if (!route) {
    return;
  }

  const userAgent = request.headers.get("user-agent") || "";
  if (!isBotUserAgent(userAgent)) {
    return;
  }

  // Special handling for /istung/:date: do NOT call the API (GET /sessions/{date} is heavy).
  // Validate YYYY-MM-DD date and build OG tags purely from the valid date.
  if (route.routeType === "istung") {
    if (!isValidSittingDate(route.id)) {
      try {
        const notFoundResp = await fetch(new URL("/404.html", request.url));
        if (notFoundResp.ok) {
          const html404 = await notFoundResp.text();
          return new Response(html404, {
            status: 404,
            headers: {
              "content-type": "text/html; charset=utf-8",
              "x-robots-tag": "noindex",
            },
          });
        }
      } catch {
        // Fall back to 404 status
        return new Response("Not Found", { status: 404 });
      }
      return;
    }

    try {
      const indexResp = await fetch(new URL("/index.html", request.url));
      if (!indexResp.ok) return;
      const html = await indexResp.text();
      const ogMeta = resolveOgMetadata("istung", route.id, null);
      if (!ogMeta) return;

      const modifiedHtml = injectOpenGraphTags(html, ogMeta);
      return new Response(modifiedHtml, {
        status: 200,
        headers: {
          "content-type": "text/html; charset=utf-8",
          "x-robots-tag": "all",
        },
      });
    } catch {
      return;
    }
  }

  const apiPath = getApiPath(route.routeType, route.id);
  if (!apiPath) {
    return;
  }

  const apiBase =
    process.env.API_BASE_URL || process.env.VITE_API_URL || "https://api.riigivaade.me";

  try {
    const indexPromise = fetch(new URL("/index.html", request.url));
    const dataPromise = fetch(`${apiBase}${apiPath}`, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(1500),
    });

    const [indexResp, dataResp] = await Promise.all([indexPromise, dataPromise]);

    // If the API answers 404, serve 404.html with status 404 (and no OG tags)
    if (dataResp.status === 404) {
      try {
        const notFoundResp = await fetch(new URL("/404.html", request.url));
        if (notFoundResp.ok) {
          const html404 = await notFoundResp.text();
          return new Response(html404, {
            status: 404,
            headers: {
              "content-type": "text/html; charset=utf-8",
              "x-robots-tag": "noindex",
            },
          });
        }
      } catch {
        return new Response("Not Found", { status: 404 });
      }
      return new Response("Not Found", { status: 404 });
    }

    if (!indexResp.ok || !dataResp.ok) return;

    const html = await indexResp.text();
    const data = await dataResp.json();

    const ogMeta = resolveOgMetadata(route.routeType, route.id, data);
    if (!ogMeta) return;

    const modifiedHtml = injectOpenGraphTags(html, ogMeta);
    return new Response(modifiedHtml, {
      status: 200,
      headers: {
        "content-type": "text/html; charset=utf-8",
        "x-robots-tag": "all",
      },
    });
  } catch {
    // Timeout or network error -> fall back to unchanged SPA
    return;
  }
}
