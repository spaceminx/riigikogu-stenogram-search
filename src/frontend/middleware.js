import { next } from "@vercel/functions";

export const config = {
  matcher: [
    "/kone/:path*",
    "/saadik/:path*",
    "/eelnou/:path*",
    "/haaletus/:path*",
    "/istung/:path*",
    "/otsing",
    "/kohalolek",
    "/haaletused",
    "/fraktsioonid",
    "/saadikud",
    "/eelnoud",
    "/andmed",
  ],
};

// Link previews of the list pages: the same title and description the page sets in the browser
// (usePageMeta), so a shared /kohalolek is not shown as the home page. No API call is needed.
export const LIST_PAGES = {
  "/kohalolek": {
    title: "Kohalolek — Riigivaade",
    description:
      "Riigikogu saadikute ja fraktsioonide kohalolekukontrollide ja hääletusel osalemise statistika.",
  },
  "/haaletused": {
    title: "Hääletused — Riigivaade",
    description:
      "Riigikogu täiskogu hääletuste tulemused, saadikute hääled ja fraktsioonide jaotused.",
  },
  "/fraktsioonid": {
    title: "Fraktsioonid — Riigivaade",
    description:
      "Riigikogu fraktsioonid ja nende liikmed koosseisude kaupa, koos valitsuskoalitsiooni jaotusega.",
  },
  "/saadikud": {
    title: "Saadikud — Riigivaade",
    description:
      "Riigikogu liikmed koosseisude kaupa: otsi saadikut nime järgi ja ava tema kõned, hääletused ja kohalolek.",
  },
  "/eelnoud": {
    title: "Eelnõud — Riigivaade",
    description:
      "Riigikogu eelnõud: menetlusetapp, juhtivkomisjon, täiskogu arutelud ja hääletused.",
  },
  "/andmed": {
    title: "Andmed ja privaatsus — Riigivaade",
    description:
      "Teave Riigivaate andmeallikate, privaatsuspõhimõtete ja avaandmete litsentside kohta.",
  },
  "/otsing": {
    title: "Otsing — Riigivaade",
    description: "Otsi Riigikogu stenogrammidest märksõnade, fraktsioonide ja saadikute kaupa.",
  },
};

/** Preview metadata for a list page, or null. The address keeps the query (filters, search). */
export function resolveListPageMetadata(pathname, search = "") {
  const path = pathname.length > 1 ? pathname.replace(/\/$/, "") : pathname;
  const page = LIST_PAGES[path];
  if (!page) return null;
  let { title, description } = page;
  if (path === "/otsing") {
    const q = (new URLSearchParams(search).get("q") || "").trim();
    if (q) {
      title = `${q} — otsing — Riigivaade`;
      description = `Otsingu „${q}“ tulemused Riigikogu stenogrammidest ja sõnavõttudest.`;
    }
  }
  return {
    title,
    description,
    url: `https://www.riigivaade.me${path}${search || ""}`,
    type: "website",
    image: null,
  };
}

// Known bot user-agent pattern: link-preview bots (Facebook, X, Slack, LinkedIn, Discord, Telegram,
// WhatsApp, Reddit, Mastodon, Bluesky, Embedly/Iframely, Skype, VK) and search engine crawlers
export const KNOWN_BOT_UA_REGEX =
  /(facebookexternalhit|Facebot|Twitterbot|Slackbot|LinkedInBot|Discordbot|TelegramBot|WhatsApp|Pinterest|redditbot|Mastodon|Bluesky|Cardyb|Embedly|Iframely|SkypeUriPreview|vkShare|Googlebot|bingbot|Applebot|DuckDuckBot|YandexBot)/i;

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
  // index.html carries site-wide defaults; drop the ones this page replaces so each appears once.
  // The default image stays unless the page has its own.
  const replaced = meta.image ? /^og:/ : /^og:(?!image)/;
  let out = html.replace(/\s*<meta\s+property="(og:[^"]+)"[^>]*>/gi, (tag, property) =>
    replaced.test(property) ? "" : tag
  );
  // Replacement functions, not strings: "$&" or "$'" in API text must stay literal.
  if (meta.title) {
    out = out.replace(
      /<title>[\s\S]*?<\/title>/i,
      () => `<title>${escapeHtml(meta.title)}</title>`
    );
  }
  if (meta.description) {
    out = out.replace(
      /<meta\s+name="description"[\s\S]*?>/i,
      () => `<meta name="description" content="${escapeHtml(meta.description)}" />`
    );
  }
  if (out.includes("</head>")) {
    return out.replace("</head>", () => `${injection}\n  </head>`);
  }
  return out + injection;
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
        ? `${speaker}: sõnavõtt Riigikogu istungil ${dateFormatted}.`
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
    // The description is usually only the step ("Lõpphääletus"); the topic is the related document
    const step = data?.description || "Hääletus";
    const docTitle = data?.related_document?.title;
    const desc = docTitle ? `${step}: ${docTitle}` : step;
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
    const mark = data?.mark ? `${data.mark}${data.type_code ? ` ${data.type_code}` : ""} ` : "";
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
 * 404.html with status 404 and noindex, or a plain 404 when the page cannot be read.
 */
