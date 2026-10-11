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

export function getPresetRange(presetId, dates) {
  const today = new Date();
  const todayKey = toDateKey(today);
  if (presetId === "xv") return { startDate: "2023-04-10", endDate: todayKey };
  if (presetId === "xiv") return { startDate: "2019-04-04", endDate: "2023-04-09" };
  if (presetId === "year") {
    const yearAgo = new Date(today);
    yearAgo.setFullYear(yearAgo.getFullYear() - 1);
    return { startDate: toDateKey(yearAgo), endDate: todayKey };
  }
  const orderedDates = [...dates].sort();
  return {
    startDate: orderedDates[0] || "2019-01-01",
    endDate: orderedDates.at(-1) || todayKey,
  };
}
