import { toRoman } from "./toRoman.js";

export const WEEKDAYS = ["E", "T", "K", "N", "R", "L", "P"];
export const MONTHS = [
  "jaanuar",
  "veebruar",
  "märts",
  "aprill",
  "mai",
  "juuni",
  "juuli",
  "august",
  "september",
  "oktoober",
  "november",
  "detsember",
];
export const currentYear = new Date().getFullYear();
export const YEARS = Array.from(
  { length: Math.max(8, currentYear - 2019 + 2) },
  (_, index) => 2019 + index
);
export const CALENDAR_MIN_MONTH = new Date(2019, 0, 1);
export const CALENDAR_MAX_MONTH = new Date(currentYear + 1, 11, 1);
export const QUICK_PRESETS = [
  { id: "xv", label: "XV Riigikogu (2023–praegu)" },
  { id: "xiv", label: "XIV Riigikogu (2019–2023)" },
  { id: "year", label: "Viimane aasta" },
  { id: "archive", label: "Kogu arhiiv" },
];

export function clampMonth(date) {
  if (date < CALENDAR_MIN_MONTH) return CALENDAR_MIN_MONTH;
  if (date > CALENDAR_MAX_MONTH) return CALENDAR_MAX_MONTH;
  return date;
}

export function toDateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

// A real calendar day as YYYY-MM-DD (rejects 2026-02-30 and 2026-13-45)
export function isValidDateKey(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
  );
}

export function fromDateKey(value) {
  if (!value) return null;
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function shiftMonth(date, amount) {
  return new Date(date.getFullYear(), date.getMonth() + amount, 1);
}

export function formatDate(value) {
  if (!value) return "";
  const [year, month, day] = value.split("-");
  return `${day}.${month}.${year}`;
}

export function getMonthDays(month) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const mondayOffset = (first.getDay() + 6) % 7;
  const gridStart = new Date(first);
  gridStart.setDate(first.getDate() - mondayOffset);
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(gridStart);
    date.setDate(gridStart.getDate() + index);
    return date;
  });
}

export function monthTitle(date) {
  return `${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}

// Memberships the site covers (XIV onwards) that have already convened. A newly elected
// membership is listed upstream before it convenes and must not show up in filters yet.
export function visibleMemberships(memberships, today = new Date()) {
  if (!Array.isArray(memberships)) return [];
  const todayKey = typeof today === "string" ? today : toDateKey(today);
  return memberships.filter((m) => m.number >= 14 && m.start_date && m.start_date <= todayKey);
}

export function getQuickPresets(memberships, today = new Date()) {
  const todayKey = typeof today === "string" ? today : toDateKey(today);
  if (!memberships || memberships.length === 0) {
    return QUICK_PRESETS;
  }
  const started = memberships.filter((m) => {
    const start = m.start_date || m.startDate;
    return Boolean(start && start <= todayKey);
  });
  if (started.length === 0) {
    return QUICK_PRESETS;
  }
  const sorted = [...started].sort((a, b) => Number(b.number || b.id) - Number(a.number || a.id));
  const topTwo = sorted.slice(0, 2);
  const presets = topTwo.map((m, index) => {
    const start = m.start_date || m.startDate;
    const end = m.end_date || m.endDate;
    const startYear = start ? start.slice(0, 4) : "";
    const endYear = end ? end.slice(0, 4) : "";
    const num = m.number || m.id;
    const roman = toRoman(num);
    const isCurrent = index === 0 && (!end || end >= todayKey);
    const label = isCurrent
      ? `${roman} Riigikogu (${startYear}–praegu)`
      : `${roman} Riigikogu (${startYear}–${endYear})`;
    const startDate = start;
    const endDate = end && end < todayKey ? end : todayKey;
    return {
      id: String(m.id || num),
      label,
      startDate,
      endDate,
    };
  });

  return [
    ...presets,
    { id: "year", label: "Viimane aasta" },
    { id: "archive", label: "Kogu arhiiv" },
  ];
}

export function getPresetRange(presetId, dates, memberships = null, today = new Date()) {
  const todayKey = typeof today === "string" ? today : toDateKey(today);

  if (memberships && memberships.length > 0) {
    const presets = getQuickPresets(memberships, today);
    const match = presets.find((p) => p.id === presetId);
    if (match && match.startDate && match.endDate) {
      return { startDate: match.startDate, endDate: match.endDate };
    }
  }

  if (presetId === "xv") return { startDate: "2023-04-10", endDate: todayKey };
  if (presetId === "xiv") return { startDate: "2019-04-04", endDate: "2023-04-09" };
  if (presetId === "year") {
    const yearDate = typeof today === "string" ? fromDateKey(today) : new Date(today);
    const yearAgo = new Date(yearDate);
    yearAgo.setFullYear(yearAgo.getFullYear() - 1);
    return { startDate: toDateKey(yearAgo), endDate: todayKey };
  }
  const orderedDates = [...(dates || [])].sort();
  return {
    startDate: orderedDates[0] || "2019-01-01",
    endDate: orderedDates.at(-1) || todayKey,
  };
}