async function notFound(request) {
  try {
    const resp = await fetch(new URL("/404.html", request.url));
    if (resp.ok) {
      return new Response(await resp.text(), {
        status: 404,
        headers: {
          "content-type": "text/html; charset=utf-8",
          "x-robots-tag": "noindex",
        },
      });
    }
  } catch {
    // Fall through to the plain response
  }
  return new Response("Not Found", { status: 404, headers: { "x-robots-tag": "noindex" } });
}

/**
 * Whether a sitting took place on `date`: true or false, or null when the list could not be read.
 */
export async function isKnownSittingDate(apiBase, date) {
  try {
    const resp = await fetch(`${apiBase}/sessions/dates`, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(1500),
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    if (!Array.isArray(data?.dates)) return null;
    return data.dates.includes(date);
  } catch {
    return null;
  }
}

/**
 * Vercel Routing Middleware handler for Edge Runtime.
 */
export default async function middleware(request) {
  const url = new URL(request.url);
  const route = parseRouteInfo(url.pathname);
  const listMeta = route ? null : resolveListPageMetadata(url.pathname, url.search);

  // If not one of the targeted shared link routes, continue
  if (!route && !listMeta) {
    return next();
  }

  const userAgent = request.headers.get("user-agent") || "";
  if (!isBotUserAgent(userAgent)) {
    return next();
  }

  if (listMeta) {
    try {
      const indexResp = await fetch(new URL("/index.html", request.url));
      if (!indexResp.ok) return next();
      const html = await indexResp.text();
      return new Response(injectOpenGraphTags(html, listMeta), {
        status: 200,
        headers: {
          "content-type": "text/html; charset=utf-8",
          "x-robots-tag": "all",
        },
      });
    } catch {
      return next();
    }
  }

  const apiBase =
    process.env.API_BASE_URL || process.env.VITE_API_URL || "https://api.riigivaade.me";

  // /istung/:date: GET /sessions/{date} is heavy, so the date is checked against the small,
  // edge-cached list of sitting dates instead
  if (route.routeType === "istung") {
    if (!isValidSittingDate(route.id)) return notFound(request);

    try {
      const [indexResp, known] = await Promise.all([
        fetch(new URL("/index.html", request.url)),
        isKnownSittingDate(apiBase, route.id),
      ]);
      if (known === false) return notFound(request);
      if (!indexResp.ok) return next();
      const html = await indexResp.text();
      const ogMeta = resolveOgMetadata("istung", route.id, null);
      if (!ogMeta) return next();

      return new Response(injectOpenGraphTags(html, ogMeta), {
        status: 200,
        headers: {
          "content-type": "text/html; charset=utf-8",
          // Unchecked when the date list could not be read: not worth indexing a possible dead end
          "x-robots-tag": known ? "all" : "noindex",
        },
      });
    } catch {
      return next();
    }
  }

  const apiPath = getApiPath(route.routeType, route.id);
  if (!apiPath) {
    return next();
  }

  try {
    const indexPromise = fetch(new URL("/index.html", request.url));
    const dataPromise = fetch(`${apiBase}${apiPath}`, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(1500),
    });

    const [indexResp, dataResp] = await Promise.all([indexPromise, dataPromise]);

    // If the API answers 404 (or 422 for a malformed id), serve 404.html with status 404
    if (dataResp.status === 404 || dataResp.status === 422) {
      return notFound(request);
    }

    if (!indexResp.ok || !dataResp.ok) return next();

    const html = await indexResp.text();
    const data = await dataResp.json();

    const ogMeta = resolveOgMetadata(route.routeType, route.id, data);
    if (!ogMeta) return next();

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
    return next();
  }
}
