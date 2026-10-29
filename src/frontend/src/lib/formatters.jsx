import React from "react";
import { MONTHS } from "./calendarUtils";

export const SHORT_MONTHS = [
  "jaan",
  "veebr",
  "märts",
  "apr",
  "mai",
  "juuni",
  "juuli",
  "aug",
  "sept",
  "okt",
  "nov",
  "dets",
];

export function formatSyncTime(isoStr) {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return "";
    const day = String(d.getDate()).padStart(2, "0");
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const year = d.getFullYear();
    const hours = String(d.getHours()).padStart(2, "0");
    const minutes = String(d.getMinutes()).padStart(2, "0");
    return `${day}.${month}.${year} ${hours}:${minutes}`;
  } catch {
    return "";
  }
}

export function isSyncStale(isoStr, maxHours = 36) {
  if (!isoStr) return false;
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return false;
    const diffHours = (Date.now() - d.getTime()) / (1000 * 60 * 60);
    return diffHours > maxHours;
  } catch {
    return false;
  }
}

export function formatMonthTooltip(monthKey) {
  if (!monthKey) return "";
  const [yearStr, monthStr] = monthKey.split("-");
  const monthIdx = parseInt(monthStr, 10) - 1;
  const now = new Date();
  const currentMonthKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const label = `${MONTHS[monthIdx] || monthStr} ${yearStr}`;
  return monthKey === currentMonthKey ? `${label} (pooleli)` : label;
}

export function formatMonthAxis(monthKey) {
  if (!monthKey) return "";
  const [yearStr, monthStr] = monthKey.split("-");
  const monthIdx = parseInt(monthStr, 10) - 1;
  const monthName = MONTHS[monthIdx] || monthStr;
  return `${monthName} ’${yearStr.slice(-2)}`;
}

export function formatDayTooltip(dateKey) {
  if (!dateKey) return "";
  const [yearStr, monthStr, dayStr] = dateKey.split("-");
  const monthIdx = parseInt(monthStr, 10) - 1;
  const day = parseInt(dayStr, 10);
  return `${day}. ${MONTHS[monthIdx] || monthStr} ${yearStr}`;
}

export function formatDayAxis(dateKey) {
  if (!dateKey) return "";
  const [, monthStr, dayStr] = dateKey.split("-");
  const monthIdx = parseInt(monthStr, 10) - 1;
  const day = parseInt(dayStr, 10);
  const monthName = SHORT_MONTHS[monthIdx] || monthStr;
  return `${day}. ${monthName}`;
}

export function formatWeekTooltip(weekStartStr) {
  if (!weekStartStr) return "";
  const [y, m, d] = weekStartStr.split("-").map(Number);
  const dMon = new Date(y, m - 1, d);
  const dSun = new Date(y, m - 1, d + 6);
  const d1 = dMon.getDate();
  const m1 = dMon.getMonth();
  const y1 = dMon.getFullYear();
  const d2 = dSun.getDate();
  const m2 = dSun.getMonth();
  const y2 = dSun.getFullYear();

  if (y1 === y2 && m1 === m2) {
    return `nädal ${d1}.–${d2}. ${MONTHS[m1]} ${y1}`;
  }
  if (y1 === y2) {
    return `nädal ${d1}. ${MONTHS[m1]} – ${d2}. ${MONTHS[m2]} ${y1}`;
  }
  return `nädal ${d1}. ${MONTHS[m1]} ${y1} – ${d2}. ${MONTHS[m2]} ${y2}`;
}

export function formatWeekAxis(weekStartStr) {
  if (!weekStartStr) return "";
  const [y, m, d] = weekStartStr.split("-").map(Number);
  const dMon = new Date(y, m - 1, d);
  const d1 = dMon.getDate();
  const m1 = dMon.getMonth();
  const monthName = SHORT_MONTHS[m1] || String(m1 + 1);
  return `${d1}. ${monthName}`;
}

export function normalizeSourceUrl(url) {
  if (!url) return url;
  return url.replace(
    /^https?:\/\/stenogrammid\.riigikogu\.ee\/(?!et\/|en\/|ru\/)(\d{12})(.*)$/,
    "https://stenogrammid.riigikogu.ee/et/$1$2"
  );
}

export function formatDateTime(dateStr, timeStr) {
  if (!dateStr && !timeStr) return "";
  let formattedDate = dateStr || "";
  try {
    if (dateStr) {
      const parts = dateStr.split("-");
      if (parts.length === 3) {
        const year = parts[0];
        const month = parseInt(parts[1], 10) - 1;
        const day = parseInt(parts[2], 10);
        formattedDate = `${day}. ${MONTHS[month]} ${year}`;
      }
    }
  } catch {
    // fallback to original dateStr if parsing fails
  }

  let formattedTime = "";
  if (timeStr) {
    if (timeStr.length === 4 && !timeStr.includes(":")) {
      formattedTime = ` kell ${timeStr.slice(0, 2)}:${timeStr.slice(2, 4)}`;
    } else {
      const tParts = timeStr.split(":");
      if (tParts.length >= 2) {
        formattedTime = ` kell ${tParts[0]}:${tParts[1]}`;
      } else {
        formattedTime = ` kell ${timeStr}`;
      }
    }
  }
  return `${formattedDate}${formattedTime}`.trim();
}

export function formatFactionName(name) {
  if (!name) return "";
  const nameMap = {
    "Eesti Reformierakonna fraktsioon": "Reformierakond",
    "Eesti Keskerakonna fraktsioon": "Keskerakond",
    "Eesti Konservatiivse Rahvaerakonna fraktsioon": "EKRE",
    "Eesti 200 fraktsioon": "Eesti 200",
    "Isamaa fraktsioon": "Isamaa",
    "Sotsiaaldemokraatliku Erakonna fraktsioon": "Sotsiaaldemokraadid",
    "Fraktsiooni mittekuuluvad Riigikogu liikmed": "Fraktsiooni mittekuuluvad",
  };
  if (nameMap[name]) return nameMap[name];

  const clean = name.replace(/ fraktsioon$/i, "").replace(/ fraktsiooni$/i, "");
  const fallbackMap = {
    "Eesti Reformierakonna": "Reformierakond",
    "Eesti Reformierakond": "Reformierakond",
    "Eesti Keskerakonna": "Keskerakond",
    "Eesti Keskerakond": "Keskerakond",
    "Eesti Konservatiivse Rahvaerakonna": "EKRE",
    "Eesti Konservatiivne Rahvaerakond": "EKRE",
    "Sotsiaaldemokraatliku Erakonna": "Sotsiaaldemokraadid",
    "Sotsiaaldemokraatlik Erakond": "Sotsiaaldemokraadid",
  };
  return fallbackMap[clean] || clean;
}

// Soft hyphens at the compound boundary, so a narrow cell can break a long one-word name
// ("Sotsiaal-demokraadid") instead of letting it run under the next column
const SOFT_HYPHENATED = {
  Sotsiaaldemokraadid: "Sotsiaal\u00addemokraadid",
  Reformierakond: "Reformi\u00aderakond",
  Keskerakond: "Kesk\u00aderakond",
  "Fraktsiooni mittekuuluvad": "Fraktsiooni mitte\u00adkuuluvad",
};

export function formatFactionNameBreakable(name) {
  const short = formatFactionName(name);
  return SOFT_HYPHENATED[short] || short;
}

export const SPEECH_TYPE_LABELS = {
  SMALL_SPEECH: "Küsimus/repliik",
  PROCEDURAL: "Protseduuriline",
  SPEECH_CONTINUE: "Kõne jätk",
};

export function formatDuration(seconds) {
  if (typeof seconds !== "number" || seconds <= 0) return null;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export function highlightKeywords(text, groups, extraTerm = "", matchedWords = []) {
  if (!text) return "";
  const allTerms = groups ? groups.flat().map((w) => w.trim().toLowerCase()) : [];
  if (extraTerm && extraTerm.trim().length >= 2) {
    allTerms.push(extraTerm.trim().toLowerCase());
  }
  if (matchedWords && Array.isArray(matchedWords)) {
    matchedWords.forEach((w) => {
      if (w && w.trim().length >= 2) {
        allTerms.push(w.trim().toLowerCase());
      }
    });
  }
  const keywords = Array.from(new Set(allTerms.filter((w) => w.length >= 2)));
  if (keywords.length === 0) return text;
  keywords.sort((a, b) => b.length - a.length);

  const escaped = keywords.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const regex = new RegExp(`(^|[^\\p{L}\\p{N}])(${escaped.join("|")})(?=[^\\p{L}\\p{N}]|$)`, "gui");

  const elements = [];
  let lastIndex = 0;
  for (const match of text.matchAll(regex)) {
    const prefix = match[1] || "";
    const keyword = match[2];
    const matchIndex = match.index;
    const keywordStart = matchIndex + prefix.length;
    const keywordEnd = keywordStart + keyword.length;

    if (keywordStart > lastIndex) {
      elements.push(text.slice(lastIndex, keywordStart));
    }
    elements.push(
      <mark key={elements.length} className="keyword-highlight">
        {keyword}
      </mark>
    );
    lastIndex = keywordEnd;
  }

  if (lastIndex < text.length) {
    elements.push(text.slice(lastIndex));
  }

  return elements.length > 0 ? elements : [text];
}

export function getSnippet(text, matchedWords = [], groups = [[]], maxLength = 380) {
  if (!text) return "";
  if (text.length <= maxLength) return text;

  const terms = [
    ...(Array.isArray(matchedWords) ? matchedWords : []),
    ...(Array.isArray(groups) ? groups.flat() : []),
  ]
    .map((w) => (typeof w === "string" ? w.trim().toLowerCase() : ""))
    .filter((w) => w.length >= 2);

  let firstIndex = -1;
  const lowerText = text.toLowerCase();
  for (const term of terms) {
    const idx = lowerText.indexOf(term);
    if (idx !== -1 && (firstIndex === -1 || idx < firstIndex)) {
      firstIndex = idx;
    }
  }

  if (firstIndex === -1 || firstIndex < 120) {
    return text.slice(0, maxLength).trim() + "...";
  }

  const start = Math.max(0, firstIndex - 100);
  const end = Math.min(text.length, start + maxLength);
  const prefix = start > 0 ? "..." : "";
  const suffix = end < text.length ? "..." : "";
  return prefix + text.slice(start, end).trim() + suffix;
}

export { toRoman } from "./toRoman.js";
export { parseQueryToGroups, mergeInputToGroups, serializeGroupsToQuery } from "./queryHelpers.js";
export {
  formatMetricRatio,
  formatPercent,
  formatVoteSplit,
  getChecksBarSegments,
  getVotesBarSegments,
  isSmallSample,
  sortAttendanceItems,
} from "./attendanceFormatters.js";
